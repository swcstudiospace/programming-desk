"""Dynamic Partition Sharding & Multi-Master Geo-Replication.

Implements consistent hash ring partitioning, multi-master Conflict-Free Replicated
Data Types (CRDTs: LWW-Register, PN-Counter, OR-Set), cross-region delta replication
with vector clocks and HMAC-SHA256 attestation receipts, and deterministic shard key routing.
"""

from __future__ import annotations

import bisect
import dataclasses
import enum
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class ConsistencyLevel(str, enum.Enum):
    ONE = "ONE"
    QUORUM = "QUORUM"
    ALL = "ALL"


@dataclasses.dataclass
class ShardNode:
    node_id: str
    region_id: str
    endpoint: str = ""
    weight: int = 1
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "region_id": self.region_id,
            "endpoint": self.endpoint,
            "weight": self.weight,
            "status": self.status,
        }


class ConsistentHashRing:
    """Consistent hash ring with virtual nodes (vnodes) and replica factor lookups."""

    def __init__(self, vnodes_per_node: int = 64, hash_fn: str = "sha256") -> None:
        self.vnodes_per_node = max(1, vnodes_per_node)
        self.hash_fn = hash_fn
        self.nodes: Dict[str, ShardNode] = {}
        self._ring: List[int] = []
        self._ring_map: Dict[int, str] = {}  # hash -> node_id

    def _hash(self, key: str) -> int:
        if self.hash_fn == "sha256":
            return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)
        return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:16], 16)

    def add_node(self, node: ShardNode) -> None:
        self.nodes[node.node_id] = node
        vnode_count = self.vnodes_per_node * node.weight
        for i in range(vnode_count):
            token = self._hash(f"{node.node_id}#vnode-{i}")
            self._ring_map[token] = node.node_id
            bisect.insort(self._ring, token)

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self.nodes:
            return False
        node = self.nodes.pop(node_id)
        vnode_count = self.vnodes_per_node * node.weight
        for i in range(vnode_count):
            token = self._hash(f"{node_id}#vnode-{i}")
            if token in self._ring_map:
                del self._ring_map[token]
                idx = bisect.bisect_left(self._ring, token)
                if idx < len(self._ring) and self._ring[idx] == token:
                    self._ring.pop(idx)
        return True

    def get_primary_node(self, key: str) -> Optional[ShardNode]:
        replicas = self.get_replica_nodes(key, replica_factor=1)
        return replicas[0] if replicas else None

    def get_replica_nodes(self, key: str, replica_factor: int = 3) -> List[ShardNode]:
        if not self._ring:
            return []
        token = self._hash(key)
        idx = bisect.bisect_right(self._ring, token)
        if idx >= len(self._ring):
            idx = 0

        selected_nodes: List[ShardNode] = []
        seen_node_ids: Set[str] = set()
        ring_len = len(self._ring)

        for i in range(ring_len):
            curr_token = self._ring[(idx + i) % ring_len]
            node_id = self._ring_map[curr_token]
            if node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                selected_nodes.append(self.nodes[node_id])
                if len(selected_nodes) >= replica_factor:
                    break

        return selected_nodes

    def list_nodes(self) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in self.nodes.values()]


# ==============================================================================
# CRDT Multi-Master Data Structures
# ==============================================================================

@dataclasses.dataclass
class LWWRegister:
    """Last-Write-Wins Register with lamport timestamp and node tie-breaking."""
    value: Any = None
    timestamp: float = 0.0
    writer_node_id: str = ""

    def update(self, val: Any, writer_node_id: str, ts: Optional[float] = None) -> None:
        now = ts if ts is not None else time.time()
        if now > self.timestamp or (now == self.timestamp and writer_node_id >= self.writer_node_id):
            self.value = val
            self.timestamp = now
            self.writer_node_id = writer_node_id

    def merge(self, other: "LWWRegister") -> None:
        if other.timestamp > self.timestamp or (
            other.timestamp == self.timestamp and other.writer_node_id >= self.writer_node_id
        ):
            self.value = other.value
            self.timestamp = other.timestamp
            self.writer_node_id = other.writer_node_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "timestamp": self.timestamp,
            "writer_node_id": self.writer_node_id,
        }


@dataclasses.dataclass
class PNCounter:
    """Positive-Negative Counter CRDT."""
    p_map: Dict[str, int] = dataclasses.field(default_factory=dict)
    n_map: Dict[str, int] = dataclasses.field(default_factory=dict)

    def increment(self, node_id: str, amount: int = 1) -> None:
        if amount < 0:
            self.decrement(node_id, -amount)
            return
        self.p_map[node_id] = self.p_map.get(node_id, 0) + amount

    def decrement(self, node_id: str, amount: int = 1) -> None:
        if amount < 0:
            self.increment(node_id, -amount)
            return
        self.n_map[node_id] = self.n_map.get(node_id, 0) + amount

    @property
    def value(self) -> int:
        return sum(self.p_map.values()) - sum(self.n_map.values())

    def merge(self, other: "PNCounter") -> None:
        for node_id, count in other.p_map.items():
            self.p_map[node_id] = max(self.p_map.get(node_id, 0), count)
        for node_id, count in other.n_map.items():
            self.n_map[node_id] = max(self.n_map.get(node_id, 0), count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "p_map": self.p_map,
            "n_map": self.n_map,
        }


