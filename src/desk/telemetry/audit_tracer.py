"""Structured Audit & Telemetry module with JSONL output and credential redaction."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
from typing import Any, Iterator
import uuid

from ..security.policy_sandbox import BoundarySecurityError, PolicySandbox


_GENESIS_PREV_HASH = "0" * 64
_LOWER_HEX64 = re.compile(r"^[0-9a-f]{64}\Z")


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


def _parse_log_line(raw_line: bytes) -> tuple[Any, str | None]:
    """Parse one non-empty log line. Callers skip blank lines themselves."""
    try:
        stripped = raw_line.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, "truncated JSON"
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError:
        return None, "truncated JSON"


def _chain_failure(entry: Any, expected_prev: str, expected_seq: int) -> str | None:
    """Return a short failure reason, or None when ``entry`` continues the chain.

    Extra keys are part of the canonical payload. They do not reject a record
    whose ``seq``, ``prev_hash``, and ``record_hash`` already link.
    """
    if not isinstance(entry, dict):
        return "truncated JSON"
    seq = entry.get("seq")
    if type(seq) is not int or seq != expected_seq:
        return "seq gap"
    if entry.get("prev_hash") != expected_prev:
        return "prev_hash mismatch"
    stored_hash = entry.get("record_hash")
    if not isinstance(stored_hash, str) or stored_hash != _record_hash(entry):
        return "bad hash"
    return None


def _rotated_head_failure(entry: Any) -> str | None:
    """Validate the first record of a rotated segment.

    That record is either a genesis record (seq 1, zero prev_hash) or a
    ``segment_anchor`` with a positive seq, any 64 lowercase-hex prev_hash,
    and a matching record_hash. Later lines are checked by ``_chain_failure``.
    """
    if not isinstance(entry, dict):
        return "truncated JSON"
    if entry.get("action") == "segment_anchor":
        seq = entry.get("seq")
        prev_hash = entry.get("prev_hash")
        stored_hash = entry.get("record_hash")
        if type(seq) is not int or seq < 1:
            return "seq gap"
        if not isinstance(prev_hash, str) or _LOWER_HEX64.fullmatch(prev_hash) is None:
            return "prev_hash mismatch"
        if not isinstance(stored_hash, str) or stored_hash != _record_hash(entry):
            return "bad hash"
        return None
    return _chain_failure(entry, _GENESIS_PREV_HASH, 1)


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

    # Resolve ancestors only. The parent directory itself must stay a real
    # directory; following it would retarget the log into the link target.
    parent = raw.parent
    if parent.is_symlink():
        raise BoundarySecurityError(
            f"Symlink rejected inside workspace: '{parent}'"
        )
    resolved_parent = parent.parent.resolve() / parent.name
    sandbox = PolicySandbox(workspace_root=resolved_parent)
    return sandbox.validate_path(resolved_parent / raw.name), sandbox


@contextmanager
def _open_nofollow(
    path: Path,
    flags: int,
    mode: str,
    dir_fd: int | None = None,
) -> Iterator[Any]:
    """Open ``path`` without following a symlink leaf.

    ``O_NOFOLLOW`` applies to the final component. When ``dir_fd`` is set, the
    leaf is opened under that already-pinned directory so a swapped parent
    cannot redirect the open.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    target: str | Path = path.name if dir_fd is not None else path
    try:
        fd = os.open(target, flags | nofollow, 0o600, dir_fd=dir_fd)
    except OSError as err:
        if nofollow and err.errno == errno.ELOOP:
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{path}'"
            ) from err
        raise
    try:
        if "b" in mode:
            handle = os.fdopen(fd, mode)
        else:
            handle = os.fdopen(fd, mode, encoding="utf-8")
    except Exception:
        os.close(fd)
        raise
    try:
        yield handle
    finally:
        handle.close()


def _directory_identity(directory: Path) -> tuple[int, int]:
    """Inode of a real directory. A symlink parent is rejected."""
    try:
        info = directory.lstat()
    except FileNotFoundError as err:
        raise BoundarySecurityError(
            f"Symlink rejected inside workspace: '{directory}'"
        ) from err
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise BoundarySecurityError(
            f"Symlink rejected inside workspace: '{directory}'"
        )
    return info.st_dev, info.st_ino


