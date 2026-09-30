import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spm_linux


class SpmLinuxTests(unittest.TestCase):
    def test_missing_manifest_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = spm_linux.check_package(Path(tmp), swift_bin="/nonexistent/swift")
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["tests_ran"])
        self.assertFalse(result["simulator_claimed"])
        self.assertFalse(result["xcodebuild_invoked"])

    def test_missing_toolchain_is_unverified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Package.swift").write_text("// swift-tools-version: 5.9\n")
            result = spm_linux.check_package(root, swift_bin="/nonexistent/swift")
        self.assertEqual(result["status"], "unverified")
        self.assertFalse(result["tests_ran"])
        self.assertIn("not available", result["reason"])
        self.assertFalse(result["xcodebuild_invoked"])

    def test_cli_unverified_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Package.swift").write_text("// swift-tools-version: 5.9\n")
            code = spm_linux.main([str(root), "--swift", "/nonexistent/swift"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
