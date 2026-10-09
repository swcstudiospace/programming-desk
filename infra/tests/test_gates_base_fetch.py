"""The base-ref fetch in both gate workflows must not be shallow.

Template sync only compares the two copies to each other. Restoring
``--depth=1`` in both files would leave that check green, and
``origin/$BASE_REF...HEAD`` would have no merge base once the base moves
past the fork point. This reads the fetch out of each file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ".github/workflows/gates.yml",
    "ci/.github/workflows/gates.yml",
]


def fetches(workflow: str) -> list[str]:
    doc = yaml.safe_load((REPO_ROOT / workflow).read_text())
    found: list[str] = []
    for job in doc["jobs"].values():
        for step in job.get("steps") or []:
            for line in (step.get("run") or "").splitlines():
                stripped = line.strip()
                if stripped.startswith("git fetch"):
                    found.append(stripped)
    return found


def assert_unshallowed(workflow: str, lines: list[str]) -> None:
    assert len(lines) == 2, (
        f"{workflow} should fetch the base ref once in each job, got {lines}"
    )
    for fetch in lines:
        assert "--depth" not in fetch, (
            f"{workflow} shallow-fetches the base ref ({fetch}). "
            "That cuts history, so origin/$BASE_REF...HEAD has no merge base "
            "once the base moves past the fork point."
        )
        assert "refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF" in fetch, (
            f"{workflow} fetch does not update origin/$BASE_REF at full depth: {fetch}"
        )


def test_depth_limited_fetch_is_rejected():
    """The old command, the one that broke G-1, is the case this guard exists for."""
    old = 'git fetch --no-tags --depth=1 origin "$BASE_REF"'
    with pytest.raises(AssertionError, match="shallow-fetches"):
        assert_unshallowed("fixture", [old, old])


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_workflow_fetches_the_base_ref_at_full_depth(workflow):
    assert_unshallowed(workflow, fetches(workflow))
