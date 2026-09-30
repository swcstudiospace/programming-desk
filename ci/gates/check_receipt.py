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

# A failure that reads back as "the target could not be found" is not the same evidence as
# "the target was searched, end to end, and found empty" — "file missing" must not stand in
# for "every value empty" (Greptile P1, PR #45, "Thin evidence passes strict validation").
MISSING_TARGET_RE = re.compile(
    r"no such file or directory|cannot access|does not exist\b|\bnot found\b"
    r"|filenotfounderror|\benoent\b",
    re.IGNORECASE,
)

# A quoted argument is the text a command searches FOR, not text describing what happened
# when it ran — `grep "not found" build.log` exiting 1 means "not found" appears nowhere in
# build.log, which is valid negative evidence, not a missing-target error. Stripped out
# before MISSING_TARGET_RE looks at the command text itself (Greptile P1, PR #45, "Search
# text mistaken for error").
_QUOTED_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


def _strip_quoted(text: str) -> str:
    return _QUOTED_RE.sub("", text)


# A command that only tests whether a path exists (test -e/-f, [ -e/-f ], stat, a bare ls)
# never looks at content, so it cannot be the "whole scope searched" evidence an exhaustive
# content claim needs, however its exit code lands. Anchored end-to-end so a command that
# CHAINS a real content search after the existence check — `test -f X && grep ... X` failing
# because grep found nothing in an X that does exist — is not misread as existence-only just
# because it starts with one (Greptile P1, PR #45, "Compound content searches rejected").
EXISTENCE_ONLY_RE = re.compile(
    r"^\s*(?:test\s+-[a-z]\s+\S+|\[\s+-[a-z]\s+\S+\s+\]|stat\s+\S+|ls\s+[^|;&]*)\s*$",
    re.IGNORECASE,
)

# The narrower probe used specifically to corroborate a quiet-search sibling (see
# _is_positive_existence_check below). Restricted to `-f`/`-e` — the only `test`/`[` flags
# that actually test FILE existence — because `test -n`/`-z` test whether a STRING is
# non-empty/empty, not whether a path exists on disk; a command like `test -n config.yaml`
# has nothing to do with the filesystem even though it names the path as its operand
# (Greptile P1, PR #45, "Unrelated checks confirm missing files"). Captures the exact path
# token so the caller can require equality rather than substring containment.
FILE_EXISTENCE_PROBE_RE = re.compile(
    r"^\s*(?:test\s+-[fe]\s+(?P<path1>\S+)|\[\s+-[fe]\s+(?P<path2>\S+)\s+\])\s*$",
    re.IGNORECASE,
)

# A claim about a path's ABSENCE ("the file no longer exists", "path/to/x was removed") is
# a different claim from one about its CONTENT ("the deprecated token was removed from
# config.yaml") — only the latter needs a search of what is inside the target, and an
# existence probe proves nothing about it. Bare "removed"/"deleted"/"gone"/"exists"/"absent"
# is also exactly how content-removal claims get phrased, so those words are only accepted
# here when a path/file noun sits next to them; a handful of full phrases ("no longer
# exists", "does not exist", "not present") stay accepted on their own because they are
# unambiguously about a thing's existence, not its contents (Greptile P1, PR #45, "Existence
# check validates content" — tightened from the earlier bare-word-list version that let a
# sole "removed" wrongly pass a content claim on existence-only evidence).
_PATH_NOUN_RE = r"(?:file|path|director(?:y|ies)|dir|folder)"
ABSENCE_CLAIM_RE = re.compile(
    rf"\b{_PATH_NOUN_RE}\b.{{0,60}}\b(?:exists?|absent|removed|deleted|gone)\b"
    rf"|\b(?:exists?|absent|removed|deleted|gone)\b.{{0,60}}\b{_PATH_NOUN_RE}\b"
    rf"|\bno longer (?:exists?|present)\b"
    rf"|\bnot present\b"
    rf"|\bdoes(?:n't| not) exist\b",
    re.IGNORECASE,
)

# `test -f X && grep ... X` short-circuits on a missing X before the search clause ever
# runs, leaving the exact same exit code as "X exists but the search found nothing" — exit
# code alone cannot tell the two apart (Greptile P1, PR #45, "Missing file passes content
# claim"). Only captured output can: a search tool that actually ran and printed something
# (e.g. `grep -c` always prints a count, even "0") is evidence the chain reached it; a
# short-circuited chain prints nothing at all. Anchored to the START of the command (not
# end-to-end like EXISTENCE_ONLY_RE above), since a content search is chained on after it.
# The path each branch guards is captured so a quiet search (see SILENT_SEARCH_RE below) can
# be checked against a separate, independent existence command for that same path.
COMPOUND_EXISTENCE_GATE_RE = re.compile(
    r"^\s*(?:test\s+-[a-z]\s+(?P<gate_path1>\S+)|\[\s+-[a-z]\s+(?P<gate_path2>\S+)\s+\])\s*&&",
    re.IGNORECASE,
)

