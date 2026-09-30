"""Regression guard for the security PR gate (SPE-5162).

.github/workflows/security-pr.yml is a GitHub Actions workflow, not a ci/gates/*.py script, so
nothing in the rest of this suite ever parses it. That means a later edit could quietly drop a
blocking flag — swap -lll for -l, add ignore-unfixed back, drop --error — and gate-self-test
would stay green, because gate-self-test only runs pytest, and pytest never looked at this file.

This does not run the scanners (that needs network access and the tools installed; the PR gate
itself is what actually exercises them). It asserts the workflow still SAYS it will enforce
HIGH+ and still contains no bypass, which is the one thing a diff review can silently miss.

    python3 -m pytest ci/tests/test_security_workflows.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security-pr.yml"

# Same bypass patterns G-2 (ci/gates/check_receipt.py) rejects in a receipt's commands — a
# workflow step that masks its own exit code is the same failure in a different file.
BYPASS_SNIPPETS = ["|| true", "|| exit 0", "2>/dev/null", "--exit-zero", "--dry-run"]


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _job(workflow: dict, name: str) -> dict:
    return workflow["jobs"][name]


def _step(job: dict, name_substring: str) -> dict:
    for step in job["steps"]:
        if name_substring in step.get("name", ""):
            return step
    raise AssertionError(f"no step matching {name_substring!r} in job {job}")


def _all_run_blocks(workflow: dict) -> list[str]:
    blocks = []
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if "run" in step:
                blocks.append(step["run"])
    return blocks


class TestNoBypass:
    """The same class of failure G-2 rejects in a receipt, checked in the workflow itself."""

    def test_no_bypass_snippets_anywhere(self, workflow):
        for block in _all_run_blocks(workflow):
            for snippet in BYPASS_SNIPPETS:
                assert snippet not in block, f"bypass {snippet!r} found in a workflow run: block"


class TestGitleaksBlocks:
    def test_exit_code_1_on_leak(self, workflow):
        step = _step(_job(workflow, "secrets"), "Gitleaks")
        assert "--exit-code 1" in step["run"]

    def test_scoped_to_pr_commits_not_full_history(self, workflow):
        # The whole point of ci/security/gitleaks.toml's design note: a full-history scan hits
        # pre-existing fixture secrets in this repo's own gate tests.
        step = _step(_job(workflow, "secrets"), "Gitleaks")
        assert "--log-opts=" in step["run"]
        assert "..HEAD" in step["run"]


class TestSemgrepBlocks:
    def test_severity_and_error_flag_present(self, workflow):
        step = _step(_job(workflow, "semgrep"), "Semgrep — repo rules")
        assert "--severity ERROR" in step["run"]
        assert "--error" in step["run"]

    def test_baseline_scoped_to_this_pr(self, workflow):
        # Without this, a whole-repo scan fails PRs on pre-existing findings they never touched
        # (confirmed locally: scripts/generate-templates.py trips p/security-audit on main).
        step = _step(_job(workflow, "semgrep"), "Semgrep — repo rules")
        assert "--baseline-commit" in step["run"]


class TestBanditBlocks:
    def test_high_severity_floor(self, workflow):
        step = _step(_job(workflow, "bandit"), "Bandit — whole repo, HIGH severity only, new findings")
        assert "-lll" in step["run"]

    def test_gating_scan_uses_baseline(self, workflow):
        # `bandit -r .` with no baseline fails every PR on infra/unified-lsp-broker/broker.py's
        # pre-existing B324 finding (confirmed live on PR #50). A per-changed-file git-diff list
        # was tried next, but a reviewer correctly flagged two problems: `mapfile < <(git diff
        # ...)` silently swallows a git-diff failure (bash's `set -e` doesn't see inside process
        # substitution) producing a false "nothing to scan" pass, and scanning whole changed
        # files still re-flags pre-existing findings in a touched file. -b/--baseline against a
        # snapshot of the base ref fixes both: no git-diff file selection to silently fail, and
        # findings already on the base ref are suppressed regardless of which files changed.
        gating_step = _step(_job(workflow, "bandit"), "Bandit — whole repo, HIGH severity only, new findings")
        assert "-b bandit-baseline.json" in gating_step["run"]
        assert "-r ." in gating_step["run"]

    def test_baseline_snapshot_fails_closed_on_error(self, workflow):
        # A crashed/misconfigured baseline scan must not be silently treated as an empty,
        # always-passing baseline — that would be the same fail-open shape as the git-diff bug.
        baseline_step = _step(_job(workflow, "bandit"), "Bandit baseline")
        assert "baseline_ec" in baseline_step["run"]
        assert "exit 1" in baseline_step["run"]

    def test_informational_sarif_step_does_not_gate(self, workflow):
        # The gating decision lives entirely in the baseline-compared JSON step; the unfiltered
        # SARIF step is for artifact/code-scanning visibility only and must not be able to fail
        # the job (bandit -b is incompatible with -f sarif, so this step can't baseline-filter).
        sarif_step = _step(_job(workflow, "bandit"), "Bandit — SARIF artifact")
        assert sarif_step.get("continue-on-error") is True


class TestTrivyBlocks:
    def test_severity_and_exit_code(self, workflow):
        job = _job(workflow, "dependencies")
        step = next(s for s in job["steps"] if s.get("uses", "").startswith("aquasecurity/trivy-action"))
        assert step["with"]["severity"] == "HIGH,CRITICAL"
        assert str(step["with"]["exit-code"]) == "1"

    def test_ignore_unfixed_not_set(self, workflow):
        # ignore-unfixed: true would let an unpatched HIGH/CRITICAL finding merge silently —
        # exactly the class of vulnerability "fail on HIGH+" exists to catch. Regression added
        # in the first version of this workflow; caught by a human reviewer, not CI.
        job = _job(workflow, "dependencies")
        step = next(s for s in job["steps"] if s.get("uses", "").startswith("aquasecurity/trivy-action"))
        assert step["with"].get("ignore-unfixed") is not True


class TestActionsPinnedBySha:
    """SECURITY.md: 'pin what executes by commit SHA, not a mutable tag.'"""

    THIRD_PARTY_PREFIXES = ("aquasecurity/", "zaproxy/", "github/codeql-action")

    def test_third_party_actions_pinned_by_sha(self, workflow):
        import re

        sha_re = re.compile(r"^[0-9a-f]{40}$")
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                uses = step.get("uses", "")
                if not uses.startswith(self.THIRD_PARTY_PREFIXES):
                    continue
                ref = uses.rsplit("@", 1)[-1]
                assert sha_re.match(ref), f"{uses!r} is not pinned by a 40-char commit SHA"


class TestPermissionsScoping:
    def test_no_write_permission_at_workflow_root(self, workflow):
        # SECURITY.md: widen permissions one job at a time, never at the workflow root.
        root_perms = workflow.get("permissions", {})
        assert root_perms.get("security-events") != "write"

    def test_jobs_with_sarif_upload_declare_the_permission_themselves(self, workflow):
        for job_name, job in workflow["jobs"].items():
            uses_codeql = any(
                step.get("uses", "").startswith("github/codeql-action") for step in job["steps"]
            )
            if uses_codeql:
                assert job.get("permissions", {}).get("security-events") == "write", (
                    f"job {job_name!r} uploads SARIF but doesn't declare security-events: write"
                )
