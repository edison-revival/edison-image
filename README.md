# edison-image

Debian 13 (trixie) for the Intel Edison (Kit for Arduino), on a mainline LTS kernel,
booted by mainline U-Boot.

**Status:** boots and passes the hardware checks (serial, USB networking, SSH, WiFi,
Bluetooth, I2C, GPIO) on a real board. Flashing is tested from Linux, macOS and Windows.

## What you get

- Linux 6.18 LTS (x86_64) with the Edison drivers built in: no initramfs.
- Debian 13 with `apt`, systemd, SSH, WiFi (`wpa_supplicant`), Bluetooth (`bluez`, with
  each board's factory address), `gpiod`, `i2c-tools`.
- **USB networking with nothing to configure on the computer:** plug J16 in, and the Edison
  appears as a USB network adapter (NCM) and hands your computer an address by DHCP.
  The board is `192.168.2.15`, or `edison.local`.
- A USB serial port (ACM) on the same cable, reserved for Arduino sketches as `Serial`
  (see [arduino-core-edison](https://github.com/open-edison/arduino-core-edison)). Log
  in over SSH on the same cable, or on the FTDI serial console on J3.
- Arduino sketches run as the `edison-sketch` service from `/var/lib/edison-sketch/`,
  restarted automatically when a new one is uploaded; the board advertises itself to the
  Arduino IDE over mDNS.
- The Arduino kit's I/O: expanders, level shifters and muxing described by ACPI overlays,
  with UART1 on IO0/IO1 and I2C-6 on SDA/SCL. The other header pins, including IO13 and
  its DS2 LED, are left for sketches to drive.
- **Settings that survive reflashing** (see below), and almost the whole eMMC (~3.5 GiB)
  for the root filesystem.

## Get an image

- **Releases:** download from the
  [releases page](https://github.com/open-edison/edison-image/releases).
- **Latest build:** each push to `main` builds the image in CI. Open the newest successful
  [build run](https://github.com/open-edison/edison-image/actions/workflows/build.yml)
  and download its `edison-image-*` artifact (kept for 7 days).
- **From source:** see [CONTRIBUTING.md](CONTRIBUTING.md).

A download contains `u-boot.bin`, `u-boot-env.bin`, `boot.vfat`, `rootfs.ext4.xz`,
`SHA256SUMS`, `packages.manifest` and `flash.py`.

## Flash

Step-by-step guides: **[Linux](docs/flashing-linux.md)** ·
**[macOS](docs/flashing-macos.md)** · **[Windows](docs/flashing-windows.md)**.

In short: install `dfu-util` and [uv](https://docs.astral.sh/uv/), then in the extracted
download run

```
uv run flash.py
```

and reboot the board into DFU mode when asked (`sudo edison-dfu` on a board already running
this image). The board must already run U-Boot with working DFU: a board recovered with
[edison-recovery](https://github.com/open-edison/edison-recovery), or with the vendor
U-Boot.

> **The first flash is a clean slate.** It replaces U-Boot and rewrites the partition
> table: everything on the old rootfs, `update` and `home` partitions is lost. Later
> flashes keep your settings (below). The IFWI and the factory partition are never touched.

## First steps on the board

- **Log in** over SSH (`ssh edison@edison.local`) or a serial console: `edison` /
  `edison`. You must change the password at first login. Root login over SSH is disabled;
  use `sudo`.
- **WiFi:**

  ```
  sudo sh -c 'wpa_passphrase "MyNetwork" >> /etc/wpa_supplicant/wpa_supplicant-wlan0.conf'
  ```

  ```
  sudo wpa_cli -i wlan0 reconfigure
  ```

- **Time zone and locale:** `sudo timedatectl set-timezone Area/City`;
  `sudo dpkg-reconfigure locales`. The image defaults to UTC and `C.UTF-8`.
- **Reflash later** with `sudo edison-dfu` on the board, then `uv run flash.py --only
  rootfs` on the computer (or the full flash for a new U-Boot or environment).

## What survives a reflash

The eMMC has one large root filesystem (with `/home`) plus a small `config` partition,
mounted at `/var/lib/edison`, which flashing never writes. It keeps:

- WiFi networks, SSH host keys (no "host key changed" warnings), users, passwords, groups
  and SSH `authorized_keys`, the hostname, time zone and locale, Bluetooth pairings, and any
  extra systemd-networkd config you put in `/var/lib/edison/network/`;
- any other files you list in `/var/lib/edison/files.list` (one absolute path per line).

Settings are saved when they change and at every clean shutdown; `sudo edison-config save`
saves now. Everything else in the root filesystem, **including `/home`**, is replaced by a
reflash. Keep data that must survive on a microSD card (the Kit for Arduino has a slot), and
update installed software with `apt` rather than by reflashing.

| Partition | Size | Contents |
|---|---|---|
| 1–6 | 32 MiB | U-Boot (×2), its environment (×2), factory data, panic |
| `boot` | 64 MiB | the kernel |
| `config` | 64 MiB | settings that survive reflashing |
| `rootfs` | the rest (~3.5 GiB) | Debian, including `/home` |

## Notes

See **[docs/hardware.md](docs/hardware.md)** for what the board's connectors, switch,
buttons, jumpers and LEDs do, and its known quirks.

- **Use `sudo edison-dfu` or `sudo reboot`, not the reset button:** an abrupt reset while
  Linux is running (the reset button, and presumably a watchdog reset) can leave the kit's
  I/O expander at I2C-1 0x20 unresponsive, because the expanders stay powered while the SoC
  restarts. A clean reboot or a power cycle is fine. The chip has no reset pin and doesn't
  support the I2C general-call reset, so only removing power clears it.
  `edison-acpi-tables.service` then fails with "TRI_STATE_ALL not found"; unplug all power
  and reconnect.
- **Clock:** there's no battery-backed time source, so the board boots with a stale clock
  until `systemd-timesyncd` syncs over the network. `apt update` fails ("Not live until")
  until then.
- **SPI on the header** (IO10–IO13) is off by default, so those pins work as GPIO for
  sketches. See `acpi/README.md` to switch.
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
[edison-recovery](https://github.com/open-edison/edison-recovery)'s
`docker/uboot.Dockerfile`; Debian packages at the exact versions listed in each release's
`packages.manifest`, available from [snapshot.debian.org](https://snapshot.debian.org/).
The Broadcom WiFi/Bluetooth firmware is redistributed unmodified under
`LICENCE.broadcom_bcm43xx` / Debian's `firmware-brcm80211` terms.

## Credits

Kernel config fragments and patches: [edison-fw/meta-intel-edison](https://github.com/edison-fw/meta-intel-edison)
(Ferry Toth, based on Andy Shevchenko's Edison kernel work). Arduino kit ACPI tables:
[meta-acpi](https://github.com/westeri/meta-acpi) (Intel).
