"""Tests for scripts/flash.py. Standard library only: python -m unittest discover tests"""

import contextlib
import hashlib
import io
import lzma
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import flash  # noqa: E402

FAKE = [sys.executable, str(HERE / "fake_dfu_util.py")]


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


class ParsingTests(unittest.TestCase):
    def test_parse_progress_line(self):
        line = "Download\t[============             ]  48%      1234567 bytes"
        self.assertEqual(flash.parse_progress(line), (48, 1234567))

    def test_parse_progress_complete(self):
        line = "Download        [=========================] 100%    494557184 bytes"
        self.assertEqual(flash.parse_progress(line), (100, 494557184))

    def test_parse_progress_ignores_other_lines(self):
        for line in ("Download done.", "Done!", "Opening DFU capable USB device...", ""):
            self.assertIsNone(flash.parse_progress(line))

    def test_split_output_handles_carriage_returns(self):
        lines, rest = flash.split_output(b"a\rb\nc\r\npartial")
        self.assertEqual(lines, ["a", "b", "c", ""])
        self.assertEqual(rest, b"partial")

    def test_download_succeeded(self):
        self.assertTrue(flash.download_succeeded(["Download done.", "Done!"]))
        self.assertTrue(flash.download_succeeded(
            ["Download done.", "Done!", "dfu-util: can't detach"]))
        self.assertFalse(flash.download_succeeded(["Done!"]))
        self.assertFalse(flash.download_succeeded(["Download done."]))
        self.assertFalse(flash.download_succeeded([]))

    def test_formatting(self):
        self.assertEqual(flash.fmt_mib(65536), "64 KiB")
        self.assertEqual(flash.fmt_mib(494928896), "472 MiB")
        self.assertEqual(flash.fmt_time(134), "2:14")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "images"
        self.images.mkdir()
        self.work = self.tmp / "work"
        self.work.mkdir()

    def make_images(self, compressed=False, with_uboot=True):
        files = {
            "boot.vfat": b"B" * 3000,
            "u-boot-env.bin": b"E" * 1024,
        }
        rootfs = b"R" * 20000
        if compressed:
            files["rootfs.ext4.xz"] = lzma.compress(rootfs)
        else:
            files["rootfs.ext4"] = rootfs
        if with_uboot:
            files["u-boot.bin"] = b"\0" * 4096 + b"U" * 1000
        for name, data in files.items():
            write(self.images / name, data)
        sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in files.items())
        write(self.images / "SHA256SUMS", sums.encode())
        return rootfs

    def test_checksums_pass(self):
        self.make_images()
        flash.verify_checksums(self.images)

    def test_checksum_mismatch_fails(self):
        self.make_images()
        write(self.images / "boot.vfat", b"tampered")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            flash.verify_checksums(self.images)

    def test_plan_order_and_uboot_from_images_dir(self):
        self.make_images()
        plan = flash.build_plan(self.images, None, None, self.work)
        self.assertEqual([alt for alt, _ in plan],
                         ["u-boot0", "u-boot-env0", "u-boot-env1", "boot", "rootfs"])
        self.assertEqual(plan[0][1], self.images / "u-boot.bin")

    def test_plan_only(self):
        self.make_images()
        plan = flash.build_plan(self.images, None, ["rootfs"], self.work)
        self.assertEqual([alt for alt, _ in plan], ["rootfs"])

    def test_plan_decompresses_xz_rootfs(self):
        rootfs = self.make_images(compressed=True)
        plan = dict(flash.build_plan(self.images, None, None, self.work))
        self.assertEqual(plan["rootfs"].read_bytes(), rootfs)
        self.assertEqual(plan["rootfs"].parent, self.work)

    def test_plan_missing_file_fails(self):
        self.make_images()
        (self.images / "boot.vfat").unlink()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            flash.build_plan(self.images, None, None, self.work)


class FlashTests(unittest.TestCase):
    """Run flash_all against tests/fake_dfu_util.py."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "dfu.log"
        self.plan = [
            ("u-boot0", write(self.tmp / "u-boot.bin", b"U" * 5000)),
            ("boot", write(self.tmp / "boot.vfat", b"B" * 7000)),
            ("rootfs", write(self.tmp / "rootfs.ext4", b"R" * 9000)),
        ]
        self.saved_dfu = flash.DFU_UTIL
        flash.DFU_UTIL = FAKE
        self.saved_env = dict(os.environ)
        os.environ["FAKE_DFU_LOG"] = str(self.log)

    def tearDown(self):
        flash.DFU_UTIL = self.saved_dfu
        os.environ.clear()
        os.environ.update(self.saved_env)

    def run_flash(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            flash.flash_all(self.plan, timeout=2)
        return out.getvalue()

    def test_flashes_every_partition_and_resets_on_the_last(self):
        output = self.run_flash()
        calls = [l.split() for l in self.log.read_text().splitlines() if "-D" in l]
        self.assertEqual([c[c.index("-a") + 1] for c in calls], ["u-boot0", "boot", "rootfs"])
        self.assertEqual(["-R" in c for c in calls], [False, False, True])
        self.assertIn("rootfs       done", output)
        self.assertIn("overall 100%", output)
        self.assertIn("Done in", output)

    def test_nonzero_exit_after_complete_download_is_success(self):
        # The fake exits 74 after -R, like dfu-util's "can't detach".
        self.run_flash()

    def test_failed_download_stops(self):
        os.environ["FAKE_DFU_FAIL"] = "boot"
        with self.assertRaises(SystemExit):
            self.run_flash()
        calls = [l for l in self.log.read_text().splitlines() if "-D" in l]
        self.assertEqual(len(calls), 2)  # never reached rootfs

    def test_no_device_times_out(self):
        os.environ["FAKE_DFU_ABSENT"] = "1"
        with self.assertRaises(SystemExit):
            self.run_flash()


if __name__ == "__main__":
    unittest.main()
