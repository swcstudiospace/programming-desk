"""Tests verifying integrity and bounds of the 15 Cursor subagents in .cursor/agents/.

Covers REQ-DRILL-001:
- Valid YAML frontmatter (name, description, model).
- Presence of mandatory sections: <swarm_runtime>, <agent>, <role>, <inputs>, <outputs>.
- Cursor tools matching allowed set (Read, Grep, Glob, Write, StrReplace, Shell).
- Prompt size and token bounds (within acceptable context window limits).
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".cursor" / "agents"

EXPECTED_AGENTS = [
    "a01-orchestrator",
    "a02-requirements",
    "a03-architect",
    "a04-ux-designer",
    "a05-backend",
    "a06-frontend",
    "a07-data",
    "a08-qa",
    "a09-reviewer",
    "a10-security",
    "a11-devops",
    "a12-release",
    "a13-observability",
    "a14-maintenance",
    "a15-docs",
]

ALLOWED_CURSOR_TOOLS = {"Read", "Grep", "Glob", "Write", "StrReplace", "Shell"}
MAX_AGENT_CHAR_COUNT = 30000
MIN_AGENT_CHAR_COUNT = 1000


def _parse_agent_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"Agent {path.name} does not start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Agent {path.name} malformed YAML frontmatter")
    frontmatter = yaml.safe_load(parts[1])
    body = parts[2]
    return frontmatter, body


def test_all_15_agents_exist():
    assert AGENTS_DIR.is_dir(), f"{AGENTS_DIR} does not exist"
    for slug in EXPECTED_AGENTS:
        agent_file = AGENTS_DIR / f"{slug}.md"
        assert agent_file.is_file(), f"Missing agent file: {agent_file.name}"


@pytest.mark.parametrize("slug", EXPECTED_AGENTS)
def test_agent_frontmatter_valid(slug: str):
    agent_file = AGENTS_DIR / f"{slug}.md"
    frontmatter, _ = _parse_agent_markdown(agent_file)
    assert isinstance(frontmatter, dict)
    assert frontmatter.get("name") == slug
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter.get("model") == "inherit"


@pytest.mark.parametrize("slug", EXPECTED_AGENTS)
def test_agent_required_sections_present(slug: str):
    agent_file = AGENTS_DIR / f"{slug}.md"
    _, body = _parse_agent_markdown(agent_file)

    assert "<swarm_runtime>" in body and "</swarm_runtime>" in body
    assert "<agent" in body and "</agent>" in body
    assert "<role>" in body and "</role>" in body
    assert "<inputs>" in body and "</inputs>" in body
    assert "<outputs>" in body and "</outputs>" in body


@pytest.mark.parametrize("slug", EXPECTED_AGENTS)
def test_agent_cursor_tools_allowed(slug: str):
    agent_file = AGENTS_DIR / f"{slug}.md"
    _, body = _parse_agent_markdown(agent_file)

    match = re.search(r"Cursor tools:\s*([^\n\.]+)", body)
    assert match, f"No 'Cursor tools:' declaration found in {agent_file.name}"
    tools_str = match.group(1).replace("and", ",")
    tools = [t.strip().strip(",") for t in tools_str.split(",") if t.strip()]
    
    for tool in tools:
        assert tool in ALLOWED_CURSOR_TOOLS, f"Unauthorized tool {tool!r} in {agent_file.name}"


@pytest.mark.parametrize("slug", EXPECTED_AGENTS)
def test_agent_token_and_character_bounds(slug: str):
    agent_file = AGENTS_DIR / f"{slug}.md"
    content = agent_file.read_text(encoding="utf-8")
    
    char_count = len(content)
    assert MIN_AGENT_CHAR_COUNT <= char_count <= MAX_AGENT_CHAR_COUNT, (
        f"{agent_file.name} char length {char_count} outside [{MIN_AGENT_CHAR_COUNT}, {MAX_AGENT_CHAR_COUNT}]"
    )
