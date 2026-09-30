"""Hash diff of two fixture files or directories. PNG width/height when present.

Not a pixel diff and not a UI render.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

_PNG = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> dict | None:
    if not data.startswith(_PNG) or data[12:16] != b"IHDR" or len(data) < 24:
        return None
    width, height = struct.unpack(">II", data[16:24])
    return {"width": width, "height": height}


def _digest(path: Path) -> dict:
    data = path.read_bytes()
    row = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    size = _png_size(data)
    if size:
        row["png"] = size
    return row


def _index(path: Path) -> dict[str, dict]:
    if path.is_file():
        return {path.name: _digest(path)}
    if not path.is_dir():
        raise FileNotFoundError(path)
    out = {}
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        out[item.relative_to(path).as_posix()] = _digest(item)
    return out


def diff(before: Path, after: Path) -> dict:
    left = _index(before)
    right = _index(after)
    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    changed = []
    for name in sorted(set(left) & set(right)):
        if left[name]["sha256"] != right[name]["sha256"]:
            row = {"path": name, "before": left[name], "after": right[name]}
            if "png" in left[name] or "png" in right[name]:
                row["png_size_changed"] = left[name].get("png") != right[name].get("png")
            changed.append(row)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(set(left) & set(right)) - len(changed),
        "pixel_diff": False,
        "ui_rendered": False,
    }


def write_diff(before: Path, after: Path, out: Path) -> dict:
    if not before.exists() or not after.exists():
        result = {"status": "error", "reason": "both --before and --after must exist"}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
        return result
    result = {"status": "ok", **diff(before, after)}
    if result["added"] or result["removed"] or result["changed"]:
        result["status"] = "changed"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result
