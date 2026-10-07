#!/usr/bin/env python3
"""Autonomous double-uplift for the Programming Lead seat.

The desk already has the uplift pipeline — `skills/gotxcot-uplift` — and the policy it runs
under, vendored at `vendor/ultrathink-policy/`. What it did not have is a trigger. The skill
loads `on_intake`, meaning a GitHub `desk:intake` label or a `desk_intake_next` call, so a plain
operator message to LEAD reached the model unplanned. This hook is that missing trigger: it runs
on every `UserPromptSubmit` and injects the instruction to uplift before LEAD answers.

It decides nothing new. The skip conditions below are the skill's own documented decision tree
("Do not use when: the message is a trivial ack ... or already a finished second-uplift XML"),
moved from prose a model may skim into a check that always runs. Enforcing the existing policy
mechanically is the whole change; inventing extra policy here would put two sources of truth in
the repository.

Two modes, chosen by argv, matching how claude-ultrathink's own `hooks/uplift.ts` dispatches:

    desk_uplift.py                 hook mode   — reads the hook payload on stdin
    desk_uplift.py off|on|...      control     — what .claude/commands/desk-uplift-*.md invoke

Written in Python 3 with nothing but the standard library, on purpose. The upstream hook is
TypeScript run through bun, and the point of this port is that someone can paste this
repository's URL into a Grok Bot and have the desk work from a bare clone — so it must not need
bun, npm, or an install step. `python3` is already required by every gate in ci/gates/.

Failure is always silent and always open. A hook that raises on a malformed payload, or an
unwritable state directory, would block the operator's prompt; an uplift that does not fire is a
missed plan, which is recoverable, while a prompt that cannot be sent is not. Every exit is 0.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# State lives outside the repository. A file under .claude/ would either be committed — and
# .claude/state/** is UNOWNED, so G-1 would fail the build — or need a .gitignore entry for
# something that is per-operator runtime and belongs to no seat. XDG keeps it out of git
# entirely and out of the ownership manifest's way.
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "programming-desk"
STATE_FILE = STATE_DIR / "uplift.json"

VERBS = ("off", "on", "skip", "quick", "status")

# Trivial acknowledgements. The skill names `ok`, `lgtm` and `thanks`; the rest are the same
# class of message — an operator steering, not asking for work. Matched on the whole prompt
# after normalisation, never as a substring, so "ok but the merge gate is wrong" still uplifts.
TRIVIAL = frozenset(
    """
    ok okay k kk yes y yep yeah no n nope sure fine good great thanks thanks! thx ty
    lgtm nice cool done go continue proceed stop wait hold nvm nevermind
    ship ship-it merge approve approved ack got-it
    """.split()
)

# A finished second-uplift XML is already the spec — re-uplifting it would fork the plan, which
# is exactly what prompts/LEAD.xml:378 forbids ("do not rewrite the operator prompt into a new
# uplift"). These markers come from that XML's own roots; see skills/gotxcot-uplift/xml-roots.md.
UPLIFTED_MARKERS = ("<uplift", "<second_uplift", "<trackplan", "<desk_task", "<?xml")

# An explicit operator escape for one message, the same affordance ultrathink spells `raw:`.
RAW_PREFIXES = ("raw:", "!")


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> bool:
    """True when the state reached disk. Callers must not claim success without checking.

    An unwritable state dir does not take the desk down, but it cannot be silent either: an
    operator told `off` who is then uplifted anyway has been lied to by their own tooling.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
        return True
    except OSError as exc:
        print(f"desk-uplift: could not persist state to {STATE_FILE}: {exc}", file=sys.stderr)
        return False


