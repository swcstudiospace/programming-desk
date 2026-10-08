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

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security-pr.yml"
BANDIT_SARIF_CONVERTER = REPO_ROOT / "ci" / "security" / "bandit_json_to_sarif.py"


def _load_converter():
    spec = importlib.util.spec_from_file_location("bandit_json_to_sarif", BANDIT_SARIF_CONVERTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

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


class TestBaseRefFetchKeepsHistory:
    """A --depth=1 fetch of the base ref shallows that tip.

    Checkout is already fetch-depth: 0. Fetching the base with --depth=1 writes a
    shallow boundary at the new tip and hides its ancestors. When main has moved
    past the PR's fork point, origin/$BASE_REF and HEAD then have no merge base:
    gitleaks' origin/$BASE_REF..HEAD walks the whole branch (fixture tokens
    included) and semgrep --baseline-commit exits 2. Confirmed on git 2.43 with a
    branch cut from an older main: the depth-1 fetch yielded 142 commits in the
    range, 21 gitleaks fixture hits, and semgrep exit 2; the full refspec fetch
    yielded 1 commit, 0 gitleaks findings, and semgrep exit 0.
    """

    FULL_FETCH = (
        'git fetch --no-tags origin "+refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF"'
    )

    def test_base_ref_is_not_fetched_shallow(self, workflow):
        for block in _all_run_blocks(workflow):
            commands = "\n".join(
                line for line in block.splitlines() if not line.strip().startswith("#")
            )
            assert "--depth=" not in commands, "a depth-limited base fetch cuts history the scanners need"

    def test_each_history_scanner_fetches_the_base_in_full(self, workflow):
        for job_name in ("secrets", "semgrep", "bandit"):
            blocks = [step["run"] for step in _job(workflow, job_name)["steps"] if "run" in step]
            assert any(self.FULL_FETCH in block for block in blocks), (
                f"{job_name} does not fetch the base ref with its history"
            )


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

    def test_baseline_worktree_path_is_unique_per_run(self, workflow):
        # A fixed path (e.g. /tmp/bandit-baseline) collides across runs on the shared self-hosted
        # runner: a cancelled/crashed run leaves it registered, and the next PR's `git worktree
        # add` fails before Bandit scans anything — confirmed locally (exit 128, "already
        # exists"). RUNNER_TEMP plus this run's own id+attempt makes collision structurally
        # impossible regardless of whether runner-level cleanup between jobs happened.
        baseline_step = _step(_job(workflow, "bandit"), "Bandit baseline")
        assert "RUNNER_TEMP" in baseline_step["run"]
        assert "GITHUB_RUN_ID" in baseline_step["run"]
        assert "GITHUB_RUN_ATTEMPT" in baseline_step["run"]
        assert "/tmp/bandit-baseline\"" not in baseline_step["run"]

    def test_sarif_artifact_built_from_the_baselined_results(self, workflow):
        # bandit -b is incompatible with -f sarif (confirmed), so a naive fix re-runs bandit
        # unfiltered for the SARIF — which repeats the pre-existing broker.py finding on every
        # PR's report regardless of whether that PR passed, confirmed live on PR #50 as making
        # the artifact useless for spotting what a PR introduced. The SARIF must instead be
        # converted from the same bandit.json the gating step already produced.
        sarif_step = _step(_job(workflow, "bandit"), "Bandit — SARIF artifact")
        assert "bandit_json_to_sarif.py" in sarif_step["run"]
        assert "bandit -r ." not in sarif_step["run"]


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


class TestBanditSarifConverter:
    """ci/security/bandit_json_to_sarif.py — converts the baselined bandit.json into SARIF."""

    def _convert(self, tmp_path, bandit_results):
        converter = _load_converter()
        src = tmp_path / "bandit.json"
        dst = tmp_path / "bandit.sarif"
        src.write_text(json.dumps({"results": bandit_results}))
        converter.convert(str(src), str(dst))
        return json.loads(dst.read_text())

    def test_empty_results_produce_valid_empty_sarif(self, tmp_path):
        sarif = self._convert(tmp_path, [])
        assert sarif["runs"][0]["results"] == []

    def test_normal_filename_round_trips_unchanged(self, tmp_path):
        sarif = self._convert(tmp_path, [{
            "test_id": "B324", "test_name": "hashlib", "issue_severity": "HIGH",
            "issue_text": "weak hash", "filename": "./ci/tests/example.py", "line_number": 3,
        }])
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert uri == "./ci/tests/example.py"

    def test_filename_with_hash_and_space_is_percent_encoded(self, tmp_path):
        # A raw '#' in a SARIF artifactLocation.uri is read as a fragment separator, and a raw
        # space makes the URI invalid outright — confirmed via a Greptile finding on PR #50.
        sarif = self._convert(tmp_path, [{
            "test_id": "B324", "test_name": "hashlib", "issue_severity": "HIGH",
            "issue_text": "weak hash", "filename": "./weird file#name.py", "line_number": 5,
        }])
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert "#" not in uri
        assert " " not in uri
        assert uri == "./weird%20file%23name.py"
