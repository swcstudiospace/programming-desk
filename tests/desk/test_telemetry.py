"""Tests for AuditTracer and AuditEvent."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
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
        assert not log_file.with_name(log_file.name + ".1").exists()
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


def _jsonl_records(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _emit_until_rotated(log_file: Path) -> tuple[AuditTracer, Path]:
    """Emit with a 400-byte cap until the first ``.1`` sibling appears."""
    tracer = AuditTracer(log_path=log_file, max_log_bytes=400)
    rotated = log_file.with_name(log_file.name + ".1")
    for n in range(1, 40):
        tracer.emit(action=f"step-{n}", phase="phase-rot", actor="bot-lead", n=n)
        if rotated.is_file() and not rotated.is_symlink():
            return tracer, rotated
    raise AssertionError("rotated segment was not created")


def test_rotation_continues_sequence_across_segment() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer, rotated = _emit_until_rotated(log_file)

        assert tracer.verify_chain() == (True, "ok")
        rotated_rows = _jsonl_records(rotated)
        active_rows = _jsonl_records(log_file)
        assert rotated_rows
        assert active_rows
        combined = rotated_rows + active_rows
        assert [row["seq"] for row in combined] == list(range(1, len(combined) + 1))
        assert rotated_rows[0]["prev_hash"] == _GENESIS_PREV_HASH
        assert rotated_rows[0]["seq"] == 1
        anchor = active_rows[0]
        assert anchor["action"] == "segment_anchor"
        assert anchor["phase"] == "audit"
        assert anchor["actor"] == "audit-tracer"
        assert anchor["details"] == {"segment_anchor": True}
        assert anchor["seq"] == rotated_rows[-1]["seq"] + 1
        assert anchor["prev_hash"] == rotated_rows[-1]["record_hash"]
        assert anchor["record_hash"] == _expected_record_hash(anchor)
        user_active = [row for row in active_rows if row.get("action") != "segment_anchor"]
        assert user_active
        assert user_active[0]["seq"] == anchor["seq"] + 1
        assert user_active[0]["prev_hash"] == anchor["record_hash"]
        for earlier, later in zip(combined, combined[1:]):
            assert later["prev_hash"] == earlier["record_hash"]

        read_back = tracer.read_events()
        user_rows = [row for row in combined if row.get("action") != "segment_anchor"]
        assert [row["seq"] for row in read_back] == [row["seq"] for row in user_rows]
        assert all(row["action"] != "segment_anchor" for row in read_back)


def test_rotated_segment_byte_flip_fails_verify() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer, rotated = _emit_until_rotated(log_file)
        assert tracer.verify_chain() == (True, "ok")

        raw = bytearray(rotated.read_bytes())
        raw[len(raw) // 2] ^= 0x01
        rotated.write_bytes(raw)

        ok, reason = tracer.verify_chain()
        assert ok is False
        assert reason


def test_read_events_stops_at_flipped_second_line() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)
        tracer.emit(action="one", phase="phase-a", actor="bot-lead", n=1)
        tracer.emit(action="two", phase="phase-a", actor="bot-lead", n=2)
        tracer.emit(action="three", phase="phase-a", actor="bot-lead", n=3)

        parts = log_file.read_bytes().split(b"\n")
        assert parts[-1] == b""
        lines = parts[:-1]
        assert len(lines) == 3
        flipped = bytearray(lines[1])
        flipped[len(flipped) // 2] ^= 0x01
        lines[1] = bytes(flipped)
        log_file.write_bytes(b"\n".join(lines) + b"\n")

        records = tracer.read_events()
        assert len(records) == 1
        assert records[0]["action"] == "one"
        assert records[0]["seq"] == 1


def test_read_events_keeps_record_with_extra_key() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file)
        tracer.emit(action="annotated", phase="phase-a", actor="bot-lead", n=1)

        record = json.loads(log_file.read_text(encoding="utf-8").strip())
        record["extra"] = "kept"
        record["record_hash"] = _expected_record_hash(record)
        log_file.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        records = tracer.read_events()
        assert len(records) == 1
        assert records[0]["action"] == "annotated"
        assert records[0]["extra"] == "kept"
        assert tracer.verify_chain() == (True, "ok")


def test_repeated_rotation_keeps_a_verifiable_window() -> None:
    """Eight events under a 320-byte cap still verify after ``.1`` is replaced."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file, max_log_bytes=320)
        for index in range(8):
            tracer.emit(action="ops", phase="v8.2", n=index, correlation_id="abcd1234")

        rotated = log_file.with_name(log_file.name + ".1")
        assert rotated.is_file()
        assert not rotated.is_symlink()
        assert tracer.verify_chain() == (True, "ok")

        rotated_rows = _jsonl_records(rotated)
        active_rows = _jsonl_records(log_file)
        assert rotated_rows[0]["action"] == "segment_anchor"
        assert active_rows[0]["action"] == "segment_anchor"
        assert active_rows[0]["phase"] == "audit"
        assert active_rows[0]["actor"] == "audit-tracer"
        assert active_rows[0]["details"] == {"segment_anchor": True}
        assert active_rows[0]["seq"] == rotated_rows[-1]["seq"] + 1
        assert active_rows[0]["prev_hash"] == rotated_rows[-1]["record_hash"]
        assert active_rows[1]["action"] == "ops"
        assert active_rows[1]["seq"] == active_rows[0]["seq"] + 1
        assert active_rows[1]["prev_hash"] == active_rows[0]["record_hash"]
        for earlier, later in zip(rotated_rows, rotated_rows[1:]):
            assert later["prev_hash"] == earlier["record_hash"]
            assert later["seq"] == earlier["seq"] + 1

        read_back = tracer.read_events()
        assert read_back
        assert all(row["action"] != "segment_anchor" for row in read_back)
        window = [
            row
            for row in rotated_rows + active_rows
            if row.get("action") != "segment_anchor"
        ]
        assert [row["seq"] for row in read_back] == [row["seq"] for row in window]