def _fsync_directory(directory: Path) -> None:
    """Flush a directory so a rename in it survives a crash. Best effort."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


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
        max_log_bytes: int | None = 1_048_576,
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
        # None disables rotation. The default cap is 1 MiB.
        self.max_log_bytes = max_log_bytes
        self._lock = threading.Lock()

        # Ensure directory exists, then pin that directory inode.
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._parent_pin = _directory_identity(self.log_path.parent)

    def _checked_log_path(self) -> Path:
        """Re-confine the log path so a swapped symlink leaf or parent is rejected."""
        parent = self.log_path.parent
        try:
            info = parent.lstat()
        except FileNotFoundError as err:
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{parent}'"
            ) from err
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or (info.st_dev, info.st_ino) != self._parent_pin
        ):
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{parent}'"
            )
        checked = self._path_sandbox.validate_path(self.log_path)
        self.log_path = checked
        return checked

    @contextmanager
    def _pinned_dir(self) -> Iterator[int]:
        """Directory fd for the pinned log parent. Does not follow a swapped link."""
        parent = self.log_path.parent
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | nofollow)
        except OSError as err:
            if nofollow and err.errno == errno.ELOOP:
                raise BoundarySecurityError(
                    f"Symlink rejected inside workspace: '{parent}'"
                ) from err
            raise
        try:
            info = os.fstat(dir_fd)
            if (info.st_dev, info.st_ino) != self._parent_pin:
                raise BoundarySecurityError(
                    f"Symlink rejected inside workspace: '{parent}'"
                )
            yield dir_fd
        finally:
            os.close(dir_fd)

    @contextmanager
    def _hold_log_lock(self, dir_fd: int, log_name: str) -> Iterator[None]:
        """Exclusive lock shared by every process appending or reading this log."""
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(
                log_name + ".lock",
                os.O_CREAT | os.O_RDWR | nofollow,
                0o600,
                dir_fd=dir_fd,
            )
        except OSError as err:
            if nofollow and err.errno == errno.ELOOP:
                raise BoundarySecurityError(
                    f"Symlink rejected inside workspace: '{log_name}.lock'"
                ) from err
            raise
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

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

    def _lstat_leaf(self, path: Path, dir_fd: int | None) -> os.stat_result:
        if dir_fd is None:
            return path.lstat()
        return os.lstat(path.name, dir_fd=dir_fd)

    def _last_link(self, path: Path, *, dir_fd: int | None = None) -> tuple[str, int]:
        """Return the last valid line's ``(record_hash, seq)`` inside the write lock."""
        prev_hash = _GENESIS_PREV_HASH
        seq = 0
        try:
            info = self._lstat_leaf(path, dir_fd)
        except FileNotFoundError:
            return prev_hash, seq
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{path}'"
            )

        with _open_nofollow(path, os.O_RDONLY, "rb", dir_fd=dir_fd) as handle:
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

    def _rotated_segment(self, path: Path) -> Path:
        """Sibling that holds the previous active segment. Same directory, ``name.1``."""
        return path.with_name(path.name + ".1")

    def _rotate_active(self, path: Path, line: str, *, dir_fd: int | None = None) -> bool:
        """Rename the active log when appending ``line`` would exceed the cap.

        ``None`` never rotates. The threshold uses the UTF-8 byte length of
        ``line``, matching the size ``stat`` reports. A symlink or regular-file
        sibling is replaced atomically with ``os.replace``, which on POSIX
        replaces a symlink itself and does not follow it. A directory sibling
        is left in place and this write is not rotated. The caller writes a
        segment anchor into the fresh active file after a successful rename.
        """
        if self.max_log_bytes is None:
            return False
        try:
            info = self._lstat_leaf(path, dir_fd)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(info.st_mode):
            raise BoundarySecurityError(
                f"Symlink rejected inside workspace: '{path}'"
            )
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            return False
        encoded_len = len(line.encode("utf-8"))
        if info.st_size + encoded_len <= self.max_log_bytes:
            return False
        sibling = self._rotated_segment(path)
        try:
            mode = self._lstat_leaf(sibling, dir_fd).st_mode
        except FileNotFoundError:
            self._replace_leaf(path, sibling, dir_fd)
            return True
        if stat.S_ISDIR(mode):
            return False
        if not (stat.S_ISLNK(mode) or stat.S_ISREG(mode)):
            return False
        self._replace_leaf(path, sibling, dir_fd)
        return True

    def _replace_leaf(self, source: Path, dest: Path, dir_fd: int | None) -> None:
        """Atomically replace ``dest`` with ``source`` inside the pinned directory."""
        if dir_fd is None:
            os.replace(source, dest)
            _fsync_directory(dest.parent)
            return
        os.replace(source.name, dest.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        try:
            os.fsync(dir_fd)
        except OSError:
            pass

    def _segment_anchor(self, prev_hash: str, seq: int) -> tuple[dict[str, Any], str]:
        """Hashed record that opens a fresh segment after rotation.

        ``seq`` is the pre-rotation tail seq plus one, and ``prev_hash`` is
        that tail's record_hash, so the anchor continues the chain that just
        moved to ``.1``.
        """
        record: dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "audit",
            "actor": "audit-tracer",
            "action": "segment_anchor",
            "duration_ms": None,
            "exit_code": None,
            "correlation_id": str(uuid.uuid4())[:8],
            "details": {"segment_anchor": True},
            "seq": seq,
            "prev_hash": prev_hash,
        }
        record["record_hash"] = _record_hash(record)
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        return record, line

    def _verify_segment(
        self,
        path: Path,
        expected_prev: str,
        expected_seq: int,
        *,
        relaxed_head: bool = False,
        dir_fd: int | None = None,
    ) -> tuple[bool, str, str, int]:
        """Verify ``path`` from the given cursor.

        A missing or empty file succeeds and leaves the cursor unchanged.
        With ``relaxed_head``, the first record may be genesis seq 1 or a
        ``segment_anchor``; every following line must link from that head.
        """
        try:
            info = self._lstat_leaf(path, dir_fd)
        except FileNotFoundError:
            return True, "ok", expected_prev, expected_seq
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return False, "truncated JSON", expected_prev, expected_seq
        saw_record = False
        with _open_nofollow(path, os.O_RDONLY, "rb", dir_fd=dir_fd) as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                entry, reason = _parse_log_line(raw_line)
                if reason is not None:
                    return False, reason, expected_prev, expected_seq
                if relaxed_head and not saw_record:
                    reason = _rotated_head_failure(entry)
                    if reason is not None:
                        return False, reason, expected_prev, expected_seq
                    expected_prev = entry["record_hash"]
                    expected_seq = entry["seq"] + 1
                    saw_record = True
                    continue
                saw_record = True
                reason = _chain_failure(entry, expected_prev, expected_seq)
                if reason is not None:
                    return False, reason, expected_prev, expected_seq
                expected_prev = entry["record_hash"]
                expected_seq += 1
        return True, "ok", expected_prev, expected_seq

    def _active_chain_start(
        self, path: Path, *, dir_fd: int | None = None
    ) -> tuple[bool, str, str, int]:
        """Cursor for the active file after a verified rotated segment, if any.

        No regular sibling starts at genesis / seq 1. A symlink sibling fails.
        A regular sibling is walked first: its head is genesis seq 1 or a
        ``segment_anchor``, and its tail hash and next seq are handed to the
        active file.
        """
        expected_prev = _GENESIS_PREV_HASH
        expected_seq = 1
        sibling = self._rotated_segment(path)
        try:
            mode = self._lstat_leaf(sibling, dir_fd).st_mode
        except FileNotFoundError:
            return True, "ok", expected_prev, expected_seq
        if stat.S_ISLNK(mode):
            return False, "rotated segment is a symlink", expected_prev, expected_seq
        if not stat.S_ISREG(mode):
            return True, "ok", expected_prev, expected_seq
        return self._verify_segment(
            sibling, expected_prev, expected_seq, relaxed_head=True, dir_fd=dir_fd
        )

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
            with self._pinned_dir() as dir_fd, self._hold_log_lock(dir_fd, path.name):
                prev_hash, last_seq = self._last_link(path, dir_fd=dir_fd)
                data["seq"] = last_seq + 1
                data["prev_hash"] = prev_hash
                data["record_hash"] = _record_hash(data)
                line = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
                # Rotation is decided from the pre-rotation link. After the
                # rename, the fresh file opens with an anchor that keeps that
                # link, and the user record is rebuilt from the anchor.
                anchor_line = ""
                if self._rotate_active(path, line, dir_fd=dir_fd):
                    anchor, anchor_line = self._segment_anchor(prev_hash, last_seq + 1)
                    data["seq"] = anchor["seq"] + 1
                    data["prev_hash"] = anchor["record_hash"]
                    data["record_hash"] = _record_hash(data)
                    line = json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n"
                with _open_nofollow(
                    path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, "a", dir_fd=dir_fd
                ) as handle:
                    if anchor_line:
                        handle.write(anchor_line)
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
        """Verify the hash chain, including one rotated ``<name>.1`` segment.

        Returns ``(True, "ok")`` for an empty log or a fully linked chain.
        A regular rotated segment is walked first. Its first record is either
        genesis seq 1 or a ``segment_anchor`` (positive seq, 64 lowercase-hex
        prev_hash, valid record_hash); every following line must link. The
        active file must then continue from that segment's tail. An empty
        active file after a verified segment is ok. With no sibling, the
        active file itself must start at genesis unless it is empty.
        Returns ``(False, reason)`` for a bad hash, a ``prev_hash`` mismatch,
        a gap in ``seq``, truncated JSON, or a symlink rotated segment.
        """
        with self._lock:
            path = self._checked_log_path()
            with self._pinned_dir() as dir_fd, self._hold_log_lock(dir_fd, path.name):
                ok, reason, expected_prev, expected_seq = self._active_chain_start(
                    path, dir_fd=dir_fd
                )
                if not ok:
                    return False, reason
                ok, reason, _last_hash, _next_seq = self._verify_segment(
                    path, expected_prev, expected_seq, dir_fd=dir_fd
                )
                if not ok:
                    return False, reason
        return True, "ok"

    def _collect_user_events(
        self,
        path: Path,
        expected_prev: str,
        expected_seq: int,
        sink: list[dict[str, Any]],
        *,
        relaxed_head: bool,
        phase: str | None,
        actor: str | None,
        action: str | None,
        correlation_id: str | None,
        dir_fd: int | None = None,
    ) -> bool:
        """Append linked user records from ``path``.

        Returns False when a line breaks the chain. Records already appended
        stay in ``sink``. A missing or empty file returns True. A relaxed head
        accepts genesis seq 1 or a ``segment_anchor``. Anchor records advance
        the cursor and are not appended. Phase, actor, and action filters run
        after the link check.
        """
        try:
            info = self._lstat_leaf(path, dir_fd)
        except FileNotFoundError:
            return True
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return False
        saw_record = False
        try:
            with _open_nofollow(path, os.O_RDONLY, "rb", dir_fd=dir_fd) as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    entry, reason = _parse_log_line(raw_line)
                    if reason is not None:
                        return False
                    if relaxed_head and not saw_record:
                        reason = _rotated_head_failure(entry)
                        if reason is not None:
                            return False
                        expected_prev = entry["record_hash"]
                        expected_seq = entry["seq"] + 1
                        saw_record = True
                    else:
                        if _chain_failure(entry, expected_prev, expected_seq) is not None:
                            return False
                        expected_prev = entry["record_hash"]
                        expected_seq += 1
                        saw_record = True

                    if entry.get("action") == "segment_anchor":
                        continue
                    if phase and entry.get("phase") != phase:
                        continue
                    if actor and entry.get("actor") != actor:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if correlation_id and entry.get("correlation_id") != correlation_id:
                        continue
                    sink.append(entry)
        except FileNotFoundError:
            return False
        return True

    def read_events(
        self,
        phase: str | None = None,
        actor: str | None = None,
        action: str | None = None,
        correlation_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read linked user events from the retained segment and the active log.

        The rotated segment uses the same head rule as ``verify_chain``. If
        that segment does not verify, the result is empty. User events from a
        verified segment are included. Blank lines are skipped. The first
        active line that is not JSON, is not a dict, or breaks ``seq`` /
        ``prev_hash`` / ``record_hash`` ends the walk; that line and everything
        after it are omitted, and earlier linked user events are kept.
        ``segment_anchor`` records are not returned. Phase, actor, action,
        correlation_id, and ``limit`` apply only to the user records that
        linked. ``limit`` keeps the newest matches across both files. Extra
        keys do not drop a record whose hash still matches.
        """
        use_bounded = limit is not None and limit > 0
        matched: list[dict[str, Any]] = []

        with self._lock:
            path = self._checked_log_path()
            with self._pinned_dir() as dir_fd, self._hold_log_lock(dir_fd, path.name):
                ok, _reason, expected_prev, expected_seq = self._active_chain_start(
                    path, dir_fd=dir_fd
                )
                if not ok:
                    return []
                sibling = self._rotated_segment(path)
                try:
                    sibling_mode = self._lstat_leaf(sibling, dir_fd).st_mode
                except FileNotFoundError:
                    sibling_mode = 0
                if stat.S_ISREG(sibling_mode):
                    retained: list[dict[str, Any]] = []
                    whole = self._collect_user_events(
                        sibling,
                        _GENESIS_PREV_HASH,
                        1,
                        retained,
                        relaxed_head=True,
                        phase=phase,
                        actor=actor,
                        action=action,
                        correlation_id=correlation_id,
                        dir_fd=dir_fd,
                    )
                    if not whole:
                        return []
                    matched.extend(retained)
                self._collect_user_events(
                    path,
                    expected_prev,
                    expected_seq,
                    matched,
                    relaxed_head=False,
                    phase=phase,
                    actor=actor,
                    action=action,
                    correlation_id=correlation_id,
                    dir_fd=dir_fd,
                )

        if use_bounded:
            return matched[-limit:]
        return matched
