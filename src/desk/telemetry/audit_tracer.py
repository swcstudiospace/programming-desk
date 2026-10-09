"""Structured Audit & Telemetry module with JSONL output and credential redaction."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
import uuid

from ..security.policy_sandbox import PolicySandbox


_GENESIS_PREV_HASH = "0" * 64


def _canonical_json(record: dict[str, Any]) -> str:
    """Canonical JSON of a persisted record, excluding ``record_hash``."""
    body = {key: value for key, value in record.items() if key != "record_hash"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _record_hash(record: dict[str, Any]) -> str:
    """Hex sha256 of ``prev_hash``, a newline, and the record's canonical JSON."""
    prev_hash = record.get("prev_hash")
    prefix = prev_hash if isinstance(prev_hash, str) else ""
    material = f"{prefix}\n{_canonical_json(record)}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _confine_log_path(
    log_path: str | Path,
    workspace_root: str | Path | None,
) -> tuple[Path, PolicySandbox]:
    """Confine ``log_path`` and return the checked path plus the sandbox used.

    Relative paths, including the default ``.planning/audit.jsonl``, are confined
    to ``workspace_root`` or the process cwd. Absolute paths stay legal for tests
    and are confined to the parent of that path, so a symlink leaf is rejected
    and ``..`` cannot escape that parent.
    """
    raw = Path(log_path)
    if not raw.is_absolute():
        sandbox = PolicySandbox(workspace_root=workspace_root)
        return sandbox.validate_path(raw), sandbox

    # Anchor above any ``..`` so PolicySandbox sees the escape instead of
    # collapsing it into a wider workspace root.
    if ".." in raw.parts:
        anchor_parts: list[str] = []
        for part in raw.parts:
            if part == "..":
                break
            anchor_parts.append(part)
        anchor = Path(*anchor_parts) if anchor_parts else Path(os.sep)
        sandbox = PolicySandbox(workspace_root=anchor)
        return sandbox.validate_path(raw), sandbox

    # Resolve ancestor symlinks, then validate the leaf so a symlink leaf fails
    # and a lexical mismatch with PolicySandbox.resolve() does not.
    parent = raw.parent.resolve()
    sandbox = PolicySandbox(workspace_root=parent)
    return sandbox.validate_path(parent / raw.name), sandbox


