#!/usr/bin/env python3
"""Generate the Grok Bot Team-only templates under grokbot/templates/<SEAT>.md.

A template carries only what Grok Bot copies when a team member adds the Bot: name,
description (permanent rules), enabled skills, routines and avatar. It carries no UUID,
channel id, prompt body, token or tailnet name — G-7 (ci/gates/check_desk_integrity.py)
fails a template that does. Everything here is read from the seat prompt sources, the
roster contracts and the team roster; the files are regenerated, never hand-edited.

    python3 scripts/generate-templates.py
    python3 scripts/generate-templates.py --roster grokbot/rosters/<team>.json --out grokbot/templates
    python3 scripts/generate-templates.py --check      # exit 1 when the committed files differ

Plan: docs/upgrade-plan-desk-v2.md §9.1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("generate-templates: pyyaml is required (pip install pyyaml)")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROSTER = "grokbot/rosters/spectrumwebco.json"
DEFAULT_OUT = "grokbot/templates"
ROSTERS_DIR = "contracts/tool-rosters"
PROMPTS_DIR = "prompts"

# (bot id, SEAT, roster short, template name)
SEATS: list[tuple[str, str, str, str]] = [
    ("bot-00-programming-lead", "LEAD", "lead", "Programming Lead (LEAD)"),
    ("bot-01-systems-backend", "SYSTEMS", "systems", "Systems & Design (SYSTEMS)"),
    ("bot-02-web-edge", "WEB", "web", "Web & Desktop (WEB)"),
    ("bot-03-android", "ANDROID", "android", "Android & Play Release (ANDROID)"),
    ("bot-04-ios", "IOS", "ios", "iOS & App Store (IOS)"),
    ("bot-05-infrastructure", "INFRA", "infra", "Infra & WEB3 (INFRA)"),
    ("bot-06-quality-security", "QUALITY", "quality", "Quality & Security (QUALITY)"),
]

# Every seat enables these regardless of what its prompt marks load="always".
#
# desk-production-loop is a base skill rather than a per-seat load="always" entry because it is
# desk policy, not a seat preference: the loop (brief -> act -> memory_write -> events_emit ->
# handoff_to_hermes, with memory_brief and its etag required before any repo work) has to hold on
# every seat or the memory plane has holes in it, and a seat that could opt out of it is a seat
# whose brief the next seat cannot trust. It also carries the two negative defaults -- no raw docs
# or memory connector, and skills list/invoke only until skills.approve exists -- which are
# likewise desk-wide.
BASE_SKILLS = [
    "desk-bootstrap",
    "desk-production-loop",
    "desk-doctor",
    "verification-receipts",
]

PAUSED = "paused until desk_doctor check is green"
LEAD_ROUTINES = [
    ("desk-held-poll", "every 10 minutes: poll held seat→LEAD handoffs (priority false)"),
    ("desk-intake-poll", "every 10 minutes, or on a GitHub desk:intake label event: "
                         "desk_intake_next, then the double uplift"),
]
SEAT_ROUTINES = [
    ("desk-heartbeat", "daily: desk_brief"),
]

# Defence in depth: the generator refuses to write what G-7 would reject. Kept in step with
# TEMPLATE_FORBIDDEN in ci/gates/check_desk_integrity.py.
FORBIDDEN = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "literal UUID"),
    (re.compile(r"\{\{[A-Z_:]+\}\}"), "unfilled placeholder"),
    (re.compile(r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xox[abp]-|AKIA[0-9A-Z]{16}|-----BEGIN"), "token shape"),
    (re.compile(r"tailscale-forwarder|\.ts\.net|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\."), "tailnet name or address"),
    (re.compile(r"railway\.internal"), "Railway private hostname"),
]


def collapse(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def skill_dir_name(path: str) -> str:
    """skills/platforms/ios/SKILL.md -> ios; skills/desk-gateway/SKILL.md -> desk-gateway."""
    parts = Path(path).parts
    if len(parts) < 2 or parts[-1] != "SKILL.md":
        raise ValueError(f"skill path {path!r} does not end in <dir>/SKILL.md")
    return parts[-2]


def read_prompt(path: Path) -> tuple[list[str], list[str]]:
    """(role_charter statements, always-loaded skill directory names) from a seat prompt source."""
    root = ET.parse(path).getroot()
    charter = root.find("role_charter")
    if charter is None:
        raise ValueError(f"{path.name}: no <role_charter>")
    statements = [collapse(s.text) for s in charter.findall("statement")]
    statements = [s for s in statements if s]
    if not statements:
        raise ValueError(f"{path.name}: <role_charter> has no <statement>")
    always: list[str] = []
    skills = root.find("skills")
    if skills is not None:
        for skill in skills.findall("skill"):
            if skill.get("load") == "always" and skill.get("path"):
                always.append(skill_dir_name(skill.get("path", "")))
    return statements, always


def read_roster_contract(path: Path, bot_id: str, short: str) -> str:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: top level is not a mapping")
    if doc.get("seat") != bot_id:
        raise ValueError(f"{path.name}: seat is {doc.get('seat')!r}, expected {bot_id!r}")
    if doc.get("short") != short:
        raise ValueError(f"{path.name}: short is {doc.get('short')!r}, expected {short!r}")
    endpoint = doc.get("endpoint")
    if endpoint != f"/mcp/{short}":
        raise ValueError(f"{path.name}: endpoint is {endpoint!r}, expected '/mcp/{short}'")
    return endpoint


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def render(seat: str, short: str, name: str, bot_id: str, statements: list[str],
           skills: list[str], gateway_url: str, endpoint: str) -> str:
    routines = LEAD_ROUTINES if seat == "LEAD" else SEAT_ROUTINES
    lines: list[str] = [
        f"# {name}",
        "",
        f"Grok Bot Team-only template for the {seat} seat. Generated by scripts/generate-templates.py "
        f"from prompts/{bot_id}.xml and {ROSTERS_DIR}/{short}.yaml; do not hand-edit. "
        "Share -> Create template -> Team-only. Carries no ids, tokens or prompt body: "
        "those arrive through /desk bootstrap.",
        "",
        "## Name",
        "",
        name,
        "",
        "## Description",
        "",
    ]
    for statement in statements:
        lines.append(statement)
        lines.append("")
    lines.append("First run: /desk bootstrap")
    lines.append(f"Gateway: {gateway_url}{endpoint}")
    lines.append("")
    lines.append("## Enabled skills")
    lines.append("")
    for skill in skills:
        lines.append(f"- {skill}")
    lines.append("")
    lines.append("## Routines")
    lines.append("")
    for routine, what in routines:
        lines.append(f"- {routine} — {what} — {PAUSED}")
    lines.append("")
    lines.append("## Avatar")
    lines.append("")
    lines.append(f"Avatar: grokbot/avatars/{short}.png")
    lines.append("")
    return "\n".join(lines)


def check_forbidden(seat: str, text: str) -> list[str]:
    problems: list[str] = []
    for pattern, why in FORBIDDEN:
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                problems.append(f"{seat}.md: contains {why} at line {line_no}")
                break
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate grokbot/templates/<SEAT>.md")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT, help="Repository checkout")
    ap.add_argument("--roster", type=Path, help=f"Team roster JSON (default: {DEFAULT_ROSTER})")
    ap.add_argument("--out", type=Path, help=f"Output directory (default: {DEFAULT_OUT})")
    ap.add_argument("--check", action="store_true",
                    help="Write nothing; exit 1 if a committed template differs from the generated one")
    args = ap.parse_args()

    repo = args.repo.resolve()
    roster_path = (args.roster or repo / DEFAULT_ROSTER).resolve()
    out_dir = (args.out or repo / DEFAULT_OUT).resolve()

    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"generate-templates: cannot read roster {roster_path}: {exc}")
    gateway_url = str(roster.get("gateway_url", "")).rstrip("/")
    if not gateway_url.startswith("https://"):
        sys.exit(f"generate-templates: roster {roster_path} has no https gateway_url")

    rendered: dict[str, str] = {}
    problems: list[str] = []
    for bot_id, seat, short, name in SEATS:
        prompt_path = repo / PROMPTS_DIR / f"{bot_id}.xml"
        contract_path = repo / ROSTERS_DIR / f"{short}.yaml"
        try:
            statements, always = read_prompt(prompt_path)
            endpoint = read_roster_contract(contract_path, bot_id, short)
        except (OSError, ValueError, ET.ParseError) as exc:
            problems.append(f"{seat}: {exc}")
            continue
        skills = dedupe(BASE_SKILLS + always)
        text = render(seat, short, name, bot_id, statements, skills, gateway_url, endpoint)
        problems.extend(check_forbidden(seat, text))
        rendered[seat] = text

    if problems:
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(f"generate-templates: {len(problems)} problem(s); nothing written", file=sys.stderr)
        return 1

    if args.check:
        drift = []
        for seat, text in rendered.items():
            dest = out_dir / f"{seat}.md"
            if not dest.exists():
                drift.append(f"{dest.relative_to(repo) if dest.is_relative_to(repo) else dest}: missing")
            elif dest.read_text(encoding="utf-8") != text:
                drift.append(f"{dest.relative_to(repo) if dest.is_relative_to(repo) else dest}: differs")
        if drift:
            for d in drift:
                print(f"  - {d}", file=sys.stderr)
            print(f"generate-templates --check: {len(drift)} template(s) out of date; "
                  "run scripts/generate-templates.py and commit the result", file=sys.stderr)
            return 1
        print(f"generate-templates --check: {len(rendered)} templates up to date")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for seat, text in rendered.items():
        dest = out_dir / f"{seat}.md"
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(repo) if dest.is_relative_to(repo) else dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
