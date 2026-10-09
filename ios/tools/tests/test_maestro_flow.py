import os
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from ios.tools.maestro_flow import maestro_flow, parse_junit_dir

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

SKIPPED_JUNIT = """<testsuite>
  <testcase name="opens"/>
  <testcase name="unsupported"><skipped/></testcase>
</testsuite>
"""

UNSAFE_JUNIT = (
    '<!DOCTYPE testsuite><testsuite><testcase name="opens"/></testsuite>',
    '<!DOCTYPE testsuite [<!ENTITY expansion "expanded">]>'
    '<testsuite><testcase name="&expansion;"/></testsuite>',
    '<!DOCTYPE testsuite SYSTEM "file:///nonexistent-maestro.dtd">'
    '<testsuite><testcase name="opens"/></testsuite>',
    '<!DOCTYPE testsuite [<!ENTITY external SYSTEM "file:///nonexistent-maestro-secret">]>'
    '<testsuite><testcase>&external;</testcase></testsuite>',
    '<!DOCTYPE testsuite [<!ENTITY % external SYSTEM "file:///nonexistent-maestro.dtd">'
    '%external;]><testsuite><testcase name="opens"/></testsuite>',
)


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


def maestro_script(calls: Path, junit: str | None, tool_exit: int) -> str:
    write_report = "" if junit is None else f"""cat > "$report" << 'ENDXML'
{junit}
ENDXML
"""
    return f"""#!/bin/sh
printf '%s\\n' "$*" > "{calls}"
out=""
report=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--test-output-dir" ]; then
    out="$arg"
  elif [ "$prev" = "--output" ]; then
    report="$arg"
  fi
  prev="$arg"
done
mkdir -p "$out"
{write_report}exit {tool_exit}
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
            self.assertFalse(calls.exists())
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("skipped:", result["reason"])
        self.assertFalse(result["invoked"])

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

    def test_skipped_junit_cases_are_not_counted_as_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n")
            write_exe(root / "maestro", maestro_script(root / "calls", SKIPPED_JUNIT, 0))
            with prepend_path(root):
                result = maestro_flow(flow, root / "out", system_name="Darwin")
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual((result["passed"], result["failed"], result["skipped"]), (1, 0, 1))

    def test_all_skipped_current_report_never_passes(self):
        junit = '<testsuite><testcase name="unsupported"><skipped/></testcase></testsuite>'
        for tool_exit in (0, 1):
            with self.subTest(tool_exit=tool_exit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                flow = root / "login.yaml"
                flow.write_text("appId: space.swc.desk\n")
                write_exe(root / "maestro", maestro_script(root / "calls", junit, tool_exit))
                with prepend_path(root):
                    result = maestro_flow(flow, root / "out", system_name="Darwin")
                self.assertEqual(result["status"], "skipped" if tool_exit == 0 else "failed", result)
                self.assertEqual(result["exit_code"], 3 if tool_exit == 0 else 1)
                self.assertTrue(result["invoked"])
                self.assertEqual((result["passed"], result["failed"], result["skipped"]), (0, 0, 1))
                if tool_exit == 0:
                    self.assertIn("skipped:", result["reason"])
                    self.assertIn("no case executed", result["reason"])

    def test_unsafe_current_report_errors_even_when_maestro_exits_zero(self):
        for junit in UNSAFE_JUNIT:
            with self.subTest(junit=junit), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                flow = root / "login.yaml"
                flow.write_text("appId: space.swc.desk\n")
                write_exe(root / "maestro", maestro_script(root / "calls", junit, 0))
                with prepend_path(root):
                    result = maestro_flow(flow, root / "out", system_name="Darwin")
                self.assertEqual(result["status"], "error", result)
                self.assertEqual(result["exit_code"], 2)
                self.assertTrue(result["invoked"])
                self.assertIn("Unsafe JUnit XML", result["reason"])
                self.assertEqual((result["passed"], result["failed"], result["skipped"]), (0, 0, 0))

    def test_directory_parser_rejects_mixed_valid_and_unsafe_reports(self):
        for junit in UNSAFE_JUNIT:
            for unsafe_first in (False, True):
                with self.subTest(junit=junit, unsafe_first=unsafe_first), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    nested = root / "nested"
                    nested.mkdir()
                    (root / "passing.xml").write_text(PASSING_JUNIT)
                    # Visit the hostile report before or after a valid nested one.
                    unsafe_name = "a-unsafe.xml" if unsafe_first else "z-unsafe.xml"
                    (nested / unsafe_name).write_text(junit)
                    (nested / "passing.xml").write_text(PASSING_JUNIT)
                    result = parse_junit_dir(root)
                    self.assertIsNotNone(result)
                    self.assertEqual(result["status"], "error", result)
                    self.assertIn("Unsafe JUnit XML", result["reason"])
                    self.assertEqual((result["passed"], result["failed"], result["skipped"]), (0, 0, 0))

    def test_directory_parser_still_skips_malformed_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "malformed.xml").write_text("<testsuite><")
            self.assertIsNone(parse_junit_dir(root))
            (root / "passing.xml").write_text(PASSING_JUNIT)
            self.assertEqual(parse_junit_dir(root), {"passed": 1, "failed": 0, "skipped": 0})

    def test_reused_output_counts_only_each_explicit_current_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            flow = root / "login.yaml"
            flow.write_text("appId: space.swc.desk\n")
            out = root / "out"
            out.mkdir()
            old_report = out / "old.xml"
            old_report.write_text(FAILING_JUNIT)
            nested = out / "nested"
            nested.mkdir()
            nested_report = nested / "old.xml"
            nested_report.write_text(UNSAFE_JUNIT[1])
            reports = []
            for junit, expected_status, expected_counts in (
                (PASSING_JUNIT, "passed", (1, 0)),
                (FAILING_JUNIT, "failed", (1, 1)),
                (PASSING_JUNIT, "passed", (1, 0)),
            ):
                write_exe(root / "maestro", maestro_script(root / "calls", junit, 0))
                with prepend_path(root):
                    result = maestro_flow(flow, out, system_name="Darwin")
                self.assertEqual(result["status"], expected_status, result)
                self.assertEqual((result["passed"], result["failed"]), expected_counts)
                report = Path(result["argv"][result["argv"].index("--output") + 1])
                self.assertEqual(report.parent, out)
                self.assertEqual(report.read_text().strip(), junit.strip())
                self.assertNotIn(report, reports)
                reports.append(report)
            self.assertTrue(all(report.is_file() for report in reports))
            self.assertEqual(old_report.read_text(), FAILING_JUNIT)
            self.assertEqual(nested_report.read_text(), UNSAFE_JUNIT[1])

    def test_stale_reports_cannot_replace_a_missing_current_report(self):
        for stale_junit in (PASSING_JUNIT, FAILING_JUNIT):
            for tool_exit in (0, 1):
                with self.subTest(stale_junit=stale_junit, tool_exit=tool_exit), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    flow = root / "login.yaml"
                    flow.write_text("appId: space.swc.desk\n")
                    out = root / "out"
                    out.mkdir()
                    old_report = out / "old.xml"
                    old_report.write_text(stale_junit)
                    write_exe(root / "maestro", maestro_script(root / "calls", None, tool_exit))
                    with prepend_path(root):
                        result = maestro_flow(flow, out, system_name="Darwin")
                    self.assertEqual(result["status"], "error" if tool_exit == 0 else "failed", result)
                    self.assertEqual(result["exit_code"], 2 if tool_exit == 0 else 1)
                    self.assertEqual((result["passed"], result["failed"], result["skipped"]), (0, 0, 0))
                    self.assertIn("current run's --output path", result["reason"])
                    self.assertEqual(old_report.read_text(), stale_junit)


if __name__ == "__main__":
    unittest.main()
