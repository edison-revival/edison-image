#!/usr/bin/env bash
# Build U-Boot, the kernel, then the rootfs and flashable images, into out/.
#   out/uboot/   u-boot.bin (built by edison-recovery at a pinned commit)
#   out/kernel/  vmlinuz, modules.tar.gz, config, RELEASE
#   out/image/   boot.vfat, rootfs.ext4, u-boot-env.bin
# Usage: scripts/build.sh [uboot|kernel|rootfs|all]   (default: all)
#
# EDISON_RECOVERY_DIR=/path/to/edison-recovery uses a local checkout instead of fetching
# the pinned commit.
set -euo pipefail

# edison-recovery owns the U-Boot build (and its OSIP/layout fixes).
EDISON_RECOVERY_URL=https://github.com/edison-revival/edison-recovery.git
EDISON_RECOVERY_COMMIT=8af50cf04f77d6e33b9a70dead0bf6d9fe0d43b2

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${OUT:-$root/out}"
what="${1:-all}"
cd "$root"

if [ "$what" = uboot ] || [ "$what" = all ]; then
    recovery="${EDISON_RECOVERY_DIR:-}"
    if [ -z "$recovery" ]; then
        recovery="$out/src/edison-recovery"
        if [ ! -d "$recovery/.git" ]; then
            git clone --quiet "$EDISON_RECOVERY_URL" "$recovery"
        fi
        git -C "$recovery" fetch --quiet origin
        git -C "$recovery" checkout --quiet --detach "$EDISON_RECOVERY_COMMIT"
    fi
    docker build --output "$out/uboot" -f "$recovery/docker/uboot.Dockerfile" "$recovery"
fi

if [ "$what" = kernel ] || [ "$what" = all ]; then
    docker build --output "$out/kernel" -f docker/kernel.Dockerfile .
fi

if [ "$what" = rootfs ] || [ "$what" = all ]; then
    docker build -t edison-image/rootfs-tools -f docker/rootfs.Dockerfile docker
    mkdir -p "$out/image" "$out/cache"
    # v0.1.0 on a tag, v0.1.0-3-gabc1234 after it, a bare commit hash before the first tag.
    version="$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"
    docker run --rm --privileged \
        -e IMAGE_VERSION="$version" \
        -e IMAGE_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)" \
        -v "$root:/src:ro" \
        -v "$out/kernel:/in/kernel:ro" \
        -v "$out/image:/out" \
        -v "$out/cache:/cache" \
        edison-image/rootfs-tools bash /src/rootfs/build-rootfs.sh
fi
