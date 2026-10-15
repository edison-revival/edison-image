#!/bin/bash
# Build the Debian rootfs and the flashable images. Runs inside the tooling container
# (docker/rootfs.Dockerfile) as root, with:
#   /src         this repo (read-only)
#   /in/kernel   kernel build output (vmlinuz, modules.tar.gz, RELEASE)
#   /out         output directory
#   /cache       optional: .deb cache kept between builds (only changed packages download)
set -euo pipefail

SUITE=trixie
MIRROR=http://deb.debian.org/debian
ROOT=/work/rootfs
USER_NAME=edison

release=$(cat /in/kernel/RELEASE)
mkdir -p /work /out
rm -rf "$ROOT"

packages=$(grep -v -e '^#' -e '^$' /src/rootfs/packages.txt | paste -sd, -)

# Fetch and verify the Edison firmware files before spending time on the rootfs.
mkdir -p /work/firmware
while read -r sha name url; do
    case "$sha" in ''|'#'*) continue ;; esac
    curl -fsSL --retry 3 -o "/work/firmware/$name" "$url"
    echo "$sha  /work/firmware/$name" | sha256sum -c --quiet -
done < /src/rootfs/firmware.lock

# Compile the ACPI table overlays listed in acpi/tables.txt.
mkdir -p /work/acpi
defines=$(sed -n 's/^defines: *//p' /src/acpi/tables.txt)
grep -E '^[^#].*\.asl$' /src/acpi/tables.txt | while read -r asl; do
    # $defines is a list of separate -D flags.
    # shellcheck disable=SC2086
    iasl -vs $defines -I /src/acpi/meta-acpi -p "/work/acpi/${asl%.asl}" "/src/acpi/meta-acpi/$asl" >/dev/null \
        || { echo "iasl failed for $asl" >&2; exit 1; }
