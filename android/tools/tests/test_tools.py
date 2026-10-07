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


if __name__ == "__main__":
    unittest.main()
