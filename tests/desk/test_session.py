"""Tests for SessionStore and SessionFrame."""

import json
import os
from pathlib import Path
import tempfile
import threading

from src.desk.security.policy_sandbox import BoundarySecurityError
from src.desk.session import SessionFrame, SessionStore


def test_session_save_and_load() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = Path(tmp_dir) / "session.json"
        state_md = Path(tmp_dir) / "STATE.md"
        store = SessionStore(storage_path=storage, state_md_path=state_md)

        assert store.load_session() is None

        frame = SessionFrame(
            session_id="sess-001",
            milestone="v8.0",
            phase="Phase 1: Foundation",
            status="active",
            active_tasks=["Build supervisor", "Build telemetry"],
            completed_tasks=["Initial audit"],
            metadata={"cluster": "alpha-west", "priority": "high"},
        )

        saved = store.save_session(frame)
        assert saved.session_id == "sess-001"
        assert storage.exists()

        loaded = store.load_session()
        assert loaded is not None
        assert loaded.session_id == "sess-001"
        assert loaded.milestone == "v8.0"
        assert loaded.phase == "Phase 1: Foundation"
        assert loaded.active_tasks == ["Build supervisor", "Build telemetry"]
        assert loaded.completed_tasks == ["Initial audit"]
        assert loaded.metadata["cluster"] == "alpha-west"


def test_session_sync_to_markdown_state() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = Path(tmp_dir) / "session.json"
        state_md = Path(tmp_dir) / "STATE.md"
        store = SessionStore(storage_path=storage, state_md_path=state_md)

        frame = SessionFrame(
            session_id="sess-002",
            milestone="v8.0",
            phase="Phase 2: Recovery",
            status="in_progress",
            active_tasks=["Implement rollback stack"],
            completed_tasks=["Setup test harnesses"],
            metadata={"operator": "bot-lead"},
        )

        md_content = store.sync_to_markdown_state(frame)
        assert state_md.exists()
        assert "# State: Milestone v8.0 — Phase 2: Recovery" in md_content
        assert "- [ ] Implement rollback stack" in md_content
        assert "- [x] Setup test harnesses" in md_content
        assert "**operator**: bot-lead" in md_content
        assert md_content.startswith("<!-- desk-session:start -->")
        assert "<!-- desk-session:end -->" in md_content
        assert state_md.read_text(encoding="utf-8") == md_content
        assert list(Path(tmp_dir).glob("*.tmp*")) == []


def test_atomic_persistence_cleans_temp() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = Path(tmp_dir) / "session.json"
        store = SessionStore(storage_path=storage)

        frame = SessionFrame(session_id="atomic-test")
        store.save_session(frame)

        # Check that no .tmp files linger in directory
        tmp_files = list(Path(tmp_dir).glob("*.tmp*"))
        assert len(tmp_files) == 0


def test_concurrent_session_saves() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = Path(tmp_dir) / "session.json"
        store = SessionStore(storage_path=storage)

        def worker(wid: int) -> None:
            for i in range(10):
                f = SessionFrame(
                    session_id=f"worker-{wid}",
                    metadata={"step": i},
                )
                store.save_session(f)

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = store.load_session()
        assert final is not None
        assert final.session_id.startswith("worker-")


def test_corrupt_json_is_quarantined_and_later_save_works() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        storage = root / "session.json"
        good_neighbor = root / "notes.json"
        good_neighbor.write_text('{"ok": true}', encoding="utf-8")
        store = SessionStore(storage_path=storage, state_md_path=root / "STATE.md")
        bad = "{not json"
        storage.write_text(bad, encoding="utf-8")

        assert store.load_session() is None
        assert not storage.exists()

        quarantine = root / f"session.json.corrupt.{os.getpid()}"
        assert quarantine.is_file()
        assert quarantine.read_text(encoding="utf-8") == bad
        assert good_neighbor.read_text(encoding="utf-8") == '{"ok": true}'

        saved = store.save_session(SessionFrame(session_id="recovered"))
        assert saved.session_id == "recovered"
        assert storage.is_file()
        assert quarantine.read_text(encoding="utf-8") == bad

        loaded = store.load_session()
        assert loaded is not None
        assert loaded.session_id == "recovered"
        assert json.loads(storage.read_text(encoding="utf-8"))["schema_version"] == 1
        assert list(root.glob("*.tmp*")) == []


