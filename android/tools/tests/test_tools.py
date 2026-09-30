"""Unit tests for android.tools — no adb/emulator/device required."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest import mock

from android.tools import adb, gradle, metavr_bridge
from android.tools.adb import DeviceUnavailable
from android.tools.cli import build_parser, main


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


class GradleModuleTaskTests(unittest.TestCase):
    def test_module_task_simple_name(self) -> None:
        self.assertEqual(gradle.module_task("app"), ":app:test")

    def test_module_task_nested_path(self) -> None:
        self.assertEqual(gradle.module_task("android/app"), ":android:app:test")

    def test_module_task_already_colon_prefixed(self) -> None:
        self.assertEqual(gradle.module_task(":android:app"), ":android:app:test")

    def test_unit_test_passes_module_as_gradle_task_not_bare_path(self) -> None:
        fake_wrapper = Path("/repo/android/gradlew")
        fake_proc = mock.Mock(returncode=0, stdout="BUILD SUCCESSFUL", stderr="")
        with mock.patch("android.tools.gradle.find_gradlew", return_value=fake_wrapper):
            with mock.patch(
                "android.tools.gradle.subprocess.run", return_value=fake_proc
            ) as run:
                gradle.unit_test(module="android/app")
        argv = run.call_args.args[0]
        self.assertEqual(argv, [str(fake_wrapper), ":android:app:test"])
        # The raw filesystem path must never appear as its own gradle arg.
        self.assertNotIn("android/app", argv)

    def test_unit_test_gradle_args_accepts_flag_like_values(self) -> None:
        parsed = build_parser().parse_args(
            ["unit_test", "--module", "app", "--gradle-args", "--offline", "--stacktrace"]
        )
        self.assertEqual(parsed.gradle_args, ["--offline", "--stacktrace"])

    def test_cli_unit_test_forwards_offline_flag_to_gradlew(self) -> None:
        fake_wrapper = Path("/repo/android/gradlew")
        fake_proc = mock.Mock(returncode=0, stdout="BUILD SUCCESSFUL", stderr="")
        with mock.patch("android.tools.gradle.find_gradlew", return_value=fake_wrapper):
            with mock.patch(
                "android.tools.gradle.subprocess.run", return_value=fake_proc
            ) as run:
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main(
                        ["unit_test", "--module", "app", "--gradle-args", "--offline"]
                    )
        self.assertEqual(code, 0)
        argv = run.call_args.args[0]
        self.assertIn("--offline", argv)


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


class MetaVRRealDetectionTests(unittest.TestCase):
    """The connection flag must reflect a real adb query, not a hardcoded
    False — so bridge calls can actually succeed once a device is present."""

    def tearDown(self) -> None:
        metavr_bridge.reset_device_override()

    def test_no_override_checks_adb_devices_and_succeeds_when_connected(self) -> None:
        fake_proc = mock.Mock(
            returncode=0,
            stdout=SAMPLE_DEVICES,  # includes emulator-5554 in "device" state
        )
        with mock.patch("android.tools.adb.run_adb", return_value=fake_proc):
            tid = metavr_bridge.screenshot(out="/tmp/x.png")
        self.assertEqual(tid, "device_screenshot")

    def test_no_override_raises_when_adb_reports_no_device_state(self) -> None:
        fake_proc = mock.Mock(returncode=0, stdout="List of devices attached\n")
        with mock.patch("android.tools.adb.run_adb", return_value=fake_proc):
            with self.assertRaises(DeviceUnavailable):
                metavr_bridge.screenshot(out="/tmp/x.png")

    def test_serial_filter_only_matches_that_serial_in_device_state(self) -> None:
        fake_proc = mock.Mock(returncode=0, stdout=SAMPLE_DEVICES)
        with mock.patch("android.tools.adb.run_adb", return_value=fake_proc):
            # emulator-5554 is "device"; the other serial is "unauthorized".
            tid = metavr_bridge.screenshot(serial="emulator-5554", out="/tmp/x.png")
            self.assertEqual(tid, "device_screenshot")
            with self.assertRaises(DeviceUnavailable):
                metavr_bridge.screenshot(serial="0123456789ABCDEF", out="/tmp/x.png")

    def test_missing_adb_binary_is_treated_as_no_device_not_an_error(self) -> None:
        with mock.patch(
            "android.tools.adb.run_adb",
            side_effect=DeviceUnavailable("missing binary: adb"),
        ):
            with self.assertRaises(DeviceUnavailable):
                metavr_bridge.screenshot(out="/tmp/x.png")


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


class CliNonzeroAdbIsARealFailureTests(unittest.TestCase):
    """A nonzero adb return code is a real failure and must not be reported
    as a skip / exit 0 success."""

    def test_install_apk_nonzero_returncode_is_nonzero_exit_not_skip(self) -> None:
        fake_proc = mock.Mock(returncode=1, stdout="", stderr="INSTALL_FAILED_X")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake_proc):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["install_apk", "--apk", "/tmp/app.apk"])
        self.assertEqual(code, 1)
        self.assertNotIn("skipped:", err.getvalue())
        self.assertIn("INSTALL_FAILED_X", err.getvalue())

    def test_instrumented_run_nonzero_returncode_is_nonzero_exit_not_skip(self) -> None:
        fake_proc = mock.Mock(returncode=3, stdout="", stderr="instrumentation crashed")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake_proc):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["instrumented_run", "--class", "pkg.Test"])
        self.assertEqual(code, 3)
        self.assertNotIn("skipped:", err.getvalue())

    def test_screenshot_nonzero_returncode_is_nonzero_exit_not_skip(self) -> None:
        fake_proc = mock.Mock(returncode=1, stdout=b"", stderr=b"no devices")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch("android.tools.cli.subprocess.run", return_value=fake_proc):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = main(["screenshot", "--out", "/tmp/x.png"])
        self.assertEqual(code, 1)
        self.assertNotIn("skipped:", err.getvalue())


class CliLogcatCaptureTests(unittest.TestCase):
    def test_failed_dump_does_not_overwrite_out_file(self) -> None:
        out_path = Path("/tmp/spe5160-logcat-existing.txt")
        out_path.write_text("previous good log\n", encoding="utf-8")
        try:
            fake_proc = mock.Mock(returncode=1, stdout="", stderr="adb server died")
            with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
                with mock.patch(
                    "android.tools.cli.subprocess.run", return_value=fake_proc
                ):
                    with mock.patch("sys.stderr", new_callable=io.StringIO):
                        code = main(
                            ["logcat_capture", "--out", str(out_path)]
                        )
            self.assertNotEqual(code, 0)
            # The previously written good log must survive a failed capture.
            self.assertEqual(out_path.read_text(encoding="utf-8"), "previous good log\n")
        finally:
            out_path.unlink(missing_ok=True)

    def test_dump_mode_used_when_seconds_is_zero(self) -> None:
        fake_proc = mock.Mock(returncode=0, stdout="line1\n", stderr="")
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch(
                "android.tools.cli.subprocess.run", return_value=fake_proc
            ) as run:
                with mock.patch("android.tools.cli.subprocess.Popen") as popen:
                    with mock.patch("sys.stdout", new_callable=io.StringIO):
                        code = main(
                            ["logcat_capture", "--out", "/tmp/spe5160-dump.txt"]
                        )
        self.assertEqual(code, 0)
        popen.assert_not_called()
        self.assertIn("-d", run.call_args.args[0])

    def test_seconds_triggers_live_capture_for_the_requested_duration(self) -> None:
        fake_proc = mock.Mock()
        fake_proc.communicate.return_value = ("captured output\n", "")
        fake_proc.returncode = 0
        with mock.patch("android.tools.adb.which_or_raise", return_value="adb"):
            with mock.patch(
                "android.tools.cli.subprocess.Popen", return_value=fake_proc
            ) as popen:
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main(
                        [
                            "logcat_capture",
                            "--out",
                            "/tmp/spe5160-timed.txt",
                            "--seconds",
                            "3",
                        ]
                    )
        self.assertEqual(code, 0)
        argv = popen.call_args.args[0]
        self.assertNotIn("-d", argv)  # live stream, not a one-shot dump
        fake_proc.communicate.assert_called_once_with(timeout=3)


class CliEmuBootReadinessTests(unittest.TestCase):
    def test_process_that_exits_immediately_is_reported_as_failure(self) -> None:
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = 1
        fake_proc.returncode = 1
        with mock.patch("android.tools.adb.which_or_raise", return_value="emulator"):
            with mock.patch(
                "android.tools.cli.subprocess.Popen", return_value=fake_proc
            ):
                with mock.patch("android.tools.cli.time.sleep"):
                    with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                        code = main(["emu_boot", "--avd", "Pixel_7_API_34"])
        self.assertEqual(code, 1)
        self.assertNotIn("skipped:", err.getvalue())
        self.assertIn("exited early", err.getvalue())

    def test_process_still_alive_after_check_window_is_reported_as_started(self) -> None:
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None  # still running
        fake_proc.pid = 4242
        with mock.patch("android.tools.adb.which_or_raise", return_value="emulator"):
            with mock.patch(
                "android.tools.cli.subprocess.Popen", return_value=fake_proc
            ):
                with mock.patch("android.tools.cli.time.sleep"):
                    with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                        code = main(["emu_boot", "--avd", "Pixel_7_API_34"])
        self.assertEqual(code, 0)
        self.assertIn("started", out.getvalue())
        self.assertGreater(fake_proc.poll.call_count, 1)


if __name__ == "__main__":
    unittest.main()
