"""Tests for AuditTracer and AuditEvent."""

import json
from pathlib import Path
import tempfile
import threading

from src.desk.telemetry import AuditEvent, AuditTracer


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
