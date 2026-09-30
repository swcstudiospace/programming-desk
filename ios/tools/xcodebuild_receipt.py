#!/usr/bin/env python3
"""Parse an xcodebuild log or JSON artifact that CI already saved.

Does not invoke xcodebuild. A log with no result line stays unverified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


RESULT_RE = re.compile(r"\*\*\s+(TEST|BUILD)\s+(SUCCEEDED|FAILED)\s+\*\*")
SCHEME_RE = re.compile(r"(?:^|\s)-scheme\s+(\S+)")
DEST_RE = re.compile(r"(?:^|\s)-destination\s+(\S+)")
ERROR_RE = re.compile(r"^error:\s+(.*)$", re.MULTILINE)


def parse_log(text: str, source: str) -> dict:
    results = list(RESULT_RE.finditer(text))
    schemes = SCHEME_RE.findall(text)
    destinations = DEST_RE.findall(text)
    errors = ERROR_RE.findall(text)
    base = {
        "source": source,
        "xcodebuild_invoked": False,
        "simulator_booted": False,
        "scheme": schemes[-1] if schemes else None,
        "destination": destinations[-1] if destinations else None,
        "error_lines": errors[:20],
        "error_count": len(errors),
    }
    if not results:
        base.update(
            {
                "status": "unverified",
                "reason": "artifact has no ** TEST/BUILD SUCCEEDED/FAILED ** line",
                "action": None,
                "result": None,
            }
        )
        return base
    action, result = results[-1].group(1), results[-1].group(2)
    base.update(
        {
            "status": "passed" if result == "SUCCEEDED" else "failed",
            "action": action,
            "result": result,
        }
    )
    return base


def parse_path(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "status": "error",
                "reason": f"JSON artifact did not parse: {exc}",
                "source": str(path),
                "xcodebuild_invoked": False,
            }
        if isinstance(data, dict) and "log" in data and isinstance(data["log"], str):
            parsed = parse_log(data["log"], str(path))
            parsed["artifact_format"] = "json-log"
            return parsed
        if isinstance(data, dict) and {"status", "scheme"} <= set(data):
            data = dict(data)
            data["source"] = str(path)
            data["xcodebuild_invoked"] = False
            data["simulator_booted"] = False
            data["artifact_format"] = "json-summary"
            return data
        return {
            "status": "unverified",
            "reason": "JSON artifact has neither a log field nor status+scheme",
            "source": str(path),
            "xcodebuild_invoked": False,
            "simulator_booted": False,
        }
    parsed = parse_log(raw, str(path))
    parsed["artifact_format"] = "text-log"
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse a saved xcodebuild CI artifact")
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    if not args.artifact.is_file():
        json.dump({"status": "error", "reason": "artifact not found", "xcodebuild_invoked": False}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    result = parse_path(args.artifact)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if result.get("status") == "error":
        return 2
    if result.get("status") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
