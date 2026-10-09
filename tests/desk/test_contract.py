"""One drill across sandbox, recovery, session, and audit contracts."""

from pathlib import Path
import tempfile

import sys

import pytest

from src.desk.recovery import RecoveryManager
from src.desk.security.policy_sandbox import BoundarySecurityError, PolicySandbox
from src.desk.session import SessionFrame, SessionStore
from src.desk.supervision import ProcessSupervisor
from src.desk.telemetry import AuditTracer


def test_hardened_workbench_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir).resolve()
        outside = Path(tempfile.mkdtemp(prefix="desk-contract-out-"))
        secret = outside / "secret.txt"
        try:
            secret.write_text("hidden", encoding="utf-8")
            link = root / "alias"
            link.symlink_to(secret)
            sandbox = PolicySandbox(workspace_root=root)
            with pytest.raises(BoundarySecurityError):
                sandbox.validate_path(link)

            target = root / "config.txt"
            target.write_text("original", encoding="utf-8")
            manager = RecoveryManager()
            with pytest.raises(RuntimeError):
                with manager.transaction("contract", reraise=True) as tx:
                    tx.backup_file(target)
                    target.write_text("mutated", encoding="utf-8")
                    raise RuntimeError("abort")
            assert target.read_text(encoding="utf-8") == "original"

            store = SessionStore(
                storage_path=root / "session.json",
                state_md_path=root / "STATE.md",
            )
            saved = store.save_session(
                SessionFrame(
                    session_id="contract-1",
                    milestone="v8.1",
                    phase="hardening",
                )
            )
            loaded = store.load_session()
            assert loaded is not None
            assert saved.schema_version == 1
            assert loaded.schema_version == 1
            assert '"schema_version": 1' in (root / "session.json").read_text(encoding="utf-8")

            tracer = AuditTracer(log_path=root / "audit.jsonl")
            recorded = tracer.emit(
                action="contract_drill",
                phase="hardening",
                session_id="contract-1",
            )
            assert recorded.action == "contract_drill"
            assert recorded.phase == "hardening"
            assert tracer.verify_chain() == (True, "ok")
        finally:
            secret.unlink(missing_ok=True)
            outside.rmdir()


def test_operations_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir).resolve()
        store = SessionStore(
            storage_path=root / "session.json",
            state_md_path=root / "STATE.md",
        )
        saved = store.save_session(SessionFrame(session_id="ops-1", milestone="v8.2"))
        loaded = store.load_session()
        assert loaded is not None
        assert saved.correlation_id == loaded.correlation_id
        assert len(loaded.correlation_id) >= 8

        outside = Path(tempfile.mkdtemp(prefix="desk-ops-out-"))
        try:
            leaked = outside / "leaked.json"
            leaked.write_text('{"session_id": "stolen"}', encoding="utf-8")
            live = root / "session.json"
            live.unlink()
            live.symlink_to(leaked)
            with pytest.raises(BoundarySecurityError):
                store.load_session()
        finally:
            leaked.unlink(missing_ok=True)
            outside.rmdir()

        tracer = AuditTracer(log_path=root / "audit.jsonl", max_log_bytes=320)
        for index in range(8):
            tracer.emit(action="ops", phase="v8.2", n=index, correlation_id=saved.correlation_id)
        assert (root / "audit.jsonl.1").is_file()
        assert tracer.verify_chain() == (True, "ok")

        supervisor = ProcessSupervisor()
        limited = supervisor.run(
            [sys.executable, "-c", "import sys; sys.exit(75)"],
            max_retries=5,
            backoff_base=0.4,
            deadline_s=0.35,
            retry_on_exit_codes=[75],
        )
        assert limited.exit_code == 75
        assert limited.retries < 5
        assert limited.duration_ms < 2000

        target = root / "notes.txt"
        target.write_text("notes", encoding="utf-8")
        original_mode = target.stat().st_mode & 0o777
        manager = RecoveryManager()
        with manager.transaction("ops-backup") as tx:
            tx.backup_file(target)
            backup = next(iter(tx._file_backups.values()))
            assert tx._backup_dir is not None
            assert (backup.stat().st_mode & 0o777) == 0o600
            assert (tx._backup_dir.stat().st_mode & 0o777) == 0o700
        assert (target.stat().st_mode & 0o777) == original_mode
