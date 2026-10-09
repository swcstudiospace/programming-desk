"""Workspace session persistence with atomic writes and corrupt-file quarantine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
import uuid

from ..security.policy_sandbox import BoundarySecurityError, PolicySandbox

SESSION_SCHEMA_VERSION = 1
_CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_STATE_REGION_START = "<!-- desk-session:start -->"
_STATE_REGION_END = "<!-- desk-session:end -->"


def _confine_path(path: str | Path) -> Path:
    """Confine a storage path without following symlinks.

    Relative paths must stay inside the process workspace. Absolute paths are
    confined to their parent so tempfile locations keep working while a symlink
    leaf is rejected.
    """
    raw = Path(path)
    if raw.is_absolute():
        return PolicySandbox(workspace_root=raw.parent).validate_path(raw)
    return PolicySandbox().validate_path(raw)


def _read_text_nofollow(path: Path) -> str:
    """Read UTF-8 text without following a symlink leaf."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, os.O_RDONLY | nofollow)
    except OSError as err:
        if nofollow and err.errno == errno.ELOOP:
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{path}'"
            ) from err
        raise
    try:
        handle = os.fdopen(fd, "r", encoding="utf-8")
    except Exception:
        os.close(fd)
        raise
    with handle:
        return handle.read()


@dataclass
class SessionFrame:
    """Represents a discrete workbench execution context snapshot."""

    session_id: str
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    milestone: str = "v1.0"
    phase: str = "general"
    status: str = "in_progress"
    active_tasks: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: int = SESSION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = SESSION_SCHEMA_VERSION
        return payload

    @classmethod
    def from_dict(cls, data: Any) -> SessionFrame:
        if not isinstance(data, dict):
            raise TypeError(f"SessionFrame payload must be a dict, got: {type(data)}")
        if "schema_version" in data:
            version = data["schema_version"]
            if type(version) is not int or version != SESSION_SCHEMA_VERSION:
                raise ValueError(
                    "Unsupported session schema_version "
                    f"{version!r}; expected integer {SESSION_SCHEMA_VERSION}"
                )
        if "session_id" not in data or not isinstance(data["session_id"], str):
            raise ValueError("SessionFrame requires a valid string 'session_id'")

        if "correlation_id" not in data:
            correlation_id = uuid.uuid4().hex[:8]
        else:
            correlation_id = data["correlation_id"]
            if (
                not isinstance(correlation_id, str)
                or _CORRELATION_ID_RE.fullmatch(correlation_id) is None
            ):
                raise ValueError(
                    "SessionFrame correlation_id must match ^[A-Za-z0-9_-]{8,64}$"
                )

        raw_active = data.get("active_tasks")
        raw_completed = data.get("completed_tasks")
        raw_meta = data.get("metadata")

        active_tasks = [str(t) for t in raw_active if t is not None] if isinstance(raw_active, list) else []
        completed_tasks = [str(t) for t in raw_completed if t is not None] if isinstance(raw_completed, list) else []
        metadata = raw_meta if isinstance(raw_meta, dict) else {}

        return cls(
            session_id=data["session_id"],
            correlation_id=correlation_id,
            milestone=str(data.get("milestone", "v1.0")),
            phase=str(data.get("phase", "general")),
            status=str(data.get("status", "in_progress")),
            active_tasks=active_tasks,
            completed_tasks=completed_tasks,
            metadata=metadata,
            updated_at=str(data.get("updated_at", datetime.now(timezone.utc).isoformat())),
            schema_version=SESSION_SCHEMA_VERSION,
        )


class SessionStore:
    """Manages atomic session persistence, state hydration, and .planning/STATE.md synchronization."""

    def __init__(
        self,
        storage_path: str | Path = ".planning/session.json",
        state_md_path: str | Path = ".planning/STATE.md",
    ) -> None:
        self.storage_path = _confine_path(storage_path)
        self.state_md_path = _confine_path(state_md_path)
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

    def _reconfine_storage(self) -> None:
        self.storage_path = _confine_path(self.storage_path)

    def _reconfine_state(self) -> None:
        self.state_md_path = _confine_path(self.state_md_path)

    def save_session(self, frame: SessionFrame) -> SessionFrame:
        """Atomically persist session frame to JSON storage."""
        frame.updated_at = datetime.now(timezone.utc).isoformat()
        frame.schema_version = SESSION_SCHEMA_VERSION
        payload = json.dumps(frame.to_dict(), indent=2)

        with self._lock:
            self._reconfine_storage()
            self.persist_atomic(self.storage_path, payload)

        return frame

    def load_session(self) -> SessionFrame | None:
        """Hydrate session frame from disk if present.

        JSON decode failures, read errors, and unsupported payloads are moved
        aside to ``<name>.corrupt.<pid>`` in the same directory. The live path
        is left absent so a later save can write a new file. A path that fails
        confinement raises and is not quarantined.
        """
        with self._lock:
            self._reconfine_storage()
            if not self.storage_path.exists():
                return None
            try:
                raw = _read_text_nofollow(self.storage_path)
            except BoundarySecurityError:
                raise
            except OSError:
                self._quarantine_corrupt_storage()
                return None
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self._quarantine_corrupt_storage()
                return None
            try:
                return SessionFrame.from_dict(data)
            except (ValueError, TypeError):
                self._quarantine_corrupt_storage()
                return None

    def _quarantine_corrupt_storage(self) -> None:
        """Rename the bad session file aside. Never writes a replacement over it."""
        source = self.storage_path
        destination = source.with_name(f"{source.name}.corrupt.{os.getpid()}")
        if destination == source:
            return
        try:
            os.replace(source, destination)
        except FileNotFoundError:
            return

    def sync_to_markdown_state(self, frame: SessionFrame) -> str:
        """Render session frame into .planning/STATE.md and atomically persist.

        A missing or empty file becomes one marked document. An existing
        document without the start marker keeps its text and gains one marked
        section. When both markers are present, only that span is replaced.
        """
        section = _marked_session_document(_render_state_markdown(frame))
        with self._lock:
            self._reconfine_state()
            merged = self._merge_state_markdown(section)
            self.persist_atomic(self.state_md_path, merged)
        return merged

    def _merge_state_markdown(self, section: str) -> str:
        path = self.state_md_path
        if not path.exists():
            return section
        existing = _read_text_nofollow(path)
        if existing == "":
            return section
        start_idx = existing.find(_STATE_REGION_START)
        if start_idx == -1:
            if existing.endswith("\n"):
                return existing + section
            return existing + "\n" + section
        end_idx = existing.find(_STATE_REGION_END, start_idx + len(_STATE_REGION_START))
        if end_idx == -1:
            return existing[:start_idx] + section
        end_span = end_idx + len(_STATE_REGION_END)
        if end_span < len(existing) and existing[end_span] == "\n":
            end_span += 1
        return existing[:start_idx] + section + existing[end_span:]


def _render_state_markdown(frame: SessionFrame) -> str:
    lines = [
        f"# State: Milestone {frame.milestone} — {frame.phase}",
        "",
        "## Current Status",
        f"- Session ID: `{frame.session_id}`",
        f"- Correlation ID: `{frame.correlation_id}`",
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
    return "\n".join(lines)


def _marked_session_document(body: str) -> str:
    if not body.endswith("\n"):
        body += "\n"
    return f"{_STATE_REGION_START}\n{body}{_STATE_REGION_END}\n"