def test_rotation_uses_encoded_byte_length() -> None:
    """A line that fits by character count still rotates when its UTF-8 size does not."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        log_file.write_bytes(b"1234567")
        tracer = AuditTracer(log_path=log_file, max_log_bytes=10)
        # "ää\n" is 3 characters and 5 UTF-8 bytes: 7+3 <= 10, 7+5 > 10.
        assert tracer._rotate_active(log_file, "ää\n") is True
        rotated = log_file.with_name(log_file.name + ".1")
        assert rotated.read_bytes() == b"1234567"
        assert not log_file.exists()


def test_rotation_replaces_symlink_sibling_without_following() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        log_file = root / "audit.jsonl"
        secret = root / "secret.jsonl"
        secret.write_text("keep-me\n", encoding="utf-8")
        sibling = log_file.with_name(log_file.name + ".1")
        sibling.symlink_to(secret)
        tracer = AuditTracer(log_path=log_file, max_log_bytes=1)
        tracer.emit(action="first", phase="v8.2", n=1)
        inode = log_file.stat().st_ino
        tracer.emit(action="second", phase="v8.2", n=2)
        assert secret.read_text(encoding="utf-8") == "keep-me\n"
        assert sibling.is_file()
        assert not sibling.is_symlink()
        assert sibling.stat().st_ino == inode
        assert tracer.verify_chain() == (True, "ok")


def test_directory_sibling_skips_rotation() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        sibling = log_file.with_name(log_file.name + ".1")
        sibling.mkdir()
        tracer = AuditTracer(log_path=log_file, max_log_bytes=1)
        tracer.emit(action="first", phase="v8.2", n=1)
        tracer.emit(action="second", phase="v8.2", n=2)
        assert sibling.is_dir()
        assert list(sibling.iterdir()) == []
        assert tracer.verify_chain() == (True, "ok")
        rows = _jsonl_records(log_file)
        assert [row["seq"] for row in rows] == [1, 2]
        assert rows[0]["prev_hash"] == _GENESIS_PREV_HASH


def test_replaced_log_parent_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        parent = root / "logs"
        parent.mkdir()
        outside = root / "outside"
        outside.mkdir()
        leaked = outside / "audit.jsonl"
        leaked.write_text("keep\n", encoding="utf-8")
        log_file = parent / "audit.jsonl"
        tracer = AuditTracer(log_path=log_file, max_log_bytes=None)
        tracer.emit(action="inside", phase="v8.2")
        moved = root / "logs-real"
        parent.rename(moved)
        parent.symlink_to(outside)
        with pytest.raises(BoundarySecurityError):
            tracer.emit(action="escaped", phase="v8.2")
        assert leaked.read_text(encoding="utf-8") == "keep\n"
        assert (moved / "audit.jsonl").is_file()


def test_two_processes_keep_one_audit_chain() -> None:
    script = (
        "import sys\n"
        "from src.desk.telemetry import AuditTracer\n"
        "path, ident, count = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])\n"
        "tracer = AuditTracer(log_path=path, max_log_bytes=None)\n"
        "for i in range(count):\n"
        "    tracer.emit(action='proc', phase='v8.2', worker=ident, n=i)\n"
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "audit.jsonl"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path.cwd()), env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(log_file), str(ident), "20"],
                env=env,
            )
            for ident in (1, 2)
        ]
        for proc in procs:
            assert proc.wait(timeout=20) == 0
        tracer = AuditTracer(log_path=log_file, max_log_bytes=None)
        assert tracer.verify_chain() == (True, "ok")
        records = tracer.read_events()
        assert len(records) == 40
        assert [row["seq"] for row in records] == list(range(1, 41))