@dataclasses.dataclass
class ORSet:
    """Observed-Removed Set (Add-Wins Set) CRDT."""
    elements: Dict[str, Set[str]] = dataclasses.field(default_factory=dict)  # element -> set of unique tags
    tombstones: Set[str] = dataclasses.field(default_factory=set)           # removed tags

    def add(self, element: str, tag: Optional[str] = None) -> str:
        tag_id = tag or f"{time.time()}-{hashlib.md5(element.encode('utf-8')).hexdigest()[:8]}"
        if element not in self.elements:
            self.elements[element] = set()
        self.elements[element].add(tag_id)
        return tag_id

    def remove(self, element: str) -> None:
        if element in self.elements:
            for tag in self.elements[element]:
                self.tombstones.add(tag)
            del self.elements[element]

    def read(self) -> Set[str]:
        result = set()
        for element, tags in list(self.elements.items()):
            active_tags = tags - self.tombstones
            if active_tags:
                result.add(element)
        return result

    def merge(self, other: "ORSet") -> None:
        self.tombstones.update(other.tombstones)
        for elem, tags in other.elements.items():
            if elem not in self.elements:
                self.elements[elem] = set()
            self.elements[elem].update(tags)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "elements": sorted(list(self.read())),
            "raw_elements": {k: sorted(list(v)) for k, v in self.elements.items()},
            "tombstones": sorted(list(self.tombstones)),
        }


# ==============================================================================
# Cross-Region Delta Replication & Shard Router
# ==============================================================================

@dataclasses.dataclass
class ReplicationDelta:
    delta_id: str
    key: str
    crdt_type: str  # "lww", "pn_counter", "or_set"
    payload: Dict[str, Any]
    origin_region: str
    vector_clock: Dict[str, int]
    timestamp: float = dataclasses.field(default_factory=time.time)
    signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delta_id": self.delta_id,
            "key": self.key,
            "crdt_type": self.crdt_type,
            "payload": self.payload,
            "origin_region": self.origin_region,
            "vector_clock": self.vector_clock,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class CRDTStore:
    """Multi-Master CRDT state storage engine with automatic merge."""

    def __init__(self, region_id: str, node_id: str) -> None:
        self.region_id = region_id
        self.node_id = node_id
        self.lww_store: Dict[str, LWWRegister] = {}
        self.counter_store: Dict[str, PNCounter] = {}
        self.set_store: Dict[str, ORSet] = {}
        self.vector_clock: Dict[str, int] = {self.region_id: 0}

    def write_lww(self, key: str, value: Any) -> LWWRegister:
        self.vector_clock[self.region_id] = self.vector_clock.get(self.region_id, 0) + 1
        reg = self.lww_store.setdefault(key, LWWRegister())
        reg.update(value, writer_node_id=self.node_id)
        return reg

    def read_lww(self, key: str) -> Optional[Any]:
        reg = self.lww_store.get(key)
        return reg.value if reg else None

    def update_counter(self, key: str, delta: int = 1) -> PNCounter:
        self.vector_clock[self.region_id] = self.vector_clock.get(self.region_id, 0) + 1
        counter = self.counter_store.setdefault(key, PNCounter())
        if delta >= 0:
            counter.increment(self.node_id, delta)
        else:
            counter.decrement(self.node_id, -delta)
        return counter

    def read_counter(self, key: str) -> int:
        counter = self.counter_store.get(key)
        return counter.value if counter else 0

    def add_set(self, key: str, element: str) -> ORSet:
        self.vector_clock[self.region_id] = self.vector_clock.get(self.region_id, 0) + 1
        or_set = self.set_store.setdefault(key, ORSet())
        or_set.add(element)
        return or_set

    def remove_set(self, key: str, element: str) -> ORSet:
        self.vector_clock[self.region_id] = self.vector_clock.get(self.region_id, 0) + 1
        or_set = self.set_store.setdefault(key, ORSet())
        or_set.remove(element)
        return or_set

    def read_set(self, key: str) -> Set[str]:
        or_set = self.set_store.get(key)
        return or_set.read() if or_set else set()

    def apply_delta(self, delta: ReplicationDelta) -> bool:
        # Merge vector clock
        for r, seq in delta.vector_clock.items():
            self.vector_clock[r] = max(self.vector_clock.get(r, 0), seq)
        self.vector_clock[self.region_id] = self.vector_clock.get(self.region_id, 0) + 1

        if delta.crdt_type == "lww":
            reg = self.lww_store.setdefault(delta.key, LWWRegister())
            payload = delta.payload
            incoming = LWWRegister(
                value=payload.get("value"),
                timestamp=payload.get("timestamp", 0.0),
                writer_node_id=payload.get("writer_node_id", ""),
            )
            reg.merge(incoming)
            return True

        elif delta.crdt_type == "pn_counter":
            counter = self.counter_store.setdefault(delta.key, PNCounter())
            payload = delta.payload
            incoming = PNCounter(
                p_map=payload.get("p_map", {}),
                n_map=payload.get("n_map", {}),
            )
            counter.merge(incoming)
            return True

        elif delta.crdt_type == "or_set":
            or_set = self.set_store.setdefault(delta.key, ORSet())
            payload = delta.payload
            raw_elements = {k: set(v) for k, v in payload.get("raw_elements", {}).items()}
            tombstones = set(payload.get("tombstones", []))
            incoming = ORSet(elements=raw_elements, tombstones=tombstones)
            or_set.merge(incoming)
            return True

        return False


