"""Record the device screen and pull the file into --out. Seconds cap at 180."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from . import adb
from .maestro_flow import Skip, UsageError, _serial_ok, output_path, prepare_out

SKIP_EXIT = 3
MAX_SECONDS = 180
DEFAULT_SECONDS = 30
LOCAL_NAME = "screenrecord.mp4"


def run(
    *,
    serial: str,
    out: str | Path,
    seconds: int = DEFAULT_SECONDS,
) -> tuple[int, str]:
    """Record, pull into --out, then remove the device-side file.

    Exit 3 when adb is missing or the serial is not connected. Exit 2 when
    --seconds is outside 1..180 or local output preparation/cleanup fails.
    Pull to a fresh file under --out, then atomically replace screenrecord.mp4
    only after a successful, nonempty pull. Remote cleanup is always attempted;
    an interruption exits 130 rather than claiming a successful recording.
    """
    if type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
        return 2, f"error: --seconds must be an integer from 1 to {MAX_SECONDS}"
    if not _serial_ok(serial):
        return 2, f"error: invalid serial {serial!r}"
    try:
        root = prepare_out(out)
        local = output_path(root, LOCAL_NAME)
    except UsageError as exc:
        return 2, f"error: {exc}"
    if local.exists() and (local.is_symlink() or not local.is_file()):
        return 2, f"error: refusing to replace {local}"
    binary = shutil.which("adb")
    if not binary:
        return SKIP_EXIT, "skipped: missing binary: adb"
    try:
        _require_device(binary, serial)
    except Skip as exc:
        return SKIP_EXIT, f"skipped: {exc}"
    remote = f"/sdcard/desk-screenrecord-{uuid.uuid4().hex}.mp4"
    record_argv = adb.build_adb_argv(
        "shell",
        "screenrecord",
        "--time-limit",
        str(seconds),
        remote,
        serial=serial,
        adb=binary,
    )
    temporary: Path | None = None
    code = 1
    message = ""
    try:
        try:
            recorded = subprocess.run(
                record_argv,
                capture_output=True,
                text=True,
                timeout=seconds + 30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            message = "screenrecord timed out"
        except OSError as exc:
            message = f"screenrecord failed to start: {exc}"
        else:
            if recorded.returncode != 0:
                err = (recorded.stderr or recorded.stdout or "").strip()
                message = err or f"screenrecord exited {recorded.returncode}"
            else:
                with tempfile.NamedTemporaryFile(
                    dir=root, prefix=".screenrecord-", suffix=".mp4", delete=False
                ) as destination:
                    temporary = Path(destination.name)
                pull_argv = adb.build_adb_argv(
                    "pull",
                    remote,
                    str(temporary),
                    serial=serial,
                    adb=binary,
                )
                try:
                    pulled = subprocess.run(
                        pull_argv,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    message = f"adb pull failed: {exc}"
                else:
                    if pulled.returncode != 0:
                        err = (pulled.stderr or pulled.stdout or "").strip()
                        message = err or f"adb pull exited {pulled.returncode}"
                    elif temporary.is_symlink() or not temporary.is_file() or not temporary.stat().st_size:
                        message = "adb pull did not write a nonempty screenrecord.mp4"
                    elif temporary.resolve().parent != root:
                        message = f"error: pull wrote outside --out: {temporary.resolve()}"
                    else:
                        temporary.replace(local)
                        code = 0
                        message = f"wrote {local}"
    except OSError as exc:
        code = 2
        message = f"error: --out recording file is not usable: {exc}"
    except KeyboardInterrupt:
        code = 130
        message = "screenrecord interrupted"
    finally:
        try:
            removed, remove_err = _remove_remote(binary, serial, remote)
        except KeyboardInterrupt:
            removed, remove_err = False, "device cleanup interrupted"
            code = 130
            message = f"{message} (interrupted)"
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                message = f"{message} (error: cannot remove temporary recording: {exc})"
                if code != 130:
                    code = 2
    if not removed:
        message = f"{message} (device file may remain: {remove_err})"
    return code, message


def _require_device(binary: str, serial: str) -> None:
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


def _remove_remote(binary: str, serial: str, remote: str) -> tuple[bool, str]:
    """Best-effort delete of the file this command created on the device."""
    if not remote.startswith("/sdcard/desk-screenrecord-") or not remote.endswith(".mp4"):
        return False, "refusing to remove an unexpected device path"
    try:
        proc = subprocess.run(
            adb.build_adb_argv("shell", "rm", remote, serial=serial, adb=binary),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return False, err
    return True, ""
