"""Distributed Sensory Memory Graph & Cross-Modal Embeddings Engine.

Implements:
- REQ-GRAPH-001: Knowledge graph linkage mapping multi-modal artifacts, desk ledger events,
  and tool execution traces into an integrated property graph.
- REQ-GRAPH-002: Cross-modal semantic search engine with cosine nearest-neighbor vector retrieval
  across heterogeneous embeddings (text, code, image, event, tool_trace).
- REQ-GRAPH-003: Temporal graph decay and attention weighting prioritizing recent and high-relevance nodes.
- REQ-GRAPH-004: Graph partitioning and edge-node caching for low-latency graph traversals.
- REQ-GRAPH-005: Cryptographic graph state commitment and Merkle verification receipts.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import hmac
import json
import math
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class ModalType(str, Enum):
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    EVENT = "event"
    TOOL_TRACE = "tool_trace"


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two numeric vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclasses.dataclass
class GraphNode:
    """Node in the multi-modal sensory memory graph."""
    node_id: str
    modality: ModalType
    label: str
    content: str
    embedding: List[float] = dataclasses.field(default_factory=list)
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    partition_id: str = "default"
    attention_score: float = 1.0
    created_at: float = dataclasses.field(default_factory=time.time)
    last_accessed_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "modality": self.modality.value,
            "label": self.label,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "partition_id": self.partition_id,
            "attention_score": self.attention_score,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
        }

    def compute_hash(self) -> str:
        serialized = json.dumps(
            {
                "node_id": self.node_id,
                "modality": self.modality.value,
                "label": self.label,
                "content": self.content,
                "embedding": self.embedding,
                "metadata": self.metadata,
                "partition_id": self.partition_id,
                "attention_score": self.attention_score,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclasses.dataclass
class GraphEdge:
    """Directed, attributed relationship between two memory graph nodes."""
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    created_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    def compute_hash(self) -> str:
        serialized = json.dumps(
            {
                "edge_id": self.edge_id,
                "source_id": self.source_id,
                "target_id": self.target_id,
                "relation": self.relation,
                "weight": self.weight,
                "metadata": self.metadata,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclasses.dataclass
class GraphCommitReceipt:
    """Cryptographic commitment receipt over memory graph state."""
    commit_id: str
    state_root: str
    node_count: int
    edge_count: int
    timestamp: float
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_id": self.commit_id,
            "state_root": self.state_root,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


@dataclasses.dataclass
class SemanticSearchResult:
    """Result of cross-modal semantic query with temporal decay."""
    node: GraphNode
    raw_similarity: float
    decayed_score: float
    temporal_factor: float


class SensoryMemoryGraphEngine:
    """Distributed Sensory Memory Graph Engine managing cross-modal relationships,

    semantic search, temporal decay, partitioned caching, and cryptographic verification.
    """

    def __init__(
        self,
        signing_secret: str = "sensory-memory-graph-secret",  # pragma: allowlist secret
        decay_half_life_seconds: float = 86400.0,  # 24 hours
        traversal_cache_size: int = 1000,
    ) -> None:
        self.signing_secret = signing_secret
        self.decay_half_life_seconds = max(decay_half_life_seconds, 1.0)
        self.traversal_cache_size = traversal_cache_size

        # In-memory graph storage
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}

        # Adjacency indexes: source_id -> list[edge_id], target_id -> list[edge_id]
        self._out_edges: Dict[str, List[str]] = collections.defaultdict(list)
        self._in_edges: Dict[str, List[str]] = collections.defaultdict(list)

        # Partition indexes: partition_id -> set[node_id]
        self.partitions: Dict[str, Set[str]] = collections.defaultdict(set)

        # Traversal LRU cache: (start_node_id, max_depth, partition_id) -> (traversal_result, cached_at)
        self._traversal_cache: collections.OrderedDict[Tuple[str, int, Optional[str]], Tuple[Dict[str, Any], float]] = collections.OrderedDict()

        # Commitment log
        self.commitments: Dict[str, GraphCommitReceipt] = {}

    def add_node(
        self,
        node_id: str,
        modality: ModalType | str,
        label: str,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        partition_id: str = "default",
        attention_score: float = 1.0,
    ) -> GraphNode:
        """Create or update a node in the property graph (REQ-GRAPH-001)."""
        if isinstance(modality, str):
            modality = ModalType(modality.lower())

        node = GraphNode(
            node_id=node_id,
            modality=modality,
            label=label,
            content=content,
            embedding=embedding or [],
            metadata=metadata or {},
            partition_id=partition_id,
            attention_score=max(attention_score, 0.0),
            created_at=time.time(),
            last_accessed_at=time.time(),
        )
        self.nodes[node_id] = node
        self.partitions[partition_id].add(node_id)
        self._invalidate_traversal_cache()
        return node

    def add_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        relation: str,
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """Link two nodes with a directed, attributed relationship (REQ-GRAPH-001)."""
        if source_id not in self.nodes:
            raise KeyError(f"Source node '{source_id}' does not exist")
        if target_id not in self.nodes:
            raise KeyError(f"Target node '{target_id}' does not exist")

        edge = GraphEdge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=max(weight, 0.0),
            metadata=metadata or {},
            created_at=time.time(),
        )
        self.edges[edge_id] = edge
        self._out_edges[source_id].append(edge_id)
        self._in_edges[target_id].append(edge_id)
        self._invalidate_traversal_cache()
        return edge

    def link_ledger_event_to_artifact(
        self,
        event_id: str,
        artifact_id: str,
        relation: str = "PRODUCED_ARTIFACT",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """Convenience method to link ledger events with multimodal artifacts (REQ-GRAPH-001)."""
        edge_id = f"edge_link_{event_id}_{artifact_id}"
        return self.add_edge(
            edge_id=edge_id,
            source_id=event_id,
            target_id=artifact_id,
            relation=relation,
            metadata=metadata or {},
        )

    def link_tool_trace_to_event(
        self,
        tool_trace_id: str,
        event_id: str,
        relation: str = "TRIGGERED_BY",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GraphEdge:
        """Convenience method to link tool execution traces to ledger events (REQ-GRAPH-001)."""
        edge_id = f"edge_link_{tool_trace_id}_{event_id}"
        return self.add_edge(
            edge_id=edge_id,
            source_id=tool_trace_id,
            target_id=event_id,
            relation=relation,
            metadata=metadata or {},
        )

    def get_temporal_decay_factor(self, timestamp: float, current_time: Optional[float] = None) -> float:
        """Compute exponential temporal decay factor: e^(-lambda * dt) (REQ-GRAPH-003)."""
        now = current_time if current_time is not None else time.time()
        dt = max(0.0, now - timestamp)
        # half-life T_1/2: lambda = ln(2) / T_1/2
        decay_lambda = math.log(2.0) / self.decay_half_life_seconds
        return math.exp(-decay_lambda * dt)

    def search_semantic(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        modality: Optional[ModalType | str] = None,
        partition_id: Optional[str] = None,
        min_score: float = 0.0,
        apply_decay: bool = True,
        current_time: Optional[float] = None,
    ) -> List[SemanticSearchResult]:
        """Cross-modal semantic search engine with cosine nearest-neighbor retrieval,

        attention score weighting, and temporal decay (REQ-GRAPH-002, REQ-GRAPH-003).
        """
        if isinstance(modality, str):
            modality = ModalType(modality.lower())

        now = current_time if current_time is not None else time.time()
        results: List[SemanticSearchResult] = []

        candidate_ids = self.partitions[partition_id] if partition_id else self.nodes.keys()

        for nid in candidate_ids:
            node = self.nodes.get(nid)
            if not node:
                continue
            if modality and node.modality != modality:
                continue
            if not node.embedding or len(node.embedding) != len(query_embedding):
                continue

            sim = cosine_similarity(query_embedding, node.embedding)
            if sim < 0.0:
                sim = 0.0

            if apply_decay:
                decay_factor = self.get_temporal_decay_factor(node.created_at, current_time=now)
                decayed = sim * decay_factor * node.attention_score
            else:
                decay_factor = 1.0
                decayed = sim * node.attention_score

            if decayed >= min_score:
                node.last_accessed_at = now
                results.append(
                    SemanticSearchResult(
                        node=node,
                        raw_similarity=sim,
                        decayed_score=decayed,
                        temporal_factor=decay_factor,
                    )
                )

        # Sort descending by decayed score
        results.sort(key=lambda res: res.decayed_score, reverse=True)
        return results[:top_k]

    def traverse(
        self,
        start_node_id: str,
        max_depth: int = 2,
        partition_id: Optional[str] = None,
        direction: str = "out",  # "out", "in", "both"
    ) -> Dict[str, Any]:
        """Partitioned subgraph traversal with edge-node caching (REQ-GRAPH-004)."""
        cache_key = (start_node_id, max_depth, partition_id)
        if cache_key in self._traversal_cache:
            entry, cached_at = self._traversal_cache[cache_key]
            # Move to end for LRU
            self._traversal_cache.move_to_end(cache_key)
            return entry

        if start_node_id not in self.nodes:
            raise KeyError(f"Node '{start_node_id}' not found")

        visited_nodes: Set[str] = set()
        visited_edges: Set[str] = set()
        queue: collections.deque[Tuple[str, int]] = collections.deque([(start_node_id, 0)])

        while queue:
            curr_id, depth = queue.popleft()
            if curr_id in visited_nodes:
                continue
            visited_nodes.add(curr_id)

            if depth >= max_depth:
                continue

            # Outgoing edges
            if direction in ("out", "both"):
                for eid in self._out_edges.get(curr_id, []):
                    edge = self.edges.get(eid)
                    if not edge:
                        continue
                    target_node = self.nodes.get(edge.target_id)
                    if partition_id and target_node and target_node.partition_id != partition_id:
                        continue
                    visited_edges.add(eid)
                    if edge.target_id not in visited_nodes:
                        queue.append((edge.target_id, depth + 1))

            # Incoming edges
            if direction in ("in", "both"):
                for eid in self._in_edges.get(curr_id, []):
                    edge = self.edges.get(eid)
                    if not edge:
                        continue
                    source_node = self.nodes.get(edge.source_id)
                    if partition_id and source_node and source_node.partition_id != partition_id:
                        continue
                    visited_edges.add(eid)
                    if edge.source_id not in visited_nodes:
                        queue.append((edge.source_id, depth + 1))

        nodes_data = [self.nodes[nid].to_dict() for nid in visited_nodes if nid in self.nodes]
        edges_data = [self.edges[eid].to_dict() for eid in visited_edges if eid in self.edges]

        res = {
            "start_node_id": start_node_id,
            "max_depth": max_depth,
            "partition_id": partition_id,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
            "nodes": nodes_data,
            "edges": edges_data,
        }

        self._put_traversal_cache(cache_key, res)
        return res

    def _put_traversal_cache(self, key: Tuple[str, int, Optional[str]], value: Dict[str, Any]) -> None:
        if len(self._traversal_cache) >= self.traversal_cache_size:
            self._traversal_cache.popitem(last=False)
        self._traversal_cache[key] = (value, time.time())

    def _invalidate_traversal_cache(self) -> None:
        self._traversal_cache.clear()

    def compute_state_root(self) -> str:
        """Compute deterministic Merkle / SHA-256 state root over sorted nodes and edges (REQ-GRAPH-005)."""
        node_hashes = [self.nodes[nid].compute_hash() for nid in sorted(self.nodes.keys())]
        edge_hashes = [self.edges[eid].compute_hash() for eid in sorted(self.edges.keys())]

        combined = {
            "nodes_hash": hashlib.sha256("".join(node_hashes).encode("utf-8")).hexdigest(),
            "edges_hash": hashlib.sha256("".join(edge_hashes).encode("utf-8")).hexdigest(),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }
        return hashlib.sha256(json.dumps(combined, sort_keys=True).encode("utf-8")).hexdigest()

    def commit_state(self, commit_id: Optional[str] = None) -> GraphCommitReceipt:
        """Generate cryptographic state commitment and Merkle verification receipt (REQ-GRAPH-005)."""
        cid = commit_id or f"commit_{int(time.time()*1000)}"
        state_root = self.compute_state_root()
        now = time.time()

        sign_payload = f"{cid}:{state_root}:{len(self.nodes)}:{len(self.edges)}:{now}".encode("utf-8")
        signature = hmac.new(self.signing_secret.encode("utf-8"), sign_payload, hashlib.sha256).hexdigest()

        receipt = GraphCommitReceipt(
            commit_id=cid,
            state_root=state_root,
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            timestamp=now,
            signature=signature,
        )
        self.commitments[cid] = receipt
        return receipt

    def verify_commitment(self, receipt: GraphCommitReceipt) -> bool:
        """Cryptographically verify a state commitment receipt against signing secret (REQ-GRAPH-005)."""
        sign_payload = f"{receipt.commit_id}:{receipt.state_root}:{receipt.node_count}:{receipt.edge_count}:{receipt.timestamp}".encode("utf-8")
        expected_sig = hmac.new(self.signing_secret.encode("utf-8"), sign_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(receipt.signature, expected_sig)
