# Flashing from macOS

## 1. Install the tools (once)

With [Homebrew](https://brew.sh):

```
brew install dfu-util uv
```

(or install uv with `curl -LsSf https://astral.sh/uv/install.sh | sh`). macOS needs no
USB driver for DFU mode.

## 2. Get an image

Download every file from the latest
[release](https://github.com/open-edison/edison-image/releases) into one folder (or
extract a CI build artifact). The folder should contain `flash.py`, `SHA256SUMS`,
`u-boot.bin`, `u-boot-env.bin`, `boot.vfat` and `rootfs.ext4.xz`.

## 3. Connect the board

- A micro-USB **data** cable from your Mac to **J16** (the middle micro-USB).
- **SW1** towards the micro-USB ports (device mode).
- Optional: a second cable to **J3** for the serial console (macOS includes the FTDI
  driver):

  ```
  screen /dev/cu.usbserial-* 115200
  ```

  (Quit `screen` with Ctrl+A, then K.)

macOS asks whether to allow each new USB accessory (**Allow accessory to connect**):
allow the board's DFU device, its network and serial ports, and the J3 console. It may ask
again after a flash that changes how the board describes itself over USB; allow it again.

## 4. Flash

In the image folder, in Terminal:

```
uv run flash.py
```

It checks the files, then waits for the board. Put the board into DFU mode:

- **Board already running this image:** on the board, `sudo edison-dfu`.
- **Anything else:** power-cycle it, or `sudo reboot` it. The flasher catches the short DFU
  window during boot, and waits for the next one if it misses.

Don't use the reset button while Linux is running (see the README's Notes).

A flash takes about 2½ minutes (tested on a Mac: 2:22), in two stages with a reset (or two)
in between.
**It erases the old system completely.** Later flashes keep your settings; to update only
the system: `uv run flash.py --only rootfs`.

## 5. First boot

Allow the accessory if macOS asks again.

The board appears as a USB network adapter ("Intel Edison") and gives your Mac an address
by DHCP. Then:

```
ssh edison@edison.local
```

The password is `edison`, and you must choose a new one. See the README's "First steps on
the board" for WiFi, time zone and locale.

## Troubleshooting

See the [Linux guide's table](flashing-linux.md#troubleshooting); everything except the
udev rule applies.
