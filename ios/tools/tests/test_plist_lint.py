import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plist_lint


class PlistLintTests(unittest.TestCase):
    def test_blank_usage_string_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSCameraUsageDescription": "  "}))
            result = plist_lint.lint_tree(Path(tmp))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_count"], 1)
        self.assertFalse(result["submitted"])

    def test_present_usage_string_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSCameraUsageDescription": "Scans a QR code to join a room."}))
            result = plist_lint.lint_tree(Path(tmp))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["error_count"], 0)

    def test_always_location_without_when_in_use_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_bytes(plistlib.dumps({"NSLocationAlwaysAndWhenInUseUsageDescription": "Shares location."}))
            findings = plist_lint.lint_info_plist(path)
        self.assertTrue(any(f["severity"] == "warning" for f in findings))

    def test_malformed_plist_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Info.plist"
            path.write_text("this is not a plist", encoding="utf-8")
            result = plist_lint.lint_tree(Path(tmp))
        self.assertEqual(result["status"], "failed")

    def test_entitlement_private_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "App.entitlements"
            path.write_text("-----BEGIN PRIVATE KEY-----\nAAAA\n", encoding="utf-8")
            result = plist_lint.lint_tree(Path(tmp))
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("key or certificate" in f["message"] for f in result["findings"]))

    def test_entitlement_keys_are_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "App.entitlements"
            path.write_bytes(plistlib.dumps({"aps-environment": "development"}))
            result = plist_lint.lint_tree(Path(tmp))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(f.get("key") == "aps-environment" for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
