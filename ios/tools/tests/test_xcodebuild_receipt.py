import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import xcodebuild_receipt


LOG = """
xcodebuild -scheme DeskApp -destination platform=iOS,id=ABC build test
error: something failed to compile
** TEST FAILED **
"""


class XcodebuildReceiptTests(unittest.TestCase):
    def test_parses_failed_log_without_invoking_xcodebuild(self):
        parsed = xcodebuild_receipt.parse_log(LOG, "fixture.log")
        self.assertEqual(parsed["status"], "failed")
        self.assertEqual(parsed["action"], "TEST")
        self.assertEqual(parsed["scheme"], "DeskApp")
        self.assertEqual(parsed["destination"], "platform=iOS,id=ABC")
        self.assertEqual(parsed["error_count"], 1)
        self.assertFalse(parsed["xcodebuild_invoked"])
        self.assertFalse(parsed["simulator_booted"])

    def test_missing_result_line_is_unverified(self):
        parsed = xcodebuild_receipt.parse_log("build started\n", "partial.log")
        self.assertEqual(parsed["status"], "unverified")
        self.assertFalse(parsed["xcodebuild_invoked"])

    def test_json_log_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps({"log": "** BUILD SUCCEEDED **\n"}))
            parsed = xcodebuild_receipt.parse_path(path)
        self.assertEqual(parsed["status"], "passed")
        self.assertEqual(parsed["action"], "BUILD")
        self.assertEqual(parsed["artifact_format"], "json-log")
        self.assertFalse(parsed["xcodebuild_invoked"])

    def test_cli_missing_file(self):
        code = xcodebuild_receipt.main(["/tmp/does-not-exist-ios-artifact.log"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
