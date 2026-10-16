# The Intel Edison Kit for Arduino: hardware guide

What the connectors, switch, buttons, jumpers and LEDs on the Arduino expansion board
(`EDI1ARDUIN.AL.K`) do, and the hardware quirks found while bringing it back up. Facts about
the board come from Intel's documents (see [Sources](#sources)), whose intel.com copies are
gone; quirks come from testing this project's image on real boards.

Designators (J16, SW1UI2, …) are printed on the board next to each part. Left and right
here are with the board the way its printing reads: USB ports on the right.

## Connectors

| Ref | What | Use it for |
|---|---|---|
| **J16** | Micro-USB, the module's USB OTG port in device mode; also a power input | Flashing (DFU), recovery, and with edison-image: USB networking, SSH and the Arduino `Serial` port |
| **J3** | Micro-USB to an FTDI FT232R USB-serial chip on the module's UART2 | The Linux and U-Boot console, 115200 8N1 |
| **J6** | Full-size USB-A, the same OTG port in host mode | USB devices (keyboard, storage, …) when SW1 selects host mode |
| **J1** | DC barrel jack, **7–15 V** | Power; needed for USB host mode and recommended for shields |
| **J2** (BATT) | 2-pin battery header: pin 1 = battery +, pin 2 = ground. One Li-ion/Li-Po cell (3.0–4.3 V, charged to 4.2 V at 100 mA) | Use a cell of 200 mAh or more with its own protection circuit. **It isn't a jumper: a jumper here shorts the charger's battery output to ground.** |
| — | Micro-SD slot | Storage |
| J4 | 2×3 ICSP header: MISO/SCK/MOSI (= IO12/IO13/IO11), 5 V, RESET, GND | Shields that take SPI from ICSP |
| Headers | Arduino Uno R3 layout: IO0–IO13, A0–A5 (IO14–IO19), AREF, SDA/SCL, power | Shields |

## Switch SW1: USB host or device

SW1 routes the module's single USB port to one of the two connectors:

- **Towards the micro-USB ports (J16): device mode.** Use this for flashing, recovery,
  USB networking and Arduino uploads. This is the position you almost always want.
- **Towards the large USB-A port (J6): host mode.** J16 is disconnected. **Host mode
  always needs the DC supply on J1**; the board can't power USB devices from J16.

## Buttons

From the board edge inwards: **RM, FW, PWR, SHLD RST**, then **RESET** further in.

