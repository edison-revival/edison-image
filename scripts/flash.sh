#!/usr/bin/env bash
# Flash U-Boot, its environment, the kernel (boot) and the rootfs over DFU.
# The IFWI is not touched. Needs dfu-util and, on Linux, edison-recovery's udev rule.
#
# Usage: scripts/flash.sh [IMAGE_DIR] [U_BOOT_BIN]
#   IMAGE_DIR   directory with boot.vfat, rootfs.ext4, u-boot-env.bin (default out/image)
#   U_BOOT_BIN  mainline U-Boot u-boot.bin (default out/uboot/u-boot.bin, from scripts/build.sh)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
images="${1:-$root/out/image}"
uboot="${2:-$root/out/uboot/u-boot.bin}"
dev=8087:0a99
timeout=120

for f in "$images/boot.vfat" "$images/rootfs.ext4" "$images/u-boot-env.bin" "$uboot"; do
    [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done
(cd "$images" && sha256sum -c --quiet SHA256SUMS)

echo "Waiting up to ${timeout} s for the Edison in DFU mode ($dev)."
echo "Plug in J16 and reset the board if it isn't already waiting."
for _ in $(seq "$timeout"); do
    dfu-util -l -d "$dev" 2>/dev/null | grep -q "Found DFU: \[$dev\]" && break
    sleep 1
done
dfu-util -l -d "$dev" 2>/dev/null | grep -q "Found DFU: \[$dev\]" \
    || { echo "no DFU device found (check the cable, SW1 and the udev rule)" >&2; exit 1; }

log=$(mktemp)
trap 'rm -f "$log"' EXIT
flash() {
    echo "==> $1"
    if ! dfu-util -d "$dev" -a "$1" -D "$2" "${@:3}" >"$log" 2>&1; then
        cat "$log" >&2
        echo "flashing $1 failed" >&2
        exit 1
    fi
    grep -E "^Sent a total" "$log" || true
}

start=$(date +%s)
flash u-boot0 "$uboot"
flash u-boot-env0 "$images/u-boot-env.bin"
flash u-boot-env1 "$images/u-boot-env.bin"
flash boot "$images/boot.vfat"
flash rootfs "$images/rootfs.ext4" -R
echo "Done in $(( $(date +%s) - start )) s. The board resets and boots; first boot takes a little longer."
