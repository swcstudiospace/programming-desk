"""Gate test suite.

Implements the test schedule in docs/quality-gates.md. Every gate is exercised against real
fixtures — a temporary git repository for the diff-based gates, real receipt JSON for the rest —
so the tests run the gates the way CI does rather than mocking them.

The property under test throughout: **does the gate actually block what it claims to block?**
A gate that has silently stopped working looks identical to a gate with nothing to catch.

    python3 -m pytest ci/tests/ -v
"""

from __future__ import annotations

import json
import subprocess
import sys
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


def write_receipt(tmp_path: Path, **overrides) -> Path:
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
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
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


# ===========================================================================
# G-3 — committed secrets
# ===========================================================================

class TestG3Secrets:

    def _scan(self, tmp_path: Path, content: str, name: str = "config.py"):
        (tmp_path / name).write_text(content)
        return run_gate("check_secrets.py", "--root", str(tmp_path), "--files", name)

    @pytest.mark.parametrize("content,label", [
        ('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"',                       "AWS access key"),
        ('token = "ghp_016C7f8a9B2c3D4e5F6g7H8i9J0k1L2m3N4o5"',    "GitHub token"),
        ('SLACK = "xoxb-123456789012-1234567890123-abcdefghijkl"', "Slack token"),
        ('key = "AIzaSyD-abcdefghijklmnopqrstuvwxyz1234567"',      "Google API key"),
        ('DB = "postgresql://admin:hunter2@db.internal:5432/prod"', "connection string"),
        ('-----BEGIN RSA PRIVATE KEY-----',                        "private key block"),
        ('STRIPE = "sk_live_abcdefghijklmnopqrstuvwx"',            "Stripe live key"),
    ])
    def test_known_secret_formats_blocked(self, tmp_path, content, label):
        r = self._scan(tmp_path, content)
        assert r.returncode == 1, f"{label} should have been caught"

    def test_high_entropy_with_secret_name_blocked(self, tmp_path):
        r = self._scan(tmp_path, 'api_secret = "8Kf3nQ9pL2mX7vB4tR6wY1zA5cD0eG8h"')
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
        secret = "ghp_016C7f8a9B2c3D4e5F6g7H8i9J0k1L2m3N4o5"
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
# Receipt directory ownership
#
# Found by end-to-end testing: every bot writes receipts, so a single shared
# .receipts/ was an unowned, permanently contended path. Per-bot subdirectories
# keep one owner per path and stop a bot editing another's evidence.
# ===========================================================================

class TestReceiptDirectoryOwnership:

    @pytest.mark.parametrize("bot", [
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
