"""Run ``maestro test`` and count passed and failed cases from its JUnit XML.

The argv includes ``--format junit --test-output-dir <out> --output <fresh.xml>``.
A JUnit ``<failure>`` or ``<error>`` makes the command exit 1. On Linux, or when
``maestro`` is missing, the command skips with exit 3. ``--dry-run`` prints the
argv and spawns nothing. A skip is not a pass. Unsafe XML is an error (exit 2).

Maestro itself rejects physical iPhones. This wrapper does not add a device
flag and does not call App Store Connect.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

SKIP = 3
MAX_JUNIT_BYTES = 20 * 1024 * 1024


def _system(system_name: str | None) -> str:
    return system_name if system_name is not None else platform.system()


def _output_tail(proc) -> str:
    stdout = getattr(proc, "stdout", None) or ""
    stderr = getattr(proc, "stderr", None) or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    return (stdout + stderr)[-2000:]


def build_argv(flow: Path, out: Path, report: Path) -> list[str]:
    return [
        "maestro", "test", "--format", "junit",
        "--test-output-dir", str(out), "--output", str(report), str(flow),
    ]


def parse_junit_dir(out: Path) -> dict | None:
    """Count all reports recursively; any unsafe XML makes the result an error."""
    return _parse_junit_files(sorted(path for path in out.rglob("*.xml") if path.is_file()))


def _parse_junit_files(files: list[Path]) -> dict | None:
    if not files:
        return None
    passed = failed = skipped = 0
    seen = False
    for path in files:
        if path.stat().st_size > MAX_JUNIT_BYTES:
            return {
                "status": "error",
                "reason": f"JUnit file exceeds {MAX_JUNIT_BYTES} bytes: {path.name}",
                "passed": 0,
                "failed": 0,
                "skipped": 0,
            }
        try:
            root = ET.parse(
                path, forbid_dtd=True, forbid_entities=True, forbid_external=True,
            ).getroot()
        except DefusedXmlException:
            return {
                "status": "error",
                "reason": f"Unsafe JUnit XML (DTD, entity or external reference): {path.name}",
                "passed": 0,
                "failed": 0,
                "skipped": 0,
            }
        except ET.ParseError:
            continue
        if root is None:
            continue
        for case in root.iter("testcase"):
            seen = True
            if case.find("failure") is not None or case.find("error") is not None:
                failed += 1
            elif case.find("skipped") is not None:
                skipped += 1
            else:
                passed += 1
    if not seen:
        return None
    return {"passed": passed, "failed": failed, "skipped": skipped}


def maestro_flow(
    flow: Path,
    out: Path,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    flow = Path(flow)
    out = Path(out)
    if out.exists() and not out.is_dir():
        return {"status": "error", "reason": f"--out is not a directory: {out}", "exit_code": 2, "invoked": False}
    report = out / f"junit-{uuid4().hex}.xml"
    argv = build_argv(flow, out, report)
    if dry_run:
        return {"status": "dry-run", "argv": argv, "exit_code": 0, "invoked": False}
    system_name = _system(system_name)
    if system_name != "Darwin":
        return {
            "status": "skipped",
            "reason": "skipped: not on macOS",
            "argv": argv,
            "exit_code": SKIP,
            "invoked": False,
        }
    binary = which("maestro")
    if not binary:
        return {
            "status": "skipped",
            "reason": "skipped: maestro is not on PATH",
            "argv": argv,
            "exit_code": SKIP,
            "invoked": False,
        }
    if not flow.is_file():
        return {
            "status": "error",
            "reason": f"flow not found: {flow}",
            "exit_code": 2,
            "invoked": False,
        }
    resolved = [binary, *argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    proc = runner(resolved, capture_output=True, text=True, check=False, env=os.environ.copy())
    counts = _parse_junit_files([report] if report.is_file() else [])
    tail = _output_tail(proc)
    if counts is None:
        exit_code = 1 if proc.returncode != 0 else 2
        return {
            "status": "failed" if proc.returncode != 0 else "error",
            "reason": "maestro produced no JUnit XML at the current run's --output path",
            "argv": resolved,
            "exit_code": exit_code,
            "invoked": True,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "tool_exit_code": proc.returncode,
            "output_tail": tail,
        }
    if counts.get("status") == "error":
        return {
            "status": "error",
            "reason": counts["reason"],
            "argv": resolved,
            "exit_code": 2,
            "invoked": True,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "output_tail": tail,
        }
    failed = int(counts["failed"])
    if not counts["passed"] and not failed and proc.returncode == 0:
        return {
            "status": "skipped",
            "reason": "skipped: all JUnit cases were skipped; no case executed",
            "argv": resolved,
            "exit_code": SKIP,
            "invoked": True,
            "passed": 0,
            "failed": 0,
            "skipped": counts["skipped"],
            "tool_exit_code": proc.returncode,
            "output_tail": tail,
        }
    # A JUnit failure is exit 1 even when maestro itself exited 0.
    # A clean current-run report is a pass only when maestro also exited 0.
    if failed:
        exit_code = 1
        status = "failed"
    elif proc.returncode != 0:
        exit_code = 1
        status = "failed"
    else:
        exit_code = 0
        status = "passed"
    return {
        "status": status,
        "argv": resolved,
        "exit_code": exit_code,
        "invoked": True,
        "passed": counts["passed"],
        "failed": failed,
        "skipped": counts["skipped"],
        "tool_exit_code": proc.returncode,
        "output_tail": tail,
    }
