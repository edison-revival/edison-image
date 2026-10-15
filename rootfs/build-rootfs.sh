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

mkdir -p /cache/apt
mmdebstrap \
    --variant=apt \
    --components="main non-free-firmware" \
    --include="$packages" \
    --skip=download/empty --skip=essential/unlink \
    --setup-hook='mkdir -p "$1/var/cache/apt/archives"' \
    --setup-hook='sync-in /cache/apt /var/cache/apt/archives/' \
    --customize-hook='sync-out /var/cache/apt/archives /cache/apt' \
    --customize-hook='cp -a /src/rootfs/overlay/. "$1/"' \
    --customize-hook="tar -C \"\$1\" --keep-directory-symlink -xzf /in/kernel/modules.tar.gz" \
    --customize-hook="chroot \"\$1\" depmod -a $release" \
    --customize-hook='install -m 0644 -t "$1/usr/lib/firmware/brcm/" /work/firmware/*' \
    --customize-hook='ln -sf brcmfmac43340-sdio.txt "$1/usr/lib/firmware/brcm/brcmfmac43340-sdio.Intel Corporation-Merrifield.txt"' \
    --customize-hook='test -e "$1/usr/lib/firmware/brcm/brcmfmac43340-sdio.bin" || { echo "firmware-brcm80211 lacks brcmfmac43340-sdio.bin" >&2; exit 1; }' \
    --customize-hook='chmod 0755 "$1/usr/local/sbin/edison-gadget"' \
    --customize-hook='chroot "$1" systemctl enable systemd-networkd systemd-resolved systemd-timesyncd edison-gadget rfkill-unblock wpa_supplicant@wlan0 serial-getty@ttyGS0' \
    --customize-hook="chroot \"\$1\" useradd -m -s /bin/bash -G sudo,netdev,plugdev,dialout $USER_NAME" \
    --customize-hook="echo '$USER_NAME:$USER_NAME' | chroot \"\$1\" chpasswd" \
    --customize-hook="chroot \"\$1\" passwd --expire $USER_NAME" \
    --customize-hook='ln -sf /run/systemd/resolve/stub-resolv.conf "$1/etc/resolv.conf"' \
    --customize-hook='rm -f "$1"/etc/ssh/ssh_host_*' \
    --customize-hook=': > "$1/etc/machine-id"; rm -f "$1/var/lib/dbus/machine-id"' \
    --customize-hook='rm -rf "$1"/var/lib/apt/lists/* "$1"/var/cache/apt/*.bin' \
    "$SUITE" "$ROOT" "$MIRROR"

# ext4 image: used space + 25% + 64 MiB headroom; it grows to the partition on first boot.
used_kib=$(du -sk "$ROOT" | cut -f1)
size_kib=$(( used_kib * 125 / 100 + 65536 ))
max_kib=$(( 1536 * 1024 ))
if [ "$size_kib" -gt "$max_kib" ]; then
    echo "rootfs (${size_kib} KiB) doesn't fit the 1536 MiB rootfs partition" >&2
    exit 1
fi
rm -f /out/rootfs.ext4
mke2fs -q -t ext4 -L rootfs -d "$ROOT" /out/rootfs.ext4 "${size_kib}k"

# FAT boot partition (32 MiB) with the kernel.
rm -f /out/boot.vfat
mkfs.vfat -n BOOT -C /out/boot.vfat 32768 >/dev/null
mcopy -i /out/boot.vfat /in/kernel/vmlinuz ::vmlinuz

# Redundant U-Boot environment (comments and blank lines stripped first).
grep -v -e '^#' -e '^$' /src/uboot/env.txt > /work/env.txt
mkenvimage -r -s 0x10000 -o /out/u-boot-env.bin /work/env.txt

cp /in/kernel/RELEASE /out/KERNEL_RELEASE
cd /out
sha256sum rootfs.ext4 boot.vfat u-boot-env.bin > SHA256SUMS
chmod 0644 rootfs.ext4 boot.vfat u-boot-env.bin KERNEL_RELEASE SHA256SUMS
echo "rootfs: ${used_kib} KiB used, image $(( size_kib / 1024 )) MiB; kernel ${release}"
