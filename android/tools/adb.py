"""adb helpers — argv builders and device listing. No shell=True."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from typing import Sequence


class DeviceUnavailable(Exception):
    """Raised when a required binary or connected device is missing."""


# Substrings adb prints when a command failed because no device was present,
# as opposed to a real command failure on a connected device. Anything not
# matching one of these is treated as a genuine failure, not a skip.
_MISSING_DEVICE_HINTS = (
    "no devices/emulators found",
    "device not found",
    "device offline",
    "device unauthorized",
    "no device",
)


def is_missing_device_error(message: str) -> bool:
    """True when an adb error message indicates no device was present.

    Used to tell a documented missing-device skip apart from a real command
    failure on a connected device, which must be reported, not swallowed.
    """
    lowered = (message or "").lower()
    return any(hint in lowered for hint in _MISSING_DEVICE_HINTS)


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str
    extras: dict[str, str]


def which_or_raise(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        raise DeviceUnavailable(f"missing binary: {binary}")
    return path


def build_adb_argv(
    *args: str,
    serial: str | None = None,
    adb: str = "adb",
) -> list[str]:
    """Build an adb argv list. Omits -s when serial is empty/None."""
    argv = [adb]
    if serial:
        argv.extend(["-s", serial])
    argv.extend(args)
    return argv


def parse_adb_devices(text: str) -> list[AdbDevice]:
    """Parse `adb devices -l` output into structured rows."""
    devices: list[AdbDevice] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state, *rest = parts
        extras: dict[str, str] = {}
        for token in rest:
            if ":" in token:
                key, _, value = token.partition(":")
                extras[key] = value
            else:
                extras.setdefault("flags", "")
                extras["flags"] = (extras["flags"] + " " + token).strip()
        devices.append(AdbDevice(serial=serial, state=state, extras=extras))
    return devices


def run_adb(
    args: Sequence[str],
    *,
    serial: str | None = None,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    which_or_raise("adb")
    argv = build_adb_argv(*args, serial=serial)
    try:
        return subprocess.run(
            argv,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise DeviceUnavailable("missing binary: adb") from exc
    except subprocess.TimeoutExpired as exc:
        raise DeviceUnavailable(f"adb timed out: {' '.join(argv)}") from exc


def adb_devices_list(*, as_json: bool = False) -> str:
    """Run `adb devices -l` and return a structured print string or JSON."""
    proc = run_adb(["devices", "-l"], check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise DeviceUnavailable(f"adb devices failed: {err}")
    devices = parse_adb_devices(proc.stdout or "")
    if as_json:
        return json.dumps([asdict(d) for d in devices], indent=2)
    if not devices:
        return "no devices"
    lines = []
    for d in devices:
        extra = " ".join(f"{k}:{v}" for k, v in d.extras.items())
        lines.append(f"{d.serial}\t{d.state}" + (f"\t{extra}" if extra else ""))
    return "\n".join(lines)


def emu_boot_argv(avd: str, emulator: str = "emulator") -> list[str]:
    return [emulator, "-avd", avd]


def install_apk_argv(apk: str, serial: str | None = None) -> list[str]:
    return build_adb_argv("install", "-r", apk, serial=serial)


def instrument_argv(
    component: str,
    *,
    serial: str | None = None,
) -> list[str]:
    # `adb shell am instrument -w <component>`
    return build_adb_argv("shell", "am", "instrument", "-w", component, serial=serial)


def logcat_argv(*, serial: str | None = None) -> list[str]:
    """Dump the current logcat buffer and exit (no timed window)."""
    return build_adb_argv("logcat", "-d", serial=serial)


def logcat_stream_argv(*, serial: str | None = None) -> list[str]:
    """Stream logcat continuously, for a caller-managed capture window."""
    return build_adb_argv("logcat", serial=serial)


def capture_logcat_for(seconds: float, *, serial: str | None = None) -> tuple[str, int, str]:
    """Stream logcat for `seconds` and return (text, returncode, stderr).

    Unlike `adb logcat -d` (dump-and-exit), this actually records events for
    the requested window instead of returning whatever was already buffered.
    returncode is 0 when the window elapsed normally; nonzero only when the
    adb process itself exited early with an error.
    """
    which_or_raise("adb")
    argv = logcat_stream_argv(serial=serial)
    try:
        proc = subprocess.Popen(  # noqa: S603
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError as exc:
        raise DeviceUnavailable("missing binary: adb") from exc

    out_chunks: list[str] = []
    err_chunks: list[str] = []

    def _drain(pipe, sink: list[str]) -> None:
        for line in iter(pipe.readline, ""):
            sink.append(line)

    out_thread = threading.Thread(target=_drain, args=(proc.stdout, out_chunks), daemon=True)
    err_thread = threading.Thread(target=_drain, args=(proc.stderr, err_chunks), daemon=True)
    out_thread.start()
    err_thread.start()

    deadline = time.monotonic() + max(seconds, 0)
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)

    early_exit = proc.poll()
    if early_exit is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        returncode = 0
    else:
        returncode = early_exit

    out_thread.join(timeout=1)
    err_thread.join(timeout=1)
    return "".join(out_chunks), returncode, "".join(err_chunks).strip()


def screenshot_argv(*, serial: str | None = None) -> list[str]:
    return build_adb_argv("exec-out", "screencap", "-p", serial=serial)
