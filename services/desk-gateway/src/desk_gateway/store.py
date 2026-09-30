"""Small JSON-file store for gateway state (roster registrations, intake queue, packs, acks).

The index of record for the desk moves to TimescaleDB in substrate Phase 3 of the v2 plan; this
store keeps the same shapes so that swap is a backend change. Every write is atomic and taken
under one process lock.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

INTAKE_STATES = ("queued", "claimed", "accepted", "rejected", "in_progress", "done")


def _now() -> float:
    return time.time()


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write(self, name: str, payload: Any) -> None:
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)

    def roster(self) -> dict[str, Any]:
        with self._lock:
            return self._read("roster", {"seats": {}, "channel_id": None, "updated_at": None})

    def register_seat(
        self, short: str, *, agent_uuid: str | None, channel_id: str | None, tool_count: int
    ) -> dict[str, Any]:
        with self._lock:
            roster = self.roster()
            entry = roster["seats"].get(short) or {}
            if agent_uuid:
                entry["agent_uuid"] = agent_uuid
            entry["tool_count"] = tool_count
            entry["registered_at"] = entry.get("registered_at") or _now()
            entry["last_seen"] = _now()
            roster["seats"][short] = entry
            if channel_id:
                roster["channel_id"] = channel_id
            roster["updated_at"] = _now()
            self._write("roster", roster)
            return roster

    def touch_seat(self, short: str, **fields: Any) -> None:
        with self._lock:
            roster = self.roster()
            entry = roster["seats"].get(short) or {}
            entry["last_seen"] = _now()
            for k, v in fields.items():
                if v is not None:
                    entry[k] = v
            roster["seats"][short] = entry
            self._write("roster", roster)

    def packs_for(self, short: str) -> list[str]:
        with self._lock:
            packs = self._read("packs", {})
            return [p["app"] for p in packs.get(short) or []]

    def pack_records(self, short: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._read("packs", {}).get(short) or [])

    def load_pack(self, short: str, app: str, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            packs = self._read("packs", {})
            records = [p for p in packs.get(short) or [] if p["app"] != app]
            records.append({"app": app, "task_id": task_id, "loaded_at": _now()})
            packs[short] = records
            self._write("packs", packs)
            return records

    def unload_pack(self, short: str, app: str) -> list[dict[str, Any]]:
        with self._lock:
            packs = self._read("packs", {})
            records = [p for p in packs.get(short) or [] if p["app"] != app]
            packs[short] = records
            self._write("packs", packs)
            return records

    def intake_create(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            queue = self._read("intake", [])
            key = item.get("idempotency_key")
            if key:
                # Scoped by origin: intake tokens authenticate separate origins, and each
                # builds its own keys (the GitHub workflow uses github:<repo>:<issue>).
                # Deduplicating on the key alone lets one origin's key swallow another's
                # request — the second caller gets the first's intake_id and is told it was
                # accepted, while its own ask is never queued.
                for existing in queue:
                    if (existing.get("origin") == item.get("origin")
                            and existing.get("idempotency_key") == key):
                        return existing
            record = {
                "intake_id": "in-" + secrets.token_hex(6),
                "state": "queued",
                "created_at": _now(),
                "claimed_at": None,
                "acks": [],
                **item,
            }
            queue.append(record)
            self._write("intake", queue)
            return record

    def intake_next(self, origin: str | None) -> dict[str, Any] | None:
        with self._lock:
            queue = self._read("intake", [])
            for record in queue:
                if record["state"] != "queued":
                    continue
                if origin and record.get("origin") != origin:
                    continue
                record["state"] = "claimed"
                record["claimed_at"] = _now()
                self._write("intake", queue)
                return record
            return None

    def intake_get(self, intake_id: str) -> dict[str, Any] | None:
        with self._lock:
            for record in self._read("intake", []):
                if record["intake_id"] == intake_id:
                    return record
            return None

    def intake_ack(self, intake_id: str, ack: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            queue = self._read("intake", [])
            for record in queue:
                if record["intake_id"] == intake_id:
                    record["state"] = ack["status"]
                    if ack.get("graph_id"):
                        record["graph_id"] = ack["graph_id"]
                    record["acks"].append({**ack, "at": _now()})
                    self._write("intake", queue)
                    return record
            return None

    def intake_counts(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for record in self._read("intake", []):
                counts[record["state"]] = counts.get(record["state"], 0) + 1
            return counts

    def acks(self) -> dict[str, Any]:
        with self._lock:
            return self._read("acks", {})

    def record_ack(self, change_id: str, bot_id: str, ack: bool, note: str) -> dict[str, Any]:
        with self._lock:
            acks = self._read("acks", {})
            entry = acks.get(change_id) or {"acknowledgements": []}
            entry["acknowledgements"] = [a for a in entry["acknowledgements"] if a["bot"] != bot_id]
            entry["acknowledgements"].append({"bot": bot_id, "ack": ack, "note": note, "at": _now()})
            acks[change_id] = entry
            self._write("acks", acks)
            return entry

    def doctor_result(self, short: str, result: dict[str, Any]) -> None:
        with self._lock:
            results = self._read("doctor", {})
            results[short] = {"at": _now(), **result}
            self._write("doctor", results)

    def doctor_results(self) -> dict[str, Any]:
        with self._lock:
            return self._read("doctor", {})

    def audit_append(self, event: dict[str, Any]) -> None:
        with self._lock:
            path = self.dir / "audit.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
