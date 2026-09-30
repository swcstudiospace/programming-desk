import datetime
import json
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ios.tools.metavr_bridge import wrap
from ios.tools.spm_linux import spm_test
from ios.tools.xcodebuild_receipt import parse_log

ROOT = Path(__file__).resolve().parents[3]


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ios.tools", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_plist_lint_blank_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSCameraUsageDescription": " "}))
            proc = run("plist_lint", "--path", str(path), "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"], "failed")

    def test_entitlements_diff_usage_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            for side, keys in ((base, {}), (head, {"NSCameraUsageDescription": "Scan a code."})):
                side.mkdir()
                (side / "Info.plist").write_bytes(plistlib.dumps(keys))
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(body["usage"]["added"], ["NSCameraUsageDescription"])

    def test_spm_skip_code_when_toolchain_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / "Package.swift").write_text("// swift-tools-version:5.9\n")
            result = spm_test(package, swift_bin="/nonexistent/swift")
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["tests_ran"])
        self.assertFalse(result["xcodebuild_invoked"])

    def test_spm_dry_run_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / "Package.swift").write_text("// swift-tools-version:5.9\n")

            def boom(*_a, **_k):
                raise AssertionError("runner called")

            result = spm_test(package, dry_run=True, swift_bin="/nonexistent/swift", runner=boom)
        self.assertEqual(result["status"], "dry-run")
        self.assertFalse(result["tests_ran"])

    def test_snapshot_png_hash(self):
        def png(w, h, extra: bytes) -> bytes:
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0) + extra
            return sig + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr

        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before"
            after = Path(tmp) / "after"
            before.mkdir(); after.mkdir()
            out = Path(tmp) / "diff.json"
            (before / "shot.png").write_bytes(png(2, 2, b"a"))
            (after / "shot.png").write_bytes(png(3, 2, b"b"))
            proc = run("snapshot_diff", "--before", str(before), "--after", str(after), "--out", str(out))
            body = json.loads(out.read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(body["status"], "changed")
        self.assertTrue(body["changed"][0]["png_size_changed"])
        self.assertFalse(body["pixel_diff"])

    def test_xcodebuild_log_does_not_claim_simulator_boot(self):
        parsed = parse_log(
            "xcodebuild -scheme Desk -destination platform=iOS-Simulator,name=iPhone16 test\n** TEST SUCCEEDED **\n",
            "fixture.log",
        )
        self.assertEqual(parsed["status"], "passed")
        self.assertFalse(parsed["xcodebuild_invoked"])
        self.assertFalse(parsed["simulator_booted"])
        self.assertTrue(parsed["simulator_mentioned"])

    def test_metavr_missing_tool_skips(self):
        result = wrap("device_screenshot", "serial-1", "/tmp/out.png", which=lambda _name: None)
        self.assertEqual(result["exit_code"], 3)
        self.assertFalse(result["invoked"])
        self.assertFalse(result["artifact_written_by_wrapper"])

    def test_module_help(self):
        proc = run("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("plist_lint", proc.stdout)
        self.assertIn("ui_tap", proc.stdout)

    def test_ui_tap_requires_target(self):
        result = wrap("ui_tap", "serial-1", "/tmp/out.png", which=lambda _name: None)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["exit_code"], 2)
        self.assertFalse(result["invoked"])

    def test_ui_tap_passes_target_through(self):
        result = wrap(
            "ui_tap", "serial-1", "/tmp/out.png", target="login.button",
            which=lambda _name: "/usr/bin/ui_tap",
            runner=lambda argv, **_k: subprocess.CompletedProcess(argv, 0, "", ""),
        )
        self.assertEqual(result["status"], "recorded")
        self.assertIn("--target", result["argv"])
        self.assertIn("login.button", result["argv"])

    def test_cli_ui_tap_requires_target(self):
        proc = run("ui_tap", "--serial", "s1", "--out", "/tmp/out.png")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--target", proc.stderr)

    def test_cli_ui_tap_forwards_target(self):
        proc = run("ui_tap", "--serial", "s1", "--out", "/tmp/out.png", "--target", "login.button")
        body = json.loads(proc.stdout)
        self.assertIn("--target", body["argv"])
        self.assertIn("login.button", body["argv"])

    def test_xcodebuild_log_any_failed_banner_fails(self):
        parsed = parse_log(
            "** TEST FAILED **\n"
            "xcodebuild -scheme Desk clean\n"
            "** BUILD SUCCEEDED **\n",
            "fixture.log",
        )
        self.assertEqual(parsed["status"], "failed")
        self.assertTrue(parsed["any_failed"])
        self.assertEqual(parsed["banner_count"], 2)

    def test_snapshot_diff_single_files_with_different_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "recorded_shot.png"
            after = Path(tmp) / "candidate_shot.png"
            out = Path(tmp) / "diff.json"
            before.write_bytes(b"one")
            after.write_bytes(b"two")
            proc = run("snapshot_diff", "--before", str(before), "--after", str(after), "--out", str(out))
            body = json.loads(out.read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(body["status"], "changed")
        self.assertEqual(len(body["changed"]), 1)
        self.assertEqual(body["added"], [])
        self.assertEqual(body["removed"], [])

    def test_entitlements_scan_flags_blank_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSCameraUsageDescription": " "}))
            proc = run("entitlements_scan", "--path", str(tmp))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["usage_findings"][0]["key"], "NSCameraUsageDescription")

    def test_entitlements_diff_flags_value_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            base.mkdir(); head.mkdir()
            (base / "App.entitlements").write_bytes(plistlib.dumps({"aps-environment": "development"}))
            (head / "App.entitlements").write_bytes(plistlib.dumps({"aps-environment": "production"}))
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        change = body["entitlements"]["App.entitlements"]["changed"][0]
        self.assertEqual(change["key"], "aps-environment")
        self.assertEqual(change["before"], "development")
        self.assertEqual(change["after"], "production")

    def test_entitlements_diff_renamed_single_files_still_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "Old.entitlements"
            head = Path(tmp) / "New.entitlements"
            base.write_bytes(plistlib.dumps({"aps-environment": "development"}))
            head.write_bytes(plistlib.dumps({"aps-environment": "production"}))
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        change = body["entitlements"]["."]["changed"][0]
        self.assertEqual(change["before"], "development")
        self.assertEqual(change["after"], "production")

    def test_entitlements_diff_per_target_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            base.mkdir(); head.mkdir()
            (base / "App.entitlements").write_bytes(plistlib.dumps({"keychain-access-groups": ["x"]}))
            (base / "Widget.entitlements").write_bytes(plistlib.dumps({"keychain-access-groups": ["x"]}))
            (head / "App.entitlements").write_bytes(plistlib.dumps({"keychain-access-groups": ["x"]}))
            (head / "Widget.entitlements").write_bytes(plistlib.dumps({}))
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("App.entitlements", body["entitlements"])
        self.assertEqual(body["entitlements"]["Widget.entitlements"]["removed"], ["keychain-access-groups"])

    def test_entitlements_diff_type_change_is_not_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            base.mkdir(); head.mkdir()
            (base / "App.entitlements").write_bytes(plistlib.dumps({"get-task-allow": True}))
            (head / "App.entitlements").write_bytes(plistlib.dumps({"get-task-allow": 1}))
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(body["entitlements"]["App.entitlements"]["changed"]), 1)

    def test_entitlements_diff_data_and_date_values_do_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            base.mkdir(); head.mkdir()
            (base / "App.entitlements").write_bytes(
                plistlib.dumps({"stamp": b"\x00\x01", "when": datetime.datetime(2020, 1, 1)})
            )
            (head / "App.entitlements").write_bytes(
                plistlib.dumps({"stamp": b"\x02\x03", "when": datetime.datetime(2021, 1, 1)})
            )
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = json.loads(proc.stdout)
        changed = {c["key"] for c in body["entitlements"]["App.entitlements"]["changed"]}
        self.assertEqual(changed, {"stamp", "when"})

    def test_snapshot_diff_file_vs_directory_pair_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "shot.png"
            after_dir = Path(tmp) / "after"
            after_dir.mkdir()
            out = Path(tmp) / "diff.json"
            before.write_bytes(b"same")
            (after_dir / "shot.png").write_bytes(b"same")
            proc = run("snapshot_diff", "--before", str(before), "--after", str(after_dir), "--out", str(out))
            body = json.loads(out.read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["added"], [])
        self.assertEqual(body["removed"], [])

    def test_xcodebuild_receipt_fields_agree_when_any_failed(self):
        parsed = parse_log(
            "** TEST FAILED **\n"
            "xcodebuild -scheme Desk clean\n"
            "** BUILD SUCCEEDED **\n",
            "fixture.log",
        )
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["result"], "FAILED")
        self.assertEqual(parsed["action"], "TEST")


if __name__ == "__main__":
    unittest.main()
