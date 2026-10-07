#!/usr/bin/env python3
"""Directory snapshot diff by relative path and sha256.

This compares file bytes. It is not a pixel diff and it does not render UI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


def _files(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")
    out: dict[str, str] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[rel] = digest
    return out


def diff_dirs(left: Path, right: Path) -> dict:
    before = _files(left)
    after = _files(right)
    left_keys = set(before)
    right_keys = set(after)
    added = sorted(right_keys - left_keys)
    removed = sorted(left_keys - right_keys)
    changed = sorted(k for k in (left_keys & right_keys) if before[k] != after[k])
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(left_keys & right_keys) - len(changed),
        "pixel_diff": False,
    }


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG IHDR, or None when the bytes are not a PNG."""
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _paths(root: Path) -> dict[str, Path]:
    """{label: file} — relative paths for a directory, the bare filename for a single file."""
    if root.is_dir():
        return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob("*")) if p.is_file()}
    if root.is_file():
        return {root.name: root}
    raise FileNotFoundError(f"not a file or directory: {root}")


def _changed_entry(label: str, left: Path, right: Path) -> dict:
    before_size = _png_size(left.read_bytes())
    after_size = _png_size(right.read_bytes())
    return {
        "path": label,
        "png_size_changed": bool(before_size and after_size and before_size != after_size),
        "before_png_size": list(before_size) if before_size else None,
        "after_png_size": list(after_size) if after_size else None,
    }


def compare(before: Path, after: Path) -> dict:
    """diff_dirs widened to the shapes the CLI is actually handed, with per-file detail.

    Two directories pair by relative path. A pair of single files is compared on content even
    when the names differ — a renamed snapshot is still the same artefact, and reporting it as
    one removal plus one addition hides whether the image changed. A file against a directory
    pairs by filename. `changed` carries an entry per file rather than a bare path so a caller
    can tell a re-encode from a genuine resize without opening the images.
    """
    left, right = _paths(before), _paths(after)
    pairing = "tree"

    if before.is_file() and after.is_file():
        lname, rname = next(iter(left)), next(iter(right))
        if lname != rname:
            # Same artefact under a new name: re-key the right side onto the left's label.
            right = {lname: right[rname]}
            pairing = "renamed-file"
        else:
            pairing = "file"
    elif before.is_file() or after.is_file():
        pairing = "file-in-tree"

    shared = set(left) & set(right)
    changed = [
        _changed_entry(label, left[label], right[label])
        for label in sorted(shared)
        if _digest(left[label]) != _digest(right[label])
    ]
    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(shared) - len(changed),
        "pixel_diff": False,
        "pairing": pairing,
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_diff(before: Path, after: Path, out: Path) -> dict:
    """compare(), persisted to `out` as JSON, for `python -m ios.tools snapshot_diff`."""
    try:
        result = compare(before, after)
    except FileNotFoundError as exc:
        return {"status": "error", "reason": str(exc), "exit_code": 2}
    drifted = bool(result["added"] or result["removed"] or result["changed"])
    payload = {**result, "status": "changed" if drifted else "ok", "exit_code": 0}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {**payload, "out": str(out)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hash-compare two snapshot directories")
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Exit 1 when any file was added, removed, or changed",
    )
    args = parser.parse_args(argv)
    try:
        result = diff_dirs(args.left, args.right)
    except FileNotFoundError as exc:
        json.dump({"status": "error", "reason": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    dirty = bool(result["added"] or result["removed"] or result["changed"])
    if args.fail_on_diff and dirty:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