def _normalise(prompt: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, for the TRIVIAL comparison only."""
    return re.sub(r"[\s]+", " ", re.sub(r"[^\w\s-]", "", prompt.strip().lower())).strip()


def should_uplift(prompt: str, state: dict) -> tuple[bool, str]:
    """(uplift?, reason). Reason is logged either way so a skipped turn is explainable."""
    if state.get("mode") == "off":
        return False, "uplift is off (/desk-uplift-on to re-enable)"

    if state.get("skip_next"):
        return False, "one-shot skip was armed by /desk-uplift-skip"

    text = prompt.strip()
    if not text:
        return False, "empty prompt"

    lowered = text.lower()
    if lowered.startswith(RAW_PREFIXES):
        return False, "operator escape prefix"

    if any(m in lowered for m in UPLIFTED_MARKERS):
        return False, "already a second-uplift XML — that XML is the spec, do not re-uplift"

    norm = _normalise(text)
    if norm in TRIVIAL or norm.replace(" ", "-") in TRIVIAL:
        return False, f"trivial acknowledgement ({norm!r})"

    return True, "quick mode" if state.get("mode") == "quick" else "full double uplift"


def _instruction(quick: bool) -> str:
    """The context injected ahead of the operator's prompt."""
    if quick:
        return (
            "<desk_uplift mode=\"quick\">\n"
            "Uplift is in QUICK mode. Before answering, restate this ask as a single dense XML "
            "uplift and name the seats it touches. Skip the Graph of Thought, the Chain of "
            "Thought, and Notion/Linear materialisation — quick mode exists so a small ask does "
            "not pay for a full plan. Then answer.\n"
            "Run the full pipeline instead with /desk-uplift-on if this turns out to be real "
            "build work.\n"
            "</desk_uplift>"
        )
    return (
        "<desk_uplift mode=\"full\">\n"
        "Before answering, run skills/gotxcot-uplift on the operator message below. That skill "
        "is the procedure; this is only the trigger. In order: first XML uplift, 5-8 Graph of "
        "Thought nodes, 4-8 Chain of Thought steps per node filled one node at a time, Notion + "
        "Linear materialisation, second uplift carrying the live URLs, then hand to "
        "skills/trackplan-dispatch. Do not implement.\n"
        "Constants are vendor/ultrathink-policy/constants.ts: MIN_NODES=5, MAX_NODES=8, "
        "MIN_STEPS=4, MAX_STEPS=8. Do not go below 5 nodes for a real build task.\n"
        "If you are not the Programming Lead seat, do not run this. Per prompts/LEAD.xml, a "
        "specialist executes the ticket it was given and never rewrites the operator prompt into "
        "a new uplift — the dispatched second-uplift XML is already the spec.\n"
        "Escape hatches for the operator, if this ask did not warrant a plan: /desk-uplift-skip "
        "for one message, /desk-uplift-quick for a lighter pass, /desk-uplift-off until turned "
        "back on.\n"
        "</desk_uplift>"
    )


def run_hook() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # Not a payload we understand. Never block the prompt.

    prompt = payload.get("prompt") or ""
    state = _read_state()
    uplift, reason = should_uplift(prompt, state)

    if state.get("skip_next"):
        _write_state({**state, "skip_next": False})

    if not uplift:
        # Nothing on stdout means nothing is added to the turn. The reason goes to stderr, which
        # the operator can see with `claude --debug` but which never reaches the model.
        print(f"desk-uplift: skipped — {reason}", file=sys.stderr)
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": _instruction(quick=state.get("mode") == "quick"),
                }
            }
        )
    )
    return 0


def run_control(argv: list[str]) -> int:
    verb = argv[0]
    state = _read_state()

    if verb == "status":
        mode = state.get("mode", "on")
        armed = " (one-shot skip armed for the next message)" if state.get("skip_next") else ""
        since = state.get("changed_at")
        when = f", set {time.strftime('%Y-%m-%d %H:%M', time.localtime(since))}" if since else ""
        print(f"desk-uplift: {mode}{armed}{when}")
        print(f"state: {STATE_FILE}")
        print("verbs: " + " ".join(f"/desk-uplift-{v}" for v in VERBS))
        return 0

    if verb == "skip":
        if not _write_state({**state, "skip_next": True, "changed_at": time.time()}):
            print("desk-uplift: NOT armed — the state file could not be written (see above).")
            return 0
        print("desk-uplift: next message will not be uplifted. Later messages are unaffected.")
        return 0

    if not _write_state({**state, "mode": verb, "skip_next": False, "changed_at": time.time()}):
        print(f"desk-uplift: still {state.get('mode', 'on')} — {verb!r} could not be saved (see above).")
        return 0

    if verb == "off":
        print("desk-uplift: OFF. Prompts reach LEAD unplanned until /desk-uplift-on.")
    elif verb == "on":
        print("desk-uplift: ON. Every non-trivial prompt now runs the full double uplift.")
    else:
        print("desk-uplift: QUICK. One dense XML restatement per prompt, no GoT/CoT, no trackers.")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] in VERBS:
        return run_control(argv)
    if argv:
        print(f"desk-uplift: unknown verb {argv[0]!r}; expected one of {', '.join(VERBS)}", file=sys.stderr)
        return 0
    return run_hook()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 — a hook must never break the operator's turn
        print(f"desk-uplift: non-fatal error: {exc}", file=sys.stderr)
        sys.exit(0)
