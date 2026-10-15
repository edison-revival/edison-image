#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Flash an Intel Edison over DFU: U-Boot, its environment, the kernel and the rootfs.

The IFWI is not touched. Needs dfu-util on PATH (and, on Linux, the udev rule from
edison-recovery/udev/; on Windows, the WinUSB driver for 8087:0a99).

Usage:
    uv run scripts/flash.py [--images DIR] [--uboot FILE] [--only PART ...]

--images is a local build (out/image, the default) or an extracted CI artifact / release
(which also holds u-boot.bin and a compressed rootfs.ext4.xz). --uboot defaults to
u-boot.bin in the images directory, else out/uboot/u-boot.bin.
"""

from __future__ import annotations

import argparse
import hashlib
import lzma
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEVICE = "8087:0a99"
ROOT = Path(__file__).resolve().parent.parent
DFU_UTIL = ["dfu-util"]  # command prefix; the tests point this at a fake

# DFU alt setting -> file name in the image directory (U-Boot comes from --uboot).
PARTS = [
    ("u-boot0", None),
    ("u-boot-env0", "u-boot-env.bin"),
    ("u-boot-env1", "u-boot-env.bin"),
    ("boot", "boot.vfat"),
    ("rootfs", "rootfs.ext4"),
]

# dfu-util 0.11 draws "Download\t[=====    ]  45%    123456 bytes", redrawn with \r.
PROGRESS_RE = re.compile(r"\]\s+(\d+)%\s+(\d+) bytes")


def fail(msg: str) -> None:
    print(f"\nerror: {msg}", file=sys.stderr)
    sys.exit(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def verify_checksums(images: Path) -> None:
    sums = images / "SHA256SUMS"
    if not sums.exists():
        print(f"warning: no {sums}, skipping checksum verification")
        return
    print("Verifying checksums...")
    for line in sums.read_text().splitlines():
        want, name = line.split()
        if (images / name).exists() and sha256(images / name) != want:
            fail(f"checksum mismatch for {name}")


def decompress_xz(src: Path, workdir: Path) -> Path:
    dest = workdir / src.stem  # rootfs.ext4.xz -> rootfs.ext4
    print(f"Decompressing {src.name}...")
    with lzma.open(src) as fin, dest.open("wb") as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)
    return dest


def dfu_present() -> bool:
    out = subprocess.run(
        [*DFU_UTIL, "-l", "-d", DEVICE], capture_output=True, text=True
    ).stdout
    return f"Found DFU: [{DEVICE}]" in out


def wait_for_device(timeout: int) -> None:
    print(f"Waiting up to {timeout} s for the Edison in DFU mode ({DEVICE}).")
    print("Plug in J16 (SW1 towards the micro-USB ports), then reboot the board: "
          "'sudo reboot' if it's running Linux, otherwise power-cycle it.")
    print("Avoid the reset button while Linux is running: it can wedge the Arduino "
          "kit's I/O expander until the next power cycle.")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dfu_present():
            return
        time.sleep(0.5)
    fail("no DFU device found (check the cable, SW1, and the udev rule / driver)")


def fmt_mib(n: float) -> str:
    return f"{n / 1048576:.0f} MiB" if n >= 1048576 else f"{n / 1024:.0f} KiB"


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_progress(line: str) -> tuple[int, int] | None:
    """(percent, bytes sent) from a dfu-util progress line, else None."""
    m = PROGRESS_RE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


def split_output(buf: bytes) -> tuple[list[str], bytes]:
    """Split dfu-util output on \\r or \\n; return complete lines and the remainder."""
    *lines, rest = re.split(rb"[\r\n]", buf)
    return [l.decode(errors="replace") for l in lines], rest


def download_succeeded(log: list[str]) -> bool:
    """With -R, dfu-util exits non-zero when it "can't detach" after a complete
    download; U-Boot resets anyway. Judge success by the download completing."""
    return any(l.startswith("Download done") for l in log) and any(
        l.startswith("Done!") for l in log
    )


def flash_part(alt: str, path: Path, reset: bool, done_before: int, total: int,
               start: float) -> None:
    cmd = [*DFU_UTIL, "-d", DEVICE, "-a", alt, "-D", str(path)]
    if reset:
        cmd.append("-R")
    size = path.stat().st_size
    log: list[str] = []

    def show(pct: int, sent: int) -> None:
        overall = done_before + sent
        rate = overall / max(time.monotonic() - start, 0.001)
        eta = (total - overall) / rate if rate else 0
        print(
            f"\r  {alt:<12} {pct:3d}%   "
            f"overall {overall * 100 // total:3d}%  "
            f"{fmt_mib(overall)}/{fmt_mib(total)}  "
            f"{rate / 1048576:.1f} MiB/s  ETA {fmt_time(eta)}   ",
            end="",
            flush=True,
        )

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        assert proc.stdout is not None
        buf = b""
        while chunk := proc.stdout.read1(4096):
            buf += chunk
            # dfu-util redraws the progress bar with \r; treat \r and \n alike.
            lines, buf = split_output(buf)
            for line in lines:
                log.append(line)
                if progress := parse_progress(line):
                    show(*progress)
        log.append(buf.decode(errors="replace"))

    if not download_succeeded(log):
        print()
        print("\n".join(l for l in log if l.strip()), file=sys.stderr)
        fail(f"flashing {alt} failed")
    print(f"\r  {alt:<12} done     {fmt_mib(size):>9}" + " " * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--images", type=Path, default=ROOT / "out" / "image")
    parser.add_argument("--uboot", type=Path, default=None)
    parser.add_argument("--only", nargs="+", choices=[p for p, _ in PARTS],
                        help="flash only these partitions (default: all)")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if not shutil.which(DFU_UTIL[0]):
        fail("dfu-util not found on PATH")

    verify_checksums(args.images)
    workdir = Path(tempfile.mkdtemp(prefix="edison-flash-"))
    try:
        plan = build_plan(args.images, args.uboot, args.only, workdir)
        flash_all(plan, args.timeout)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def build_plan(images: Path, uboot: Path | None, only: list[str] | None,
               workdir: Path) -> list[tuple[str, Path]]:
    """Map each DFU alt setting to the file to write, decompressing .xz if needed."""
    if uboot is None:
        uboot = images / "u-boot.bin"
        if not uboot.is_file():
            uboot = ROOT / "out" / "uboot" / "u-boot.bin"
    plan = []
    for alt, name in PARTS:
        if only and alt not in only:
            continue
        path = uboot if name is None else images / name
        if not path.is_file() and path.with_name(path.name + ".xz").is_file():
            path = decompress_xz(path.with_name(path.name + ".xz"), workdir)
        if not path.is_file():
            fail(f"missing {path}")
        plan.append((alt, path))
    return plan


def flash_all(plan: list[tuple[str, Path]], timeout: int) -> None:
    wait_for_device(timeout)

    total = sum(p.stat().st_size for _, p in plan)
    print(f"Flashing {len(plan)} partitions, {fmt_mib(total)} in total.")
    start = time.monotonic()
    done = 0
    for i, (alt, path) in enumerate(plan):
        flash_part(alt, path, reset=(i == len(plan) - 1), done_before=done,
                   total=total, start=start)
        done += path.stat().st_size

    print(f"Done in {fmt_time(time.monotonic() - start)}. "
          "The board resets and boots; first boot takes a little longer.")


if __name__ == "__main__":
    main()
