"""Map local Android tool names to documented MetaVR tool ids.

This module does NOT call MCP, the network, or a metavr binary. It only
resolves names and raises DeviceUnavailable when no device is connected.
"""

from __future__ import annotations

from . import adb as _adb
from .adb import DeviceUnavailable

# Constraint: only these documented MetaVR tool ids may appear in the map.
_TOOL_IDS: dict[str, str] = {
    "logcat": "device_logcat",
    "device_logcat": "device_logcat",
    "screenshot": "device_screenshot",
    "device_screenshot": "device_screenshot",
    "ui_dump": "ui_dump",
    "ui_tap": "ui_tap",
    "device": "metavr_device",
    "metavr_device": "metavr_device",
}

# None = auto-detect via `adb devices` (a Quest/MetaVR headset in USB
# debugging mode enumerates over adb like any other device). True/False
# force the state, for tests or for callers that know better than adb.
_DEVICE_CONNECTED: bool | None = None


def tool_id(name: str) -> str:
    """Return the documented MetaVR tool id for a local name."""
    key = name.strip()
    if key not in _TOOL_IDS:
        raise KeyError(f"unknown MetaVR bridge name: {name!r}")
    return _TOOL_IDS[key]


def _adb_device_connected(serial: str | None) -> bool:
    try:
        proc = _adb.run_adb(["devices", "-l"], check=False)
    except DeviceUnavailable:
        return False
    if proc.returncode != 0:
        return False
    for device in _adb.parse_adb_devices(proc.stdout or ""):
        if device.state != "device":
            continue
        if serial and device.serial != serial:
            continue
        return True
    return False


def is_device_connected(serial: str | None = None) -> bool:
    """Whether a device is considered connected for MetaVR bridge calls."""
    if _DEVICE_CONNECTED is not None:
        return _DEVICE_CONNECTED
    return _adb_device_connected(serial)


def require_device(for_tool: str | None = None, *, serial: str | None = None) -> None:
    """Raise DeviceUnavailable naming the tool id when no device is connected."""
    tid = tool_id(for_tool) if for_tool else "metavr_device"
    if not is_device_connected(serial):
        raise DeviceUnavailable(
            f"no MetaVR/Quest device connected for tool id {tid}"
        )


def set_device_connected(connected: bool | None) -> None:
    """Force the connected state (True/False), or None to auto-detect via adb."""
    global _DEVICE_CONNECTED
    _DEVICE_CONNECTED = None if connected is None else bool(connected)


def screenshot(*, serial: str | None = None, out: str | None = None) -> str:
    """Resolve device_screenshot; raise when no device is connected."""
    tid = tool_id("screenshot")
    require_device("screenshot", serial=serial)
    return tid


def logcat(*, serial: str | None = None, out: str | None = None, seconds: int | None = None) -> str:
    """Resolve device_logcat; raise when no device is connected."""
    tid = tool_id("logcat")
    require_device("logcat", serial=serial)
    return tid


def ui_dump(*, serial: str | None = None, out: str | None = None) -> str:
    """Resolve ui_dump; raise when no device is connected."""
    tid = tool_id("ui_dump")
    require_device("ui_dump", serial=serial)
    return tid


def ui_tap(
    *,
    serial: str | None = None,
    resource_id: str | None = None,
    text: str | None = None,
) -> str:
    """Resolve ui_tap; require resource_id or text; raise when no device."""
    if not resource_id and not text:
        raise ValueError("ui_tap requires --resource-id or --text")
    tid = tool_id("ui_tap")
    require_device("ui_tap", serial=serial)
    return tid
