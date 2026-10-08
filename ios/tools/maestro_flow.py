"""Run ``maestro test`` and count passed and failed cases from its JUnit XML.

The argv is ``maestro test --format junit --test-output-dir <out> <flow>``.
A JUnit ``<failure>`` or ``<error>`` makes the command exit 1. On Linux, or when
``maestro`` is missing, the command skips with exit 3. ``--dry-run`` prints the
argv and spawns nothing. A skip is not a pass.

Maestro itself rejects physical iPhones. This wrapper does not add a device
flag and does not call App Store Connect.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

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


def build_argv(flow: Path, out: Path) -> list[str]:
    return ["maestro", "test", "--format", "junit", "--test-output-dir", str(out), str(flow)]


def _junit_files(out: Path) -> list[Path]:
    direct = sorted(path for path in out.glob("*.xml") if path.is_file())
    if direct:
        return direct
    return sorted(path for path in out.rglob("*.xml") if path.is_file())


def parse_junit_dir(out: Path) -> dict | None:
    """Return passed/failed/skipped counts, or None when no JUnit cases were found."""
    files = _junit_files(out)
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
            root = ET.parse(path).getroot()
        except ET.ParseError:
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
    argv = build_argv(flow, out)
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
    counts = parse_junit_dir(out)
    tail = _output_tail(proc)
    if counts is None:
        exit_code = 1 if proc.returncode != 0 else 2
        return {
            "status": "failed" if proc.returncode != 0 else "error",
            "reason": "maestro produced no JUnit XML under --out",
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
    # A JUnit failure is exit 1 even when maestro itself exited 0.
    # A clean report is a pass only when maestro also exited 0, so a crash
    # that left a stale green report is not reported as a pass.
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
