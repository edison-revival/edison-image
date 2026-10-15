#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Flash an Intel Edison over DFU: U-Boot, its environment, kernel and rootfs.

The IFWI is not touched. Needs dfu-util on PATH (and, on Linux, the udev rule
from edison-recovery/udev/; on Windows, the WinUSB driver for 8087:0a99).

Usage:
    uv run scripts/flash.py [--images DIR] [--uboot FILE] [--only PART ...]

--images is a local build (out/image, the default) or an extracted CI
artifact or release, which also holds u-boot.bin and rootfs.ext4.xz.
--uboot defaults to u-boot.bin in the images directory, else
out/uboot/u-boot.bin.
"""

from __future__ import annotations

import argparse
import hashlib
import lzma
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEVICE = "8087:0a99"
ROOT = Path(__file__).resolve().parent.parent
DFU_UTIL = ["dfu-util"]  # command prefix; the tests point this at a fake
WIDTH = 79  # keep output within 80 columns

# DFU alt setting -> file in the image directory (U-Boot comes from --uboot).
PARTS = [
    ("u-boot0", None),
    ("u-boot-env0", "u-boot-env.bin"),
    ("u-boot-env1", "u-boot-env.bin"),
    ("boot", "boot.vfat"),
    ("rootfs", "rootfs.ext4"),
]
# Interrupting these could leave the board unable to boot (then only
# edison-recovery can fix it). They take well under a second, so Ctrl+C waits.
CRITICAL = {"u-boot0", "u-boot-env0", "u-boot-env1"}

# dfu-util 0.11 draws "Download\t[====   ]  45%   123456 bytes", redrawn with \r.
PROGRESS_RE = re.compile(r"\]\s+(\d+)%\s+(\d+) bytes")


class Interrupted(Exception):
    pass


interrupted = False


def on_sigint(signum, frame) -> None:
    global interrupted
    if interrupted:  # second Ctrl+C: give up waiting
        raise KeyboardInterrupt
    interrupted = True


def say(*lines: str) -> None:
    for line in lines:
        print(line)


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
        say(f"warning: no {sums}, skipping checksum verification")
        return
    say("Verifying checksums...")
    for line in sums.read_text().splitlines():
        want, name = line.split()
        if (images / name).exists() and sha256(images / name) != want:
            fail(f"checksum mismatch for {name}")


def decompress_xz(src: Path, workdir: Path) -> Path:
    dest = workdir / src.stem  # rootfs.ext4.xz -> rootfs.ext4
    say(f"Decompressing {src.name}...")
    with lzma.open(src) as fin, dest.open("wb") as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)
    return dest


def dfu_present() -> bool:
    out = subprocess.run([*DFU_UTIL, "-l", "-d", DEVICE], capture_output=True, text=True).stdout
    return f"Found DFU: [{DEVICE}]" in out


def wait_for_device(timeout: int) -> None:
    say(
        f"Waiting up to {timeout} s for the Edison in DFU mode ({DEVICE}).",
        "Plug in J16 (SW1 towards the micro-USB ports), then reboot the board:",
        "  'sudo reboot' if it runs Linux, otherwise power-cycle it.",
        "Avoid the reset button while Linux runs: it can wedge the Arduino",
        "kit's I/O expander until the next power cycle.",
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if interrupted:
            raise Interrupted
        if dfu_present():
            return
        time.sleep(0.5)
    fail("no DFU device found (check the cable, SW1, udev rule or driver)")


def fmt_mib(n: float) -> str:
    return f"{n / 1048576:.0f} MiB" if n >= 1048576 else f"{n / 1024:.0f} KiB"


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def status(text: str, end: str = "") -> None:
    """Redraw the current status line, padded/cut to the output width."""
    print("\r" + text[:WIDTH].ljust(WIDTH), end=end, flush=True)


def parse_progress(line: str) -> tuple[int, int] | None:
    """(percent, bytes sent) from a dfu-util progress line, else None."""
    m = PROGRESS_RE.search(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


def split_output(buf: bytes) -> tuple[list[str], bytes]:
    """Split dfu-util output on \\r or \\n; return lines and the rest."""
    *lines, rest = re.split(rb"[\r\n]", buf)
    return [line.decode(errors="replace") for line in lines], rest


def download_succeeded(log: list[str]) -> bool:
    """With -R, dfu-util exits non-zero when it "can't detach" after a
    complete download; U-Boot resets anyway. Judge success by the download
    completing."""
    return any(line.startswith("Download done") for line in log) and any(
        line.startswith("Done!") for line in log
    )


def own_process_group() -> dict:
    """Popen options so Ctrl+C reaches only us, not dfu-util."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def flash_part(
    alt: str, path: Path, reset: bool, done_before: int, total: int, start: float
) -> None:
    cmd = [*DFU_UTIL, "-d", DEVICE, "-a", alt, "-D", str(path)]
    if reset:
        cmd.append("-R")
    size = path.stat().st_size
    log: list[str] = []
    noted = False

    def show(pct: int, sent: int) -> None:
        overall = done_before + sent
        rate = overall / max(time.monotonic() - start, 0.001)
        eta = (total - overall) / rate if rate else 0
        status(
            f"  {alt:<12}{pct:4d}%  overall {overall * 100 // total:3d}%  "
            f"{fmt_mib(overall)}/{fmt_mib(total)}  "
            f"{rate / 1048576:.1f} MiB/s  ETA {fmt_time(eta)}"
        )

    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **own_process_group()
    ) as proc:
        assert proc.stdout is not None
        buf = b""
        while chunk := proc.stdout.read1(4096):
            if interrupted and alt not in CRITICAL:
                proc.terminate()
                proc.wait()
                status(f"  {alt:<12}interrupted", end="\n")
                raise Interrupted(alt)
            if interrupted and not noted:
                status(f"  {alt:<12}Ctrl+C: finishing this small write first", end="\n")
                noted = True
            buf += chunk
            # dfu-util redraws its progress bar with \r; treat \r, \n alike.
            lines, buf = split_output(buf)
            for line in lines:
                log.append(line)
                if progress := parse_progress(line):
                    show(*progress)
        log.append(buf.decode(errors="replace"))

    if not download_succeeded(log):
        print()
        print("\n".join(line for line in log if line.strip()), file=sys.stderr)
        fail(f"flashing {alt} failed")
    status(f"  {alt:<12}done  {fmt_mib(size):>9}", end="\n")


