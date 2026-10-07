#!/usr/bin/env python3
"""Directory snapshot diff by relative path and sha256.

This compares file bytes. It is not a pixel diff and it does not render UI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
