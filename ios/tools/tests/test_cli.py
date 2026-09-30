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


if __name__ == "__main__":
    unittest.main()
