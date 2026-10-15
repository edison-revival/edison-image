# Tooling for rootfs/build-rootfs.sh. mmdebstrap needs to mount /proc etc. in the chroot,
# so the container runs with --privileged (see scripts/build.sh).
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      mmdebstrap gpg debian-archive-keyring ca-certificates curl \
      e2fsprogs dosfstools mtools u-boot-tools acpica-tools \
 && rm -rf /var/lib/apt/lists/*