| Ref | Label | What it does |
|---|---|---|
| **SW1UI5** | RESET (system reset) | Resets the module (an abrupt reset) and, per Intel, the I/O expanders. **Avoid it while Linux runs**: see [Quirks](#quirks). |
| **SW1UI1** | SHLD RST (shield reset) | Pulls the shield header's RESET pin low; doesn't affect the module |
| **SW1UI2** | PWR (power) | While running, a **short press** shuts Linux down cleanly and powers off (tested on edison-image), the safe alternative to RESET. From off, **hold 3 s** to power on. While running, **hold 10 s or more** to force power off. (Intel's 2–7 s "access point mode" was a feature of Intel's own software and doesn't apply to edison-image.) |
| SW1UI3, SW1UI4 | FW (firmware recovery), RM (recovery mode) | "For factory use only" per Intel; no documented use. Recovery doesn't need them: see [edison-recovery](https://github.com/open-edison/edison-recovery). |

To enter DFU mode for flashing, run `sudo edison-dfu` (or `sudo reboot`) on the board rather
than pressing reset; U-Boot opens a short DFU window on every boot.

## Jumpers

| Ref | Sets | Positions |
|---|---|---|
| **J9** | **IOREF**: the voltage the header's level shifters use, and the IOREF pin | **Pins 1-2: 5 V** (as shipped). Pins 2-3: 3.3 V, for 3.3 V shields. |
| **J8** | Analog reference for A0–A5 | **Pins 1-2: IOREF** (as shipped), so A0–A5 read 0–5 V, or 0–3.3 V with J9 at 3.3 V. Pins 2-3: the external AREF pin. |
| **J11, J12** | Which header pins get the module's four PWM outputs (the "PWM swizzler") | Default (J12 1-2, J12 3-4, J11 1-2, J11 3-4): PWM on IO3, IO5, IO6 and IO9. See below. |
| **J13** | The battery charger's thermistor (NTC) input | **Pins 2-3: grounded** (as shipped), which turns off the charger's battery-temperature check. Pins 1-2: the input goes to pin 1, for a battery pack's own thermistor. Leave it on 2-3 unless your battery has one. |

Pin 1 of J8, J9 and J13 is marked with an arrow on the board. Pin assignments are from
Intel's schematic: J9 pin 1 = 5 V, pin 2 = IOREF, pin 3 = 3.3 V; J8 pin 1 = IOREF, pin 2 =
the ADC reference, pin 3 = AREF; J13 pin 1 = thermistor connection, pin 2 = the LTC4067
charger's NTC input, pin 3 = ground. "As shipped" was checked on one board.

**PWM:** the module has only four PWM channels, for the six "~" pins (3, 5, 6, 9, 10, 11).
The J11/J12 jumpers choose which four; Intel's hardware guide (Table 9) lists the
combinations. A pin whose jumper is moved away has no function left: driven as an output
it stays high, and as an input it reads nothing.

## LEDs

Intel's drawing of where they are: Figure 5 on
[page 18 of the hardware guide](https://web.archive.org/web/20181010021857/https://www.intel.com/content/dam/support/us/en/documents/edison/sb/edison-arduino-hardware-guide.pdf#page=18).

| Ref | Meaning |
|---|---|
| **DS1** | On while the module runs, off while it's held in reset. Next to DS3, on its left. |
| **DS2** | The Arduino "L" LED, on IO13 (`LED_BUILTIN`). Next to the module. |
| **DS3** | Green: battery charging. Next to the module. |

## Power

- **Sources:** the DC jack (through a 5 V regulator) and J16's USB power are combined with
  diodes; the higher one wins. There's nothing to switch.
- **USB power is limited to 500 mA** (1 A from the DC jack). The module draws about 200 mA,
  with WiFi bursts up to 600 mA; together with shields and the SD card this can exceed what
  a USB port allows, and some computers then shut the port off until they're rebooted. Use
  the DC supply when using WiFi heavily or powering shields.
- On USB power, the shield header's 5 V can be as low as 4.4 V.
- The 3.3 V supply for shields is good for about 250 mA.

## Header pins and I/O

- Every header pin goes through a level shifter from the module's 1.8 V to IOREF (J9), and
  can source or sink up to 24 mA at 3.3 V or 32 mA at 5 V. Optional pull-ups are 47 kΩ.
- A0–A5 are read by a 12-bit ADC (TI ADS7951), switched with the digital function. Its
  reference is IOREF halved (J8 on IOREF), and edison-image sets its 2× range, so full
  scale is IOREF: on USB power that's the 5 V rail at about 4.5 V. (A4/A5 are I2C in
  edison-image, so only A0–A3 are analog inputs.)
- **IO0/IO1 are UART1** (`Serial1` in Arduino), not the console: the console is UART2 on J3.
- **In edison-image** (fixed by the ACPI tables it loads at boot):
  - IO0/IO1 are UART1 and A4/A5 are I2C-6 (`Serial1` and `Wire`), so those pins can't be
    plain GPIO.
  - SPI on IO10–IO13 is off by default, so those pins, including IO13 and DS2, work as GPIO.
    See [acpi/README.md](../acpi/README.md) to switch.

## Quirks

- **The reset button can leave the board's I/O half-working.** Pressing reset (SW1UI5)
  while Linux runs can leave the I/O expander at I2C address 0x20 not responding until power
  is removed, though Intel's guide says the button resets the expanders. Symptoms:
  `edison-acpi-tables.service` fails with "TRI_STATE_ALL not found", and many header pins
  don't work. **Fix: unplug all power (DC and both USB cables) and reconnect.** Avoid it by
  using `sudo reboot`, `sudo poweroff`, `sudo edison-dfu` or a short press of PWR. A
  watchdog reset is probably
  just as abrupt.
- **A brief unknown or DFU device at every power-on.** U-Boot opens a 3-second DFU window
  (`8087:0a99`) on each boot, before Linux brings up the network and serial ports. Hosts may
  show an unrecognised device, or log a failed enumeration ("error -32"), for those seconds.
  Both are harmless.
- **Cables cause most "nothing shows up" problems.** Charge-only cables and loose-fitting
  micro-USB plugs look the same as a dead board. Reseat, or swap the J3 and J16 cables: a
  cable that works on the console carries data.
- **No clock that survives power-off.** The board starts with a stale date until it syncs
  over the network; `apt update` fails ("Not live until …") until then.
- **No second-chance bootloader.** The boot firmware has no fallback to a second U-Boot copy,
  so a broken U-Boot means recovery over USB with
  [edison-recovery](https://github.com/open-edison/edison-recovery). The recovery
  window (USB `8086:e005`) lasts under a second per boot, which is why recovery needs a
  native Linux host rather than a VM.
- **USB host mode needs the DC supply** (see SW1).
- **The watchdog's panic margin.** The SCU watchdog driver raises a panic 15 s before its
  timeout and can't change the timeout once running. edison-image sets systemd's runtime
  and reboot watchdog timeouts both to 60 s; shorter or unequal values can panic the board,
  especially during shutdown.

## Sources

- *Intel Edison Kit for Arduino Hardware Guide*, document 331191-008 (March 2017):
  [archived copy](https://web.archive.org/web/20181010021857/https://www.intel.com/content/dam/support/us/en/documents/edison/sb/edison-arduino-hardware-guide.pdf).
  Revision 007 (February 2015) gives 7–17 V for the DC input in one place; 008 corrects it
  to 7–15 V.
- Intel schematic *Edison for Arduino board*, H40485 rev 5 (August 2014):
  [archived copy](https://web.archive.org/web/20160417191754/http://www.intel.com:80/content/dam/support/us/en/documents/edison/sb/edison_arduino_hvm_8_26.pdf).
  Source for the J2, J3, J8, J9 and J13 designators and pin assignments.
- Analog Devices (Linear Technology) LTC4067 datasheet: the charger on J2; its NTC input
  has a disable threshold, so grounding it (J13 at 2-3) turns the temperature check off.
- Quirks: tested on real boards while developing edison-image.
