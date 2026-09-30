"""Parse a saved xcodebuild log. Does not invoke xcodebuild or boot a Simulator."""

from __future__ import annotations

import re
from pathlib import Path

RESULT_RE = re.compile(r"\*\*\s+(TEST|BUILD)\s+(SUCCEEDED|FAILED)\s+\*\*")
SCHEME_RE = re.compile(r"(?:^|\s)-scheme\s+(\S+)")
DEST_RE = re.compile(r'(?:^|\s)-destination\s+(".*?"|\'.*?\'|\S+)')
ERROR_RE = re.compile(r"^error:\s+(.*)$", re.MULTILINE)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_log(text: str, source: str) -> dict:
    results = list(RESULT_RE.finditer(text))
    schemes = SCHEME_RE.findall(text)
    destinations = DEST_RE.findall(text)
    destination = _unquote(destinations[-1]) if destinations else None
    errors = ERROR_RE.findall(text)
    parsed = {
        "source": source,
        "xcodebuild_invoked": False,
        "simulator_booted": False,
        "simulator_mentioned": bool(destination and "simulator" in destination.lower()),
        "scheme": schemes[-1] if schemes else None,
        "destination": destination,
        "error_count": len(errors),
        "error_lines": errors[:20],
    }
    if not results:
        parsed.update({
            "status": "unverified",
            "reason": "log has no ** TEST/BUILD SUCCEEDED/FAILED ** line",
            "action": None,
            "result": None,
        })
        return parsed
    failed = [r for r in results if r.group(2) == "FAILED"]
    action, result = results[-1].group(1), results[-1].group(2)
    parsed.update({
        # A later SUCCEEDED banner (e.g. a run summary) must not paper over
        # an earlier FAILED one for a different test/build action.
        "status": "failed" if failed else "passed",
        "action": action,
        "result": result,
        "failed_banners": [f"{r.group(1)} {r.group(2)}" for r in failed],
    })
    return parsed


def parse_file(path: Path) -> dict:
    if not path.is_file():
        return {"status": "error", "reason": f"log not found: {path}", "xcodebuild_invoked": False, "simulator_booted": False}
    return parse_log(path.read_text(encoding="utf-8", errors="replace"), str(path))
