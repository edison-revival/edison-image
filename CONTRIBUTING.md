# Contributing to edison-image

## Build from source

Needs Docker on Linux (WSL2 works). The rootfs step runs a privileged container, because
`mmdebstrap` mounts `/proc` in the chroot. CI runs exactly these scripts.

```
scripts/build.sh
```

`scripts/build.sh uboot|kernel|rootfs` builds one stage. Outputs:
- `out/uboot/`: mainline U-Boot, built from
  [edison-recovery](https://github.com/edison-revival/edison-recovery) at the commit pinned
  in `scripts/build.sh` (set `EDISON_RECOVERY_DIR` to use a local checkout instead)
- `out/kernel/`: `vmlinuz`, `modules.tar.gz`, `config`
- `out/image/`: `boot.vfat` (kernel), `rootfs.ext4`, `u-boot-env.bin`, `packages.manifest`
- `out/cache/`: downloaded Debian packages, reused by later builds

Then `uv run scripts/flash.py` flashes `out/`.

## Layout

| Path | Purpose |
|---|---|
| `docker/kernel.Dockerfile` | Kernel build: pinned tarball, patches, config, required-symbol check |
| `docker/rootfs.Dockerfile` | Tooling image for the rootfs build |
| `kernel/fragments/edison-fw/` | Config fragments from edison-fw/meta-intel-edison (MIT), unchanged |
| `kernel/fragments/edison-revival.cfg` | Our overrides: built-in eMMC/ext4/console, systemd needs, debug off |
| `kernel/patches/` | edison-fw patches still needed on 6.18 (8250_mid DMA, dwc3, tusb1210) |
| `kernel/required.txt` | Symbols the build checks after `olddefconfig` |
| `rootfs/build-rootfs.sh` | `mmdebstrap`, overlay, firmware, ACPI tables, images |
| `rootfs/packages.txt` | Debian packages |
| `rootfs/firmware.lock` | Edison WiFi NVRAM and Bluetooth firmware: URLs + SHA256 |
| `rootfs/overlay/` | Files copied into the rootfs (units, scripts, network config) |
| `acpi/` | Arduino kit ACPI overlays (meta-acpi) and which ones to load |
| `uboot/env.txt` | U-Boot environment (boot from the `boot` partition, `console=ttyS2`) |
| `scripts/flash.py` | DFU flasher, standard library only |
| `tests/` | `flash.py` unit tests and a fake `dfu-util` |

## CI and tests

- `.github/workflows/build.yml` builds everything on a GitHub-hosted runner on each push
  and uploads the images (rootfs xz-compressed) as an artifact. Pushing a `v*` tag also
  creates a release.
- `.github/workflows/test.yml` runs the `flash.py` unit tests on Linux, macOS and Windows
  (Python 3.9 and 3.13), Ruff (format and lint) and `shellcheck`.

Run them locally before pushing (the tests use only the standard library and a fake
`dfu-util`):

```
uv run --no-project python -m unittest discover -s tests
```

```
uvx ruff format . && uvx ruff check .
```

```
shellcheck scripts/*.sh rootfs/build-rootfs.sh kernel/check-config.sh rootfs/overlay/usr/local/sbin/*
```

## Conventions

- **Commits:** [Conventional Commits](https://www.conventionalcommits.org)
  (`feat(rootfs): ...`, `fix: ...`, `docs: ...`).
- **Python:** formatted and linted with Ruff (settings in `pyproject.toml`, 100-column
  code). Standard library only unless a dependency clearly pays for itself; then manage it
  with uv. User-facing output stays within 80 columns (the tests check `flash.py`'s).
- **Shell:** clean under `shellcheck`.
- **Pin every external input** (kernel tarball, U-Boot and xFSTK commits, firmware) by
  version and checksum or commit. Nothing that can't be redistributed goes in the repo;
  fetch it and verify it instead.
- **Builds must work from a clone with only Docker,** using the same scripts as CI.
- **Workflow actions:** pin to the commit SHA of the latest release, with the version in a
  comment (`actions/checkout@<sha> # v7.0.1`). Actions published as immutable releases use
  their exact tag instead (`astral-sh/setup-uv@v10.3.0`). Dependabot opens one grouped pull
  request a month with updates.
- **Hardware changes need a hardware test.** Note what you tested on a real board in the
  pull request; findings go in
  [edison-docs](https://github.com/edison-revival/edison-docs).
- **Flashing:** enter DFU with `sudo reboot`, not the reset button (see the README's Notes).
