# edison-image

Debian 13 (trixie) for the Intel Edison, on a mainline LTS kernel, booted by mainline
U-Boot. See `edison-docs/decisions/0001-stage3-os-image.md` for why it's built this way.

**Status:** first test build, not yet booted on hardware.

## What you get

- Linux 6.18 LTS (x86_64) with the Edison drivers built in: no initramfs.
- Debian 13 with `apt`, systemd, SSH, WiFi (`wpa_supplicant`), Bluetooth (`bluez`),
  `gpiod`, `i2c-tools`.
- **USB networking with nothing to configure on the computer:** plug J16 in, and the Edison
  appears as a USB network adapter (NCM) and hands your computer an address by DHCP.
  The board is `192.168.2.15`, or `edison.local`.
- A USB serial console (ACM) on the same cable, besides the FTDI console on J3.
- Login `edison` / `edison`. You must change the password at first login. Root login over
  SSH is disabled; use `sudo`.

## Build

Needs Docker on Linux (WSL2 works). The rootfs step runs a privileged container, because
`mmdebstrap` mounts `/proc` in the chroot.

```
scripts/build.sh
```

Outputs:
- `out/uboot/`: mainline U-Boot, built from
  [edison-recovery](https://github.com/edison-revival/edison-recovery) at the commit pinned
  in `scripts/build.sh` (set `EDISON_RECOVERY_DIR` to use a local checkout instead)
- `out/kernel/`: `vmlinuz`, `modules.tar.gz`, `config`
- `out/image/`: `boot.vfat` (kernel), `rootfs.ext4`, `u-boot-env.bin`

## Flash

Needs `dfu-util` and, on Linux, the udev rule from `edison-recovery/udev/`. The board must
already run mainline U-Boot (a board recovered with `edison-recovery`, or one with
working vendor U-Boot DFU).

```
scripts/flash.sh
```

Writes U-Boot, its environment (both copies), the kernel and the rootfs. The IFWI isn't
touched.

## Layout

| Path | Purpose |
|---|---|
| `kernel/fragments/edison-fw/` | Config fragments from edison-fw/meta-intel-edison (MIT), unchanged |
| `kernel/fragments/edison-revival.cfg` | Our overrides: built-in eMMC/ext4/console, systemd needs, debug off |
| `kernel/patches/` | edison-fw patches still needed on 6.18 (8250_mid DMA, dwc3, tusb1210) |
| `kernel/required.txt` | Symbols the build checks after `olddefconfig` |
| `rootfs/packages.txt` | Debian packages |
| `rootfs/firmware.lock` | Edison WiFi NVRAM and Bluetooth firmware: URLs + SHA256 |
| `rootfs/overlay/` | Config files copied into the rootfs |
| `uboot/env.txt` | U-Boot environment (boot from the `boot` partition, `console=ttyS2`) |

## Credits

Kernel config fragments and patches: [edison-fw/meta-intel-edison](https://github.com/edison-fw/meta-intel-edison)
(Ferry Toth, based on Andy Shevchenko's Edison kernel work), MIT licence.
