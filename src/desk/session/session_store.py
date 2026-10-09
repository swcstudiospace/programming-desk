"""Workspace Context & Session State persistence module with atomic temp-rename writes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any


@dataclass
class SessionFrame:
    """Represents a discrete workbench execution context snapshot."""

    session_id: str
    milestone: str = "v1.0"
    phase: str = "general"
    status: str = "in_progress"
    active_tasks: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> SessionFrame:
        if not isinstance(data, dict):
            raise TypeError(f"SessionFrame payload must be a dict, got: {type(data)}")
        if "session_id" not in data or not isinstance(data["session_id"], str):
            raise ValueError("SessionFrame requires a valid string 'session_id'")

        raw_active = data.get("active_tasks")
        raw_completed = data.get("completed_tasks")
        raw_meta = data.get("metadata")

        active_tasks = [str(t) for t in raw_active if t is not None] if isinstance(raw_active, list) else []
        completed_tasks = [str(t) for t in raw_completed if t is not None] if isinstance(raw_completed, list) else []
        metadata = raw_meta if isinstance(raw_meta, dict) else {}

        return cls(
            session_id=data["session_id"],
            milestone=str(data.get("milestone", "v1.0")),
            phase=str(data.get("phase", "general")),
            status=str(data.get("status", "in_progress")),
            active_tasks=active_tasks,
            completed_tasks=completed_tasks,
            metadata=metadata,
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
        )


class SessionStore:
    """Manages atomic session persistence, state hydration, and .planning/STATE.md synchronization."""

    def __init__(
        self,
        storage_path: str | Path = ".planning/session.json",
        state_md_path: str | Path = ".planning/STATE.md",
    ) -> None:
        self.storage_path = Path(storage_path).resolve()
        self.state_md_path = Path(state_md_path).resolve()
        self._lock = threading.Lock()

        # Ensure parent directories exist
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_md_path.parent.mkdir(parents=True, exist_ok=True)

    def persist_atomic(self, target_path: Path, content: str) -> None:
        """Write content to temporary file and atomically rename to target_path."""
        temp_path = target_path.with_name(
            f"{target_path.name}.tmp.{os.getpid()}.{datetime.now().timestamp()}"
        )
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            # Atomic filesystem replacement
            os.replace(temp_path, target_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def save_session(self, frame: SessionFrame) -> SessionFrame:
        """Atomically persist session frame to JSON storage."""
        frame.updated_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(frame.to_dict(), indent=2)

        with self._lock:
            self.persist_atomic(self.storage_path, payload)

        return frame

    def load_session(self) -> SessionFrame | None:
        """Hydrate session frame from disk if present."""
        with self._lock:
            if not self.storage_path.exists():
                return None
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionFrame.from_dict(data)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
                return None

    def sync_to_markdown_state(self, frame: SessionFrame) -> str:
        """Render session frame into .planning/STATE.md format and atomically persist."""
        lines = [
            f"# State: Milestone {frame.milestone} — {frame.phase}",
            "",
            "## Current Status",
            f"- Session ID: `{frame.session_id}`",
            f"- Milestone: {frame.milestone}",
            f"- Phase: {frame.phase}",
            f"- Status: {frame.status}",
            f"- Updated At: {frame.updated_at}",
            "",
            "## Active Tasks",
        ]

        if frame.active_tasks:
            for task in frame.active_tasks:
                lines.append(f"- [ ] {task}")
        else:
            lines.append("- *(No active tasks)*")

        lines.append("")
        lines.append("## Completed Tasks")
        if frame.completed_tasks:
            for task in frame.completed_tasks:
                lines.append(f"- [x] {task}")
        else:
            lines.append("- *(No completed tasks)*")

        if frame.metadata:
            lines.append("")
            lines.append("## Metadata")
            for k, v in frame.metadata.items():
                lines.append(f"- **{k}**: {v}")

        lines.append("")
        content = "\n".join(lines)

        with self._lock:
            self.persist_atomic(self.state_md_path, content)

        return content
