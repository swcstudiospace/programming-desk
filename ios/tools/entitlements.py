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
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    entitlements: set[str] = set()
    usage: set[str] = set()
    unreadable: list[str] = []
    for item in files:
        if item.suffix == ".entitlements":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            entitlements.update(data.keys())
        elif item.name == "Info.plist":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            usage.update(k for k in USAGE_KEYS if k in data)
    return {
        "entitlements": entitlements,
        "usage": usage,
        "unreadable": unreadable,
    }


def _public(collected: dict) -> dict:
    return {
        "entitlements": sorted(collected["entitlements"]),
        "usage": sorted(collected["usage"]),
        "unreadable": collected["unreadable"],
    }


def scan(path: Path) -> dict:
    if not path.exists():
        return {"status": "error", "reason": f"path not found: {path}"}
    collected = _collect(path)
    result = {"status": "ok", "path": str(path.resolve()), **_public(collected)}
    if collected["unreadable"]:
        result["status"] = "failed"
    return result


def diff(base: Path, head: Path) -> dict:
    if not base.exists() or not head.exists():
        return {"status": "error", "reason": "both --diff paths must exist"}
    left = _collect(base)
    right = _collect(head)
    def delta(a: set[str], b: set[str]) -> dict:
        return {"added": sorted(b - a), "removed": sorted(a - b)}
    status = "failed" if left["unreadable"] or right["unreadable"] else "ok"
    return {
        "status": status,
        "base": str(base.resolve()),
        "head": str(head.resolve()),
        "entitlements": delta(left["entitlements"], right["entitlements"]),
        "usage": delta(left["usage"], right["usage"]),
        "unreadable": left["unreadable"] + right["unreadable"],
    }
