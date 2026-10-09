"""Tests for Desk CLI commands."""

import json
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

    # Verbose text report test
    code = cli.main(["doctor", "--verbose"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Programming Desk Health Inspection" in captured.out
    assert "Detail:" in captured.out


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


def test_cli_run_rejects_shell(capsys, monkeypatch, tmp_path) -> None:
    from src.desk.telemetry.audit_tracer import AuditTracer
    orig_init = AuditTracer.__init__
    monkeypatch.setattr(
        AuditTracer,
        "__init__",
        lambda self, log_path=None: orig_init(self, log_path=log_path or (tmp_path / "audit.jsonl")),
    )
    code = cli.main(["run", "sh", "-c", "echo should_not_run"])
    assert code == 126
    captured = capsys.readouterr()
    assert "should_not_run" not in captured.out
    assert str(cli._desk_run_allowlist()) in captured.err


def test_cli_run_correlates_session(capsys, monkeypatch, tmp_path) -> None:
    from src.desk.session.session_store import SessionStore
    from src.desk.telemetry.audit_tracer import AuditTracer

    orig_store_init = SessionStore.__init__
    orig_tracer_init = AuditTracer.__init__

    def custom_store_init(self, storage_path=None, state_md_path=None):
        orig_store_init(
            self,
            storage_path=tmp_path / "session.json",
            state_md_path=tmp_path / "STATE.md",
        )

    monkeypatch.setattr(SessionStore, "__init__", custom_store_init)
    monkeypatch.setattr(
        AuditTracer,
        "__init__",
        lambda self, log_path=None: orig_tracer_init(
            self, log_path=log_path or (tmp_path / "audit.jsonl")
        ),
    )

    code = cli.main(["session", "--init", "corr-session-001"])
    assert code == 0
    capsys.readouterr()

    code = cli.main(["session", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    correlation_id = json.loads(captured.out)["correlation_id"]

    code = cli.main(["session"])
    assert code == 0
    assert f"Correlation: {correlation_id}" in capsys.readouterr().out

    code = cli.main(["run", sys.executable, "-c", "print('correlated')"])
    assert code == 0

    supervised = [
        json.loads(line)
        for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    supervised = [event for event in supervised if event.get("action") == "supervised_run"]
    assert supervised
    assert supervised[-1]["correlation_id"] == correlation_id


def test_cli_audit_filters_correlation(capsys, monkeypatch, tmp_path) -> None:
    from src.desk.telemetry.audit_tracer import AuditTracer

    orig_init = AuditTracer.__init__
    monkeypatch.setattr(
        AuditTracer,
        "__init__",
        lambda self, log_path=None: orig_init(self, log_path=log_path or (tmp_path / "audit.jsonl")),
    )
    tracer = AuditTracer()
    tracer.emit(action="kept", phase="v8.3", correlation_id="corr-aaaa")
    tracer.emit(action="dropped", phase="v8.3", correlation_id="corr-bbbb")

    code = cli.main(["audit", "--correlation", "corr-aaaa", "--json"])
    assert code == 0
    events = json.loads(capsys.readouterr().out)
    assert [event["correlation_id"] for event in events] == ["corr-aaaa"]

    code = cli.main(["audit", "--correlation", "corr-aaaa"])
    assert code == 0
    out = capsys.readouterr().out
    assert "<corr-aaaa>" in out
    assert "corr-bbbb" not in out


def test_cli_session_sync_rewrites_state(capsys, monkeypatch, tmp_path) -> None:
    from src.desk.session.session_store import SessionStore

    orig_init = SessionStore.__init__

    def custom_init(self, storage_path=None, state_md_path=None):
        orig_init(
            self,
            storage_path=tmp_path / "session.json",
            state_md_path=tmp_path / "STATE.md",
        )

    monkeypatch.setattr(SessionStore, "__init__", custom_init)
    assert cli.main(["session", "--init", "sync-test-001"]) == 0
    capsys.readouterr()

    state_md = tmp_path / "STATE.md"
    state_md.write_text("# Operator notes\n", encoding="utf-8")
    assert cli.main(["session", "--sync"]) == 0
    out = capsys.readouterr().out
    assert "sync-test-001" in out
    text = state_md.read_text(encoding="utf-8")
    assert "# Operator notes" in text
    assert "sync-test-001" in text
