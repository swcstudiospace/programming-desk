"""Tests for Desk CLI commands."""

from pathlib import Path
import sys
import tempfile

from src.desk import cli


def test_cli_help(capsys) -> None:
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Available subcommands" in captured.out or "show this help message" in captured.out


def test_cli_doctor(capsys) -> None:
    code = cli.main(["doctor", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    assert "overall_status" in captured.out


def test_cli_session_lifecycle(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Re-point storage path for testing
        from src.desk.session.session_store import SessionStore
        old_storage = SessionStore.__init__

        def custom_init(self, storage_path=None, state_md_path=None):
            old_storage(
                self,
                storage_path=Path(tmp_dir) / "session.json",
                state_md_path=Path(tmp_dir) / "STATE.md",
            )

        SessionStore.__init__ = custom_init
        try:
            code = cli.main(["session", "--init", "test-session-001", "--milestone", "v8.0"])
            assert code == 0

            code = cli.main(["session", "--json"])
            assert code == 0
            captured = capsys.readouterr()
            assert "test-session-001" in captured.out
        finally:
            SessionStore.__init__ = old_storage


def test_cli_run(capsys, monkeypatch, tmp_path) -> None:
    # Ensure audit log writes to temporary location
    from src.desk.telemetry.audit_tracer import AuditTracer
    orig_init = AuditTracer.__init__
    monkeypatch.setattr(
        AuditTracer,
        "__init__",
        lambda self, log_path=None: orig_init(self, log_path=log_path or (tmp_path / "audit.jsonl")),
    )
    code = cli.main(["run", sys.executable, "-c", "print('desk_run_success')"])
    assert code == 0
    captured = capsys.readouterr()
    assert "desk_run_success" in captured.out
