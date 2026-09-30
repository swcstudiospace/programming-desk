"""Parse and validate an Info.plist already on disk."""

from __future__ import annotations

import plistlib
from pathlib import Path

USAGE_KEYS = (
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSPhotoLibraryUsageDescription",
    "NSPhotoLibraryAddUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSLocationAlwaysAndWhenInUseUsageDescription",
    "NSLocationAlwaysUsageDescription",
    "NSUserTrackingUsageDescription",
    "NSBluetoothAlwaysUsageDescription",
    "NSBluetoothPeripheralUsageDescription",
    "NSFaceIDUsageDescription",
    "NSLocalNetworkUsageDescription",
    "NSContactsUsageDescription",
    "NSCalendarsUsageDescription",
    "NSRemindersUsageDescription",
    "NSMotionUsageDescription",
    "NSHealthShareUsageDescription",
    "NSHealthUpdateUsageDescription",
    "NSHealthClinicalHealthRecordsShareUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSSiriUsageDescription",
    "NSHomeKitUsageDescription",
    "NSAppleMusicUsageDescription",
    "NSVideoSubscriberAccountUsageDescription",
    "NSNearbyInteractionUsageDescription",
    "NSSensorKitUsageDescription",
)


def lint_path(path: Path) -> dict:
    path = path.resolve()
    if not path.is_file():
        return {"status": "error", "reason": f"Info.plist not found: {path}", "findings": []}
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception as exc:
        return {"status": "failed", "reason": f"plist did not parse: {exc}", "path": str(path), "findings": []}
    if not isinstance(data, dict):
        return {"status": "failed", "reason": "Info.plist root is not a dictionary", "path": str(path), "findings": []}

    findings = []
    for key in USAGE_KEYS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            findings.append({"severity": "error", "key": key, "message": "usage description is blank"})
    always = "NSLocationAlwaysAndWhenInUseUsageDescription" in data or "NSLocationAlwaysUsageDescription" in data
    if always and "NSLocationWhenInUseUsageDescription" not in data:
        findings.append({
            "severity": "warning",
            "key": "NSLocationWhenInUseUsageDescription",
            "message": "always-location usage is present without a when-in-use usage string",
        })
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "status": "failed" if errors else "ok",
        "path": str(path),
        "key_count": len(data),
        "findings": findings,
        "submitted": False,
    }
