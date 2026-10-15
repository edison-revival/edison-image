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
        self.assertTrue(
            flash.download_succeeded(["Download done.", "Done!", "dfu-util: can't detach"])
        )
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
        self.assertEqual(
            [alt for alt, _ in plan], ["u-boot0", "u-boot-env0", "u-boot-env1", "boot", "rootfs"]
        )
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

    def test_default_images_dir_download_layout(self):
        self.make_images()
        self.assertEqual(flash.default_images_dir(self.images), self.images)

    def test_default_images_dir_source_checkout(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        self.assertEqual(flash.default_images_dir(scripts), self.tmp / "out" / "image")

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
        # The fake never disappears after a reset; don't wait long for it to.
        self.saved_reset_wait = flash.RESET_WAIT
        flash.RESET_WAIT = 0.3
        self.saved_env = dict(os.environ)
        os.environ["FAKE_DFU_LOG"] = str(self.log)

    def tearDown(self):
        flash.DFU_UTIL = self.saved_dfu
        flash.RESET_WAIT = self.saved_reset_wait
        flash.interrupted = False
        os.environ.clear()
        os.environ.update(self.saved_env)

    def run_flash(self, plan=None):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                flash.flash_all(plan or self.plan, timeout=2)
        finally:
            self.output = out.getvalue()
        return self.output

    def calls(self):
        lines = self.log.read_text().splitlines()
        return [line.split() for line in lines if "-D" in line]

    def press_ctrl_c_once_device_found(self):
        """Simulate Ctrl+C arriving just after the board appears."""
        original = flash.wait_for_device

        def wait(timeout, intro=True):
            original(timeout, intro)
            flash.interrupted = True

        flash.wait_for_device = wait
        self.addCleanup(setattr, flash, "wait_for_device", original)

    def test_output_fits_80_columns(self):
        output = self.run_flash()
        for line in output.replace("\r", "\n").splitlines():
            self.assertLessEqual(len(line), 80, line)

    def test_ctrl_c_while_waiting_writes_nothing(self):
        os.environ["FAKE_DFU_ABSENT"] = "1"
        flash.interrupted = True
        with self.assertRaises(flash.Interrupted) as cm:
            self.run_flash()
        self.assertEqual(cm.exception.args, ())
        self.assertFalse(self.log.exists() and self.calls())

    def test_ctrl_c_during_u_boot_finishes_that_write_then_stops(self):
        self.press_ctrl_c_once_device_found()
        with self.assertRaises(flash.Interrupted) as cm:
            self.run_flash()
        self.assertEqual(cm.exception.args, ("u-boot0",))
        self.assertEqual([c[c.index("-a") + 1] for c in self.calls()], ["u-boot0"])
        self.assertIn("u-boot0     done", self.output)

    def test_ctrl_c_during_rootfs_stops_dfu_util(self):
        self.press_ctrl_c_once_device_found()
        with self.assertRaises(flash.Interrupted) as cm:
            self.run_flash(plan=[self.plan[2]])
        self.assertEqual(cm.exception.args, ("rootfs",))
        self.assertIn("rootfs      interrupted", self.output)

    def test_ctrl_c_between_phases_names_the_last_written_partition(self):
        original = flash.wait_for_device

        def wait(timeout, intro=True):
            if not intro:  # the wait between phases
                flash.interrupted = True
            original(timeout, intro)

        flash.wait_for_device = wait
        self.addCleanup(setattr, flash, "wait_for_device", original)
        with self.assertRaises(flash.Interrupted) as cm:
            self.run_flash()
        self.assertEqual(cm.exception.args, ("u-boot0",))

    def test_interrupt_explanations_fit_80_columns(self):
        for alt in (None, "u-boot0", "rootfs"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                flash.explain_interrupt(alt)
            for line in out.getvalue().splitlines():
                self.assertLessEqual(len(line), 80, line)

    def test_phases_split_u_boot_from_the_rest(self):
        alts = [[alt for alt, _ in ph] for ph in flash.phases(self.plan)]
        self.assertEqual(alts, [["u-boot0"], ["boot", "rootfs"]])
        self.assertEqual(len(flash.phases(self.plan[1:])), 1)  # --only boot rootfs
        self.assertEqual(len(flash.phases(self.plan[:1])), 1)  # --only u-boot0

    def test_flashes_every_partition_resetting_after_each_phase(self):
        output = self.run_flash()
        calls = self.calls()
        self.assertEqual([c[c.index("-a") + 1] for c in calls], ["u-boot0", "boot", "rootfs"])
        # Reset after U-Boot (to apply the new layout) and after the last partition.
        self.assertEqual(["-R" in c for c in calls], [True, False, True])
        self.assertIn("Waiting for the board to come back", output)
        self.assertIn("rootfs      done", output)
        self.assertIn("overall 100%", output)
        self.assertIn("Done in", output)

    def test_missed_dfu_window_waits_and_retries(self):
        marker = self.tmp / "miss-once"
        marker.write_text("")
        os.environ["FAKE_DFU_MISS"] = str(marker)
        output = self.run_flash(plan=[self.plan[2]])
        self.assertIn("missed the DFU window, nothing written", output)
        self.assertIn("rootfs      done", output)
        self.assertEqual(len(self.calls()), 2)  # the miss, then the real write

    def test_missed_window_needs_no_progress(self):
        lost = ["dfu-util: No DFU capable USB device available"]
        progress = ["Download\t[==   ]  10%        1000 bytes"]
        self.assertTrue(flash.missed_window(lost))
        self.assertFalse(flash.missed_window(progress + lost))  # partly written: not safe
        self.assertFalse(flash.missed_window(["dfu-util: Error during download"]))

    def test_nonzero_exit_after_complete_download_is_success(self):
        # The fake exits 74 after -R, like dfu-util's "can't detach".
        self.run_flash()

    def test_failed_download_stops(self):
        os.environ["FAKE_DFU_FAIL"] = "boot"
        with self.assertRaises(SystemExit):
            self.run_flash()
        self.assertEqual(len(self.calls()), 2)  # never reached rootfs

    def test_no_device_times_out(self):
        os.environ["FAKE_DFU_ABSENT"] = "1"
        with self.assertRaises(SystemExit):
            self.run_flash()


if __name__ == "__main__":
    unittest.main()
