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

INTAKE_STATES = ("queued", "claimed", "accepted", "rejected", "in_progress", "done", "dead_letter")


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
                "retry_count": 0,
                "max_retries": int(item.get("max_retries", 3)),
                "failures": [],
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

    def intake_delivery(self, intake_id: str, key: str, state: str) -> dict[str, Any] | None:
        """Record how far the origin reply for one ack got, as a write of its own.

        Separate from intake_ack because it has to be durable *before* the reply is posted:
        the reply goes out first (see tools.lead.intake_ack), so a failure anywhere after it
        asks LEAD to call again, and only a record written before the post tells that second
        call a comment may already exist. Keyed per ack rather than per intake, so a later
        ack on the same intake is its own delivery.

        `attempted` keeps `first_at` from the first attempt for this ack, because that is the
        moment a recovery lookup has to search from — refreshing it on every attempt would
        move the window past the comment it is looking for. A state that means nothing was
        sent drops it, so the next attempt is a first attempt again rather than inheriting a
        search window for a post that never happened.
        """
        with self._lock:
            queue = self._read("intake", [])
            for record in queue:
                if record["intake_id"] == intake_id:
                    deliveries = record.get("ack_deliveries") or {}
                    entry = deliveries.get(key) or {}
                    now = _now()
                    if state == "attempted":
                        deliveries[key] = {"state": state, "at": now, "first_at": entry.get("first_at") or now}
                    elif state == "delivered":
                        deliveries[key] = {**entry, "state": state, "at": now}
                    else:
                        deliveries[key] = {"state": state, "at": now}
                    record["ack_deliveries"] = deliveries
                    self._write("intake", queue)
                    return record
            return None

    def intake_delivery_get(self, record: dict[str, Any], key: str) -> dict[str, Any]:
        return ((record.get("ack_deliveries") or {}).get(key) or {})

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

    def intake_fail(
        self,
        intake_id: str,
        reason: str,
        *,
        error_code: str = "dispatch_failure",
        max_retries: int | None = None,
    ) -> dict[str, Any] | None:
        """Record an execution/dispatch failure against an intake item.

        Increments retry_count. If retry_count exceeds max_retries, moves the item
        to terminal 'dead_letter' state (DLQ) and records dead_letter_at and dead_letter_reason.
        Otherwise resets state to 'queued' so it can be retried.
        """
        with self._lock:
            queue = self._read("intake", [])
            for record in queue:
                if record["intake_id"] == intake_id:
                    retries = record.get("retry_count", 0) + 1
                    record["retry_count"] = retries
                    effective_max = max_retries if max_retries is not None else record.get("max_retries", 3)
                    failure_entry = {
                        "attempt": retries,
                        "reason": reason,
                        "error_code": error_code,
                        "at": _now(),
                    }
                    record.setdefault("failures", []).append(failure_entry)
                    if retries >= effective_max:
                        record["state"] = "dead_letter"
                        record["dead_letter_at"] = _now()
                        record["dead_letter_reason"] = reason
                        record["dead_letter_error_code"] = error_code
                    else:
                        record["state"] = "queued"
                        record["claimed_at"] = None
                    self._write("intake", queue)
                    return record
            return None

    def intake_dlq_list(self, origin: str | None = None) -> list[dict[str, Any]]:
        """List items currently in dead-letter queue (state == 'dead_letter')."""
        with self._lock:
            queue = self._read("intake", [])
            items = [r for r in queue if r.get("state") == "dead_letter"]
            if origin:
                items = [r for r in items if r.get("origin") == origin]
            return items

    def intake_dlq_replay(self, intake_id: str, *, reset_retries: bool = True) -> dict[str, Any] | None:
        """Replay a dead-lettered item back into the active intake queue ('queued')."""
        with self._lock:
            queue = self._read("intake", [])
            for record in queue:
                if record["intake_id"] == intake_id and record.get("state") == "dead_letter":
                    record["state"] = "queued"
                    record["replayed_at"] = _now()
                    record["claimed_at"] = None
                    if reset_retries:
                        record["retry_count"] = 0
                    self._write("intake", queue)
                    return record
            return None

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

    def task_graphs(self) -> dict[str, Any]:
        """Return all local federated task graphs (REQ-FED-004)."""
        with self._lock:
            return self._read("task_graphs", {})

    def get_task_graph(self, graph_id: str) -> dict[str, Any] | None:
        """Get a specific task graph by graph_id (REQ-FED-004)."""
        with self._lock:
            graphs = self.task_graphs()
            return graphs.get(graph_id)

    def upsert_task_graph(
        self,
        graph_id: str,
        title: str,
        nodes: dict[str, Any],
        version: int = 1,
        vector_clock: dict[str, int] | None = None,
        origin_desk: str | None = None,
        updated_at: float | None = None,
    ) -> dict[str, Any]:
        """Create or update a local task graph (REQ-FED-004)."""
        with self._lock:
            graphs = self.task_graphs()
            now = _now() if updated_at is None else updated_at
            vc = dict(vector_clock or {})
            if origin_desk:
                vc[origin_desk] = max(vc.get(origin_desk, 0), version)

            record = {
                "graph_id": graph_id,
                "title": title,
                "nodes": nodes,
                "version": version,
                "vector_clock": vc,
                "origin_desk": origin_desk,
                "updated_at": now,
            }
            graphs[graph_id] = record
            self._write("task_graphs", graphs)
            return record

    def merge_task_graph(
        self,
        remote_graph: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        """Merge a remote task graph with deterministic conflict resolution (REQ-FED-004).

        Resolution rules:
        1. Causality check via Vector Clocks:
           - If remote strictly dominates local -> Remote wins.
           - If local strictly dominates remote -> Local wins (noop).
        2. Concurrent updates (divergent vector clocks):
           - Highest version wins.
           - Tie-break: Highest updated_at timestamp wins.
           - Tie-break: Lexicographical comparison of origin_desk (deterministic).
        - For nodes within graph: Merge node states deterministically:
           - If remote node has higher updated_at / version or local node doesn't exist, adopt remote node.
           - Union nodes to prevent state loss across partitioned desks.

        Returns (merged_graph, resolution_status) where status is:
        'adopted_remote', 'kept_local', or 'merged_concurrent'.
        """
        graph_id = remote_graph.get("graph_id")
        if not graph_id:
            raise ValueError("remote_graph missing 'graph_id'")

        with self._lock:
            graphs = self.task_graphs()
            local_graph = graphs.get(graph_id)
            if not local_graph:
                graphs[graph_id] = remote_graph
                self._write("task_graphs", graphs)
                return remote_graph, "adopted_remote"

            local_vc = dict(local_graph.get("vector_clock") or {})
            remote_vc = dict(remote_graph.get("vector_clock") or {})

            # Check vector clock dominance
            all_desks = set(local_vc.keys()) | set(remote_vc.keys())
            local_dominates = True
            remote_dominates = True
            for d in all_desks:
                l_v = local_vc.get(d, 0)
                r_v = remote_vc.get(d, 0)
                if l_v < r_v:
                    local_dominates = False
                if r_v < l_v:
                    remote_dominates = False

            if remote_dominates and not local_dominates:
                graphs[graph_id] = remote_graph
                self._write("task_graphs", graphs)
                return remote_graph, "adopted_remote"

            if local_dominates and not remote_dominates:
                return local_graph, "kept_local"

            # Concurrent updates: merge nodes deterministically and union vector clocks
            merged_vc = {d: max(local_vc.get(d, 0), remote_vc.get(d, 0)) for d in all_desks}
            merged_nodes = dict(local_graph.get("nodes") or {})
            for node_id, remote_node in (remote_graph.get("nodes") or {}).items():
                if node_id not in merged_nodes:
                    merged_nodes[node_id] = remote_node
                else:
                    local_node = merged_nodes[node_id]
                    # Deterministic node conflict resolution: latest updated_at wins, then status precedence
                    l_ts = local_node.get("updated_at", 0)
                    r_ts = remote_node.get("updated_at", 0)
                    if r_ts > l_ts:
                        merged_nodes[node_id] = remote_node
                    elif r_ts == l_ts:
                        # Tie break on state progression: done > in_progress > open
                        state_weights = {"done": 3, "in_progress": 2, "open": 1}
                        l_w = state_weights.get(local_node.get("status", ""), 0)
                        r_w = state_weights.get(remote_node.get("status", ""), 0)
                        if r_w > l_w:
                            merged_nodes[node_id] = remote_node

            merged_version = max(local_graph.get("version", 1), remote_graph.get("version", 1)) + 1
            merged_updated_at = max(local_graph.get("updated_at", 0), remote_graph.get("updated_at", 0), _now())
            origin_desk = local_graph.get("origin_desk") or remote_graph.get("origin_desk")

            merged_record = {
                "graph_id": graph_id,
                "title": remote_graph.get("title") or local_graph.get("title", ""),
                "nodes": merged_nodes,
                "version": merged_version,
                "vector_clock": merged_vc,
                "origin_desk": origin_desk,
                "updated_at": merged_updated_at,
            }
            graphs[graph_id] = merged_record
            self._write("task_graphs", graphs)
            return merged_record, "merged_concurrent"

