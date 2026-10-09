"""Tests for AuditTracer and AuditEvent."""

import hashlib
import json
from pathlib import Path
import tempfile
import threading

import pytest

from src.desk.security import BoundarySecurityError
from src.desk.telemetry import AuditEvent, AuditTracer


_GENESIS_PREV_HASH = "0" * 64


def _expected_record_hash(record: dict) -> str:
    """Independent chain hash: sha256(prev_hash + newline + canonical JSON)."""
    body = {key: value for key, value in record.items() if key != "record_hash"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    prev_hash = body.get("prev_hash")
    prefix = prev_hash if isinstance(prev_hash, str) else ""
    material = f"{prefix}\n{canonical}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def test_emit_and_read_event() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)

        event = tracer.emit(
            action="compile_circuit",
            phase="phase-118",
            actor="bot-lead",
            duration_ms=42.5,
            exit_code=0,
            circuit_depth=16,
        )

        assert event.action == "compile_circuit"
        assert event.duration_ms == 42.5
        assert event.exit_code == 0
        assert log_file.exists()

        records = tracer.read_events()
        assert len(records) == 1
        rec = records[0]
        assert rec["action"] == "compile_circuit"
        assert rec["phase"] == "phase-118"
        assert rec["actor"] == "bot-lead"
        assert rec["details"]["circuit_depth"] == 16


def test_audit_redaction() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)

        secret_token = "ghp_" + "z" * 36
        tracer.emit(
            action="deploy_job",
            author="Alice",
            token_count=123,
            token=secret_token,
            clientSecret="my_secret_999",
            accessToken="my_access_888",
            dbPassword="super_secret_password",
            nested={"auth": f"Bearer token1234567890abcdef", "safe": "public_data"},
        )

        records = tracer.read_events()
        assert len(records) == 1
        details = records[0]["details"]
        assert secret_token not in json.dumps(details)
        assert details["author"] == "Alice"
        assert details["token_count"] == 123
        assert details["token"] == "[REDACTED]"
        assert details["clientSecret"] == "[REDACTED]"
        assert details["accessToken"] == "[REDACTED]"
        assert details["dbPassword"] == "[REDACTED]"
        assert "token1234567890abcdef" not in details["nested"]["auth"]  # pragma: allowlist secret (redaction test fixture)
        assert details["nested"]["safe"] == "public_data"


def test_read_events_filtering_and_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)

        for i in range(10):
            phase = "phase-A" if i % 2 == 0 else "phase-B"
            actor = "bot-systems" if i < 5 else "bot-lead"
            tracer.emit(action=f"action-{i}", phase=phase, actor=actor, idx=i)

        all_events = tracer.read_events()
        assert len(all_events) == 10

        phase_a_events = tracer.read_events(phase="phase-A")
        assert len(phase_a_events) == 5

        bot_lead_events = tracer.read_events(actor="bot-lead")
        assert len(bot_lead_events) == 5

        limited_events = tracer.read_events(limit=3)
        assert len(limited_events) == 3
        assert limited_events[-1]["details"]["idx"] == 9


def test_concurrent_writes() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)

        def worker(worker_id: int) -> None:
            for i in range(20):
                tracer.emit(action="worker_ping", worker=worker_id, iter=i)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = tracer.read_events()
        assert len(records) == 100
        assert tracer.verify_chain() == (True, "ok")
        assert [record["seq"] for record in records] == list(range(1, 101))


def test_clean_chain_verifies() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)
        assert tracer.verify_chain() == (True, "ok")

        tracer.emit(action="one", phase="phase-a", actor="bot-lead", n=1)
        tracer.emit(action="two", phase="phase-a", actor="bot-lead", n=2)
        tracer.emit(action="three", phase="phase-a", actor="bot-lead", n=3)

        assert tracer.verify_chain() == (True, "ok")
        records = tracer.read_events()
        assert [record["seq"] for record in records] == [1, 2, 3]
        assert records[0]["prev_hash"] == _GENESIS_PREV_HASH
        assert records[1]["prev_hash"] == records[0]["record_hash"]
        assert records[2]["prev_hash"] == records[1]["record_hash"]
        for record in records:
            assert record["record_hash"] == _expected_record_hash(record)
            assert len(record["record_hash"]) == 64


def test_verify_chain_detects_byte_flip() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)
        tracer.emit(action="before", phase="phase-a", actor="bot-lead", n=1)
        tracer.emit(action="after", phase="phase-a", actor="bot-lead", n=2)
        assert tracer.verify_chain() == (True, "ok")

        raw = bytearray(log_file.read_bytes())
        flip_at = len(raw) // 2
        raw[flip_at] ^= 0x01
        log_file.write_bytes(raw)

        ok, reason = tracer.verify_chain()
        assert ok is False
        assert reason


def test_verify_chain_detects_deleted_middle_line() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)
        tracer.emit(action="first", phase="phase-a", actor="bot-lead")
        tracer.emit(action="middle", phase="phase-a", actor="bot-lead")
        tracer.emit(action="last", phase="phase-a", actor="bot-lead")
        assert tracer.verify_chain() == (True, "ok")

        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        del lines[1]
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        ok, reason = tracer.verify_chain()
        assert ok is False
        assert reason


def test_record_event_returns_sanitized_values() -> None:
    secret = "ghp_" + "b" * 36
    with tempfile.TemporaryDirectory() as tmp_dir:
        tracer = AuditTracer(log_path=Path(tmp_dir) / "audit.jsonl")
        original = AuditEvent(
            action=f"ship {secret}",
            phase=f"phase-{secret}",
            actor=f"bot-{secret}",
            details={"token": secret, "note": "plain"},
        )
        recorded = tracer.record_event(original)

        assert recorded is not original
        assert secret not in recorded.action
        assert secret not in recorded.phase
        assert secret not in recorded.actor
        assert recorded.details["token"] == "[REDACTED]"
        assert recorded.details["note"] == "plain"
        assert recorded.details is not original.details
        assert original.details["token"] == secret

        stored = tracer.read_events()[0]
        assert stored["action"] == recorded.action
        assert stored["phase"] == recorded.phase
        assert stored["actor"] == recorded.actor
        assert stored["details"] == recorded.details


def test_relative_log_path_is_confined(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        monkeypatch.chdir(root)
        tracer = AuditTracer(log_path=".planning/audit.jsonl", workspace_root=root)
        tracer.emit(action="confined")
        assert (root / ".planning" / "audit.jsonl").is_file()
        assert tracer.verify_chain() == (True, "ok")

        with pytest.raises(BoundarySecurityError):
            AuditTracer(log_path="../escape.jsonl", workspace_root=root)


def test_absolute_symlink_leaf_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        target = root / "real.jsonl"
        target.write_text("", encoding="utf-8")
        link = root / "audit.jsonl"
        link.symlink_to(target)
        with pytest.raises(BoundarySecurityError):
            AuditTracer(log_path=link)


def test_absolute_dotdot_cannot_escape_parent() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        escape = root / ".." / "audit.jsonl"
        with pytest.raises(BoundarySecurityError):
            AuditTracer(log_path=escape)
