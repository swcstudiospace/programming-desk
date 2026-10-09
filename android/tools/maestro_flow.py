"""Run a Maestro flow and read its JUnit report. Writes only under --out."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from . import adb

SKIP_EXIT = 3
JUNIT_NAME = "maestro-junit.xml"
DEBUG_DIR_NAME = "debug"
_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")


class UsageError(Exception):
    """Caller input that will not be retried as a skip."""


class Skip(Exception):
    """Host has no binary or no connected device."""


def _serial_ok(serial: str) -> bool:
    return _SERIAL_RE.fullmatch(serial or "") is not None


def prepare_out(out: str | Path) -> Path:
    root = Path(out).expanduser()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise UsageError(f"--out is not usable: {exc}") from exc
    root = root.resolve()
    if not root.is_dir():
        raise UsageError(f"--out is not a directory: {out}")
    return root


def output_path(root: Path, name: str) -> Path:
    """A direct child of root. Symlinks and paths that resolve outside root fail."""
    if name != Path(name).name or name in {".", ".."}:
        raise UsageError(f"refusing output name {name!r}")
    path = root / name
    if path.is_symlink():
        raise UsageError(f"refusing symlink under --out: {name}")
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise UsageError(f"refusing to write outside --out: {resolved}")
    return path


def junit_has_failure(path: Path) -> tuple[bool, str]:
    """True for failures/errors, unreadable JUnit, or no executed test cases."""
    try:
        root = ET.parse(
            path, forbid_dtd=True, forbid_entities=True, forbid_external=True,
        ).getroot()
    except (DefusedXmlException, ET.ParseError, OSError) as exc:
        return True, f"junit report is not safe readable XML: {exc}"
    if root is None or root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
        return True, "junit report has no test suite"
    failures = 0
    errors = 0
    saw_failure_element = False
    saw_executed_case = False
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in {"testsuite", "testsuites"}:
            try:
                failures = max(failures, int(el.attrib.get("failures") or 0))
                errors = max(errors, int(el.attrib.get("errors") or 0))
            except ValueError:
                return True, "junit report has a non-integer failures or errors count"
            if tag == "testsuite":
                for case in el:
                    if case.tag.rsplit("}", 1)[-1] == "testcase" and not any(
                        child.tag.rsplit("}", 1)[-1] == "skipped" for child in case.iter()
                    ):
                        saw_executed_case = True
        elif tag in {"failure", "error"}:
            saw_failure_element = True
    if failures or errors:
        return True, f"junit reports failures={failures} errors={errors}"
    if saw_failure_element:
        return True, "junit report contains a failure or error element"
    if not saw_executed_case:
        return True, "junit report has no executed test cases"
    return False, "junit reports failures=0 errors=0"


def _require_device(serial: str) -> None:
    binary = shutil.which("adb")
    if not binary:
        raise Skip("missing binary: adb")
    try:
        proc = subprocess.run(
            adb.build_adb_argv("devices", "-l", adb=binary),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Skip(f"adb devices failed: {exc}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise Skip(f"adb devices failed: {err}")
    connected = {
        device.serial
        for device in adb.parse_adb_devices(proc.stdout or "")
        if device.state == "device"
    }
    if serial not in connected:
        raise Skip(f"device not connected: {serial}")


def maestro_argv(
    maestro: str,
    serial: str,
    flow: str,
    junit_path: Path,
    debug_dir: Path,
) -> list[str]:
    return [
        maestro,
        "--device",
        serial,
        "test",
        "--format",
        "junit",
        "--output",
        str(junit_path),
        "--debug-output",
        str(debug_dir),
        flow,
    ]


def run(*, serial: str, flow: str, out: str | Path) -> tuple[int, str]:
    """Run maestro and return (exit_code, message).

    Exit 3 when maestro or adb is missing, or the serial is not a connected
    device. Exit 1 when the JUnit report contains a failure or an error, or no
    executed test cases.
    Exit 2 when the caller's paths or serial are unusable. Reports and the
    debug directory are created only as children of --out.
    """
    if not _serial_ok(serial):
        return 2, f"error: invalid serial {serial!r}"
    try:
        flow_path = Path(flow).resolve()
    except (OSError, RuntimeError) as exc:
        return 2, f"error: flow path is not usable: {exc}"
    if not flow_path.exists() or not (flow_path.is_file() or flow_path.is_dir()):
        return 2, f"error: flow not found: {flow}"
    try:
        root = prepare_out(out)
        junit_path = output_path(root, JUNIT_NAME)
        debug_dir = output_path(root, DEBUG_DIR_NAME)
    except UsageError as exc:
        return 2, f"error: {exc}"
    if debug_dir.exists() and not debug_dir.is_dir():
        return 2, f"error: debug output path is not a directory: {debug_dir}"
    try:
        _require_device(serial)
    except Skip as exc:
        return SKIP_EXIT, f"skipped: {exc}"
    maestro = shutil.which("maestro")
    if not maestro:
        return SKIP_EXIT, "skipped: missing binary: maestro"
    maestro = str(Path(maestro).resolve())
    try:
        if junit_path.exists():
            if junit_path.is_symlink() or not junit_path.is_file():
                raise UsageError(f"refusing to replace {junit_path}")
            try:
                junit_path.unlink()
            except OSError as exc:
                raise UsageError(f"cannot remove previous JUnit report: {exc}") from exc
        try:
            debug_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise UsageError(f"--out debug directory is not usable: {exc}") from exc
    except UsageError as exc:
        return 2, f"error: {exc}"
    argv = maestro_argv(maestro, serial, str(flow_path), junit_path, debug_dir)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 1, "maestro timed out"
    except OSError as exc:
        return 1, f"maestro failed to start: {exc}"
    if not junit_path.is_file():
        err = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode != 0:
            return proc.returncode, err or f"maestro exited {proc.returncode} without a JUnit report"
        return 1, "maestro exited 0 without a JUnit report"
    failed, summary = junit_has_failure(junit_path)
    if failed:
        return 1, summary
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return proc.returncode, err or f"maestro exited {proc.returncode}"
    return 0, f"wrote {junit_path}"
