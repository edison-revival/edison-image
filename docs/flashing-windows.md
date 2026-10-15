# Flashing from Windows

> **Not yet tested on hardware.** This guide follows the documented behaviour of
> dfu-util, Zadig and Windows' built-in USB drivers. If you try it, please report what
> worked or didn't in an issue.

Windows needs one extra step compared with Linux and macOS: a driver for the board's DFU
mode, installed once with Zadig.

## 1. Install the tools (once)

- **uv**, in PowerShell:

  ```
  winget install astral-sh.uv
  ```

- **dfu-util**, either with [Scoop](https://scoop.sh):

  ```
  scoop install dfu-util
  ```

  or by downloading `dfu-util-0.11-binaries.tar.xz` from the
  [dfu-util releases](https://dfu-util.sourceforge.net/releases/), extracting
  `win64\dfu-util.exe` and putting its folder on your `PATH`. Check with
  `dfu-util --version` in a new PowerShell window.

- **[Zadig](https://zadig.akeo.ie/)** (no install needed; just download it).

## 2. Get an image

Download every file from the latest
[release](https://github.com/edison-revival/edison-image/releases) into one folder (or
extract a CI build artifact). The folder should contain `flash.py`, `SHA256SUMS`,
`u-boot.bin`, `u-boot-env.bin`, `boot.vfat` and `rootfs.ext4.xz`.

## 3. Connect the board

- A micro-USB **data** cable from your PC to **J16** (the middle micro-USB).
- **SW1** towards the micro-USB ports (device mode).
- Strongly recommended for the first time: a second cable to **J3** for the serial
  console. Windows installs the FTDI driver automatically; find the COM port in Device
  Manager under *Ports (COM & LPT)*, then connect with [PuTTY](https://www.putty.org/):
  connection type *Serial*, that COM port, speed 115200, flow control *None*.

## 4. Install the DFU driver (once)

Zadig can only install the driver while the board is in DFU mode, so hold it there:

- **Board already running this image:** on the board, `sudo edison-dfu`.
- **Otherwise:** power-cycle the board and, in the serial console, press a key when you see
  `Hit any key to stop autoboot`. At the `=>` prompt, start DFU mode and leave it running:
  `run do_dfu` on edison-revival U-Boot, or `run do_force_flash_os` on vendor U-Boot.

Then in Zadig:

1. *Options* → **List All Devices**.
2. Select **USB download gadget** (USB ID `8087 0A99`).
3. Choose **WinUSB** as the driver and click **Install Driver**.

That's needed once per PC. Press Ctrl+C in the serial console to leave DFU mode, or just
continue with the next step while the board waits.

## 5. Flash

In PowerShell, in the image folder:

```
uv run flash.py
```

It checks the files, then waits for the board. If the board isn't still waiting in DFU
mode from step 4, put it there: `sudo edison-dfu` on a board running this image, or
power-cycle it (the flasher catches the short DFU window during boot, and waits for the
next one if it misses).

Don't use the reset button while Linux is running (see the README's Notes).

The first flash takes about 3 minutes in two stages, with a reset (or two) in between.
**It erases the old system completely.** Later flashes keep your settings; to update only
the system: `uv run flash.py --only rootfs`.

## 6. First boot

The board appears as a USB network adapter (Windows 10 and 11 include the NCM driver) and
gives your PC an address by DHCP. Then, in PowerShell:

```
ssh edison@edison.local
```

(or `ssh edison@192.168.2.15`). The password is `edison`, and you must choose a new one.
See the README's "First steps on the board" for WiFi, time zone and locale.

## Troubleshooting

| Symptom | Fix |
|---|---|
| dfu-util: "Cannot open DFU device" / `LIBUSB_ERROR_NOT_SUPPORTED` | The WinUSB driver isn't installed for `8087:0a99`: repeat step 4. |
| "no DFU device found" | Check the cable is a data cable, it's in J16, and SW1 is towards the micro-USB ports. |
| "missed the DFU window" | Power-cycle the board again; the flasher keeps waiting. `sudo edison-dfu` avoids the race. |

For everything else, see the [Linux guide's table](flashing-linux.md#troubleshooting).