def test_schema_version_one_round_trips() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage = Path(tmp_dir) / "session.json"
        store = SessionStore(storage_path=storage, state_md_path=Path(tmp_dir) / "STATE.md")
        storage.write_text(
            json.dumps({"session_id": "legacy-1", "active_tasks": ["keep"]}),
            encoding="utf-8",
        )

        loaded = store.load_session()
        assert loaded is not None
        assert loaded.session_id == "legacy-1"
        assert loaded.schema_version == 1
        assert loaded.active_tasks == ["keep"]

        store.save_session(loaded)
        payload = json.loads(storage.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["session_id"] == "legacy-1"

        again = store.load_session()
        assert again is not None
        assert again.schema_version == 1
        assert again.session_id == "legacy-1"
        assert again.active_tasks == ["keep"]


def test_schema_version_two_is_quarantined() -> None:
    rejected = False
    try:
        SessionFrame.from_dict({"session_id": "future", "schema_version": 2})
    except ValueError:
        rejected = True
    assert rejected

    for bad_version in ("1", 1.0, True, None, 0):
        rejected = False
        try:
            SessionFrame.from_dict({"session_id": "bad", "schema_version": bad_version})
        except ValueError:
            rejected = True
        assert rejected, bad_version

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        storage = root / "session.json"
        store = SessionStore(storage_path=storage, state_md_path=root / "STATE.md")
        storage.write_text(
            json.dumps({"schema_version": 2, "session_id": "future"}),
            encoding="utf-8",
        )

        assert store.load_session() is None
        assert not storage.exists()
        quarantine = root / f"session.json.corrupt.{os.getpid()}"
        assert quarantine.is_file()
        assert json.loads(quarantine.read_text(encoding="utf-8"))["schema_version"] == 2


def test_sync_preserves_existing_state_markdown() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        state_md = root / "STATE.md"
        state_md.write_text("# Kept\n\nPrior notes.\n", encoding="utf-8")
        store = SessionStore(storage_path=root / "session.json", state_md_path=state_md)
        frame = SessionFrame(
            session_id="sess-kept",
            milestone="v8.1",
            phase="harden",
            active_tasks=["Confine paths"],
        )

        rendered = store.sync_to_markdown_state(frame)
        text = state_md.read_text(encoding="utf-8")
        assert rendered == text
        assert text.startswith("# Kept")
        assert "Prior notes." in text
        start = text.index("<!-- desk-session:start -->")
        end = text.index("<!-- desk-session:end -->")
        assert text.index("# Kept") < start < end
        assert "sess-kept" in text[start:end]
        assert text.count("<!-- desk-session:start -->") == 1
        assert text.count("<!-- desk-session:end -->") == 1

        store.sync_to_markdown_state(
            SessionFrame(session_id="sess-next", milestone="v8.1", phase="harden")
        )
        replaced = state_md.read_text(encoding="utf-8")
        assert replaced.startswith("# Kept")
        assert "Prior notes." in replaced
        assert replaced.count("<!-- desk-session:start -->") == 1
        assert replaced.count("<!-- desk-session:end -->") == 1
        marked_start = replaced.index("<!-- desk-session:start -->")
        marked_end = replaced.index("<!-- desk-session:end -->")
        assert "sess-next" in replaced[marked_start:marked_end]
        assert "sess-kept" not in replaced


def test_symlink_session_leaf_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        real = root / "real.json"
        real.write_text('{"session_id": "hidden"}', encoding="utf-8")
        link = root / "session.json"
        link.symlink_to(real)
        rejected = False
        try:
            SessionStore(storage_path=link, state_md_path=root / "STATE.md")
        except BoundarySecurityError:
            rejected = True
        assert rejected
        assert link.is_symlink()
        assert real.read_text(encoding="utf-8") == '{"session_id": "hidden"}'


def test_relative_path_escape_is_rejected() -> None:
    rejected = False
    try:
        SessionStore(storage_path="../outside-session.json", state_md_path="STATE.md")
    except BoundarySecurityError:
        rejected = True
    assert rejected
