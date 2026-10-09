"""Verification-harness commands. No host adb, emulator, maestro, or /dev/kvm required."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from android.tools import accel_check, maestro_flow, screenrecord
from android.tools.adb import DeviceUnavailable
from android.tools.cli import main

SERIAL = "emulator-5554"

ADB_BODY = """
import os, sys
log = os.environ.get("ADB_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(" ".join(sys.argv) + "\\n")
args = sys.argv[1:]
if args[:1] == ["-s"]:
    args = args[2:]
if args == ["devices", "-l"]:
    serial = os.environ.get("ADB_FAKE_SERIAL", "emulator-5554")
    state = os.environ.get("ADB_FAKE_STATE", "device")
    if os.environ.get("ADB_FAKE_NONE") == "1":
        sys.stdout.write("List of devices attached\\n")
    else:
        sys.stdout.write(f"List of devices attached\\n{serial} {state}\\n")
    sys.exit(0)
if len(args) >= 2 and args[0] == "shell" and args[1] == "screenrecord":
    if "--time-limit" not in args:
        sys.stderr.write("missing --time-limit\\n")
        sys.exit(2)
    limit = args[args.index("--time-limit") + 1]
    if int(limit) > 180:
        sys.stderr.write("time-limit over 180\\n")
        sys.exit(2)
    sys.exit(int(os.environ.get("ADB_SCREENRECORD_EXIT", "0")))
if args[:1] == ["pull"] and len(args) >= 3:
    mode = os.environ.get("ADB_PULL_MODE", "write")
    if mode != "missing":
        with open(args[2], "wb") as fh:
            if mode != "empty":
                fh.write(b"fake-screenrecord")
    sys.exit(int(os.environ.get("ADB_PULL_EXIT", "0")))
if args[:2] == ["shell", "rm"] and len(args) == 3:
    remote = args[2]
    if remote.startswith("/sdcard/desk-screenrecord-") and remote.endswith(".mp4"):
        sys.exit(int(os.environ.get("ADB_RM_EXIT", "0")))
    sys.stderr.write("unexpected rm\\n")
    sys.exit(2)
sys.stderr.write("unexpected adb args: %s\\n" % args)
sys.exit(99)
"""

MAESTRO_BODY = """
import os, sys
log = os.environ.get("MAESTRO_ARGV_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("\\n".join(sys.argv) + "\\n---\\n")
if "--output" not in sys.argv or "--debug-output" not in sys.argv:
    sys.stderr.write("missing output flags\\n")
    sys.exit(2)
if not os.path.exists(sys.argv[-1]):
    sys.stderr.write("flow not found from Maestro cwd\\n")
    sys.exit(2)
out = sys.argv[sys.argv.index("--output") + 1]
debug = sys.argv[sys.argv.index("--debug-output") + 1]
os.makedirs(debug, exist_ok=True)
with open(os.path.join(debug, "marker.txt"), "w", encoding="utf-8") as fh:
    fh.write("debug")
mode = os.environ.get("MAESTRO_FAKE_RESULT", "fail")
if mode == "missing-xml":
    sys.exit(int(os.environ.get("MAESTRO_EXIT", "1")))
failures = "1" if mode == "fail" else "0"
inner = '<failure message="assertVisible">nope</failure>' if mode == "fail" else ""
body = (
    '<?xml version="1.0" encoding="UTF-8"?>\\n'
    '<testsuite name="flow" tests="1" failures="%s" errors="0">\\n'
    '  <testcase name="Login">%s</testcase>\\n'
    '</testsuite>\\n'
) % (failures, inner)
with open(out, "w", encoding="utf-8") as fh:
    fh.write(os.environ.get("MAESTRO_FAKE_XML", body))
sys.exit(0 if mode != "crash" else 2)
"""

EMULATOR_BODY = """
import os, sys
log = os.environ.get("EMULATOR_ARGV_LOG")
if log:
    with open(log, "w", encoding="utf-8") as fh:
        fh.write("\\n".join(sys.argv))
if "-avd" in sys.argv or len(sys.argv) != 2 or sys.argv[1] != "-accel-check":
    sys.stderr.write("refusing argv %s\\n" % sys.argv)
    sys.exit(9)
sys.stdout.write(os.environ.get("EMULATOR_ACCEL_STDOUT", "KVM is installed and usable.\\n"))
sys.exit(int(os.environ.get("EMULATOR_ACCEL_EXIT", "0")))
"""


def write_exe(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class IsolatedCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.out = self.root / "out"
        self.argv_log = self.root / "argv.log"
        self.addCleanup(self._tmp.cleanup)

    def path_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {"PATH": str(self.bin), "ADB_ARGV_LOG": str(self.argv_log)}
        if extra:
            env.update(extra)
        return env

    def install(self, name: str, body: str) -> None:
        write_exe(self.bin / name, body)


class AccelCheckTests(IsolatedCase):
    def test_default_kvm_path_is_dev_kvm(self) -> None:
        self.assertEqual(accel_check.KVM_PATH, Path("/dev/kvm"))

    def test_missing_node_and_missing_emulator_is_no_emulator(self) -> None:
        missing = self.root / "no-kvm"
        with mock.patch.object(accel_check, "KVM_PATH", missing):
            with mock.patch.dict(os.environ, self.path_env()):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["accel_check", "--json"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertFalse(payload["kvm_node"])
        self.assertFalse(payload["kvm_usable"])
        self.assertIsNone(payload["emulator_accel"])
        self.assertEqual(payload["recommendation"], "no-emulator")

    def test_require_exits_3_when_not_accelerated(self) -> None:
        missing = self.root / "no-kvm"
        with mock.patch.object(accel_check, "KVM_PATH", missing):
            with mock.patch.dict(os.environ, self.path_env()):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main(["accel_check", "--json", "--require"])
        self.assertEqual(code, 3)

    def test_usable_kvm_and_accel_check_is_accelerated(self) -> None:
        node = self.root / "kvm-node"
        node.write_text("", encoding="utf-8")
        self.install("emulator", EMULATOR_BODY)
        log = self.root / "emulator-argv.txt"
        with mock.patch.object(accel_check, "KVM_PATH", node):
            with mock.patch.dict(
                os.environ,
                self.path_env({"EMULATOR_ARGV_LOG": str(log)}),
            ):
                report = accel_check.build_report()
        self.assertTrue(report["kvm_node"])
        self.assertTrue(report["kvm_usable"])
        self.assertEqual(report["recommendation"], "accelerated")
        self.assertIn("KVM is installed and usable", str(report["emulator_accel"]))
        argv = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(argv[1:], ["-accel-check"])
        self.assertNotIn("-avd", argv)

    def test_node_that_cannot_be_opened_with_emulator_is_tcg_only(self) -> None:
        node = self.root / "kvm-node"
        node.write_text("", encoding="utf-8")
        self.install("emulator", EMULATOR_BODY)
        with mock.patch.object(accel_check, "KVM_PATH", node):
            with mock.patch("android.tools.accel_check.os.open", side_effect=PermissionError(13, "denied")):
                with mock.patch.dict(
                    os.environ,
                    self.path_env({"EMULATOR_ACCEL_EXIT": "1", "EMULATOR_ACCEL_STDOUT": ""}),
                ):
                    report = accel_check.build_report()
        self.assertTrue(report["kvm_node"])
        self.assertFalse(report["kvm_usable"])
        self.assertEqual(report["recommendation"], "tcg-only")
        self.assertIn("exited 1", str(report["emulator_accel"]))

    def test_require_passes_only_when_accelerated(self) -> None:
        node = self.root / "kvm-node"
        node.write_text("", encoding="utf-8")
        self.install("emulator", EMULATOR_BODY)
        with mock.patch.object(accel_check, "KVM_PATH", node):
            with mock.patch.dict(os.environ, self.path_env()):
                with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                    code = main(["accel_check", "--require", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["recommendation"], "accelerated")


class MaestroFlowTests(IsolatedCase):
    def setUp(self) -> None:
        super().setUp()
        self.flow = self.root / "login.yaml"
        self.flow.write_text("appId: example\\n---\\n- launchApp\\n", encoding="utf-8")
        self.install("adb", ADB_BODY)
        self.install("maestro", MAESTRO_BODY)

    def test_returns_1_when_junit_reports_a_failure(self) -> None:
        log = self.root / "maestro-argv.txt"
        with mock.patch.dict(
            os.environ,
            self.path_env({"MAESTRO_ARGV_LOG": str(log), "MAESTRO_FAKE_RESULT": "fail"}),
        ):
            code, message = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
        self.assertEqual(code, 1)
        self.assertIn("failures=1", message)
        report = self.out / "maestro-junit.xml"
        self.assertTrue(report.is_file())
        self.assertEqual(report.resolve().parent, self.out.resolve())
        self.assertTrue((self.out / "debug" / "marker.txt").is_file())
        recorded = log.read_text(encoding="utf-8")
        self.assertIn("--format\njunit\n", recorded)
        self.assertIn(f"--device\n{SERIAL}\n", recorded)
        self.assertIn(str(report), recorded)

    def test_cli_returns_1_when_junit_reports_a_failure(self) -> None:
        with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_RESULT": "fail"})):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(
                    [
                        "maestro_flow",
                        "--serial",
                        SERIAL,
                        "--flow",
                        str(self.flow),
                        "--out",
                        str(self.out),
                    ]
                )
        self.assertEqual(code, 1)
        self.assertIn("failures=1", out.getvalue())

    def test_returns_0_when_junit_is_clean(self) -> None:
        with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_RESULT": "pass"})):
            code, message = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
        self.assertEqual(code, 0)
        self.assertTrue(message.startswith("wrote "))
        self.assertTrue(str(self.out.resolve()) in message or str(self.out) in message)

    def test_relative_path_and_flow_are_resolved_before_output_cwd(self) -> None:
        log = self.root / "maestro-argv.txt"
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.dict(
                os.environ,
                self.path_env({
                    "PATH": "bin",
                    "MAESTRO_FAKE_RESULT": "pass",
                    "MAESTRO_ARGV_LOG": str(log),
                }),
            ):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main([
                        "maestro_flow", "--serial", SERIAL,
                        "--flow", "login.yaml", "--out", "out",
                    ])
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(code, 0)
        argv = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(Path(argv[0]), self.bin / "maestro")
        self.assertEqual(Path(argv[-2]), self.flow)
        self.assertTrue((self.out / "maestro-junit.xml").is_file())

    def test_reports_without_executed_cases_fail_from_cli(self) -> None:
        reports = (
            '<testsuite tests="0"/>',
            '<testsuites tests="0"/>',
            '<testsuite><testcase><skipped/></testcase></testsuite>',
            '<testsuites><testsuite><testcase><skipped/></testcase></testsuite></testsuites>',
            '<config/>',
        )
        for report in reports:
            with self.subTest(report=report):
                with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_XML": report})):
                    with mock.patch("sys.stdout", new_callable=io.StringIO):
                        code = main([
                            "maestro_flow", "--serial", SERIAL,
                            "--flow", str(self.flow), "--out", str(self.out),
                        ])
                self.assertEqual(code, 1)

    def test_mixed_skipped_and_executed_cases_pass(self) -> None:
        report = (
            '<testsuites><testsuite><testcase><skipped/></testcase>'
            '<testcase name="executed"/></testsuite></testsuites>'
        )
        with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_XML": report})):
            code, _ = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
        self.assertEqual(code, 0)

    def test_failure_and_error_elements_still_fail_without_counts(self) -> None:
        for tag in ("failure", "error"):
            with self.subTest(tag=tag):
                report = f'<testsuite><testcase><{tag}/></testcase></testsuite>'
                with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_XML": report})):
                    code, _ = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
                self.assertEqual(code, 1)

    def test_unsafe_junit_is_rejected_from_cli(self) -> None:
        reports = (
            '<!DOCTYPE testsuite><testsuite><testcase name="executed"/></testsuite>',
            '<!DOCTYPE testsuite [<!ENTITY x "expanded">]>'
            '<testsuite><testcase name="&x;"/></testsuite>',
        )
        for report in reports:
            with self.subTest(report=report):
                with mock.patch.dict(os.environ, self.path_env({"MAESTRO_FAKE_XML": report})):
                    with mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                        code = main([
                            "maestro_flow", "--serial", SERIAL,
                            "--flow", str(self.flow), "--out", str(self.out),
                        ])
                self.assertEqual(code, 1)
                self.assertIn("not safe readable XML", output.getvalue())

    def test_unremovable_previous_report_is_a_cli_usage_error(self) -> None:
        self.out.mkdir()
        report = self.out / "maestro-junit.xml"
        report.write_text("previous report", encoding="utf-8")
        original_unlink = Path.unlink

        def deny_report_unlink(path, *args, **kwargs):
            if path == report:
                raise PermissionError("report cannot be removed")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.dict(os.environ, self.path_env()):
            with mock.patch.object(Path, "unlink", autospec=True, side_effect=deny_report_unlink):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main([
                        "maestro_flow", "--serial", SERIAL,
                        "--flow", str(self.flow), "--out", str(self.out),
                    ])
        self.assertEqual(code, 2)
        self.assertEqual(report.read_text(encoding="utf-8"), "previous report")

    def test_missing_maestro_exits_3(self) -> None:
        (self.bin / "maestro").unlink()
        with mock.patch.dict(os.environ, self.path_env()):
            code, message = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
        self.assertEqual(code, 3)
        self.assertIn("skipped: missing binary: maestro", message)
        self.assertFalse((self.out / "maestro-junit.xml").exists())

    def test_missing_device_exits_3(self) -> None:
        with mock.patch.dict(os.environ, self.path_env({"ADB_FAKE_NONE": "1"})):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(
                    [
                        "maestro_flow",
                        "--serial",
                        SERIAL,
                        "--flow",
                        str(self.flow),
                        "--out",
                        str(self.out),
                    ]
                )
        self.assertEqual(code, 3)
        self.assertIn("skipped:", out.getvalue())
        self.assertIn("device not connected", out.getvalue())

    def test_missing_flow_exits_2_before_skip(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(self.root / "empty")}):
            code, message = maestro_flow.run(
                serial=SERIAL,
                flow=str(self.root / "missing.yaml"),
                out=self.out,
            )
        self.assertEqual(code, 2)
        self.assertIn("flow not found", message)

    def test_looping_flow_is_a_cli_usage_error_before_output_creation(self) -> None:
        loop = self.root / "loop.yaml"
        loop.symlink_to(loop)
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            code = main([
                "maestro_flow", "--serial", SERIAL,
                "--flow", str(loop), "--out", str(self.out),
            ])
        self.assertEqual(code, 2)
        self.assertFalse(self.out.exists())

    def test_refuses_debug_symlink_outside_out(self) -> None:
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.out.mkdir()
        (self.out / "debug").symlink_to(elsewhere, target_is_directory=True)
        with mock.patch.dict(os.environ, {"PATH": str(self.root / "empty-path")}):
            code, message = maestro_flow.run(serial=SERIAL, flow=str(self.flow), out=self.out)
        self.assertEqual(code, 2)
        self.assertIn("symlink", message)
        self.assertEqual(list(elsewhere.iterdir()), [])


class ScreenRecordTests(IsolatedCase):
    def setUp(self) -> None:
        super().setUp()
        self.install("adb", ADB_BODY)

    def test_pulls_only_under_out_and_caps_seconds(self) -> None:
        with mock.patch.dict(os.environ, self.path_env()):
            code, message = screenrecord.run(serial=SERIAL, out=self.out, seconds=180)
        self.assertEqual(code, 0)
        local = self.out / "screenrecord.mp4"
        self.assertTrue(local.is_file())
        self.assertEqual(local.read_bytes(), b"fake-screenrecord")
        self.assertIn(str(local), message)
        log = self.argv_log.read_text(encoding="utf-8")
        self.assertIn("screenrecord --time-limit 180 /sdcard/desk-screenrecord-", log)
        self.assertIn(f"pull /sdcard/desk-screenrecord-", log)
        pull_line = next(line for line in log.splitlines() if " pull " in line)
        destination = Path(pull_line.split()[-1])
        self.assertEqual(destination.parent, self.out)
        self.assertNotEqual(destination, local)
        self.assertFalse(destination.exists())
        self.assertIn(" shell rm /sdcard/desk-screenrecord-", log)
        self.assertNotIn("rm -", log)

    def test_seconds_over_cap_exit_2_from_cli(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(
                [
                    "screenrecord",
                    "--serial",
                    SERIAL,
                    "--out",
                    str(self.out),
                    "--seconds",
                    "181",
                ]
            )
        self.assertEqual(ctx.exception.code, 2)

    def test_library_rejects_seconds_over_cap_without_adb(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(self.root / "nowhere")}):
            code, message = screenrecord.run(serial=SERIAL, out=self.out, seconds=181)
        self.assertEqual(code, 2)
        self.assertIn("180", message)
        self.assertFalse(self.argv_log.exists())

    def test_missing_adb_exits_3(self) -> None:
        (self.bin / "adb").unlink()
        with mock.patch.dict(os.environ, self.path_env()):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(
                    ["screenrecord", "--serial", SERIAL, "--out", str(self.out), "--seconds", "5"]
                )
        self.assertEqual(code, 3)
        self.assertIn("skipped: missing binary: adb", out.getvalue())
        self.assertFalse((self.out / "screenrecord.mp4").exists())

    def test_unauthorized_device_exits_3(self) -> None:
        with mock.patch.dict(os.environ, self.path_env({"ADB_FAKE_STATE": "unauthorized"})):
            code, message = screenrecord.run(serial=SERIAL, out=self.out, seconds=5)
        self.assertEqual(code, 3)
        self.assertIn("skipped:", message)
        self.assertIn("device not connected", message)

    def test_failed_or_empty_pull_preserves_previous_recording(self) -> None:
        self.out.mkdir()
        local = self.out / "screenrecord.mp4"
        cases = (
            {"ADB_PULL_EXIT": "1"},
            {"ADB_PULL_MODE": "missing"},
            {"ADB_PULL_MODE": "empty"},
        )
        for extra in cases:
            with self.subTest(extra=extra):
                local.write_bytes(b"previous recording")
                with mock.patch.dict(os.environ, self.path_env(extra)):
                    with mock.patch("sys.stdout", new_callable=io.StringIO):
                        code = main([
                            "screenrecord", "--serial", SERIAL,
                            "--out", str(self.out), "--seconds", "5",
                        ])
                self.assertEqual(code, 1)
                self.assertEqual(local.read_bytes(), b"previous recording")
                self.assertEqual(list(self.out.iterdir()), [local])

    def test_successful_pull_atomically_replaces_previous_recording(self) -> None:
        self.out.mkdir()
        local = self.out / "screenrecord.mp4"
        local.write_bytes(b"previous recording")
        original_run = subprocess.run

        def observe_pull(argv, **kwargs):
            if "pull" in argv:
                self.assertEqual(local.read_bytes(), b"previous recording")
                self.assertNotEqual(Path(argv[-1]), local)
                result = original_run(argv, **kwargs)
                self.assertEqual(local.read_bytes(), b"previous recording")
                return result
            return original_run(argv, **kwargs)

        with mock.patch.dict(os.environ, self.path_env()):
            with mock.patch.object(subprocess, "run", side_effect=observe_pull):
                code, _ = screenrecord.run(serial=SERIAL, out=self.out, seconds=5)
        self.assertEqual(code, 0)
        self.assertEqual(local.read_bytes(), b"fake-screenrecord")
        self.assertEqual(list(self.out.iterdir()), [local])

    def test_recording_and_pull_interruptions_clean_remote_and_preserve_output(self) -> None:
        self.out.mkdir()
        local = self.out / "screenrecord.mp4"
        original_run = subprocess.run
        for stage in ("screenrecord", "pull"):
            with self.subTest(stage=stage):
                local.write_bytes(b"previous recording")
                calls = []

                def interrupt(argv, **kwargs):
                    calls.append(argv)
                    if stage in argv:
                        if stage == "pull":
                            Path(argv[-1]).write_bytes(b"partial recording")
                        raise KeyboardInterrupt
                    return original_run(argv, **kwargs)

                with mock.patch.dict(os.environ, self.path_env()):
                    with mock.patch.object(subprocess, "run", side_effect=interrupt):
                        with mock.patch("sys.stdout", new_callable=io.StringIO):
                            code = main([
                                "screenrecord", "--serial", SERIAL,
                                "--out", str(self.out), "--seconds", "5",
                            ])
                self.assertEqual(code, 130)
                self.assertEqual(local.read_bytes(), b"previous recording")
                self.assertEqual(list(self.out.iterdir()), [local])
                record = next(argv for argv in calls if "screenrecord" in argv)
                cleanup = next(argv for argv in calls if "rm" in argv)
                self.assertEqual(cleanup[1:], ["-s", SERIAL, "shell", "rm", record[-1]])

    def test_cleanup_failure_is_reported_even_after_pull_failure(self) -> None:
        with mock.patch.dict(
            os.environ, self.path_env({"ADB_PULL_EXIT": "1", "ADB_RM_EXIT": "1"})
        ):
            code, message = screenrecord.run(serial=SERIAL, out=self.out, seconds=5)
        self.assertEqual(code, 1)
        self.assertIn("device file may remain", message)

    def test_cleanup_interruption_does_not_report_success(self) -> None:
        original_run = subprocess.run
        calls = []

        def interrupt_cleanup(argv, **kwargs):
            calls.append(argv)
            if "rm" in argv:
                raise KeyboardInterrupt
            return original_run(argv, **kwargs)

        with mock.patch.dict(os.environ, self.path_env()):
            with mock.patch.object(subprocess, "run", side_effect=interrupt_cleanup):
                code, message = screenrecord.run(serial=SERIAL, out=self.out, seconds=5)
        self.assertEqual(code, 130)
        self.assertIn("device file may remain", message)
        self.assertEqual((self.out / "screenrecord.mp4").read_bytes(), b"fake-screenrecord")
        self.assertEqual(sum("rm" in argv for argv in calls), 1)

    def test_temporary_cleanup_failure_is_a_cli_usage_error(self) -> None:
        original_unlink = Path.unlink

        def deny_temporary_unlink(path, *args, **kwargs):
            if path.name.startswith(".screenrecord-"):
                raise PermissionError("temporary file cannot be removed")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.dict(os.environ, self.path_env({"ADB_PULL_EXIT": "1"})):
            with mock.patch.object(Path, "unlink", autospec=True, side_effect=deny_temporary_unlink):
                with mock.patch("sys.stdout", new_callable=io.StringIO):
                    code = main([
                        "screenrecord", "--serial", SERIAL,
                        "--out", str(self.out), "--seconds", "5",
                    ])
        self.assertEqual(code, 2)
        self.assertIn(" shell rm /sdcard/desk-screenrecord-", self.argv_log.read_text(encoding="utf-8"))


class ExistingSkipExitTests(unittest.TestCase):
    def test_existing_adb_devices_skip_stays_exit_0(self) -> None:
        with mock.patch(
            "android.tools.adb.which_or_raise",
            side_effect=DeviceUnavailable("missing binary: adb"),
        ):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                code = main(["adb_devices"])
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("skipped:"))


if __name__ == "__main__":
    unittest.main()
