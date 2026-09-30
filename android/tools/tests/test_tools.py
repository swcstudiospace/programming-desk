"""Unit tests for android.tools — no adb/emulator/device required."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest import mock

from android.tools import adb, gradle, metavr_bridge
from android.tools.adb import DeviceUnavailable
from android.tools.cli import main


SAMPLE_DEVICES = """\
List of devices attached
emulator-5554          device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a transport_id:1
0123456789ABCDEF       unauthorized transport_id:2
"""


class DryRunArgvTests(unittest.TestCase):
    def test_emu_boot_dry_run_builds_argv_and_does_not_spawn(self) -> None:
        with mock.patch("android.tools.cli.subprocess.Popen") as popen:
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["emu_boot", "--avd", "Pixel_7_API_34", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "emulator -avd Pixel_7_API_34")
        popen.assert_not_called()
        self.assertEqual(
            adb.emu_boot_argv("Pixel_7_API_34"),
            ["emulator", "-avd", "Pixel_7_API_34"],
        )

    def test_install_apk_dry_run_with_serial(self) -> None:
        with mock.patch("android.tools.cli.subprocess.run") as run:
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(
                    [
                        "install_apk",
                        "--apk",
                        "/tmp/app.apk",
                        "--serial",
                        "emulator-5554",
                        "--dry-run",
                    ]
                )
        self.assertEqual(code, 0)
        self.assertEqual(
            out.getvalue().strip(),
            "adb -s emulator-5554 install -r /tmp/app.apk",
        )
        run.assert_not_called()

    def test_install_apk_dry_run_without_serial(self) -> None:
        argv = adb.install_apk_argv("/tmp/app.apk", serial=None)
        self.assertEqual(argv, ["adb", "install", "-r", "/tmp/app.apk"])


class AdbParseTests(unittest.TestCase):
    def test_parse_adb_devices_l_sample(self) -> None:
        devices = adb.parse_adb_devices(SAMPLE_DEVICES)
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].serial, "emulator-5554")
        self.assertEqual(devices[0].state, "device")
        self.assertEqual(devices[0].extras.get("model"), "sdk_gphone64_arm64")
        self.assertEqual(devices[1].serial, "0123456789ABCDEF")
        self.assertEqual(devices[1].state, "unauthorized")

    def test_adb_devices_json_uses_parser(self) -> None:
        fake = mock.Mock(returncode=0, stdout=SAMPLE_DEVICES, stderr="")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.adb.subprocess.run", return_value=fake):
                text = adb.adb_devices_list(as_json=True)
        payload = json.loads(text)
        self.assertEqual(payload[0]["serial"], "emulator-5554")


class GradleSkipTests(unittest.TestCase):
    def test_unit_test_skips_when_gradlew_absent(self) -> None:
        with mock.patch("android.tools.gradle.find_gradlew", return_value=None):
            code, out = gradle.unit_test(module="app")
        self.assertEqual(code, 0)
        self.assertIn("skipped: no gradlew found", out)

    def test_cli_unit_test_skip(self) -> None:
        with mock.patch("android.tools.gradle.find_gradlew", return_value=None):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["unit_test", "--module", "app"])
        self.assertEqual(code, 0)
        self.assertIn("skipped: no gradlew found", out.getvalue())


class MetaVRBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        metavr_bridge.set_device_connected(False)

    def tearDown(self) -> None:
        metavr_bridge.set_device_connected(False)

    def test_screenshot_resolves_device_screenshot_and_raises(self) -> None:
        self.assertEqual(metavr_bridge.tool_id("screenshot"), "device_screenshot")
        with self.assertRaises(DeviceUnavailable) as ctx:
            metavr_bridge.screenshot(out="/tmp/x.png")
        self.assertIn("device_screenshot", str(ctx.exception))

    def test_logcat_resolves_device_logcat_and_raises(self) -> None:
        self.assertEqual(metavr_bridge.tool_id("logcat"), "device_logcat")
        with self.assertRaises(DeviceUnavailable) as ctx:
            metavr_bridge.logcat(out="/tmp/log.txt", seconds=1)
        self.assertIn("device_logcat", str(ctx.exception))

    def test_ui_dump_maps_to_ui_dump(self) -> None:
        self.assertEqual(metavr_bridge.tool_id("ui_dump"), "ui_dump")
        with self.assertRaises(DeviceUnavailable) as ctx:
            metavr_bridge.ui_dump(out="/tmp/ui.xml")
        self.assertIn("ui_dump", str(ctx.exception))

    def test_ui_tap_rejects_missing_target(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            metavr_bridge.ui_tap()
        self.assertIn("resource-id", str(ctx.exception).lower())

    def test_ui_tap_with_text_raises_without_device(self) -> None:
        with self.assertRaises(DeviceUnavailable) as ctx:
            metavr_bridge.ui_tap(text="OK")
        self.assertIn("ui_tap", str(ctx.exception))

    def test_cli_metavr_screenshot_skips_without_device(self) -> None:
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = main(
                [
                    "screenshot",
                    "--out",
                    "/tmp/spe5160-shot.png",
                    "--backend",
                    "metavr",
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("skipped:"))
        self.assertIn("device_screenshot", out.getvalue())


class CliSkipOnMissingBinary(unittest.TestCase):
    def test_adb_devices_skips_when_adb_missing(self) -> None:
        with mock.patch(
            "android.tools.adb.which_or_raise",
            side_effect=DeviceUnavailable("missing binary: adb"),
        ):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["adb_devices"])
        self.assertEqual(code, 0)
        self.assertIn("skipped:", out.getvalue())


class AdbFailureClassificationTests(unittest.TestCase):
    """Greptile P1: a real command failure on a connected device must be
    reported, not swallowed as the documented missing-device skip."""

    def test_missing_device_error_detected(self) -> None:
        self.assertTrue(adb.is_missing_device_error("error: no devices/emulators found"))
        self.assertTrue(adb.is_missing_device_error("error: device offline"))

    def test_real_failure_is_not_classified_as_missing_device(self) -> None:
        self.assertFalse(adb.is_missing_device_error("INSTALL_FAILED_INSUFFICIENT_STORAGE"))

    def test_install_apk_real_failure_is_reported_not_skipped(self) -> None:
        fake = mock.Mock(returncode=1, stdout="", stderr="Failure [INSTALL_FAILED_INVALID_APK]")
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["install_apk", "--apk", "/tmp/app.apk"])
        self.assertEqual(code, 1)
        self.assertIn("error: install failed", err.getvalue())

    def test_install_apk_missing_device_still_skips(self) -> None:
        fake = mock.Mock(returncode=1, stdout="", stderr="error: no devices/emulators found")
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["install_apk", "--apk", "/tmp/app.apk"])
        self.assertEqual(code, 0)
        self.assertIn("skipped:", out.getvalue())

    def test_screenshot_real_failure_is_reported_not_skipped(self) -> None:
        fake = mock.Mock(returncode=1, stdout=b"", stderr=b"screencap: permission denied")
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["screenshot", "--out", "/tmp/s.png"])
        self.assertEqual(code, 1)
        self.assertIn("error: screencap failed", err.getvalue())

    def test_instrumented_run_real_failure_is_reported_not_skipped(self) -> None:
        fake = mock.Mock(returncode=1, stdout="", stderr="INSTRUMENTATION_FAILED")
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["instrumented_run", "--class", "pkg.Test"])
        self.assertEqual(code, 1)
        self.assertIn("error: instrument failed", err.getvalue())


class LogcatCaptureTests(unittest.TestCase):
    def test_dry_run_reports_argv(self) -> None:
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = main(["logcat_capture", "--out", "/tmp/l.txt", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "adb logcat -d")

    def test_timed_dry_run_uses_streaming_argv(self) -> None:
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = main(
                ["logcat_capture", "--out", "/tmp/l.txt", "--seconds", "30", "--dry-run"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "adb logcat")

    def test_timed_capture_uses_streaming_window_not_dump(self) -> None:
        with mock.patch(
            "android.tools.cli.adb.which_or_raise", return_value="adb"
        ), mock.patch(
            "android.tools.cli.adb.capture_logcat_for",
            return_value=("line1\nline2\n", 0, ""),
        ) as captured, mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ), mock.patch.object(
            Path, "write_text"
        ) as write_text:
            code = main(
                ["logcat_capture", "--out", "/tmp/l.txt", "--seconds", "5"]
            )
        self.assertEqual(code, 0)
        captured.assert_called_once()
        self.assertEqual(captured.call_args.args[0], 5)
        write_text.assert_called_once_with("line1\nline2\n", encoding="utf-8")

    def test_failed_capture_does_not_overwrite_out_file(self) -> None:
        with mock.patch(
            "android.tools.cli.adb.which_or_raise", return_value="adb"
        ), mock.patch(
            "android.tools.cli.adb.capture_logcat_for",
            return_value=("", 1, "device offline"),
        ), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ), mock.patch.object(
            Path, "write_text"
        ) as write_text:
            code = main(["logcat_capture", "--out", "/tmp/l.txt", "--seconds", "5"])
        self.assertEqual(code, 0)  # missing-device classification -> skip
        write_text.assert_not_called()

    def test_failed_capture_real_error_is_reported_not_skipped(self) -> None:
        with mock.patch(
            "android.tools.cli.adb.which_or_raise", return_value="adb"
        ), mock.patch(
            "android.tools.cli.adb.capture_logcat_for",
            return_value=("", 1, "permission denied"),
        ), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as err, mock.patch.object(
            Path, "write_text"
        ) as write_text:
            code = main(["logcat_capture", "--out", "/tmp/l.txt", "--seconds", "5"])
        self.assertEqual(code, 1)
        self.assertIn("error: logcat failed", err.getvalue())
        write_text.assert_not_called()


class GradleModuleTaskTests(unittest.TestCase):
    def test_module_path_becomes_scoped_project_task(self) -> None:
        self.assertEqual(gradle.module_test_task("android/app"), ":android:app:test")
        self.assertEqual(gradle.module_test_task("app"), ":app:test")

    def test_unit_test_passes_single_scoped_task_not_raw_path(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch(
            "android.tools.gradle.find_gradlew", return_value=Path("/repo/android/gradlew")
        ):
            with mock.patch("android.tools.gradle.subprocess.run", side_effect=fake_run):
                gradle.unit_test(module="android/app")
        self.assertEqual(
            captured["argv"], ["/repo/android/gradlew", ":android:app:test"]
        )

    def test_gradle_args_with_leading_dash_are_forwarded(self) -> None:
        with mock.patch("android.tools.gradle.find_gradlew", return_value=None):
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code = main(
                    ["unit_test", "--gradle-args", "--offline", "--stacktrace"]
                )
        self.assertEqual(code, 0)  # still skips cleanly without a wrapper present


class MetaVRAutoDetectTests(unittest.TestCase):
    def tearDown(self) -> None:
        metavr_bridge.set_device_connected(None)

    def test_auto_detect_true_when_adb_reports_connected_device(self) -> None:
        fake = mock.Mock(returncode=0, stdout=SAMPLE_DEVICES, stderr="")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.adb.subprocess.run", return_value=fake):
                metavr_bridge.set_device_connected(None)
                self.assertTrue(metavr_bridge.is_device_connected())

    def test_auto_detect_false_when_adb_missing(self) -> None:
        with mock.patch(
            "android.tools.adb.which_or_raise",
            side_effect=DeviceUnavailable("missing binary: adb"),
        ):
            metavr_bridge.set_device_connected(None)
            self.assertFalse(metavr_bridge.is_device_connected())

    def test_explicit_override_wins_over_auto_detect(self) -> None:
        fake = mock.Mock(returncode=0, stdout=SAMPLE_DEVICES, stderr="")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.adb.subprocess.run", return_value=fake):
                metavr_bridge.set_device_connected(False)
                self.assertFalse(metavr_bridge.is_device_connected())


class EmuBootReadinessTests(unittest.TestCase):
    def test_emu_boot_reports_early_exit_as_failure(self) -> None:
        proc = mock.Mock()
        proc.poll.return_value = 1
        proc.stderr = io.StringIO("Failed to find AVD 'missing_avd'\n")
        proc.pid = 4242
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="emulator"):
            with mock.patch("android.tools.cli.subprocess.Popen", return_value=proc):
                with mock.patch("android.tools.cli.time.sleep"):
                    with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                        code = main(
                            ["emu_boot", "--avd", "missing_avd", "--timeout-sec", "1"]
                        )
        self.assertEqual(code, 0)  # skip convention, but reports the real reason
        self.assertIn("emulator exited early", out.getvalue())
        self.assertIn("missing_avd", out.getvalue())

    def test_emu_boot_reports_running_process_as_started(self) -> None:
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 4242
        with mock.patch("android.tools.cli.adb.which_or_raise", return_value="emulator"):
            with mock.patch("android.tools.cli.subprocess.Popen", return_value=proc):
                with mock.patch("android.tools.cli.time.monotonic", side_effect=[0, 0, 10]):
                    with mock.patch("android.tools.cli.time.sleep"):
                        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                            code = main(
                                ["emu_boot", "--avd", "Pixel_7_API_34", "--timeout-sec", "1"]
                            )
        self.assertEqual(code, 0)
        self.assertIn("emulator started", out.getvalue())


if __name__ == "__main__":
    unittest.main()