# `grep -q`/`grep --quiet` is defined to print nothing at all, whether it matches or not —
# silence is its normal, successful behaviour, not a sign the chain short-circuited. But that
# cuts both ways: it also means a quiet search's empty output_tail can never be told apart
# from `test -f X` failing and the chain short-circuiting before grep ever ran — both leave
# the same non-zero exit code and the same empty output (Greptile P1, PR #45, "Missing file
# passes quiet-grep check"). Exit code plus output_tail alone cannot resolve that ambiguity,
# so a quiet-search chain needs independent proof the file existed: a separate, EARLIER
# command in the receipt that tests the exact same path and exits 0 (see
# _confirmed_by_sibling_existence_check below). Without that sibling evidence, a quiet-grep
# compound is rejected as content proof, same as the unquiet case above (Greptile P1, PR #45,
# "Silent searches fail validation" — superseded: accepting a bare quiet-grep chain on its own
# exit code let a missing file pass as a quiet no-match).
SILENT_SEARCH_RE = re.compile(r"\bgrep\b[^&|;]*(?:-[a-zA-Z]*q[a-zA-Z]*\b|--quiet\b)")


def _is_positive_existence_check(cmd: dict, path: str) -> bool:
    """True if `cmd` is a real file-existence probe (`test -f`/`test -e`, or the `[ ... ]`
    equivalent — see FILE_EXISTENCE_PROBE_RE) naming EXACTLY `path`, that itself exited 0 —
    independent proof the path was actually there, not inferred from the exit code of a
    compound command that might never have reached it.

    Two things a looser check would get wrong: a path match must be exact-token equality,
    not substring (`config.yaml.bak` must not corroborate `config.yaml`), and the flag must
    be a real file-existence test, not `test -n`/`-z` (those test a STRING's emptiness, not
    the filesystem, even when the string happens to be the path) (Greptile P1, PR #45,
    "Unrelated checks confirm missing files").
    """
    if cmd.get("exit_code") != 0:
        return False
    match = FILE_EXISTENCE_PROBE_RE.match(str(cmd.get("cmd", "")).strip())
    if not match:
        return False
    return (match.group("path1") or match.group("path2")) == path


