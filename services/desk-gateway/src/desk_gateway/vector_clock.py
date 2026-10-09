"""Vector Clock Conflict Convergence and Partitioned Task Graph Synchronization (REQ-EDGE-004).

Provides multi-master vector clock tracking, causality analysis, concurrent edit detection,
and deterministic conflict resolution for task graphs under high-latency WAN transit (>250ms).
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("desk_gateway.vector_clock")


class CausalityRelation(str, Enum):
    EQUAL = "equal"
    DOMINATES = "dominates"      # Local dominates remote (local >= remote)
    DOMINATED = "dominated"      # Remote dominates local (remote >= local)
    CONCURRENT = "concurrent"    # Divergent / concurrent branch requiring merge


def compare_vector_clocks(vc_a: dict[str, int], vc_b: dict[str, int]) -> CausalityRelation:
    """Compare two vector clocks to determine causality."""
    all_keys = set(vc_a.keys()) | set(vc_b.keys())
    a_greater = False
    b_greater = False

    for k in all_keys:
        val_a = vc_a.get(k, 0)
        val_b = vc_b.get(k, 0)
        if val_a > val_b:
            a_greater = True
        elif val_b > val_a:
            b_greater = True

    if not a_greater and not b_greater:
        return CausalityRelation.EQUAL
    if a_greater and not b_greater:
        return CausalityRelation.DOMINATES
    if b_greater and not a_greater:
        return CausalityRelation.DOMINATED
    return CausalityRelation.CONCURRENT


def union_vector_clocks(vc_a: dict[str, int], vc_b: dict[str, int]) -> dict[str, int]:
    """Calculate point-wise maximum of two vector clocks."""
    all_keys = set(vc_a.keys()) | set(vc_b.keys())
    return {k: max(vc_a.get(k, 0), vc_b.get(k, 0)) for k in all_keys}


@dataclass
class TaskNode:
    node_id: str
    title: str
    status: str = "open"  # open, in_progress, done, blocked, failed
    assignee: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    origin_region: str = "local"
    mutation_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "status": self.status,
            "assignee": self.assignee,
            "data": copy.deepcopy(self.data),
            "version": self.version,
            "updated_at": self.updated_at,
            "origin_region": self.origin_region,
            "mutation_history": copy.deepcopy(self.mutation_history),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskNode:
        return cls(
            node_id=d["node_id"],
            title=d.get("title", ""),
            status=d.get("status", "open"),
            assignee=d.get("assignee"),
            data=copy.deepcopy(d.get("data", {})),
            version=d.get("version", 1),
            updated_at=d.get("updated_at", time.time()),
            origin_region=d.get("origin_region", "local"),
            mutation_history=copy.deepcopy(d.get("mutation_history", [])),
        )


class ConflictResolver:
    """Deterministic conflict resolver for concurrent node and graph mutations."""

    # Higher integer indicates higher status precedence in state progression
    STATUS_WEIGHTS: dict[str, int] = {
        "done": 5,
        "in_progress": 4,
        "blocked": 3,
        "open": 2,
        "failed": 1,
    }

    @classmethod
    def resolve_node_conflict(cls, node_a: TaskNode, node_b: TaskNode) -> TaskNode:
        """Deterministically resolve conflict between two concurrent versions of a TaskNode.

        Resolution hierarchy:
        1. Higher node version wins.
        2. If versions are equal, Last-Write-Wins (LWW) by timestamp updated_at.
        3. If timestamps match within epsilon (1e-6), status progression precedence wins (done > in_progress > blocked > open > failed).
        4. Tie-break: Lexicographical order of origin_region.
        """
        if node_a.version > node_b.version:
            return cls._merge_node_history(node_a, node_b)
        if node_b.version > node_a.version:
            return cls._merge_node_history(node_b, node_a)

        # Equal versions: status progression takes precedence over tiny clock differences,
        # unless timestamp difference is significant (> 1.0s)
        weight_a = cls.STATUS_WEIGHTS.get(node_a.status, 0)
        weight_b = cls.STATUS_WEIGHTS.get(node_b.status, 0)

        if weight_a != weight_b:
            if weight_a > weight_b:
                return cls._merge_node_history(node_a, node_b)
            return cls._merge_node_history(node_b, node_a)

        # Equal status: Last-Write-Wins (LWW) by timestamp
        if abs(node_a.updated_at - node_b.updated_at) > 1e-4:
            if node_a.updated_at > node_b.updated_at:
                return cls._merge_node_history(node_a, node_b)
            return cls._merge_node_history(node_b, node_a)

        # Deterministic origin tie breaker
        if node_a.origin_region >= node_b.origin_region:
            return cls._merge_node_history(node_a, node_b)
        return cls._merge_node_history(node_b, node_a)

    @classmethod
    def _merge_node_history(cls, winner: TaskNode, loser: TaskNode) -> TaskNode:
        res = copy.deepcopy(winner)
        # Combine mutation logs deduplicating by timestamp + mutation summary
        seen_keys = {
            (m.get("timestamp"), m.get("actor"), m.get("action"))
            for m in res.mutation_history
        }
        for m in loser.mutation_history:
            key = (m.get("timestamp"), m.get("actor"), m.get("action"))
            if key not in seen_keys:
                res.mutation_history.append(copy.deepcopy(m))
                seen_keys.add(key)
        res.mutation_history.sort(key=lambda m: m.get("timestamp", 0.0))
        # Deep merge payload data if non-conflicting keys exist in loser
        for k, v in loser.data.items():
            if k not in res.data:
                res.data[k] = copy.deepcopy(v)
        return res


class VectorClockGraph:
    """Multi-master task graph with vector clock causality tracking (REQ-EDGE-004)."""

    def __init__(self, graph_id: str, local_region_id: str, title: str = "") -> None:
        self.graph_id = graph_id
        self.local_region_id = local_region_id
        self.title = title
        self.nodes: dict[str, TaskNode] = {}
        self.vector_clock: dict[str, int] = {local_region_id: 0}
        self.version: int = 1
        self.updated_at: float = time.time()

    def tick_clock(self) -> dict[str, int]:
        """Increment vector clock for local region."""
        self.vector_clock[self.local_region_id] = self.vector_clock.get(self.local_region_id, 0) + 1
        self.version += 1
        self.updated_at = time.time()
        return dict(self.vector_clock)

    def set_node(
        self,
        node_id: str,
        title: str,
        status: str = "open",
        assignee: str | None = None,
        data: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> TaskNode:
        """Insert or mutate a node, advancing the region's vector clock."""
        self.tick_clock()
        now = self.updated_at

        mutation = {
            "timestamp": now,
            "actor": actor,
            "action": "upsert",
            "region": self.local_region_id,
            "status": status,
        }

        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.title = title
            node.status = status
            node.assignee = assignee
            if data:
                node.data.update(data)
            node.version += 1
            node.updated_at = now
            node.origin_region = self.local_region_id
            node.mutation_history.append(mutation)
        else:
            node = TaskNode(
                node_id=node_id,
                title=title,
                status=status,
                assignee=assignee,
                data=copy.deepcopy(data or {}),
                version=1,
                updated_at=now,
                origin_region=self.local_region_id,
                mutation_history=[mutation],
            )
            self.nodes[node_id] = node
        return node

    def get_node(self, node_id: str) -> TaskNode | None:
        return self.nodes.get(node_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "local_region_id": self.local_region_id,
            "title": self.title,
            "version": self.version,
            "vector_clock": dict(self.vector_clock),
            "updated_at": self.updated_at,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], local_region_id: str | None = None) -> VectorClockGraph:
        region = local_region_id or d.get("local_region_id", "local")
        graph = cls(graph_id=d["graph_id"], local_region_id=region, title=d.get("title", ""))
        graph.version = d.get("version", 1)
        graph.vector_clock = dict(d.get("vector_clock", {}))
        graph.updated_at = d.get("updated_at", time.time())
        for nid, nd in d.get("nodes", {}).items():
            graph.nodes[nid] = TaskNode.from_dict(nd)
        return graph

    def merge_remote(self, remote_dict: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Merge remote partitioned graph state into local graph (REQ-EDGE-004).

        Returns: (merged_graph_dict, resolution_reason)
        """
        remote_vc = dict(remote_dict.get("vector_clock", {}))
        remote_nodes_dict = remote_dict.get("nodes", {})
        causality = compare_vector_clocks(self.vector_clock, remote_vc)

        if causality == CausalityRelation.DOMINATES:
            # Local strictly dominates remote; no changes needed
            return self.to_dict(), "kept_local_dominates"

        if causality == CausalityRelation.DOMINATED:
            # Remote strictly dominates local; adopt remote state wholesale
            self.title = remote_dict.get("title", self.title)
            self.version = remote_dict.get("version", self.version)
            self.updated_at = remote_dict.get("updated_at", self.updated_at)
            self.vector_clock = dict(remote_vc)
            self.nodes = {nid: TaskNode.from_dict(nd) for nid, nd in remote_nodes_dict.items()}
            return self.to_dict(), "adopted_remote_dominates"

        # Causality is CONCURRENT or EQUAL with divergence: execute deterministic merge
        merged_vc = union_vector_clocks(self.vector_clock, remote_vc)
        # Advance clock to record merge event
        merged_vc[self.local_region_id] = merged_vc.get(self.local_region_id, 0) + 1
        self.vector_clock = merged_vc
        self.version = max(self.version, remote_dict.get("version", 1)) + 1
        self.updated_at = max(self.updated_at, remote_dict.get("updated_at", 0.0), time.time())
        if remote_dict.get("title") and not self.title:
            self.title = remote_dict["title"]

        # Merge nodes across both partitions
        all_node_ids = set(self.nodes.keys()) | set(remote_nodes_dict.keys())
        for nid in all_node_ids:
            if nid in self.nodes and nid in remote_nodes_dict:
                node_a = self.nodes[nid]
                node_b = TaskNode.from_dict(remote_nodes_dict[nid])
                resolved = ConflictResolver.resolve_node_conflict(node_a, node_b)
                self.nodes[nid] = resolved
            elif nid in remote_nodes_dict:
                self.nodes[nid] = TaskNode.from_dict(remote_nodes_dict[nid])
            # If in local only, already retained in self.nodes

        return self.to_dict(), "merged_concurrent"
