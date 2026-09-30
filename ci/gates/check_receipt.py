#!/usr/bin/env python3
"""Gate G-2 — verification receipts.

The gate this system exists for. A coding agent's characteristic failure is not writing bad code;
it is writing plausible code, reasoning convincingly about why it works, and reporting success
without ever executing it.

This gate does not ask whether the bot verified something. It asks for the exit code, and CI can
re-run the command. A model can be confident about a claim it never tested; it cannot fabricate a
0 that survives re-execution.

    python3 ci/gates/check_receipt.py --receipt .receipts/task.json --bot bot-03-android
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Commands that produce a green result from work that never ran.
BYPASS_PATTERNS: list[tuple[str, str]] = [
    (r"--no-verify",                  "skips git hooks, including the secret scanner"),
    (r"--no-gpg-sign",                "skips commit signing"),
    (r"-x\s+test",                    "excludes the Gradle test task"),
    (r"-x\s+check",                   "excludes the Gradle check task"),
    (r"--skip-tests?\b",              "skips tests"),
    (r"-DskipTests",                  "skips tests"),
    (r"-skipTesting",                 "skips xcodebuild tests"),
    (r"\|\|\s*true",                  "masks a non-zero exit code"),
    (r"\|\|\s*exit\s+0",              "masks a non-zero exit code"),
    (r";\s*exit\s+0\s*$",             "masks a non-zero exit code"),
    (r"--passWithNoTests",            "passes when no tests ran"),
    (r"--exitcode-only",              "discards output needed for review"),
    (r"2>\s*/dev/null",               "hides the error stream"),
    (r"--auto-approve",               "applies infrastructure without a reviewed plan"),
    (r"--force\b",                    "forces past a safety check"),
    (r"-f\s+--",                      "forces past a safety check"),
    (r"--ignore-errors",              "continues past failures"),
    (r"pytest.*--co\b",               "collect-only: no tests actually ran"),
    (r"--dry-run(?!=server)",         "dry run: nothing actually executed"),
]

REQUIRED_FIELDS = ["task_id", "bot", "commands", "claims", "unverified"]

# A degraded-mode turn acknowledgement (loop skill §3) — a human saying "work this ticket even
# though the memory brief failed". Not to be confused with `approvals[]`: G-6's `check_rollback.py`
# pairs `approvals[]` entries to destructive operations by count, so a turn ack landing there either
# falsely fails a properly-approved destructive op or silently satisfies the count for one nobody
# approved. loop_acks stays out of approvals[] and check_rollback.py must never read it.
REQUIRED_LOOP_ACK_FIELDS = ["condition", "operation", "ack_id", "human_granted_by", "at", "scope"]
LOOP_ACK_CONDITIONS = {"brief_degraded", "brief_no_revision_marker"}
SEAT_ID_RE = re.compile(
    r"^\s*(?:bot-0[0-6](?:-[a-z0-9-]+)?|LEAD|SYSTEMS|WEB|ANDROID|IOS|INFRA|QUALITY|the desk"
    r"|desk-[a-z][a-z0-9-]*)\s*$",
    re.IGNORECASE,
)

# Claims whose wording asserts exhaustiveness. These need more than one piece of evidence.
EXHAUSTIVE_RE = re.compile(
    r"\b(all|every|everything|fully|completely|entirely|no regressions|nothing broke)\b",
    re.IGNORECASE,
)


class ReceiptError(Exception):
    pass


def load(path: Path) -> dict:
    if not path.exists():
        raise ReceiptError(
            f"no receipt at {path}\n"
            "  A completion claim requires a receipt. See skills/verification-receipts/SKILL.md"
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"receipt is not valid JSON: {exc}") from exc


def check(receipt: dict, expected_bot: str | None, strict: bool = False) -> list[str]:
    problems: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in receipt:
            problems.append(f"missing required field '{field}'")
    if problems:
        return problems

    commands = receipt["commands"]
    claims = receipt["claims"]
    unverified = receipt["unverified"]

    # --- structural ------------------------------------------------------
    if not isinstance(commands, list) or not commands:
        problems.append(
            "no commands recorded — nothing was actually run, so nothing is verified"
        )
    if not isinstance(claims, list):
        problems.append("'claims' must be a list")
    if not isinstance(unverified, list):
        problems.append("'unverified' must be a list (an empty list is allowed but rarely honest)")

    if expected_bot and receipt.get("bot") != expected_bot:
        problems.append(f"receipt bot '{receipt.get('bot')}' does not match --bot '{expected_bot}'")

    # --- self-approval ---------------------------------------------------
    approved_by = receipt.get("approved_by")
    if not approved_by:
        problems.append("'approved_by' is missing — work must be reviewed by someone else")
    elif approved_by == receipt.get("bot"):
        problems.append(
            f"self-approval: approved_by == bot ({approved_by}). "
            "A bot approving its own work removes the independent check."
        )

    # --- bypass commands -------------------------------------------------
    for i, cmd in enumerate(commands if isinstance(commands, list) else []):
        cmd_str = cmd.get("cmd", "") if isinstance(cmd, dict) else str(cmd)
        for pattern, why in BYPASS_PATTERNS:
            if re.search(pattern, cmd_str):
                problems.append(
                    f"command[{i}] contains a bypass: {cmd_str!r}\n"
                    f"    matched {pattern!r} — {why}"
                )

    # --- exit codes present ----------------------------------------------
    for i, cmd in enumerate(commands if isinstance(commands, list) else []):
        if not isinstance(cmd, dict):
            problems.append(f"command[{i}] must be an object with 'cmd' and 'exit_code'")
            continue
        if "cmd" not in cmd:
            problems.append(f"command[{i}] has no 'cmd'")
        if "exit_code" not in cmd:
            problems.append(
                f"command[{i}] has no 'exit_code' — an unrecorded exit code is not evidence"
            )

    # --- claims cite valid, passing commands ------------------------------
    for i, claim in enumerate(claims if isinstance(claims, list) else []):
        if not isinstance(claim, dict):
            problems.append(f"claim[{i}] must be an object")
            continue

        text = claim.get("claim", "<no text>")
        idx = claim.get("evidence_command_index")

        if idx is None:
            problems.append(
                f"claim[{i}] {text!r} cites no command — "
                "a claim without evidence is a guess with confident phrasing"
            )
            continue

        if not isinstance(idx, int) or not (0 <= idx < len(commands)):
            problems.append(f"claim[{i}] {text!r} cites command index {idx}, which does not exist")
            continue

        cited = commands[idx]
        exit_code = cited.get("exit_code") if isinstance(cited, dict) else None

        # A claim may legitimately cite a FAILING command: "reproduced the bug" is evidenced
        # by a non-zero exit. That reproduction step is what makes the later green run mean
        # something, so the gate must support it rather than forcing every claim to be green.
        expects_failure = bool(claim.get("expects_failure"))

        if expects_failure:
            if exit_code == 0:
                problems.append(
                    f"claim[{i}] {text!r} sets expects_failure but command[{idx}] exited 0\n"
                    f"    {cited.get('cmd', '')!r}"
                )
        elif exit_code != 0:
            problems.append(
                f"claim[{i}] {text!r} cites command[{idx}] which exited {exit_code}\n"
                f"    {cited.get('cmd', '')!r}\n"
                f"    If this is a reproduction step, set \"expects_failure\": true on the claim."
            )

        if strict and EXHAUSTIVE_RE.search(text) and len(commands) < 2:
            problems.append(
                f"claim[{i}] {text!r} asserts exhaustiveness but the receipt has "
                f"only {len(commands)} command(s)"
            )

    # --- loop_acks: degraded-mode turn acks (G-2) -------------------------
    # Optional: a receipt for a turn that never went degraded OMITS the field, or carries [].
    # A present-but-null field is a different shape from omission — `"loop_acks" in receipt`
    # (rather than `.get(...) is not None`) is what tells the two apart, so an explicit null
    # is caught here instead of silently reading the same as "no field at all".
    if "loop_acks" in receipt:
        loop_acks = receipt.get("loop_acks")
        if not isinstance(loop_acks, list):
            problems.append(
                "'loop_acks' must be a list — omit the field entirely if this turn never "
                "went degraded; do not set it to null"
            )
        else:
            task_id = receipt.get("task_id")
            for i, ack in enumerate(loop_acks):
                if not isinstance(ack, dict):
                    problems.append(f"loop_acks[{i}] must be an object")
                    continue
                missing = [f for f in REQUIRED_LOOP_ACK_FIELDS if not ack.get(f)]
                if missing:
                    problems.append(
                        f"loop_acks[{i}] is missing {missing} — a degraded-mode ack records the "
                        "condition, the operation, the ack id, the human who granted it, when, "
                        "and the one turn it covers")

                granter = ack.get("human_granted_by")
                if granter is not None and not isinstance(granter, str):
                    # A truthy non-string (e.g. `true`, an id, an object) would otherwise be
                    # silently stringified below and could dodge both the missing-field check
                    # (it is truthy) and the seat-name regex (it does not look like a seat).
                    problems.append(
                        f"loop_acks[{i}] human_granted_by must be a string naming a person, "
                        f"got {type(granter).__name__} ({granter!r})")
                elif granter and SEAT_ID_RE.match(granter):
                    problems.append(
                        f"loop_acks[{i}] human_granted_by is {granter!r}, which is a seat, not a "
                        "human — degraded repo work needs a person's acknowledgement. The "
                        "relaying seat goes in 'relayed_by'")

                cond = ack.get("condition")
                if cond and (not isinstance(cond, str) or cond not in LOOP_ACK_CONDITIONS):
                    problems.append(f"loop_acks[{i}] condition {cond!r} is not one of "
                                    f"{sorted(LOOP_ACK_CONDITIONS)}")

                scope = ack.get("scope")
                if scope is not None and not isinstance(scope, str):
                    problems.append(f"loop_acks[{i}] scope must be a string")
                elif scope and isinstance(task_id, str) and task_id not in scope:
                    # An ack's scope is supposed to bind it to *this* turn. A scope carried
                    # over from another ticket, or a blanket phrase like "all turns", is
                    # truthy and would otherwise pass unnoticed.
                    problems.append(
                        f"loop_acks[{i}] scope {scope!r} does not name this receipt's "
                        f"task_id ({task_id!r}) — an ack scoped to another ticket, or a "
                        "blanket scope, does not authorise this turn")

    # --- unverified honesty ----------------------------------------------
    if isinstance(unverified, list) and not unverified:
        # Not a hard failure — occasionally true — but it is worth surfacing, because an
        # empty list asserts complete verification and that is rarely the case.
        print(
            "  NOTE: 'unverified' is empty. That asserts everything was verified. "
            "Confirm it is true rather than forgotten.",
            file=sys.stderr,
        )

    vague = {"some edge cases", "minor things", "full testing", "everything else",
             "various things", "misc", "other cases"}
    for entry in unverified if isinstance(unverified, list) else []:
        if str(entry).strip().lower().rstrip(".") in vague:
            problems.append(
                f"unverified entry {entry!r} is too vague to be useful — "
                "name what was not verified and why"
            )

    # --- deployment needs a rollback plan (G-5 handoff) --------------------
    if receipt.get("deployment") and not receipt.get("rollback_plan"):
        problems.append("deployment recorded but 'rollback_plan' is null — G-5 requires one")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-2: verification receipts")
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--bot", help="Expected bot id")
    ap.add_argument("--strict", action="store_true",
                    help="Also flag exhaustive claims backed by thin evidence")
    args = ap.parse_args()

    try:
        receipt = load(args.receipt)
    except ReceiptError as exc:
        print(f"G-2 FAIL — {exc}", file=sys.stderr)
        return 1

    problems = check(receipt, args.bot, strict=args.strict)

    if problems:
        print(f"G-2 FAIL — {args.receipt}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  See skills/verification-receipts/SKILL.md", file=sys.stderr)
        return 1

    n_cmds = len(receipt["commands"])
    n_claims = len(receipt["claims"])
    n_unver = len(receipt["unverified"])
    print(f"G-2 PASS — {receipt['task_id']}: "
          f"{n_cmds} command(s), {n_claims} substantiated claim(s), {n_unver} unverified item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
