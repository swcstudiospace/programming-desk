import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from ios.tools.xcodebuild_test import xcodebuild_test

ROOT = Path(__file__).resolve().parents[3]


def write_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@contextmanager
def prepend_path(directory: Path):
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = str(directory) + os.pathsep + old
    try:
        yield
    finally:
        os.environ["PATH"] = old


def xcodebuild_script(calls: Path, banner: str) -> str:
    return f"""#!/bin/sh
printf '%s\\n' "$*" > "{calls}"
for arg in "$@"; do
  case "$arg" in
    *CODE_SIGN_IDENTITY*|*DEVELOPMENT_TEAM*|*PROVISIONING_PROFILE*)
      echo "signing flag" >&2
      exit 4
      ;;
  esac
done
printf '%s\\n' '{banner}'
exit 0
"""


class XcodebuildTestTests(unittest.TestCase):
    def test_linux_skips_without_spawning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            write_exe(root / "xcodebuild", xcodebuild_script(calls, "** TEST SUCCEEDED **"))
            out = root / "out"
            with prepend_path(root):
                result = xcodebuild_test(
                    "Desk", "platform=iOS Simulator,name=iPhone 17", out, out / "xcodebuild.log",
                    system_name="Linux",
                )
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("skipped:", result["reason"])
        self.assertFalse(result["xcodebuild_invoked"])
        self.assertFalse(calls.exists())

    def test_dry_run_argv_has_no_signing_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = xcodebuild_test(
                "Desk",
                "platform=iOS Simulator,name=iPhone 17",
                out,
                out / "xcodebuild.log",
                only_testing=["DeskTests/LoginTests"],
                dry_run=True,
                system_name="Linux",
            )
        argv = result["argv"]
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(argv[:2], ["xcodebuild", "test"])
        self.assertIn("-scheme", argv)
        self.assertIn("Desk", argv)
        self.assertIn("-destination", argv)
        self.assertIn("-resultBundlePath", argv)
        self.assertIn("-only-testing", argv)
        self.assertIn("DeskTests/LoginTests", argv)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", argv)
        self.assertFalse(any("CODE_SIGN_IDENTITY" in token or "DEVELOPMENT_TEAM" in token for token in argv))
        self.assertFalse(result["xcodebuild_invoked"])

    def test_device_destination_omits_the_simulator_signing_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = xcodebuild_test(
                "Desk", "generic/platform=iOS", out, out / "xcodebuild.log", dry_run=True,
            )
        self.assertNotIn("CODE_SIGNING_ALLOWED=NO", result["argv"])
        self.assertFalse(any("DEVELOPMENT_TEAM" in token for token in result["argv"]))

    def test_log_outside_out_is_refused(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("runner called")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = xcodebuild_test(
                "Desk", "platform=iOS Simulator,name=iPhone 17",
                root / "out", root / "elsewhere.log",
                system_name="Darwin", which=lambda _n: "/usr/bin/xcodebuild", runner=boom,
            )
        self.assertEqual(result["exit_code"], 2)
        self.assertFalse(result["invoked"])

    def test_fake_xcodebuild_log_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            out = root / "out"
            write_exe(root / "xcodebuild", xcodebuild_script(calls, "** TEST FAILED **"))
            with prepend_path(root):
                result = xcodebuild_test(
                    "Desk", "platform=iOS Simulator,name=iPhone 17", out, out / "xcodebuild.log",
                    system_name="Darwin",
                )
            log = (out / "xcodebuild.log").read_text()
            recorded = calls.read_text()
        self.assertEqual(result["exit_code"], 1, result)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["xcodebuild_invoked"])
        self.assertIn("** TEST FAILED **", log)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", recorded)
        self.assertNotIn("DEVELOPMENT_TEAM", recorded)
        self.assertEqual(result["receipt"]["result"], "FAILED")

    def test_succeeded_banner_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            write_exe(root / "xcodebuild", xcodebuild_script(root / "calls", "** TEST SUCCEEDED **"))
            with prepend_path(root):
                result = xcodebuild_test(
                    "Desk", "platform=iOS Simulator,name=iPhone 17", out, out / "xcodebuild.log",
                    system_name="Darwin",
                )
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(result["status"], "passed")

    def test_cli_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            proc = subprocess.run(
                [sys.executable, "-m", "ios.tools", "xcodebuild_test",
                 "--scheme", "Desk", "--destination", "platform=iOS Simulator,name=iPhone 17",
                 "--out", str(out), "--log", str(out / "xcodebuild.log"), "--dry-run", "--json"],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = json.loads(proc.stdout)
        self.assertEqual(body["argv"][0], "xcodebuild")
        self.assertIn("CODE_SIGNING_ALLOWED=NO", body["argv"])


if __name__ == "__main__":
    unittest.main()
