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
        step = _step(_job(workflow, "bandit"), "Bandit — this PR's changed Python files")
        assert "-lll" in step["run"]

    def test_scoped_to_pr_changed_files_not_whole_repo(self, workflow):
        # `bandit -r .` on the whole repo fails every PR on infra/unified-lsp-broker/broker.py's
        # pre-existing B324 finding (SHA1 in a WebSocket handshake) — confirmed live on PR #50.
        # Same class of bug as the Semgrep whole-repo scan; the fix here is a computed file list
        # instead of Semgrep's --baseline-commit, since bandit has no equivalent single flag.
        step = _step(_job(workflow, "bandit"), "Bandit — this PR's changed Python files")
        assert "PY_FILES" in step["run"]
        assert "bandit -r ." not in step["run"]
        assert "bandit \"${PY_FILES[@]}\"" in step["run"]

    def test_diff_failure_fails_closed_not_open(self, workflow):
        # Greptile P1 (PR #50): `mapfile -t PY_FILES < <(git diff ...)` runs the diff in a
        # process substitution whose exit status `set -e` never sees, so a `git diff` failure
        # (no merge-base, a too-shallow fetch) would silently look identical to "PR touched no
        # .py files" and pass. The fix captures the diff into a variable first and checks its
        # own exit status explicitly before ever treating the result as a file list.
        step = _step(_job(workflow, "bandit"), "Bandit — this PR's changed Python files")
        run = step["run"]
        assert "mapfile -t PY_FILES < <(git diff" not in run
        assert "if ! PY_DIFF=$(git diff" in run
        lines = run.splitlines()
        start = next(i for i, l in enumerate(lines) if "if ! PY_DIFF=$(git diff" in l)
        end = next(i for i, l in enumerate(lines[start:], start) if l.strip() == "fi")
        assert any("exit 1" in l for l in lines[start:end])

    def test_baseline_gate_invoked_for_new_vs_preexisting_findings(self, workflow):
        # Scoping to changed files alone doesn't stop a PR that edits
        # infra/unified-lsp-broker/broker.py for an unrelated reason from re-tripping its
        # pre-existing B324 finding. bandit_baseline_gate.py re-scans each changed file at the
        # base ref and only fails on findings that are NEW at HEAD, so unrelated edits to an
        # already-flagged file don't block the PR.
        step = _step(_job(workflow, "bandit"), "Bandit — this PR's changed Python files")
        assert "ci/security/bandit_baseline_gate.py" in step["run"]
        assert "--base-ref" in step["run"]


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