done
ls /work/acpi/*.aml >/dev/null

mkdir -p /cache/apt
# Hooks are run by mmdebstrap with the rootfs path as $1, so most must stay unexpanded here.
# shellcheck disable=SC2016
mmdebstrap \
    --variant=apt \
    --components="main non-free-firmware" \
    --include="$packages" \
    --skip=download/empty --skip=essential/unlink \
    --setup-hook='mkdir -p "$1/var/cache/apt/archives"' \
    --setup-hook='sync-in /cache/apt /var/cache/apt/archives/' \
    --customize-hook='sync-out /var/cache/apt/archives /cache/apt' \
    --customize-hook='cp -r --no-preserve=mode,ownership /src/rootfs/overlay/. "$1/"' \
    --customize-hook="tar -C \"\$1\" --keep-directory-symlink -xzf /in/kernel/modules.tar.gz" \
    --customize-hook="chroot \"\$1\" depmod -a $release" \
    --customize-hook='install -m 0644 -t "$1/usr/lib/firmware/brcm/" /work/firmware/*' \
    --customize-hook='ln -sf brcmfmac43340-sdio.txt "$1/usr/lib/firmware/brcm/brcmfmac43340-sdio.Intel Corporation-Merrifield.txt"' \
    --customize-hook='ln -sf brcmfmac43340-sdio.bin "$1/usr/lib/firmware/brcm/brcmfmac43340-sdio.Intel Corporation-Merrifield.bin"' \
    --customize-hook='test -e "$1/usr/lib/firmware/brcm/brcmfmac43340-sdio.bin" || { echo "firmware-brcm80211 lacks brcmfmac43340-sdio.bin" >&2; exit 1; }' \
    --customize-hook='install -d "$1/usr/lib/edison/acpi" && install -m 0644 -t "$1/usr/lib/edison/acpi/" /work/acpi/*.aml' \
    --customize-hook='chmod 0755 "$1"/usr/local/sbin/edison-*' \
    --customize-hook='mkdir -p "$1/factory" "$1/var/lib/edison"' \
    --customize-hook='ln -sf /var/lib/edison/wifi/wpa_supplicant-wlan0.conf "$1/etc/wpa_supplicant/wpa_supplicant-wlan0.conf"' \
    --customize-hook='for f in /usr/bin/login /usr/sbin/agetty /usr/sbin/sshd /usr/sbin/wpa_supplicant /usr/sbin/rfkill /usr/bin/gpioset /usr/sbin/i2cdetect /usr/sbin/mkfs.ext4 /usr/sbin/e2fsck /usr/bin/script /usr/bin/fw_setenv; do test -x "$1$f" || { echo "missing $f in rootfs" >&2; exit 1; }; done' \
    --customize-hook='chroot "$1" systemctl enable systemd-networkd systemd-resolved systemd-timesyncd edison-acpi-tables edison-gadget edison-bt-addr edison-config-restore edison-config-save.path rfkill-unblock wpa_supplicant@wlan0 serial-getty@ttyGS0' \
    --customize-hook='chroot "$1" groupadd -r -f gpio' \
    --customize-hook="chroot \"\$1\" useradd -m -s /bin/bash -G sudo,netdev,plugdev,dialout,gpio,i2c $USER_NAME" \
    --customize-hook='find "$1/etc/systemd" "$1/etc/udev/rules.d" -type f -perm /022 -print -exec false {} + >&2 || { echo "group/world-writable config files in rootfs" >&2; exit 1; }' \
    --customize-hook="echo '$USER_NAME:$USER_NAME' | chroot \"\$1\" chpasswd" \
    --customize-hook="chroot \"\$1\" passwd --expire $USER_NAME" \
    --customize-hook='ln -sf /run/systemd/resolve/stub-resolv.conf "$1/etc/resolv.conf"' \
    --customize-hook='rm -f "$1"/etc/ssh/ssh_host_*' \
    --customize-hook=': > "$1/etc/machine-id"; rm -f "$1/var/lib/dbus/machine-id"' \
    --customize-hook='chroot "$1" dpkg-query -W -f="\${Package} \${Version} \${source:Package} \${source:Version}\n" > /out/packages.manifest' \
    --customize-hook='rm -rf "$1"/var/lib/apt/lists/* "$1"/var/cache/apt/*.bin' \
    "$SUITE" "$ROOT" "$MIRROR"

# ext4 image: used space + 25% + 64 MiB headroom; it grows to the partition on first boot.
# The rootfs partition is the rest of the eMMC (about 3.5 GiB); keep the image well below.
used_kib=$(du -sk "$ROOT" | cut -f1)
size_kib=$(( used_kib * 125 / 100 + 65536 ))
max_kib=$(( 3000 * 1024 ))
if [ "$size_kib" -gt "$max_kib" ]; then
    echo "rootfs (${size_kib} KiB) is too big for the rootfs partition" >&2
    exit 1
fi
rm -f /out/rootfs.ext4
mke2fs -q -t ext4 -L rootfs -d "$ROOT" /out/rootfs.ext4 "${size_kib}k"

# FAT boot partition (64 MiB) with the kernel.
rm -f /out/boot.vfat
mkfs.vfat -n BOOT -C /out/boot.vfat 65536 >/dev/null
mcopy -i /out/boot.vfat /in/kernel/vmlinuz ::vmlinuz

# Redundant U-Boot environment (comments and blank lines stripped first).
grep -v -e '^#' -e '^$' /src/uboot/env.txt > /work/env.txt
mkenvimage -r -s 0x10000 -o /out/u-boot-env.bin /work/env.txt

cp /in/kernel/RELEASE /out/KERNEL_RELEASE
cd /out
sha256sum rootfs.ext4 boot.vfat u-boot-env.bin > SHA256SUMS
chmod 0644 rootfs.ext4 boot.vfat u-boot-env.bin KERNEL_RELEASE SHA256SUMS packages.manifest
echo "rootfs: ${used_kib} KiB used, image $(( size_kib / 1024 )) MiB; kernel ${release}"
