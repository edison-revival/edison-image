# Flashing from Linux

Tested on Linux Mint 22.3 (Ubuntu 24.04 base) with dfu-util 0.11.

## 1. Install the tools (once)

```
sudo apt install dfu-util
```

(Fedora: `sudo dnf install dfu-util`; Arch: `sudo pacman -S dfu-util`.)

Install [uv](https://docs.astral.sh/uv/), which runs the flasher and fetches a suitable
Python if needed:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Allow your user to access the Edison over USB without root (both the DFU mode U-Boot
uses and the recovery mode, for later):

```
curl -fsSL https://raw.githubusercontent.com/open-edison/edison-recovery/main/udev/99-edison.rules | sudo tee /etc/udev/rules.d/99-edison.rules
```

```
sudo udevadm control --reload-rules
```

The rule gives the `plugdev` group access; check you're in it with `groups` (Debian and
Ubuntu add desktop users by default). Without the rule, dfu-util fails with
`LIBUSB_ERROR_ACCESS`.

## 2. Get an image

Download every file from the latest
[release](https://github.com/open-edison/edison-image/releases) into one folder (or
extract a CI build artifact). The folder should contain `flash.py`, `SHA256SUMS`,
`u-boot.bin`, `u-boot-env.bin`, `boot.vfat` and `rootfs.ext4.xz`.

## 3. Connect the board

- A micro-USB **data** cable from your computer to **J16** (the middle micro-USB).
- **SW1** towards the micro-USB ports (device mode).
- Power from J16 is enough for flashing; a 7–15 V supply on the DC jack doesn't hurt.
- Optional but useful: a second cable to **J3** for the serial console:

  ```
  picocom -b 115200 /dev/ttyUSB0
  ```

## 4. Flash

In the image folder:

```
uv run flash.py
```

It checks the files, then waits for the board. Put the board into DFU mode:

- **Board already running this image:** on the board, `sudo edison-dfu`. U-Boot then waits
  for the flasher as long as needed.
- **Anything else** (vendor image, older open-edison builds, no Linux): power-cycle it,
  or `sudo reboot` it. U-Boot opens a DFU window for a few seconds during boot; the flasher
  catches it, and if it misses, it says so and waits for the next boot.

Don't use the reset button while Linux is running (see the README's Notes).

The first flash of this image takes about 3 minutes and has two stages: U-Boot and its
environment first, then the board resets (and on the first flash rewrites its partition
table and resets again), then the kernel and rootfs. **This first flash erases the old
system completely.** Later flashes keep your settings; to update only the system:

```
uv run flash.py --only rootfs
```

## 5. First boot

The board resets and boots by itself; the first boot takes a minute or so. Your computer
gets a USB network connection automatically, then:

```
ssh edison@edison.local
```

(or `ssh edison@192.168.2.15`). The password is `edison`, and you must choose a new one.
See the README's "First steps on the board" for WiFi, time zone and locale.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LIBUSB_ERROR_ACCESS` | The udev rule isn't installed, or your user isn't in `plugdev` (log out and back in after adding it). |
| "no DFU device found" | Check the cable is a data cable, it's in J16, and SW1 is towards the micro-USB ports. Swap cables between J3 and J16 to rule out a bad connector. |
| "missed the DFU window" | Reboot the board again; the flasher keeps waiting. `sudo edison-dfu` avoids the race. |
| Nothing at all on J16, even after a power cycle, and the serial console stops at `*** Ready to receive application ***` | The bootloader is gone: recover with [edison-recovery](https://github.com/open-edison/edison-recovery). |
| After boot, `edison-acpi-tables.service` failed ("TRI_STATE_ALL not found") | The Arduino kit's I/O expander is wedged after an abrupt reset. Unplug all power and reconnect. |
