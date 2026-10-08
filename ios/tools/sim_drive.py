"""Drive the iOS Simulator through ``xcrun simctl``.

``boot`` creates a device from the caller's ``--device-type`` and ``--runtime``
(or reuses one this run already created) and prints its UDID. ``shutdown`` and
``erase`` touch only that UDID, and only when the caller passes it explicitly
and it is in the ledger ``boot`` wrote under ``--out``.

On Linux, or when ``xcrun`` is missing, every subcommand skips with exit 3.
``--dry-run`` prints the argv as JSON and spawns nothing. A skip is not a pass.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

SKIP = 3
LEDGER_NAME = "created-udids.json"
UDID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def _tail(proc) -> str:
    stdout = getattr(proc, "stdout", None) or ""
    stderr = getattr(proc, "stderr", None) or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    return (stdout + stderr)[-2000:]


def _dry(argv: list[str], **extra) -> dict:
    body = {"status": "dry-run", "argv": argv, "exit_code": 0, "invoked": False}
    body.update(extra)
    return body


def _skipped(reason: str, argv: list[str]) -> dict:
    return {
        "status": "skipped",
        "reason": f"skipped: {reason}",
        "argv": argv,
        "exit_code": SKIP,
        "invoked": False,
    }


def _error(reason: str, **extra) -> dict:
    body = {"status": "error", "reason": reason, "exit_code": 2, "invoked": False}
    body.update(extra)
    return body


def _failed(reason: str, argv: list[str], proc, **extra) -> dict:
    body = {
        "status": "failed",
        "reason": reason,
        "argv": argv,
        "exit_code": 1,
        "invoked": True,
        "tool_exit_code": getattr(proc, "returncode", None),
        "output_tail": _tail(proc),
    }
    body.update(extra)
    return body


def _system(system_name: str | None) -> str:
    return system_name if system_name is not None else platform.system()


def _blocked(binary: str, argv: list[str], *, dry_run: bool, system_name: str | None, which) -> dict | None:
    """Skip when a real spawn would need macOS or a missing binary. Dry-run is not a skip."""
    if dry_run:
        return None
    if _system(system_name) != "Darwin":
        return _skipped("not on macOS", argv)
    if not which(binary):
        return _skipped(f"{binary} is not on PATH", argv)
    return None


def _resolve(which, binary: str, argv: list[str]) -> list[str]:
    found = which(binary)
    if not found:
        return list(argv)
    return [found, *argv[1:]]


def _run(runner, argv: list[str], *, timeout: int | None = None):
    kwargs = {
        "capture_output": True,
        "text": True,
        "check": False,
        "env": os.environ.copy(),
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return runner(argv, **kwargs)


def _state_text(proc) -> str:
    return _tail(proc).lower()


def _already(proc, state: str) -> bool:
    return f"current state: {state.lower()}" in _state_text(proc)


def ledger_path(out: Path) -> Path:
    return Path(out) / LEDGER_NAME


def _load_ledger(out: Path) -> list[dict]:
    path = ledger_path(out)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict) and isinstance(row.get("udid"), str)]


def _save_ledger(out: Path, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    ledger_path(out).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _runtime_compatible(flag: str, runtime_key: str) -> bool:
    flag_n = re.sub(r"[^a-z0-9]", "", flag.lower())
    key_n = re.sub(r"[^a-z0-9]", "", runtime_key.lower())
    return bool(flag_n) and flag_n in key_n


def _match_existing(list_stdout: str, ledger: list[dict], device_type: str, runtime: str) -> str | None:
    wanted = {
        row["udid"]
        for row in ledger
        if row.get("device_type") == device_type and row.get("runtime") == runtime
    }
    if not wanted or not list_stdout:
        return None
    try:
        data = json.loads(list_stdout)
    except json.JSONDecodeError:
        return None
    devices = data.get("devices") if isinstance(data, dict) else None
    if not isinstance(devices, dict):
        return None
    for runtime_key, entries in devices.items():
        if not _runtime_compatible(runtime, str(runtime_key)):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("udid") in wanted:
                return str(entry["udid"])
    return None


def _require_out_dir(out: Path | None) -> dict | None:
    if out is None:
        return _error("--out is required so evidence stays in the directory the caller passed")
    if Path(out).exists() and not Path(out).is_dir():
        return _error(f"--out is not a directory: {out}")
    return None


def _child(out: Path, name: str) -> Path | None:
    root = Path(out).resolve()
    child = (Path(out) / name).resolve()
    try:
        child.relative_to(root)
    except ValueError:
        return None
    return child


def _parse_udid(stdout: str) -> str | None:
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if not lines:
        return None
    candidate = lines[-1]
    if UDID_RE.match(candidate):
        return candidate
    return None


def boot(
    device_type: str,
    runtime: str,
    out: Path | None = None,
    name: str | None = None,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not device_type or not runtime:
        return _error("--device-type and --runtime are required")
    label = name or device_type
    create_argv = ["xcrun", "simctl", "create", label, device_type, runtime]
    boot_argv_template = ["xcrun", "simctl", "boot", "<udid-from-create>"]
    if dry_run:
        return _dry(create_argv, boot_argv=boot_argv_template)
    blocked = _blocked("xcrun", create_argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    out = Path(out)
    list_argv = _resolve(which, "xcrun", ["xcrun", "simctl", "list", "devices", "-j"])
    listed = _run(runner, list_argv)
    reused = None
    if getattr(listed, "returncode", 1) == 0:
        reused = _match_existing(getattr(listed, "stdout", "") or "", _load_ledger(out), device_type, runtime)
    if reused:
        udid = reused
        created = False
        create_used: list[str] | None = None
    else:
        create_used = _resolve(which, "xcrun", create_argv)
        created_proc = _run(runner, create_used)
        if created_proc.returncode != 0:
            return _failed("simctl create failed", create_used, created_proc)
        udid = _parse_udid(getattr(created_proc, "stdout", "") or "")
        if not udid:
            return _failed("simctl create did not print a UDID", create_used, created_proc)
        rows = _load_ledger(out)
        rows.append({"udid": udid, "device_type": device_type, "runtime": runtime, "name": label})
        _save_ledger(out, rows)
        created = True
    boot_argv = _resolve(which, "xcrun", ["xcrun", "simctl", "boot", udid])
    booted = _run(runner, boot_argv)
    if booted.returncode != 0 and not _already(booted, "Booted"):
        return _failed("simctl boot failed", boot_argv, booted, udid=udid, created=created)
    return {
        "status": "booted",
        "udid": udid,
        "created": created,
        "reused": not created,
        "device_type": device_type,
        "runtime": runtime,
        "argv": create_used or boot_argv,
        "boot_argv": boot_argv,
        "exit_code": 0,
        "invoked": True,
        "ledger": str(ledger_path(out)),
    }


def install(
    udid: str,
    app: str,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid or not app:
        return _error("--udid and --app are required")
    argv = ["xcrun", "simctl", "install", udid, app]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl install failed", resolved, proc)
    return {"status": "installed", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid}


def launch(
    udid: str,
    bundle_id: str,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid or not bundle_id:
        return _error("--udid and --bundle-id are required")
    argv = ["xcrun", "simctl", "launch", udid, bundle_id]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl launch failed", resolved, proc)
    return {"status": "launched", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid}


def screenshot(
    udid: str,
    out: Path | None,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid:
        return _error("--udid is required")
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    shot = _child(Path(out), "screenshot.png")
    if shot is None:
        return _error("screenshot path escaped --out")
    argv = ["xcrun", "simctl", "io", udid, "screenshot", str(shot)]
    if dry_run:
        return _dry(argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    Path(out).mkdir(parents=True, exist_ok=True)
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0:
        return _failed("simctl screenshot failed", resolved, proc)
    return {"status": "recorded", "argv": resolved, "exit_code": 0, "invoked": True, "artifact": str(shot)}


def record(
    udid: str,
    out: Path | None,
    seconds: int,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not udid:
        return _error("--udid is required")
    if not isinstance(seconds, int) or seconds < 1:
        return _error("--seconds must be an integer of 1 or more; it is the hard cap on recordVideo")
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    assert out is not None
    video = _child(Path(out), "recording.mov")
    if video is None:
        return _error("recording path escaped --out")
    argv = ["xcrun", "simctl", "io", udid, "recordVideo", str(video)]
    if dry_run:
        return _dry(argv, seconds=seconds)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    Path(out).mkdir(parents=True, exist_ok=True)
    resolved = _resolve(which, "xcrun", argv)
    try:
        proc = _run(runner, resolved, timeout=seconds)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills the child when the timeout fires. That kill is the cap.
        return {
            "status": "recorded",
            "reason": f"stopped at --seconds cap ({seconds})",
            "argv": resolved,
            "exit_code": 0,
            "invoked": True,
            "seconds": seconds,
            "artifact": str(video),
            "output_tail": _tail(exc),
        }
    if proc.returncode != 0:
        return _failed("simctl recordVideo failed", resolved, proc, seconds=seconds)
    return {
        "status": "recorded",
        "argv": resolved,
        "exit_code": 0,
        "invoked": True,
        "seconds": seconds,
        "artifact": str(video),
    }


def _created_here(out: Path, udid: str, created_udid: str) -> dict | None:
    if not udid or not created_udid or udid != created_udid:
        return _error(
            "refusing to shutdown or erase a UDID this run did not create; "
            "pass the UDID boot printed as both --udid and --created-udid"
        )
    out_err = _require_out_dir(out)
    if out_err:
        return out_err
    rows = _load_ledger(Path(out))
    if not any(row.get("udid") == udid for row in rows):
        return _error(
            "refusing to shutdown or erase a UDID that is not in the created-udid ledger under --out"
        )
    return None


def shutdown(
    udid: str,
    created_udid: str,
    out: Path | None,
    erase: bool = False,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if out is None:
        return _error("--out is required so shutdown can read the created-udid ledger")
    refused = _created_here(Path(out), udid, created_udid)
    if refused:
        return refused
    argv = ["xcrun", "simctl", "shutdown", udid]
    erase_argv = ["xcrun", "simctl", "erase", udid] if erase else None
    if dry_run:
        return _dry(argv, erase_argv=erase_argv)
    blocked = _blocked("xcrun", argv, dry_run=False, system_name=system_name, which=which)
    if blocked:
        return blocked
    resolved = _resolve(which, "xcrun", argv)
    proc = _run(runner, resolved)
    if proc.returncode != 0 and not _already(proc, "Shutdown"):
        return _failed("simctl shutdown failed", resolved, proc)
    if not erase:
        return {"status": "shutdown", "argv": resolved, "exit_code": 0, "invoked": True, "udid": udid, "erased": False}
    erase_resolved = _resolve(which, "xcrun", ["xcrun", "simctl", "erase", udid])
    erased = _run(runner, erase_resolved)
    if erased.returncode != 0:
        return _failed("simctl erase failed", erase_resolved, erased, udid=udid)
    return {
        "status": "erased",
        "argv": erase_resolved,
        "shutdown_argv": resolved,
        "exit_code": 0,
        "invoked": True,
        "udid": udid,
        "erased": True,
    }