def flash_all(plan: list[tuple[str, Path]], timeout: int) -> None:
    wait_for_device(timeout)

    total = sum(p.stat().st_size for _, p in plan)
    say(f"Flashing {len(plan)} partitions, {fmt_mib(total)} in total. Ctrl+C to stop.")
    start = time.monotonic()
    done = 0
    for i, (alt, path) in enumerate(plan):
        flash_part(
            alt, path, reset=(i == len(plan) - 1), done_before=done, total=total, start=start
        )
        done += path.stat().st_size
        if interrupted and i < len(plan) - 1:
            raise Interrupted(alt)

    say(f"Done in {fmt_time(time.monotonic() - start)}. The board now resets and boots.")


def build_plan(
    images: Path, uboot: Path | None, only: list[str] | None, workdir: Path
) -> list[tuple[str, Path]]:
    """Map each DFU alt setting to its file, decompressing .xz if needed."""
    if uboot is None:
        uboot = images / "u-boot.bin"
        if not uboot.is_file():
            uboot = ROOT / "out" / "uboot" / "u-boot.bin"
    plan = []
    for alt, name in PARTS:
        if only and alt not in only:
            continue
        path = uboot if name is None else images / name
        xz = path.with_name(path.name + ".xz")
        if not path.is_file() and xz.is_file():
            path = decompress_xz(xz, workdir)
        if not path.is_file():
            fail(f"missing {path}")
        plan.append((alt, path))
    return plan


def explain_interrupt(alt: str | None) -> None:
    if alt is None:
        say("\nCancelled before writing anything.")
    elif alt in CRITICAL:
        say(
            f"\nStopped after {alt}. U-Boot and its settings are intact, but",
            "the image is incomplete: run flash.py again.",
        )
    else:
        say(
            f"\nStopped during {alt}, so it is incomplete. U-Boot is intact",
            "and opens DFU on every boot: run flash.py again and reboot.",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--images", type=Path, default=ROOT / "out" / "image")
    parser.add_argument("--uboot", type=Path, default=None)
    parser.add_argument(
        "--only",
        nargs="+",
        choices=[p for p, _ in PARTS],
        help="flash only these partitions (default: all)",
    )
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if not shutil.which(DFU_UTIL[0]):
        fail("dfu-util not found on PATH")

    signal.signal(signal.SIGINT, on_sigint)
    workdir = Path(tempfile.mkdtemp(prefix="edison-flash-"))
    try:
        verify_checksums(args.images)
        plan = build_plan(args.images, args.uboot, args.only, workdir)
        flash_all(plan, args.timeout)
    except Interrupted as e:
        explain_interrupt(e.args[0] if e.args else None)
        sys.exit(130)
    except KeyboardInterrupt:
        say("\nAborted.")
        sys.exit(130)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