@dataclass
class AuditEvent:
    """Represents a structured audit record in the programming desk."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    phase: str = "general"
    actor: str = "bot-lead"
    action: str = "execution"
    duration_ms: float | None = None
    exit_code: int | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditTracer:
    """Thread-safe, append-only JSONL audit log with a tamper-evident hash chain."""

    SENSITIVE_KEY_RE = re.compile(
        r"(?:^|[a-z0-9_])(password|passwd|secret|passphrase|credential|credentials|token|key|bearer|auth|authorization|apikey)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        log_path: str | Path = ".planning/audit.jsonl",
        sandbox: PolicySandbox | None = None,
        auto_flush: bool = True,
        workspace_root: str | Path | None = None,
    ) -> None:
        checked, path_sandbox = _confine_log_path(log_path, workspace_root)
        self._path_sandbox = path_sandbox
        self.log_path = checked
        self.sandbox = (
            sandbox
            if sandbox is not None
            else PolicySandbox(workspace_root=workspace_root)
        )
        self.auto_flush = auto_flush
        self._lock = threading.Lock()

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _checked_log_path(self) -> Path:
        """Re-confine the log path so a swapped symlink leaf is rejected."""
        checked = self._path_sandbox.validate_path(self.log_path)
        self.log_path = checked
        return checked

    def _sanitize_value(self, val: Any, key_name: str | None = None) -> Any:
        """Recursively redact sensitive keys and credential values."""
        # Check sensitive key names
        if key_name and self.SENSITIVE_KEY_RE.search(key_name):
            return "[REDACTED]"

        if isinstance(val, str):
            return self.sandbox.sanitize(val)
        if isinstance(val, dict):
            return {k: self._sanitize_value(v, key_name=str(k)) for k, v in val.items()}
        if isinstance(val, (list, tuple, set)):
            return [self._sanitize_value(item, key_name=key_name) for item in val]
        return val

    def _last_link(self, path: Path) -> tuple[str, int]:
        """Return the last valid line's ``(record_hash, seq)`` inside the write lock."""
        prev_hash = _GENESIS_PREV_HASH
        seq = 0
        if not path.exists():
            return prev_hash, seq

        with open(path, "rb") as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                try:
                    stripped = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                record_hash = entry.get("record_hash")
                if not isinstance(record_hash, str):
                    continue
                prev_hash = record_hash
                record_seq = entry.get("seq")
                if type(record_seq) is int:
                    seq = record_seq
                else:
                    seq += 1
        return prev_hash, seq

    def record_event(self, event: AuditEvent) -> AuditEvent:
        """Record an audit event to the append-only JSONL log with credential redaction."""
        data = event.to_dict()

        # Sanitize details and string fields
        sanitized_details = self._sanitize_value(data["details"])
        data["details"] = sanitized_details
        data["action"] = self.sandbox.sanitize(data["action"])
        data["phase"] = self.sandbox.sanitize(data["phase"])
        data["actor"] = self.sandbox.sanitize(data["actor"])

        with self._lock:
            path = self._checked_log_path()
            prev_hash, last_seq = self._last_link(path)
            data["seq"] = last_seq + 1
            data["prev_hash"] = prev_hash
            data["record_hash"] = _record_hash(data)
            line = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line)
                if self.auto_flush:
                    handle.flush()
                    try:
                        os.fsync(handle.fileno())
                    except OSError:
                        # Some filesystems or mock pipes do not support fsync
                        pass

        return replace(
            event,
            phase=data["phase"],
            actor=data["actor"],
            action=data["action"],
            details=data["details"],
        )

    def emit(
        self,
        action: str,
        phase: str = "general",
        actor: str = "bot-lead",
        duration_ms: float | None = None,
        exit_code: int | None = None,
        correlation_id: str | None = None,
        **details: Any,
    ) -> AuditEvent:
        """Convenience method to construct and record an audit event."""
        event = AuditEvent(
            phase=phase,
            actor=actor,
            action=action,
            duration_ms=duration_ms,
            exit_code=exit_code,
            correlation_id=correlation_id or str(uuid.uuid4())[:8],
            details=details,
        )
        return self.record_event(event)

    def verify_chain(self) -> tuple[bool, str]:
        """Verify the hash chain.

        Returns ``(True, "ok")`` for an empty log or a fully linked chain.
        Returns ``(False, reason)`` for a bad hash, a ``prev_hash`` mismatch,
        a gap in ``seq``, or truncated JSON.
        """
        with self._lock:
            path = self._checked_log_path()
            if not path.exists():
                return True, "ok"

            expected_prev = _GENESIS_PREV_HASH
            expected_seq = 1
            with open(path, "rb") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    try:
                        stripped = raw_line.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        return False, "truncated JSON"
                    try:
                        entry = json.loads(stripped)
                    except json.JSONDecodeError:
                        return False, "truncated JSON"
                    if not isinstance(entry, dict):
                        return False, "truncated JSON"

                    seq = entry.get("seq")
                    if type(seq) is not int or seq != expected_seq:
                        return False, "seq gap"

                    prev_hash = entry.get("prev_hash")
                    if prev_hash != expected_prev:
                        return False, "prev_hash mismatch"

                    stored_hash = entry.get("record_hash")
                    if not isinstance(stored_hash, str) or stored_hash != _record_hash(entry):
                        return False, "bad hash"

                    expected_prev = stored_hash
                    expected_seq += 1

        return True, "ok"

    def read_events(
        self,
        phase: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read and filter structured events from the log using bounded memory."""
        use_bounded = limit is not None and limit > 0
        bounded_queue: deque[dict[str, Any]] = deque(maxlen=limit if use_bounded else None)
        unbounded_list: list[dict[str, Any]] = []

        with self._lock:
            path = self._checked_log_path()
            if not path.exists():
                return []
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        entry = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue

                    if phase and entry.get("phase") != phase:
                        continue
                    if actor and entry.get("actor") != actor:
                        continue
                    if action and entry.get("action") != action:
                        continue

                    if use_bounded:
                        bounded_queue.append(entry)
                    else:
                        unbounded_list.append(entry)

        if use_bounded:
            return list(bounded_queue)
        return unbounded_list
