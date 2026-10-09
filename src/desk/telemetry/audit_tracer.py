"""Structured Audit & Telemetry module with JSONL output and credential redaction."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
import uuid

from ..security.policy_sandbox import PolicySandbox


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
    """Thread-safe, append-only JSONL audit event recorder with integrated credential redaction."""

    SENSITIVE_KEY_RE = re.compile(
        r"^(.*_)?(password|passwd|secret|passphrase|credential|credentials|api_key|apikey|private_key|secret_key|auth_key|bearer)$"
        r"|.*(_key|_secret|_password|_passwd|_token|_auth|_credential)$"
        r"|^token$"
        r"|^auth$"
        r"|^authorization$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        log_path: str | Path = ".planning/audit.jsonl",
        sandbox: PolicySandbox | None = None,
        auto_flush: bool = True,
    ) -> None:
        self.log_path = Path(log_path).resolve()
        self.sandbox = sandbox or PolicySandbox()
        self.auto_flush = auto_flush
        self._lock = threading.Lock()

        # Ensure directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

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

    def record_event(self, event: AuditEvent) -> AuditEvent:
        """Record an audit event to the append-only JSONL log with credential redaction."""
        data = event.to_dict()

        # Sanitize details and string fields
        sanitized_details = self._sanitize_value(data["details"])
        data["details"] = sanitized_details
        data["action"] = self.sandbox.sanitize(data["action"])
        data["phase"] = self.sandbox.sanitize(data["phase"])
        data["actor"] = self.sandbox.sanitize(data["actor"])

        line = json.dumps(data, separators=(",", ":")) + "\n"

        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
                if self.auto_flush:
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        # Some filesystems or mock pipes do not support fsync
                        pass

        return event

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

    def read_events(
        self,
        phase: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read and filter structured events from the log using bounded memory."""
        if not self.log_path.exists():
            return []

        use_bounded = limit is not None and limit > 0
        bounded_queue: deque[dict[str, Any]] = deque(maxlen=limit if use_bounded else None)
        unbounded_list: list[dict[str, Any]] = []

        with self._lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
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
