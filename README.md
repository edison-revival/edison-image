# edison-image

Debian 13 (trixie) for the Intel Edison (Kit for Arduino), on a mainline LTS kernel,
booted by mainline U-Boot. See
[decision 0001](https://github.com/edison-revival/edison-docs/blob/main/decisions/0001-stage3-os-image.md)
for why it's built this way.

**Status:** boots and passes the hardware checks (serial, USB networking, SSH, WiFi,
Bluetooth, I2C, GPIO) on a real board. No tagged release yet.

## What you get

- Linux 6.18 LTS (x86_64) with the Edison drivers built in: no initramfs.
- Debian 13 with `apt`, systemd, SSH, WiFi (`wpa_supplicant`), Bluetooth (`bluez`, with
  each board's factory address), `gpiod`, `i2c-tools`.
- **USB networking with nothing to configure on the computer:** plug J16 in, and the Edison
  appears as a USB network adapter (NCM) and hands your computer an address by DHCP.
  The board is `192.168.2.15`, or `edison.local`.
- A USB serial console (ACM) on the same cable, besides the FTDI console on J3.
- The Arduino kit's I/O: expanders, level shifters and muxing described by ACPI overlays,
  with UART1 on IO0/IO1, I2C-6 on SDA/SCL and the DS2 LED on IO13 (heartbeat).
- Login `edison` / `edison`. You must change the password at first login. Root login over
  SSH is disabled; use `sudo`.

## Get an image

- **Releases** (when tagged): download from the
  [releases page](https://github.com/edison-revival/edison-image/releases).
- **Latest build:** each push to `main` builds the image in CI. Open the newest successful
  [build run](https://github.com/edison-revival/edison-image/actions/workflows/build.yml)
  and download its `edison-image-*` artifact (kept for 7 days).
- **From source:** see [CONTRIBUTING.md](CONTRIBUTING.md).

Either download contains `u-boot.bin`, `u-boot-env.bin`, `boot.vfat`, `rootfs.ext4.xz`,
`SHA256SUMS`, `packages.manifest` and `flash.py`.

## Flash

Needs:
- `dfu-util` (Linux: `sudo apt install dfu-util`; macOS: `brew install dfu-util`;
  Windows: the dfu-util release binaries plus the WinUSB driver for `8087:0a99`)
- on Linux, the udev rule from
  [edison-recovery](https://github.com/edison-revival/edison-recovery)`/udev/`
- [uv](https://docs.astral.sh/uv/), which also fetches a suitable Python if you don't have
  one: `winget install astral-sh.uv` on Windows,
  `curl -LsSf https://astral.sh/uv/install.sh | sh` on Linux/macOS. The script uses only
  the standard library, so `python3 flash.py` works too.

The board must already run U-Boot with working DFU (a board recovered with
`edison-recovery`, or vendor U-Boot).

In an extracted download (or `uv run scripts/flash.py` in a source checkout after
building):

```
uv run flash.py
```

It verifies the images, waits for the board, then writes U-Boot, its environment (both
copies), the kernel and the rootfs, showing progress, speed and time remaining. The IFWI
isn't touched. `--only rootfs` (or any list of partitions) reflashes just those. Ctrl+C is
safe: it never interrupts the U-Boot writes, and tells you how to recover otherwise.

To get the board into DFU mode, **reboot it** while the script waits (`sudo reboot` if it
runs Linux, or power-cycle it): U-Boot opens a 3-second DFU window on every boot. Don't use
the reset button while Linux is running (see Notes).

Reflashing the rootfs replaces everything in it, including WiFi settings and the `edison`
password.

## Notes

- **Arduino kit expander wedged:** an abrupt reset while Linux is running (the reset
  button, and presumably a watchdog reset) can leave the kit's I/O expander at I2C-1 0x20
  unresponsive: the expanders stay powered while the SoC restarts. A clean reboot or a power
  cycle is fine. The chip has no reset pin and doesn't support the I2C general-call reset, so
  only removing power clears it. `edison-acpi-tables.service` then fails with
  "TRI_STATE_ALL not found"; unplug all power and reconnect.
- **Clock:** there's no battery-backed time source, so the board boots with a stale clock
  until `systemd-timesyncd` syncs over the network. `apt update` fails ("Not live until")
  until then.
- **SPI on the header** is off by default: it shares IO13 with the DS2 LED. See
  `acpi/README.md` to switch.
- **Security modules:** the kernel has no active LSM policy. SELinux is disabled (Debian
  ships no policy and doesn't use it by default). Stock Debian uses AppArmor; we don't
  enable it yet. Planned approach, one image rather than two variants: build AppArmor into
  the kernel (`CONFIG_SECURITY_APPARMOR=y`) but leave it out of the default LSM list, so it
  costs nothing unless wanted. To opt in, `apt install apparmor` and add
  `lsm=landlock,lockdown,yama,apparmor` (or the current list plus `apparmor`) to `bootargs`
  in the U-Boot environment, then reboot; packages such as `avahi-daemon` then apply their
  own profiles. If AppArmor later becomes the default, it's one config change.

## Licence

Our own code is under the MIT licence (`LICENSE`). Third-party files keep their licences:

| Path | Licence |
|---|---|
| `kernel/patches/` | GPL-2.0 (they modify the Linux kernel) |
| `kernel/fragments/edison-fw/` | MIT, from [edison-fw/meta-intel-edison](https://github.com/edison-fw/meta-intel-edison) |
| `acpi/meta-acpi/` | MIT, Copyright (C) 2017 Intel Corporation, from [westeri/meta-acpi](https://github.com/westeri/meta-acpi) |

**Built images** contain GPL software (Linux, U-Boot, Debian packages). Corresponding
source: Linux from kernel.org at the version and checksum pinned in
`docker/kernel.Dockerfile`, plus `kernel/patches/` and the config in each release
(`kernel.config`); U-Boot at the commit pinned in
[edison-recovery](https://github.com/edison-revival/edison-recovery)'s
`docker/uboot.Dockerfile`; Debian packages at the exact versions listed in each release's
`packages.manifest`, available from [snapshot.debian.org](https://snapshot.debian.org/).
The Broadcom WiFi/Bluetooth firmware is redistributed unmodified under
`LICENCE.broadcom_bcm43xx` / Debian's `firmware-brcm80211` terms.

## Credits

Kernel config fragments and patches: [edison-fw/meta-intel-edison](https://github.com/edison-fw/meta-intel-edison)
(Ferry Toth, based on Andy Shevchenko's Edison kernel work). Arduino kit ACPI tables:
[meta-acpi](https://github.com/westeri/meta-acpi) (Intel).
