"""Scan entitlements and usage strings. Optional diff of two trees or files."""

from __future__ import annotations

import plistlib
from pathlib import Path

from ios.tools.plist_lint import USAGE_KEYS


def _load(path: Path) -> dict | None:
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _collect(path: Path) -> dict:
    path = path.resolve()
    root = path.parent if path.is_file() else path
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    entitlements: dict[str, dict] = {}
    usage: dict[str, dict] = {}
    unreadable: list[str] = []
    for item in files:
        target = item.relative_to(root).as_posix()
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


def _value_changes(a: dict[str, dict], b: dict[str, dict]) -> list[dict]:
    changes = []
    for target in sorted(set(a) & set(b)):
        left_vals, right_vals = a[target], b[target]
        for key in sorted(set(left_vals) & set(right_vals)):
            if left_vals[key] != right_vals[key]:
                changes.append({
                    "target": target,
                    "key": key,
                    "before": left_vals[key],
                    "after": right_vals[key],
                })
    return changes


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
    left = _collect(base)
    right = _collect(head)
    def delta(a: set[str], b: set[str]) -> dict:
        return {"added": sorted(b - a), "removed": sorted(a - b)}
    usage_findings = _usage_findings(right["usage"])
    status = "failed" if left["unreadable"] or right["unreadable"] or usage_findings else "ok"
    return {
        "status": status,
        "base": str(base.resolve()),
        "head": str(head.resolve()),
        "entitlements": delta(_flat_keys(left["entitlements"]), _flat_keys(right["entitlements"])),
        "entitlements_value_changes": _value_changes(left["entitlements"], right["entitlements"]),
        "usage": delta(_flat_keys(left["usage"]), _flat_keys(right["usage"])),
        "usage_findings": usage_findings,
        "unreadable": left["unreadable"] + right["unreadable"],
    }
