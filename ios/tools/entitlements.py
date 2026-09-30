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


def _target_id(item: Path, base: Path) -> str:
    try:
        return item.relative_to(base).as_posix()
    except ValueError:
        return item.name


def _collect(path: Path) -> dict:
    path = path.resolve()
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    base = path if path.is_dir() else path.parent
    entitlements: dict[str, dict] = {}
    usage: dict[str, dict] = {}
    unreadable: list[str] = []
    for item in files:
        if item.suffix == ".entitlements":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            entitlements[_target_id(item, base)] = dict(data)
        elif item.name == "Info.plist":
            data = _load(item)
            if data is None:
                unreadable.append(str(item))
                continue
            usage[_target_id(item, base)] = {k: data[k] for k in USAGE_KEYS if k in data}
    return {
        "entitlements": entitlements,
        "usage": usage,
        "unreadable": unreadable,
    }


def _public(collected: dict) -> dict:
    entitlement_keys = {k for values in collected["entitlements"].values() for k in values}
    usage_keys = {k for values in collected["usage"].values() for k in values}
    return {
        "entitlements": sorted(entitlement_keys),
        "usage": sorted(usage_keys),
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


def _delta(a: dict[str, dict], b: dict[str, dict]) -> dict:
    """a/b are target -> {key: value}. Per-target so a value flipped on one
    target (e.g. an entitlement toggled from true to false) is visible even
    when the same key is unchanged on every other target."""
    added: set[str] = set()
    removed: set[str] = set()
    changed: list[dict] = []
    per_target: dict[str, dict] = {}
    for target in sorted(set(a) | set(b)):
        av, bv = a.get(target, {}), b.get(target, {})
        t_added = sorted(set(bv) - set(av))
        t_removed = sorted(set(av) - set(bv))
        t_changed = [
            {"key": key, "before": av[key], "after": bv[key]}
            for key in sorted(set(av) & set(bv))
            if av[key] != bv[key]
        ]
        added.update(t_added)
        removed.update(t_removed)
        changed.extend({"target": target, **c} for c in t_changed)
        if t_added or t_removed or t_changed:
            per_target[target] = {"added": t_added, "removed": t_removed, "changed": t_changed}
    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": changed,
        "targets": per_target,
    }


def diff(base: Path, head: Path) -> dict:
    if not base.exists() or not head.exists():
        return {"status": "error", "reason": "both --diff paths must exist"}
    left = _collect(base)
    right = _collect(head)
    status = "failed" if left["unreadable"] or right["unreadable"] else "ok"
    return {
        "status": status,
        "base": str(base.resolve()),
        "head": str(head.resolve()),
        "entitlements": _delta(left["entitlements"], right["entitlements"]),
        "usage": _delta(left["usage"], right["usage"]),
        "unreadable": left["unreadable"] + right["unreadable"],
    }
