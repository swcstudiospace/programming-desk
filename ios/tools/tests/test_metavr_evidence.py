import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import metavr_evidence


class MetaVrEvidenceTests(unittest.TestCase):
    def test_simulator_kind_is_rejected(self):
        with self.assertRaises(metavr_evidence.EvidenceError):
            metavr_evidence.build_record(
                "ios-simulator", "sim-1", "localhost", ["echo", "hi"]
            )

    def test_record_without_run_stays_unverified(self):
        record = metavr_evidence.build_record(
            "metavr", "device-9", "lab-host", ["echo", "hi"]
        )
        self.assertEqual(record["status"], "unverified")
        self.assertIsNone(record["exit_code"])
        self.assertFalse(record["simulator_claimed"])
        self.assertFalse(record["xcodebuild_invoked"])
        self.assertEqual(metavr_evidence.validate_record(record), [])

    def test_cli_run_records_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "evidence.json"
            code = metavr_evidence.main(
                [
                    "--kind", "remote",
                    "--device-id", "device-9",
                    "--host", "lab-host",
                    "--out", str(out),
                    "--run",
                    "--",
                    sys.executable, "-c", "import sys; sys.exit(0)",
                ]
            )
            record = json.loads(out.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(record["status"], "recorded")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["kind"], "remote")

    def test_validate_rejects_simulator_flag(self):
        record = metavr_evidence.build_record("remote", "d", "h", ["true"])
        record["simulator_claimed"] = True
        problems = metavr_evidence.validate_record(record)
        self.assertTrue(any("simulator_claimed" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
