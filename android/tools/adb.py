"""adb helpers — argv builders and device listing. No shell=True."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Sequence


class DeviceUnavailable(Exception):
    """Raised when a required binary or connected device is missing."""


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


def logcat_argv(*, serial: str | None = None, dump: bool = True) -> list[str]:
    """Build a logcat argv. `dump=True` -> one-shot `-d` dump and exit;
    `dump=False` -> a live stream, for a timed capture window."""
    args = ["logcat"]
    if dump:
        args.append("-d")
    return build_adb_argv(*args, serial=serial)


def screenshot_argv(*, serial: str | None = None) -> list[str]:
    return build_adb_argv("exec-out", "screencap", "-p", serial=serial)
