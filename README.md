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

Needs:
- `dfu-util` (Linux: `sudo apt install dfu-util`; macOS: `brew install dfu-util`;
  Windows: the dfu-util release binaries plus the WinUSB driver for `8087:0a99`)
- on Linux, the udev rule from `edison-recovery/udev/`
- [uv](https://docs.astral.sh/uv/), which also fetches a suitable Python if you don't have
  one: `winget install astral-sh.uv` on Windows,
  `curl -LsSf https://astral.sh/uv/install.sh | sh` on Linux/macOS. The script uses only
  the standard library, so `python3 scripts/flash.py` works too.

The board must already run U-Boot with working DFU (a board recovered with
`edison-recovery`, or vendor U-Boot).

```
uv run scripts/flash.py
```

It verifies the images, waits for the board, then writes U-Boot, its
environment (both copies), the kernel and the rootfs, showing overall progress, speed and
time remaining. The IFWI isn't touched. `--only rootfs` (or any list of partitions)
reflashes just those.

To get the board into DFU mode, **reboot it** while the script waits (`sudo reboot` if it
runs Linux, or power-cycle it): U-Boot opens a 3-second DFU window on every boot. Don't use
the reset button while Linux is running (see Notes).

Reflashing the rootfs replaces everything in it, including WiFi settings and the `edison`
password.

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

## Notes

- **Security modules:** the kernel has no active LSM policy. SELinux is disabled (Debian
  ships no policy and doesn't use it by default). Stock Debian uses AppArmor; we don't
  enable it yet. Planned approach, one image rather than two variants: build AppArmor into
  the kernel (`CONFIG_SECURITY_APPARMOR=y`) but leave it out of the default LSM list, so it
  costs nothing unless wanted. To opt in, `apt install apparmor` and add
  `lsm=landlock,lockdown,yama,apparmor` (or the current list plus `apparmor`) to `bootargs`
  in the U-Boot environment, then reboot; packages such as `avahi-daemon` then apply their
  own profiles. If AppArmor later becomes the default, it's one config change.
- **Clock:** there's no battery-backed time source, so the board boots with a stale clock
  until `systemd-timesyncd` syncs over the network. `apt update` fails ("Not live until")
  until then.
- **Arduino kit expander wedged:** an abrupt reset while Linux is running (the reset
  button, and presumably a watchdog reset) can leave the kit's I/O expander at I2C-1 0x20
  unresponsive: the expanders stay powered while the SoC restarts. A clean reboot or a power
  cycle is fine. The chip has no reset pin and doesn't support the I2C general-call reset, so
  only removing power clears it. `edison-acpi-tables.service` then fails with
  "TRI_STATE_ALL not found"; unplug all power and reconnect.

## Credits

Kernel config fragments and patches: [edison-fw/meta-intel-edison](https://github.com/edison-fw/meta-intel-edison)
(Ferry Toth, based on Andy Shevchenko's Edison kernel work), MIT licence.
