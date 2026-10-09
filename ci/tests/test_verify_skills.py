#!/usr/bin/env python3
"""Structural checks for the verify skill family.

The live tree must pass. A skill that drops a required section, or that cites
a repo path which does not exist outside a fenced block marked example, must
fail. Paths inside a fence whose info string contains the word "example" are
not treated as citations.

    python3 ci/tests/test_verify_skills.py
    python3 ci/tests/test_verify_skills.py --fixture missing-section
    python3 ci/tests/test_verify_skills.py --fixture missing-path
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SKILL_PATHS = (
    "skills/verify/SKILL.md",
    "skills/verify-web/SKILL.md",
    "skills/verify-desktop/SKILL.md",
    "skills/verify-ios/SKILL.md",
    "skills/verify-android/SKILL.md",
    "skills/verify-infra/SKILL.md",
    "skills/verify-systems/SKILL.md",
)

REQUIRED_SECTIONS = (
    "Launch",
    "Doctor",
    "Drive",
    "Evidence",
    "Cleanup",
    "Where it runs",
    "Receipt mapping",
)

# First ~30 lines carry the L1 tree. Forty leaves room for a one-line
# frontmatter field without letting the tree slide into the method.
L1_LINE_BUDGET = 40

PSTACK_CREDIT = (
    "Method adapted from pstack (MIT, Lauren Tan, "
    "github.com/cursor/plugins/tree/main/pstack)."
)

FEATURE_MAP_HEADINGS = (
    "## Sub-features",
    "## How to get to it (user POV)",
    "## Driving it with <harness>",
    "## Gotchas",
)

SEAT_SKILLS = {
    "LEAD": ("skills/verify/SKILL.md",),
    "QUALITY": ("skills/verify/SKILL.md",),
    "SYSTEMS": ("skills/verify-systems/SKILL.md",),
    "WEB": ("skills/verify-web/SKILL.md", "skills/verify-desktop/SKILL.md"),
    "ANDROID": ("skills/verify-android/SKILL.md",),
    "IOS": ("skills/verify-ios/SKILL.md",),
    "INFRA": ("skills/verify-infra/SKILL.md",),
}

# A citation is a repo-relative path under one of these roots. Match the
# whole path/glob token before excluding patterns, never a glob's prefix.
# Globs and example fences are not citations. A bare filename with no slash
# is not, because skills name files absent from this checkout on purpose.
PATH_RE = re.compile(
    r"(?<![\w@./-])"
    r"((?:skills|ios|android|contracts|prompts-assembled|prompts|ci|docs|"
    r"services|scripts|\.github|web|infra|desktop|apps|tauri|electron)/"
    r"[A-Za-z0-9_./*?\[\]!^-]*[A-Za-z0-9_*?\[\]/-])"
)

FENCE_RE = re.compile(r"```([^\n]*)\n(.*?)```", re.DOTALL)


def _strip_example_fences(text: str) -> str:
    """Drop fenced blocks marked as examples. Leave every other byte."""

    def replacer(match: re.Match[str]) -> str:
        info = match.group(1)
        if re.search(r"(?i)\bexample\b", info):
            return ""
        return match.group(0)

    return FENCE_RE.sub(replacer, text)


def _frontmatter(text: str) -> str | None:
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        return None
    return match.group(1)


def skill_problems(text: str, repo_root: Path, label: str) -> list[str]:
    """Problems for one skill body. Paths resolve against repo_root."""
    problems: list[str] = []
    front = _frontmatter(text)
    if front is None:
        problems.append(f"{label}: missing frontmatter")
        scanned = text
    else:
        scanned_front = front
        if not re.search(r"(?m)^name:\s*\S+", scanned_front):
            problems.append(f"{label}: frontmatter needs name")
        if not re.search(r"(?m)^description:\s*\S+", scanned_front):
            problems.append(f"{label}: frontmatter needs description")
        if not re.search(r"(?m)^bots:\s*\[.+\]\s*$", scanned_front):
            problems.append(f"{label}: frontmatter needs a bots list")
        if not re.search(r"(?m)^gates:\s*\[[^\]]*G-2[^\]]*\]\s*$", scanned_front):
            problems.append(f"{label}: frontmatter gates must include G-2")

    head = "\n".join(text.splitlines()[:L1_LINE_BUDGET])
    if "Decision tree:" not in head:
        problems.append(
            f"{label}: L1 decision tree is not in the first {L1_LINE_BUDGET} lines"
        )

    visible = _strip_example_fences(text)
    for section in REQUIRED_SECTIONS:
        if not re.search(rf"(?m)^## {re.escape(section)}\s*$", visible):
            problems.append(f"{label}: missing section {section!r}")

    for match in PATH_RE.finditer(visible):
        cited = match.group(1).rstrip("/")
        if any(char in cited for char in "*?[]") or ".." in cited.split("/"):
            continue
        candidate = repo_root / cited
        if not candidate.exists():
            problems.append(f"{label}: cites missing path {cited}")
    return problems


def tree_problems(repo_root: Path) -> list[str]:
    problems: list[str] = []
    for rel in SKILL_PATHS:
        path = repo_root / rel
        if not path.is_file():
            problems.append(f"{rel}: skill file is missing")
            continue
        problems.extend(skill_problems(path.read_text(encoding="utf-8"), repo_root, rel))
    return problems


def _minimal_skill(*, drop: str | None = None, extra: str = "") -> str:
    sections = [name for name in REQUIRED_SECTIONS if name != drop]
    lines = [
        "---",
        "name: sample",
        "description: Sample skill used to prove the structural check can fail.",
        "bots: [bot-06-quality-security]",
        "gates: [G-2]",
        "---",
        "",
        "# Sample",
        "",
        "## L1 — Summary",
        "",
        "**Decide, then act.** A claim without a command is not a claim (G-2).",
        "",
        "**Decision tree:**",
        "",
        "```",
        "Need to verify?",
        "└─▶ Drive, then map the run onto the receipt.",
        "```",
        "",
    ]
    for name in sections:
        lines.append(f"## {name}")
        lines.append("")
        lines.append("Do this step, because skipping it leaves the receipt without evidence (G-2).")
        lines.append("")
    if extra:
        lines.append(extra)
        lines.append("")
    return "\n".join(lines)


def _write_family(root: Path, *, broken: str | None, extra: str) -> None:
    for rel in SKILL_PATHS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        drop = "Cleanup" if broken == "section" and rel == SKILL_PATHS[0] else None
        body_extra = extra if broken == "path" and rel == SKILL_PATHS[0] else ""
        path.write_text(_minimal_skill(drop=drop, extra=body_extra), encoding="utf-8")


def fixture_problems(kind: str) -> list[str]:
    """Build a throwaway family and return its problems. Nothing is written to the repo."""
    if kind not in {"missing-section", "missing-path"}:
        raise SystemExit(f"unknown fixture {kind!r}")
    with tempfile.TemporaryDirectory(prefix="verify-skills-") as tmp:
        root = Path(tmp)
        if kind == "missing-section":
            _write_family(root, broken="section", extra="")
        else:
            _write_family(
                root,
                broken="path",
                extra="The helper is web/verify/missing.sh and it is not in this checkout.",
            )
        return tree_problems(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the verify skill family")
    parser.add_argument(
        "--fixture",
        choices=("missing-section", "missing-path"),
        help="Run against a generated broken family and exit non-zero when the break is found",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Check this tree instead of the repository that contains this file",
    )
    args = parser.parse_args(argv)

    if args.fixture and args.root:
        print("pass either --fixture or --root, not both", file=sys.stderr)
        return 2
    if args.fixture:
        problems = fixture_problems(args.fixture)
    else:
        problems = tree_problems(args.root.resolve() if args.root else REPO_ROOT)

    if problems:
        print(f"verify-skills: {len(problems)} problem(s)")
        for item in problems:
            print(f"  - {item}")
        return 1
    print("verify-skills: ok")
    return 0


# --- pytest -----------------------------------------------------------------

def test_live_skills_pass() -> None:
    problems = tree_problems(REPO_ROOT)
    assert problems == [], "\n".join(problems)


def test_missing_section_is_detected() -> None:
    problems = fixture_problems("missing-section")
    assert any("missing section 'Cleanup'" in item for item in problems), problems


def test_missing_path_outside_fence_is_detected() -> None:
    problems = fixture_problems("missing-path")
    assert any("cites missing path web/verify/missing.sh" in item for item in problems), problems


def test_concrete_missing_path_fails_but_patterns_are_ignored(tmp_path: Path) -> None:
    patterns = (
        "apps/web/*",
        "apps/web/**/test_*.py",
        "apps/missing*/web/missing.py",
        "apps/web/missing?.py",
        "apps/web/[ab]/missing.py",
        "apps/web/[!ab]/missing.py",
        "apps/web/../missing.py",
    )
    text = _minimal_skill(
        extra="\n".join(
            [f"Pattern: `{pattern}`." for pattern in patterns]
            + ["Concrete helper: `apps/web/missing.py`."]
        )
    )
    assert skill_problems(text, tmp_path, "mixed") == [
        "mixed: cites missing path apps/web/missing.py"
    ]


def test_wildcard_suffix_never_cites_a_partial_missing_path(tmp_path: Path) -> None:
    for suffix in ("*", "?", "[ab]", "[!ab]", "]"):
        for token in (f"apps/web/missing{suffix}", f"apps/web/missing{suffix}/test.py"):
            text = _minimal_skill(extra=f"Pattern: `{token}`.")
            assert skill_problems(text, tmp_path, "pattern") == [], token


def test_example_fence_does_not_cite() -> None:
    text = _minimal_skill(
        extra="\n".join(
            [
                "An illustration, not a citation:",
                "",
                "```example",
                "web/verify/missing.sh",
                "```",
            ]
        )
    )
    assert skill_problems(text, REPO_ROOT, "example") == []


def test_unmarked_fence_still_cites() -> None:
    text = _minimal_skill(
        extra="\n".join(
            [
                "```text",
                "web/verify/missing.sh",
                "```",
            ]
        )
    )
    problems = skill_problems(text, REPO_ROOT, "unmarked")
    assert any("web/verify/missing.sh" in item for item in problems), problems


def test_cli_fixtures_exit_nonzero() -> None:
    import subprocess

    script = Path(__file__).resolve()
    for kind in ("missing-section", "missing-path"):
        result = subprocess.run(
            [sys.executable, str(script), "--fixture", kind],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout
        assert "problem" in result.stdout


def test_pstack_credit_is_only_on_the_router() -> None:
    router = (REPO_ROOT / "skills/verify/SKILL.md").read_text(encoding="utf-8")
    assert PSTACK_CREDIT in router
    for rel in SKILL_PATHS[1:]:
        body = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "pstack" not in body, rel


def test_feature_map_template_headings() -> None:
    text = (REPO_ROOT / "skills/verify/references/feature-map-template.md").read_text(
        encoding="utf-8"
    )
    for heading in FEATURE_MAP_HEADINGS:
        assert heading in text, heading


def test_readme_maps_every_verify_skill() -> None:
    readme = (REPO_ROOT / "skills/README.md").read_text(encoding="utf-8")
    for name in (
        "`verify`",
        "`verify-web`",
        "`verify-desktop`",
        "`verify-ios`",
        "`verify-android`",
        "`verify-infra`",
        "`verify-systems`",
    ):
        assert name in readme, name


def test_assembled_prompts_name_the_seat_skill() -> None:
    for seat, paths in SEAT_SKILLS.items():
        for folder in ("prompts-assembled", "prompts"):
            body = (REPO_ROOT / folder / f"{seat}.xml").read_text(encoding="utf-8")
            for rel in paths:
                assert rel in body, f"{folder}/{seat}.xml does not name {rel}"
    for seat in ("LEAD", "QUALITY"):
        for folder in ("prompts-assembled", "prompts"):
            body = (REPO_ROOT / folder / f"{seat}.xml").read_text(encoding="utf-8")
            assert "skills/verify-android/SKILL.md" not in body
            assert "skills/verify-ios/SKILL.md" not in body


if __name__ == "__main__":
    sys.exit(main())
