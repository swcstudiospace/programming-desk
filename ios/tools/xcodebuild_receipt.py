"""Parse a saved xcodebuild log. Does not invoke xcodebuild or boot a Simulator."""

from __future__ import annotations

import re
from pathlib import Path

RESULT_RE = re.compile(r"\*\*\s+(TEST|BUILD)\s+(SUCCEEDED|FAILED)\s+\*\*")
SCHEME_RE = re.compile(r"(?:^|\s)-scheme\s+(\S+)")
DEST_RE = re.compile(r"(?:^|\s)-destination\s+(\S+)")
ERROR_RE = re.compile(r"^error:\s+(.*)$", re.MULTILINE)


def _nearest_before(matches: list[re.Match], pos: int) -> str | None:
    before = [m for m in matches if m.start() < pos]
    if before:
        return before[-1].group(1)
    return matches[-1].group(1) if matches else None


def parse_log(text: str, source: str) -> dict:
    results = list(RESULT_RE.finditer(text))
    scheme_matches = list(SCHEME_RE.finditer(text))
    dest_matches = list(DEST_RE.finditer(text))
    errors = ERROR_RE.findall(text)
    if not results:
        destination = dest_matches[-1].group(1) if dest_matches else None
        return {
            "source": source,
            "xcodebuild_invoked": False,
            "simulator_booted": False,
            "simulator_mentioned": bool(destination and "simulator" in destination.lower()),
            "scheme": scheme_matches[-1].group(1) if scheme_matches else None,
            "destination": destination,
            "error_count": len(errors),
            "error_lines": errors[:20],
            "status": "unverified",
            "reason": "log has no ** TEST/BUILD SUCCEEDED/FAILED ** line",
            "action": None,
            "result": None,
        }
    any_failed = any(m.group(2) == "FAILED" for m in results)
    reported = [m for m in results if m.group(2) == "FAILED"] if any_failed else results
    chosen = reported[-1]
    action, result = chosen.group(1), chosen.group(2)
    destination = _nearest_before(dest_matches, chosen.start())
    return {
        "source": source,
        "xcodebuild_invoked": False,
        "simulator_booted": False,
        "simulator_mentioned": bool(destination and "simulator" in destination.lower()),
        "scheme": _nearest_before(scheme_matches, chosen.start()),
        "destination": destination,
        "error_count": len(errors),
        "error_lines": errors[:20],
        "status": "failed" if any_failed else ("passed" if result == "SUCCEEDED" else "failed"),
        "action": action,
        "result": result,
        "banner_count": len(results),
        "any_failed": any_failed,
    }


def parse_file(path: Path) -> dict:
    if not path.is_file():
        return {"status": "error", "reason": f"log not found: {path}", "xcodebuild_invoked": False, "simulator_booted": False}
    return parse_log(path.read_text(encoding="utf-8", errors="replace"), str(path))
