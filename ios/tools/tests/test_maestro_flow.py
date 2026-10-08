import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from ios.tools.maestro_flow import maestro_flow

ROOT = Path(__file__).resolve().parents[3]

FAILING_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="flow" tests="2" failures="1">
    <testcase classname="flow" name="opens"/>
    <testcase classname="flow" name="pays">
      <failure message="button missing">no button</failure>
    </testcase>
  </testsuite>
</testsuites>
"""

PASSING_JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="flow" tests="1">
  <testcase classname="flow" name="opens"/>
</testsuite>
"""


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


def maestro_script(calls: Path, junit: str, tool_exit: int) -> str:
    return f"""#!/bin/sh
printf '%s\\n' "$*" > "{calls}"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--test-output-dir" ]; then
    out="$arg"
  fi
  prev="$arg"
done
mkdir -p "$out"
cat > "$out/junit.xml" << 'ENDXML'
{junit}
ENDXML
exit {tool_exit}
"""


class MaestroFlowTests(unittest.TestCase):
    def test_linux_skips_without_spawning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n---\n- launchApp\n")
            write_exe(root / "maestro", maestro_script(calls, PASSING_JUNIT, 0))
            with prepend_path(root):
                result = maestro_flow(flow, root / "out", system_name="Linux")
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("skipped:", result["reason"])
        self.assertFalse(result["invoked"])
        self.assertFalse(calls.exists())

    def test_dry_run_prints_maestro_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = maestro_flow(root / "login.yaml", root / "out", dry_run=True, system_name="Linux")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(
            result["argv"][:5],
            ["maestro", "test", "--format", "junit", "--test-output-dir"],
        )
        self.assertFalse(result["invoked"])

    def test_junit_failure_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = root / "calls"
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n---\n- launchApp\n")
            # Maestro itself exits 0. The JUnit failure is what must produce exit 1.
            write_exe(root / "maestro", maestro_script(calls, FAILING_JUNIT, 0))
            with prepend_path(root):
                result = maestro_flow(flow, root / "out", system_name="Darwin")
            recorded = calls.read_text()
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["status"], "failed")
        self.assertIn("--format junit", recorded)
        self.assertIn("--test-output-dir", recorded)

    def test_junit_pass_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n---\n- launchApp\n")
            write_exe(root / "maestro", maestro_script(root / "calls", PASSING_JUNIT, 0))
            with prepend_path(root):
                result = maestro_flow(flow, root / "out", system_name="Darwin")
        self.assertEqual(result["exit_code"], 0, result)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["status"], "passed")

    def test_missing_binary_on_macos_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n")
            result = maestro_flow(
                flow, root / "out", system_name="Darwin", which=lambda _name: None,
            )
        self.assertEqual(result["exit_code"], 3)
        self.assertIn("maestro is not on PATH", result["reason"])
        self.assertFalse(result["invoked"])

    def test_cli_help_lists_the_harness_commands(self):
        proc = subprocess.run(
            [sys.executable, "-m", "ios.tools", "--help"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("sim_drive", proc.stdout)
        self.assertIn("xcodebuild_test", proc.stdout)
        self.assertIn("maestro_flow", proc.stdout)


if __name__ == "__main__":
    unittest.main()
