#!/usr/bin/env python3
"""Decision table for the autonomous uplift trigger.

Run directly — `python3 .claude/hooks/test_desk_uplift.py` — or under pytest. It is written to
work both ways because CI currently collects only `ci/tests/`, so until an INFRA change widens
that, the direct run is the only way this executes in the pipeline.

What matters here is the skip set, and specifically that it is matched on the whole normalised
prompt rather than as a substring. "ok" is an acknowledgement; "ok but the merge gate is wrong"
is a bug report, and a substring check would silently drop the plan for the second one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import desk_uplift as _m  # noqa: E402 — the path insert above has to happen first

# (prompt, state, expect_uplift, note)
CASES = [
    ("Add an opt-in dialog to the Android client", {}, True, "a real build ask is the default path"),
    ("", {}, False, "empty prompt"),
    ("lgtm", {}, False, "the skill names lgtm explicitly"),
    ("ok", {}, False, "and ok"),
    ("thanks", {}, False, "and thanks"),
    ("OK!", {}, False, "normalisation strips punctuation and case"),
    ("  ship it  ", {}, False, "and surrounding whitespace, via the hyphenated form"),
    ("ok but the merge gate is wrong", {}, True, "whole-prompt match, not substring — this is a bug report"),
    ("no", {}, False, "a bare no is steering"),
    ("no, use Postgres instead of SQLite", {}, True, "a no with a reason is a decision to plan"),
    ("<second_uplift graphId='g-1'>...</second_uplift>", {}, False, "already the spec; LEAD.xml:378 forbids re-uplift"),
    ("<?xml version='1.0'?><desk_task/>", {}, False, "any XML root marker"),
    ("raw: what branch am I on", {}, False, "operator escape for one message"),
    ("!status", {}, False, "the short form of the same escape"),
    ("Add a settings screen", {"mode": "off"}, False, "off wins over everything"),
    ("lgtm", {"mode": "off"}, False, "off and trivial agree"),
    ("Add a settings screen", {"mode": "quick"}, True, "quick still uplifts, with a lighter instruction"),
    ("Add a settings screen", {"skip_next": True}, False, "one-shot skip"),
    ("Add a settings screen", {"mode": "on", "skip_next": True}, False, "one-shot skip beats on"),
]


def test_decision_table() -> None:
    for prompt, state, expected, note in CASES:
        got, reason = _m.should_uplift(prompt, state)
        assert got is expected, f"{prompt!r} with {state}: expected uplift={expected}, got {got} ({reason}) — {note}"


def test_quick_and_full_instructions_differ() -> None:
    full, quick = _m._instruction(quick=False), _m._instruction(quick=True)
    assert 'mode="full"' in full and "gotxcot-uplift" in full and "MIN_NODES=5" in full
    assert 'mode="quick"' in quick and "Skip the Graph of Thought" in quick
    # The full instruction must carry the not-LEAD guard; a specialist re-running GoT forks the spec.
    assert "not the Programming Lead" in full


def test_state_round_trips_and_tolerates_a_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _m.STATE_DIR = Path(tmp) / "programming-desk"
        _m.STATE_FILE = _m.STATE_DIR / "uplift.json"
        assert _m._read_state() == {}, "a missing state file reads as empty, not an error"
        _m._write_state({"mode": "off"})
        assert _m._read_state()["mode"] == "off"
        _m.STATE_FILE.write_text("{not json", encoding="utf-8")
        assert _m._read_state() == {}, "corrupt state must degrade to defaults, never raise"


def test_unknown_verb_exits_zero() -> None:
    # A hook that exits non-zero blocks the operator's prompt. Nothing here may do that.
    assert _m.main(["bogus"]) == 0


def test_a_failed_state_write_does_not_report_success() -> None:
    """The bug this guards: off printed "OFF" on stdout even when the write failed, so an
    operator who turned uplift off and was uplifted anyway had been misled by their own tool."""
    import io, contextlib
    orig_dir, orig_file = _m.STATE_DIR, _m.STATE_FILE
    try:
        _m.STATE_DIR = Path("/proc/nonexistent/desk")
        _m.STATE_FILE = _m.STATE_DIR / "uplift.json"
        assert _m._write_state({"mode": "off"}) is False, "an unwritable dir must return False"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = _m.run_control(["off"])
        assert rc == 0, "a failed write still must not block the operator"
        assert "OFF." not in out.getvalue(), f"claimed success on a failed write: {out.getvalue()!r}"
        assert "could not be saved" in out.getvalue()
    finally:
        _m.STATE_DIR, _m.STATE_FILE = orig_dir, orig_file


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted((n, f) for n, f in vars().items() if n.startswith("test_") and callable(f)):
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {name}\n       {exc}")
    print(f"\n{len(CASES)} decision cases, {failures} failure(s)")
    sys.exit(1 if failures else 0)
