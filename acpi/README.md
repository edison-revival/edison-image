# ACPI table overlays

Mainline U-Boot's ACPI tables describe the Edison module only. The Arduino kit's GPIO
expanders, level shifters, multiplexers and pull-ups (and the devices behind them) come
from SSDT overlays, loaded at boot through ACPI configfs by `edison-acpi-tables.service`.

- `meta-acpi/`: the Edison samples from
  [westeri/meta-acpi](https://github.com/westeri/meta-acpi) at commit
  `f8276e4f58da042944c844bfa40e03adc3670425`, unchanged. MIT licence, Copyright (C) 2017
  Intel Corporation (see each file's header).
- `tables.txt`: which overlays the image compiles and loads, and the `iasl` defines that
  pick how the shared header pins are muxed.

To add hardware (a sensor, a display, SPI devices), add its `.asl` from `meta-acpi/` to
`tables.txt`. Only one table per bus segment should include `arduino.asli`.
