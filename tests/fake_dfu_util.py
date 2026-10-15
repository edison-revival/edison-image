"""Stand-in for dfu-util 0.11 used by the flash.py tests. No USB access.

Behaviour is controlled by environment variables:
  FAKE_DFU_ABSENT=1   -l finds no device
  FAKE_DFU_FAIL=alt   the download to this alt setting fails part-way
  FAKE_DFU_LOG=path   append each invocation's arguments to this file
"""

import os
import sys

DEVICE = "8087:0a99"


def main() -> int:
    args = sys.argv[1:]
    if log := os.environ.get("FAKE_DFU_LOG"):
        with open(log, "a") as f:
            f.write(" ".join(args) + "\n")

    if "-l" in args:
        if os.environ.get("FAKE_DFU_ABSENT") != "1":
            print(
                f"Found DFU: [{DEVICE}] ver=9999, devnum=5, cfg=1, intf=0, "
                f'path="3-1.2", alt=7, name="rootfs", serial="x"'
            )
        return 0

    alt = args[args.index("-a") + 1]
    path = args[args.index("-D") + 1]
    size = os.path.getsize(path)
    out = sys.stdout
    out.write(
        "dfu-util 0.11\nOpening DFU capable USB device...\nCopying data from PC to DFU device\n"
    )
    for pct in (0, 25, 50, 75, 100):
        if alt == os.environ.get("FAKE_DFU_FAIL") and pct == 50:
            out.write("\ndfu-util: Error during download get_status\n")
            return 74
        bar = "=" * (pct // 4)
        out.write(f"Download\t[{bar:<25}] {pct:3d}% {size * pct // 100:12d} bytes\r")
        out.flush()
    out.write("\nDownload done.\n")
    out.write("DFU state(7) = dfuMANIFEST, status(0) = No error condition is present\n")
    out.write("Done!\n")
    if "-R" in args:
        out.write("dfu-util: can't detach\nResetting USB to switch back to Run-Time mode\n")
        return 74  # real dfu-util exits non-zero here despite a complete download
    return 0


if __name__ == "__main__":
    sys.exit(main())
