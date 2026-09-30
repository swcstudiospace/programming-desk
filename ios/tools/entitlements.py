"""Scan entitlements and usage strings. Optional diff of two trees or files."""

from __future__ import annotations

import base64
import datetime
import plistlib
from pathlib import Path

from ios.tools.plist_lint import USAGE_KEYS


def _load(path: Path) -> dict | None:
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _json_safe(value):
    if isinstance(value, (bytes, bytearray)):
        return {"__type__": "data", "base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime.datetime):
        return {"__type__": "date", "iso": value.isoformat()}
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _values_equal(a, b) -> bool:
    return type(a) is type(b) and a == b


def _collect(path: Path, solo_key: str | None = None) -> dict:
    path = path.resolve()
    is_file = path.is_file()
    root = path.parent if is_file else path
    files = [path] if is_file else [p for p in path.rglob("*") if p.is_file()]
    entitlements: dict[str, dict] = {}
    usage: dict[str, dict] = {}
    unreadable: list[str] = []
    for item in files:
        target = solo_key if (is_file and solo_key is not None) else item.relative_to(root).as_posix()
        if item.suffix == ".entitlements":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            entitlements[target] = dict(data)
        elif item.name == "Info.plist":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            usage[target] = {k: data[k] for k in USAGE_KEYS if k in data}
    return {
        "entitlements": entitlements,
        "usage": usage,
        "unreadable": unreadable,
    }


def _flat_keys(by_target: dict[str, dict]) -> set[str]:
    keys: set[str] = set()
    for values in by_target.values():
        keys.update(values)
    return keys


def _usage_findings(by_target: dict[str, dict]) -> list[dict]:
    findings = []
    for target, values in sorted(by_target.items()):
        for key in sorted(values):
            value = values[key]
            if not isinstance(value, str) or not value.strip():
                findings.append({"target": target, "key": key, "message": "usage description is blank"})
    return findings


def _entitlement_delta(a: dict[str, dict], b: dict[str, dict]) -> dict:
    result = {}
    for target in sorted(set(a) | set(b)):
        left_vals, right_vals = a.get(target, {}), b.get(target, {})
        added = sorted(set(right_vals) - set(left_vals))
        removed = sorted(set(left_vals) - set(right_vals))
        changed = [
            {"key": key, "before": _json_safe(left_vals[key]), "after": _json_safe(right_vals[key])}
            for key in sorted(set(left_vals) & set(right_vals))
            if not _values_equal(left_vals[key], right_vals[key])
        ]
        if added or removed or changed:
            result[target] = {"added": added, "removed": removed, "changed": changed}
    return result


def _public(collected: dict) -> dict:
    return {
        "entitlements": sorted(_flat_keys(collected["entitlements"])),
        "usage": sorted(_flat_keys(collected["usage"])),
        "usage_findings": _usage_findings(collected["usage"]),
        "targets": {
            "entitlements": sorted(collected["entitlements"]),
            "usage": sorted(collected["usage"]),
        },
        "unreadable": collected["unreadable"],
    }


def scan(path: Path) -> dict:
    if not path.exists():
        return {"status": "error", "reason": f"path not found: {path}"}
    collected = _collect(path)
    result = {"status": "ok", "path": str(path.resolve()), **_public(collected)}
    if collected["unreadable"] or result["usage_findings"]:
        result["status"] = "failed"
    return result


def diff(base: Path, head: Path) -> dict:
    if not base.exists() or not head.exists():
        return {"status": "error", "reason": "both --diff paths must exist"}
    solo_key = "." if base.is_file() and head.is_file() else None
    left = _collect(base, solo_key)
    right = _collect(head, solo_key)
    def delta(a: set[str], b: set[str]) -> dict:
        return {"added": sorted(b - a), "removed": sorted(a - b)}
    usage_findings = _usage_findings(right["usage"])
    status = "failed" if left["unreadable"] or right["unreadable"] or usage_findings else "ok"
    return {
        "status": status,
        "base": str(base.resolve()),
        "head": str(head.resolve()),
        "entitlements": _entitlement_delta(left["entitlements"], right["entitlements"]),
        "usage": delta(_flat_keys(left["usage"]), _flat_keys(right["usage"])),
        "usage_findings": usage_findings,
        "unreadable": left["unreadable"] + right["unreadable"],
    }