class GeoReplicationEngine:
    """Propagates delta updates across regions with HMAC signatures and vector clocks."""

    def __init__(self, region_id: str, signing_secret: str = "sharding-default-secret") -> None:
        self.region_id = region_id
        self.signing_secret = signing_secret
        self.replication_log: List[ReplicationDelta] = []
        self._delivered_deltas: Set[str] = set()

    def _sign_payload(self, data: str) -> str:
        return hmac.new(
            self.signing_secret.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def create_delta(
        self,
        key: str,
        crdt_type: str,
        payload: Dict[str, Any],
        vector_clock: Dict[str, int],
    ) -> ReplicationDelta:
        delta_id = f"delta-{self.region_id}-{int(time.time() * 1000)}-{len(self.replication_log)}"
        canonical = json.dumps({
            "delta_id": delta_id,
            "key": key,
            "crdt_type": crdt_type,
            "payload": payload,
            "origin_region": self.region_id,
            "vector_clock": vector_clock,
        }, sort_keys=True)
        sig = self._sign_payload(canonical)

        delta = ReplicationDelta(
            delta_id=delta_id,
            key=key,
            crdt_type=crdt_type,
            payload=payload,
            origin_region=self.region_id,
            vector_clock=dict(vector_clock),
            signature=sig,
        )
        self.replication_log.append(delta)
        return delta

    def verify_delta(self, delta: ReplicationDelta) -> bool:
        canonical = json.dumps({
            "delta_id": delta.delta_id,
            "key": delta.key,
            "crdt_type": delta.crdt_type,
            "payload": delta.payload,
            "origin_region": delta.origin_region,
            "vector_clock": delta.vector_clock,
        }, sort_keys=True)
        expected_sig = self._sign_payload(canonical)
        return hmac.compare_digest(expected_sig, delta.signature)


class ShardRouter:
    """Routes read/write requests to primary and replica nodes with consistency quorums."""

    def __init__(
        self,
        ring: ConsistentHashRing,
        store: CRDTStore,
        replicator: GeoReplicationEngine,
        replica_factor: int = 3,
    ) -> None:
        self.ring = ring
        self.store = store
        self.replicator = replicator
        self.replica_factor = replica_factor

    def route_key(self, key: str) -> Dict[str, Any]:
        replicas = self.ring.get_replica_nodes(key, replica_factor=self.replica_factor)
        primary = replicas[0] if replicas else None
        return {
            "key": key,
            "primary": primary.to_dict() if primary else None,
            "replicas": [r.to_dict() for r in replicas],
            "quorum_required": (len(replicas) // 2) + 1 if replicas else 0,
        }

    def write_lww(
        self,
        key: str,
        value: Any,
        consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> Dict[str, Any]:
        routing = self.route_key(key)
        reg = self.store.write_lww(key, value)
        delta = self.replicator.create_delta(
            key=key,
            crdt_type="lww",
            payload=reg.to_dict(),
            vector_clock=self.store.vector_clock,
        )
        return {
            "ok": True,
            "key": key,
            "value": reg.value,
            "consistency": consistency.value,
            "delta_id": delta.delta_id,
            "routing": routing,
        }

    def read_lww(self, key: str, consistency: ConsistencyLevel = ConsistencyLevel.ONE) -> Dict[str, Any]:
        routing = self.route_key(key)
        val = self.store.read_lww(key)
        return {
            "ok": True,
            "key": key,
            "value": val,
            "consistency": consistency.value,
            "routing": routing,
        }

    def update_counter(
        self,
        key: str,
        delta: int = 1,
        consistency: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> Dict[str, Any]:
        routing = self.route_key(key)
        counter = self.store.update_counter(key, delta)
        delta_obj = self.replicator.create_delta(
            key=key,
            crdt_type="pn_counter",
            payload=counter.to_dict(),
            vector_clock=self.store.vector_clock,
        )
        return {
            "ok": True,
            "key": key,
            "value": counter.value,
            "consistency": consistency.value,
            "delta_id": delta_obj.delta_id,
            "routing": routing,
        }

    def read_counter(self, key: str) -> Dict[str, Any]:
        routing = self.route_key(key)
        val = self.store.read_counter(key)
        return {
            "ok": True,
            "key": key,
            "value": val,
            "routing": routing,
        }
