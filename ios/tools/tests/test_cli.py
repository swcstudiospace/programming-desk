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

    def test_plist_lint_contacts_usage_key_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSContactsUsageDescription": ""}))
            proc = run("plist_lint", "--path", str(path), "--json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"], "failed")

    def test_entitlements_diff_reports_value_change_per_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            head = Path(tmp) / "head"
            for side, value in ((base, False), (head, True)):
                target = side / "AppTarget"
                target.mkdir(parents=True)
                (target / "App.entitlements").write_bytes(
                    plistlib.dumps({"com.apple.developer.icloud-container-identifiers": value})
                )
            proc = run("entitlements_scan", "--diff", str(base), str(head))
        body = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Same key on both sides (no added/removed) but the value flipped;
        # a key-set-only diff would report no change at all.
        self.assertEqual(body["entitlements"]["added"], [])
        self.assertEqual(body["entitlements"]["removed"], [])
        changed = body["entitlements"]["changed"]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["key"], "com.apple.developer.icloud-container-identifiers")
        self.assertEqual(changed[0]["before"], False)
        self.assertEqual(changed[0]["after"], True)
        self.assertIn("AppTarget/App.entitlements", changed[0]["target"])

    def test_ui_tap_requires_target(self):
        result = wrap("ui_tap", "serial-1", "/tmp/out.json", which=lambda _name: None)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["invoked"])

    def test_ui_tap_forwards_coordinates(self):
        seen = {}

        def fake_which(_name):
            return "/usr/bin/ui_tap"

        def fake_runner(argv, **kwargs):
            seen["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            out.write_text("{}")
            wrap("ui_tap", "serial-1", str(out), which=fake_which, runner=fake_runner, x=12.0, y=34.0)
        self.assertIn("--x", seen["argv"])
        self.assertIn("12.0", seen["argv"])
        self.assertIn("--y", seen["argv"])
        self.assertIn("34.0", seen["argv"])

    def test_metavr_recorded_requires_output_file(self):
        def fake_which(_name):
            return "/usr/bin/device_screenshot"

        def fake_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            missing_out = Path(tmp) / "never_written.png"
            result = wrap("device_screenshot", "serial-1", str(missing_out), which=fake_which, runner=fake_runner)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["output_written"])

    def test_xcodebuild_earlier_failure_not_hidden_by_final_summary(self):
        parsed = parse_log(
            "xcodebuild -scheme Desk -destination platform=iOS Simulator,name=iPhone 16 test\n"
            "** TEST FAILED **\n"
            "** TEST SUCCEEDED **\n",
            "fixture.log",
        )
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["failed_banners"], ["TEST FAILED"])

    def test_xcodebuild_quoted_destination_not_truncated(self):
        parsed = parse_log(
            'xcodebuild -scheme Desk -destination "platform=iOS Simulator,name=iPhone 16" test\n'
            "** TEST SUCCEEDED **\n",
            "fixture.log",
        )
        self.assertEqual(parsed["destination"], "platform=iOS Simulator,name=iPhone 16")

    def test_unverified_xcodebuild_log_does_not_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "build.log"
            log.write_text("xcodebuild -scheme Desk test\nno banner here\n")
            proc = run("xcodebuild_receipt", "--log", str(log))
        body = json.loads(proc.stdout)
        self.assertEqual(body["status"], "unverified")
        self.assertEqual(proc.returncode, 1)

    def test_snapshot_single_file_diff_ignores_basenames(self):
        def png(w, h, extra: bytes) -> bytes:
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0) + extra
            return sig + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr

        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.png"
            after = Path(tmp) / "after.png"
            before.write_bytes(png(2, 2, b"a"))
            after.write_bytes(png(2, 2, b"b"))
            out = Path(tmp) / "diff.json"
            proc = run("snapshot_diff", "--before", str(before), "--after", str(after), "--out", str(out))
            body = json.loads(out.read_text())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(body["added"], [])
        self.assertEqual(body["removed"], [])
        self.assertEqual(len(body["changed"]), 1)

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


if __name__ == "__main__":
    unittest.main()
