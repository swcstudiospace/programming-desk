import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import snapshot_diff


class SnapshotDiffTests(unittest.TestCase):
    def test_identical_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            for side in (left, right):
                (side / "a").mkdir(parents=True)
                (side / "a" / "one.txt").write_text("same")
            result = snapshot_diff.diff_dirs(left, right)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["unchanged"], 1)
        self.assertFalse(result["pixel_diff"])

    def test_changed_added_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            left.mkdir()
            right.mkdir()
            (left / "keep.txt").write_text("v1")
            (right / "keep.txt").write_text("v2")
            (left / "gone.txt").write_text("x")
            (right / "new.txt").write_text("y")
            result = snapshot_diff.diff_dirs(left, right)
        self.assertEqual(result["changed"], ["keep.txt"])
        self.assertEqual(result["removed"], ["gone.txt"])
        self.assertEqual(result["added"], ["new.txt"])

    def test_fail_on_diff_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left"
            right = Path(tmp) / "right"
            left.mkdir()
            right.mkdir()
            (left / "a.txt").write_text("1")
            (right / "a.txt").write_text("2")
            code = snapshot_diff.main([str(left), str(right), "--fail-on-diff"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
