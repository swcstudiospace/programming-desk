"""Local record of leases this host already holds.

``graph_get`` does not return ``lease_id``, including to the holder. The id is
shown once, on the grant. This file is where the desk keeps the ids it was
given so a later tick can pass them to ``graph_heartbeat``. The file is not a
second claim protocol: a row here renews, and a rejection removes the row.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

_GRAPH_ID = re.compile(r"^ut-[a-z0-9]+-[0-9a-f]{8}$")
_NODE_ID = re.compile(r"^n[1-8]$")


class StateError(ValueError):
    """held.json is present and not a list of leases."""


@dataclass(frozen=True)
class HeldLease:
    graph_id: str
    node_id: str
    lease_id: str
    seat: str | None = None
    ttl_seconds: int | None = None

    def key(self) -> str:
        return f"{self.graph_id}/{self.node_id}"

    def to_json(self) -> dict[str, object]:
        body: dict[str, object] = {
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "lease_id": self.lease_id,
        }
        if self.seat is not None:
            body["seat"] = self.seat
        if self.ttl_seconds is not None:
            body["ttl_seconds"] = self.ttl_seconds
        return body


def load_held(path: Path) -> list[HeldLease]:
    """Return the leases in ``path``. A missing file is an empty list."""
    if not path.is_file():
        return []
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"{path}: {exc}") from exc
    rows = _rows(parsed, path)
    leases: list[HeldLease] = []
    for index, row in enumerate(rows):
        leases.append(_lease(row, path, index))
    return leases


def save_held(path: Path, leases: list[HeldLease]) -> None:
    payload = {"leases": [lease.to_json() for lease in leases]}
    _atomic_write(path, json.dumps(payload, indent=2) + "\n", 0o600)


def load_misses(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    misses: dict[str, int] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, int) and value >= 0 and "/" in key:
            misses[key] = value
    return misses


def save_misses(path: Path, misses: dict[str, int]) -> None:
    _atomic_write(path, json.dumps(misses, indent=2, sort_keys=True) + "\n", 0o600)


def write_last_renewal(path: Path, unix_s: int) -> None:
    _atomic_write(path, f"{unix_s}\n", 0o644)


def _rows(parsed: object, path: Path) -> list[object]:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict) and isinstance(parsed.get("leases"), list):
        return parsed["leases"]
    raise StateError(f"{path}: expected a list or an object with a leases list")


def _lease(row: object, path: Path, index: int) -> HeldLease:
    if not isinstance(row, dict):
        raise StateError(f"{path}: leases[{index}] is not an object")
    graph_id = row.get("graph_id")
    node_id = row.get("node_id")
    lease_id = row.get("lease_id")
    if not isinstance(graph_id, str) or not _GRAPH_ID.match(graph_id):
        raise StateError(f"{path}: leases[{index}].graph_id is not a Graph ID")
    if not isinstance(node_id, str) or not _NODE_ID.match(node_id):
        raise StateError(f"{path}: leases[{index}].node_id is not n1..n8")
    if not isinstance(lease_id, str) or not lease_id or len(lease_id) > 200 or any(ch in lease_id for ch in "\n\r"):
        raise StateError(f"{path}: leases[{index}].lease_id must be 1..200 characters on one line")
    seat = row.get("seat")
    if seat is not None and not isinstance(seat, str):
        raise StateError(f"{path}: leases[{index}].seat is not a string")
    ttl = row.get("ttl_seconds")
    if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int)):
        raise StateError(f"{path}: leases[{index}].ttl_seconds is not an integer")
    if isinstance(ttl, int) and not 30 <= ttl <= 86400:
        raise StateError(f"{path}: leases[{index}].ttl_seconds must be 30..86400")
    return HeldLease(
        graph_id=graph_id,
        node_id=node_id,
        lease_id=lease_id,
        seat=seat if isinstance(seat, str) else None,
        ttl_seconds=ttl if isinstance(ttl, int) else None,
    )


def _atomic_write(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(tmp, mode)
    os.replace(tmp, path)
