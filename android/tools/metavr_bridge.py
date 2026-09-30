"""Map local Android tool names to documented MetaVR tool ids.

This module does NOT call MCP, the network, or a metavr binary. It only
resolves names and raises DeviceUnavailable when no device is connected.
"""

from __future__ import annotations

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

# Local-only bridge: never auto-detects a Quest/MetaVR device.
_DEVICE_CONNECTED: bool = False


def tool_id(name: str) -> str:
    """Return the documented MetaVR tool id for a local name."""
    key = name.strip()
    if key not in _TOOL_IDS:
        raise KeyError(f"unknown MetaVR bridge name: {name!r}")
    return _TOOL_IDS[key]


def require_device(for_tool: str | None = None) -> None:
    """Raise DeviceUnavailable naming the tool id when no device is connected."""
    tid = tool_id(for_tool) if for_tool else "metavr_device"
    if not _DEVICE_CONNECTED:
        raise DeviceUnavailable(
            f"no MetaVR/Quest device connected for tool id {tid}"
        )


def set_device_connected(connected: bool) -> None:
    """Test hook: mark whether a device is considered connected."""
    global _DEVICE_CONNECTED
    _DEVICE_CONNECTED = bool(connected)


def screenshot(*, serial: str | None = None, out: str | None = None) -> str:
    """Resolve device_screenshot; raise when no device is connected."""
    tid = tool_id("screenshot")
    require_device("screenshot")
    return tid


def logcat(*, serial: str | None = None, out: str | None = None, seconds: int | None = None) -> str:
    """Resolve device_logcat; raise when no device is connected."""
    tid = tool_id("logcat")
    require_device("logcat")
    return tid


def ui_dump(*, serial: str | None = None, out: str | None = None) -> str:
    """Resolve ui_dump; raise when no device is connected."""
    tid = tool_id("ui_dump")
    require_device("ui_dump")
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
    require_device("ui_tap")
    return tid
