"""One drill across sandbox, recovery, session, and audit contracts."""

from pathlib import Path
import tempfile

import pytest

from src.desk.recovery import RecoveryManager
from src.desk.security.policy_sandbox import BoundarySecurityError, PolicySandbox
from src.desk.session import SessionFrame, SessionStore
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