def _confirmed_by_sibling_existence_check(commands: list, path: str, exclude_idx: int) -> bool:
    """True if some EARLIER command (lower index than `exclude_idx`) independently proves
    `path` existed before the quiet-search compound at `exclude_idx` ran.

    This is the only evidence that can break the tie between a quiet-grep compound that
    actually ran and found nothing, and one whose leading existence check failed and never
    reached grep at all — both look identical from the compound command's own exit code and
    output_tail alone. Order matters as much as existence: a `test -f X` recorded AFTER the
    quiet search only proves X exists NOW — it could have been created after the search ran
    and found nothing, which is the exact ambiguity this function exists to resolve, not
    corroborate (Greptile P1, PR #45, "Later check validates earlier search"). So only a
    sibling strictly before `exclude_idx` counts.
    """
    return any(
        _is_positive_existence_check(other, path)
        for j, other in enumerate(commands)
        if j < exclude_idx and isinstance(other, dict)
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

        if strict and EXHAUSTIVE_RE.search(text):
            if expects_failure:
                cmd_text = str(cited.get("cmd", "")) if isinstance(cited, dict) else ""
                output_tail = (
                    str(cited.get("output_tail", "")) if isinstance(cited, dict) else ""
                )

                # A quiet-grep compound (`test -f X && grep -q PATTERN X`) with empty
                # output_tail is ambiguous on its own exit code alone (see SILENT_SEARCH_RE
                # above) — it needs one specific OTHER command as corroboration: a bare
                # existence check on that same path that itself exited 0. gate_path is set
                # only when the cited command is exactly that shape, so every other claim
                # keeps the single-command rule below unchanged.
                gate_match = COMPOUND_EXISTENCE_GATE_RE.match(cmd_text)
                gate_path = (
                    gate_match.group("gate_path1") or gate_match.group("gate_path2")
                    if gate_match and not output_tail.strip() and SILENT_SEARCH_RE.search(cmd_text)
                    else None
                )

                # A single expected-failure command CAN be exhaustive evidence: a search
                # that exits non-zero exactly when it finds nothing across its whole target
                # (e.g. a grep for any populated value) is reproduction evidence and total
                # coverage at once. What it must never do is borrow OTHER, unrelated
                # commands elsewhere in the receipt to look better-supported than it is —
                # that was the original bypass this check exists for (Greptile P1, PR #45):
                # a claim citing one narrow, failing command, padded by an unrelated command
                # recorded for something else (the fix that follows it, say). len(commands)
                # is a receipt-wide count, but here it is used the other way around from the
                # passing-evidence branch below: for THIS claim, more commands elsewhere in
                # the receipt is exactly the sign that something else might be doing the
                # padding, not more support — with one narrow exception: a command that
                # EARLIER in the receipt confirms gate_path existed is not padding the
                # claim's coverage, it is the only way a quiet-grep compound's ambiguous
                # exit code can be trusted at all (Greptile P1, PR #45, "Missing file passes
                # quiet-grep check"). That exception is order-sensitive: a matching command
                # recorded AFTER idx proves nothing about whether gate_path existed when the
                # quiet search ran (it could have been created afterward), so it still
                # counts as unexplained padding, not corroboration (Greptile P1, PR #45,
                # "Later check validates earlier search"). With no other, unexplained
                # command in the receipt to borrow from, this claim's cited command is
                # plainly its entire evidence, and its own scope is what a human reviewer
                # judges (approved_by), same as any other evidence-matching question this
                # gate cannot verify by itself.
                padding = [
                    j for j, other in enumerate(commands)
                    if j != idx and not (
                        gate_path and isinstance(other, dict)
                        and j < idx
                        and _is_positive_existence_check(other, gate_path)
                    )
                ]
                if padding:
                    problems.append(
                        f"claim[{i}] {text!r} sets expects_failure and asserts "
                        "exhaustiveness, and the receipt records other commands beyond the "
                        "one cited that are not an EARLIER sibling existence check "
                        "confirming the same exact path — they cannot be what makes this "
                        "claim exhaustive, so its cited command must be the receipt's only "
                        "command (or paired only with a command that tests the exact same "
                        "path and exits 0, recorded BEFORE it) for this to pass under "
                        "--strict"
                    )
                else:
                    # Clearing the padding concern above proves nothing by itself about WHY
                    # the command failed. A claim that "every value is empty" needs a
                    # failure that came from searching the content and finding nothing, not
                    # from the target being absent — those are different facts, and only a
                    # human (approved_by) can judge whether the command's own scope truly
                    # covers "every"/"all". This gate can at least catch the shapes of thin
                    # evidence that pattern most often: a missing-target error, a command
                    # that only checks existence and never looks at content either way, and
                    # a quiet-grep compound with no independent proof its target existed.
                    if MISSING_TARGET_RE.search(output_tail) or MISSING_TARGET_RE.search(
                        _strip_quoted(cmd_text)
                    ):
                        problems.append(
                            f"claim[{i}] {text!r} sets expects_failure and asserts "
                            f"exhaustiveness, but command[{idx}]'s evidence reads as the "
                            "target being missing (\"no such file\", \"not found\", ...), "
                            "not as a search that covered the claim's whole scope and found "
                            "nothing — a missing target proves nothing about the content the "
                            "claim describes"
                        )
                    elif EXISTENCE_ONLY_RE.search(cmd_text):
                        if not ABSENCE_CLAIM_RE.search(text):
                            problems.append(
                                f"claim[{i}] {text!r} asserts exhaustiveness over content, "
                                f"but command[{idx}] ({cmd_text!r}) only tests whether a "
                                "path exists — that proves nothing about the content "
                                "inside it"
                            )
                        # else: the claim is about the path's absence, not its content —
                        # the existence probe's exit code is direct, sufficient evidence.
                    elif COMPOUND_EXISTENCE_GATE_RE.match(cmd_text) and not output_tail.strip():
                        if not SILENT_SEARCH_RE.search(cmd_text):
                            problems.append(
                                f"claim[{i}] {text!r} asserts exhaustiveness via a command "
                                f"that chains a content search after an existence check "
                                f"({cmd_text!r}) with no captured output — the existence "
                                "check failing would short-circuit the chain and produce "
                                "this exact same exit code without the search ever running. "
                                "Record output_tail evidence that the search itself "
                                "executed (e.g. a `grep -c` count), or cite the existence "
                                "check and the search as separate commands"
                            )
                        else:
                            if not gate_path or not _confirmed_by_sibling_existence_check(
                                commands, gate_path, idx
                            ):
                                problems.append(
                                    f"claim[{i}] {text!r} asserts exhaustiveness via a "
                                    f"quiet search chained after an existence check "
                                    f"({cmd_text!r}) with no captured output — `grep -q`/"
                                    "`--quiet` prints nothing whether it matches or not, so "
                                    "this exit code is identical whether the search ran and "
                                    f"found nothing, or the existence check on {gate_path!r} "
                                    "failed and the chain short-circuited before grep ever "
                                    "ran. Record a separate command in 'commands', BEFORE "
                                    f"this one, that tests the exact path {gate_path!r} and "
                                    "exits 0, proving the file was actually there when the "
                                    "search ran — the same check recorded AFTER this command "
                                    "only proves the file exists now, not that it did then"
                                )
                            # else: a separate, earlier command in the receipt already
                            # proved the target present, so the chain's own exit code —
                            # reachable only if its existence check passed too — is valid
                            # negative content evidence.
            elif len(commands) < 2:
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
