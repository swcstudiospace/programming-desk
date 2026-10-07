#!/usr/bin/env python3
"""Lint Info.plist usage strings and entitlements XML.

Reads plists already on disk. Does not sign, archive, or talk to App Store Connect.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import sys
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
    "NSCalendarsUsageDescription",
    "NSContactsUsageDescription",
    "NSFaceIDUsageDescription",
    "NSMotionUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSLocalNetworkUsageDescription",
)

PRIVATE_KEY_MARKERS = (b"BEGIN PRIVATE KEY", b"BEGIN RSA PRIVATE KEY", b"BEGIN CERTIFICATE")


def _finding(severity: str, path: Path, message: str, key: str | None = None) -> dict:
    row = {"severity": severity, "path": str(path), "message": message}
    if key:
        row["key"] = key
    return row


def _load(path: Path) -> tuple[object | None, list[dict]]:
    raw = path.read_bytes()
    for marker in PRIVATE_KEY_MARKERS:
        if marker in raw:
            return None, [_finding("error", path, "file contains a key or certificate block")]
    try:
        return plistlib.loads(raw), []
    except Exception as exc:  # plistlib raises several exception types
        return None, [_finding("error", path, f"plist did not parse: {exc}")]


def lint_info_plist(path: Path) -> list[dict]:
    data, errors = _load(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [_finding("error", path, "Info.plist root is not a dictionary")]
    findings: list[dict] = []
    for key in USAGE_KEYS:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or not value.strip():
            findings.append(_finding("error", path, "usage description is missing or blank", key))
    always = "NSLocationAlwaysAndWhenInUseUsageDescription" in data or "NSLocationAlwaysUsageDescription" in data
    if always and "NSLocationWhenInUseUsageDescription" not in data:
        findings.append(
            _finding(
                "warning",
                path,
                "always-location usage is present without a when-in-use usage string",
                "NSLocationWhenInUseUsageDescription",
            )
        )
    return findings


def lint_entitlements(path: Path) -> list[dict]:
    data, errors = _load(path)
    if errors:
        return errors
    if not isinstance(data, dict):
        return [_finding("error", path, "entitlements root is not a dictionary")]
    findings = [_finding("info", path, f"entitlement present: {key}", key) for key in sorted(data)]
    return findings


def lint_tree(root: Path) -> dict:
    info_findings: list[dict] = []
    ent_findings: list[dict] = []
    if not root.exists():
        return {
            "status": "error",
            "reason": f"path does not exist: {root}",
            "findings": [],
        }
    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
    for path in files:
        name = path.name
        if name == "Info.plist" or name.endswith(".plist") and "Info" in name:
            info_findings.extend(lint_info_plist(path))
        elif path.suffix == ".entitlements" or name.endswith(".entitlements"):
            ent_findings.extend(lint_entitlements(path))
    findings = info_findings + ent_findings
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "status": "failed" if errors else "ok",
        "error_count": len(errors),
        "findings": findings,
        "signed": False,
        "submitted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint Info.plist usage strings and entitlements")
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    result = lint_tree(args.root)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if result["status"] == "error":
        return 2
    if result["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
