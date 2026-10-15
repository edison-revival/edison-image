# Mainline LTS kernel for the Edison, pinned by version and tarball checksum.
# Build with: docker build --output out/kernel -f docker/kernel.Dockerfile .
ARG BASE=debian:trixie-slim

FROM ${BASE} AS build
ARG KERNEL_VERSION=6.18.56
ARG KERNEL_SHA256=4633bbda2ab95eaf2a7af4041236451d6759c72e6946265531af4b3aacefbf89
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils patch \
      gcc make bc bison flex libssl-dev libelf-dev cpio kmod python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN curl -fsSLO "https://cdn.kernel.org/pub/linux/kernel/v${KERNEL_VERSION%%.*}.x/linux-${KERNEL_VERSION}.tar.xz" \
 && echo "${KERNEL_SHA256}  linux-${KERNEL_VERSION}.tar.xz" | sha256sum -c - \
 && tar xf "linux-${KERNEL_VERSION}.tar.xz" --strip-components=1 \
 && rm "linux-${KERNEL_VERSION}.tar.xz"

COPY kernel/patches/ /patches/
RUN for p in /patches/*.patch; do echo "applying ${p##*/}"; patch -p1 --forward --no-backup-if-mismatch < "$p" || exit 1; done

COPY kernel/fragments/ /fragments/
COPY kernel/required.txt kernel/check-config.sh /config/
RUN scripts/kconfig/merge_config.sh -m arch/x86/configs/x86_64_defconfig \
      /fragments/edison-fw/*.cfg /fragments/edison-revival.cfg \
 && make olddefconfig \
 && sh /config/check-config.sh .config /config/required.txt

RUN make -j"$(nproc)" bzImage modules \
 && make INSTALL_MOD_PATH=/out/modules INSTALL_MOD_STRIP=1 modules_install \
 && rm -f /out/modules/lib/modules/*/build \
 && cp arch/x86/boot/bzImage /out/vmlinuz \
 && cp .config /out/config \
 && cp System.map /out/System.map \
 && make -s kernelrelease > /out/RELEASE \
 && tar -C /out/modules -czf /out/modules.tar.gz lib \
 && rm -rf /out/modules \
 && cd /out && sha256sum vmlinuz modules.tar.gz > SHA256SUMS

FROM scratch
COPY --from=build /out/ /
