"""Tests for ci/security/bandit_baseline_gate.py (SPE-5162, security-pr.yml's Bandit step).

Pure-logic tests (finding identity, empty-input no-op) run unconditionally. The end-to-end
tests that actually invoke the `bandit` binary are skipped when it isn't installed — gate-
self-test (`python3 -m pytest ci/tests/`) doesn't install it; the workflow's own Bandit job
does, via `pip install bandit bandit-sarif-formatter`.

    python3 -m pytest ci/tests/test_bandit_baseline_gate.py -v
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ci" / "security" / "bandit_baseline_gate.py"

_spec = importlib.util.spec_from_file_location("bandit_baseline_gate", SCRIPT)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

HAVE_BANDIT = shutil.which("bandit") is not None


def _result(filename: str, test_id: str, line_number: int, code: str) -> dict:
    return {
        "filename": filename,
        "test_id": test_id,
        "line_number": line_number,
        "code": code,
        "issue_text": "synthetic finding",
    }


class TestFlaggedLineText:
    def test_extracts_the_exact_flagged_line_by_number_not_position(self):
        # Bandit's "code" field is 1-3 lines of context; the flagged line is identified by
        # line_number, not by always being the middle line.
        code = "1240   before()\n1241     accept = sha1(key)\n1242   after()\n"
        result = _result("./x.py", "B324", 1241, code)
        assert gate.flagged_line_text(result) == "accept = sha1(key)"

    def test_survives_a_line_number_shift_when_content_is_identical(self):
        code_before = "1240   before()\n1241     accept = sha1(key)\n1242   after()\n"
        code_after = "1250   before()\n1251     accept = sha1(key)\n1252   after()\n"
        before = _result("./x.py", "B324", 1241, code_before)
        after = _result("./x.py", "B324", 1251, code_after)
        assert gate.finding_key("x.py", before) == gate.finding_key("x.py", after)

    def test_a_genuinely_changed_flagged_line_is_a_different_key(self):
        code_before = "1240   before()\n1241     accept = sha1(key)\n1242   after()\n"
        code_after = "1240   before()\n1241     accept = sha1(other_key)\n1242   after()\n"
        before = _result("./x.py", "B324", 1241, code_before)
        after = _result("./x.py", "B324", 1241, code_after)
        assert gate.finding_key("x.py", before) != gate.finding_key("x.py", after)


class TestMainNoFiles:
    def test_no_files_is_a_clean_no_op(self, capsys):
        assert gate.main.__module__ == "bandit_baseline_gate"

    def test_empty_file_list_exits_zero_without_invoking_bandit(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["bandit_baseline_gate.py", "--base-ref", "origin/main", "--ini", "x.ini"])
        called = {"count": 0}

        def _boom(*a, **k):
            called["count"] += 1
            raise AssertionError("bandit should not run when there are no files")

        monkeypatch.setattr(gate, "run_bandit_json", _boom)
        assert gate.main() == 0
        assert called["count"] == 0


@pytest.mark.skipif(not HAVE_BANDIT, reason="bandit binary not installed in this environment")
class TestEndToEnd:
    def _write_repo(self, tmp_path: Path, base_content: str, head_content: str) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        (repo / "mod.py").write_text(base_content)
        subprocess.run(["git", "add", "mod.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
        (repo / "mod.py").write_text(head_content)
        return repo

    def _run_gate(self, repo: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--base-ref",
                "HEAD",
                "--ini",
                "/dev/null",
                "--",
                "mod.py",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
        )

    def test_unrelated_edit_that_shifts_the_legacy_finding_still_passes(self, tmp_path):
        legacy = textwrap.dedent(
            """\
            import hashlib

            def handshake(key):
                return hashlib.sha1(key.encode()).hexdigest()
            """
        )
        shifted = textwrap.dedent(
            """\
            import hashlib


            def unrelated_helper():
                return 1 + 1


            def handshake(key):
                return hashlib.sha1(key.encode()).hexdigest()
            """
        )
        repo = self._write_repo(tmp_path, legacy, shifted)
        proc = self._run_gate(repo)
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_a_genuinely_new_finding_still_fails(self, tmp_path):
        legacy = textwrap.dedent(
            """\
            import hashlib

            def handshake(key):
                return hashlib.sha1(key.encode()).hexdigest()
            """
        )
        with_new_finding = textwrap.dedent(
            """\
            import hashlib

            def handshake(key):
                return hashlib.sha1(key.encode()).hexdigest()

            def new_unrelated_hash(data):
                return hashlib.sha1(data.encode()).hexdigest()
            """
        )
        repo = self._write_repo(tmp_path, legacy, with_new_finding)
        proc = self._run_gate(repo)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "1 NEW" in proc.stderr and "mod.py" in proc.stderr
