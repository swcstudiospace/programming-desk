"""Map local Android tool names to documented MetaVR tool ids.

This module does NOT call MCP or the network. Device presence is checked
via `adb devices -l` (the same transport a Quest/MetaVR headset uses when
plugged in and USB-debugging is enabled), so bridge calls can actually run
once a device is connected instead of always raising.
"""

from __future__ import annotations

from . import adb
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

# Test hook: when set (True/False) overrides the real adb-based detection
# below. None (the default) means "use the real check".
_DEVICE_CONNECTED_OVERRIDE: bool | None = None


def tool_id(name: str) -> str:
    """Return the documented MetaVR tool id for a local name."""
    key = name.strip()
    if key not in _TOOL_IDS:
        raise KeyError(f"unknown MetaVR bridge name: {name!r}")
    return _TOOL_IDS[key]


def _device_connected(serial: str | None = None) -> bool:
    """Real connectivity check via `adb devices -l`.

    Returns False (never raises) when adb is missing or the command fails,
    since that is exactly the "no device" case callers already skip on.
    """
    if _DEVICE_CONNECTED_OVERRIDE is not None:
        return _DEVICE_CONNECTED_OVERRIDE
    try:
        proc = adb.run_adb(["devices", "-l"], check=False)
    except DeviceUnavailable:
        return False
    if proc.returncode != 0:
        return False
    devices = adb.parse_adb_devices(proc.stdout or "")
    if serial:
        return any(d.serial == serial and d.state == "device" for d in devices)
    return any(d.state == "device" for d in devices)


def require_device(for_tool: str | None = None, *, serial: str | None = None) -> None:
    """Raise DeviceUnavailable naming the tool id when no device is connected."""
    tid = tool_id(for_tool) if for_tool else "metavr_device"
    if not _device_connected(serial=serial):
        raise DeviceUnavailable(
            f"no MetaVR/Quest device connected for tool id {tid}"
        )


def set_device_connected(connected: bool) -> None:
    """Test hook: force the connectivity check to a fixed value."""
    global _DEVICE_CONNECTED_OVERRIDE
    _DEVICE_CONNECTED_OVERRIDE = bool(connected)


def reset_device_override() -> None:
    """Test hook: restore real adb-based detection."""
    global _DEVICE_CONNECTED_OVERRIDE
    _DEVICE_CONNECTED_OVERRIDE = None


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
