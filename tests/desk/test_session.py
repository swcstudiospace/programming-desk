"""Tests for SessionStore and SessionFrame."""

import json
from pathlib import Path
import tempfile
import threading

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
