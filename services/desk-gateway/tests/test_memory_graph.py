"""Unit and integration tests for Multi-Modal Sensory Memory Graph & Cross-Modal Embeddings (Phase 30)."""

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.memory_graph import (
    SensoryMemoryGraphEngine,
    ModalType,
    GraphNode,
    GraphEdge,
    cosine_similarity,
)
from desk_gateway.server import build_app


def test_cosine_similarity():
    # Identical vectors
    assert abs(cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) - 1.0) < 1e-6
    # Orthogonal vectors
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-6
    # Zero vector
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
    # Mismatched length
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_memory_graph_node_and_edge_linkage():
    engine = SensoryMemoryGraphEngine()

    # REQ-GRAPH-001: Add multimodal artifact, desk ledger event, and tool trace
    node_event = engine.add_node(
        node_id="event-101",
        modality=ModalType.EVENT,
        label="PR Merged Event",
        content="Pull request #42 merged to main branch",
        embedding=[0.8, 0.2, 0.1],
        metadata={"seat": "lead", "tx": "0xabc"},
    )
    node_artifact = engine.add_node(
        node_id="artifact-202",
        modality=ModalType.IMAGE,
        label="Architecture Diagram",
        content="System component topology render",
        embedding=[0.75, 0.25, 0.05],
        metadata={"format": "png", "bytes": 102400},
    )
    node_trace = engine.add_node(
        node_id="trace-303",
        modality=ModalType.TOOL_TRACE,
        label="Docker Build Execution",
        content="docker build -t app:v1 .",
        embedding=[0.1, 0.9, 0.3],
        metadata={"exit_code": 0},
    )

    assert node_event.node_id == "event-101"
    assert node_artifact.modality == ModalType.IMAGE
    assert len(engine.nodes) == 3

    # Link event to artifact
    edge_prod = engine.link_ledger_event_to_artifact("event-101", "artifact-202")
    assert edge_prod.source_id == "event-101"
    assert edge_prod.target_id == "artifact-202"
    assert edge_prod.relation == "PRODUCED_ARTIFACT"

    # Link trace to event
    edge_tr = engine.link_tool_trace_to_event("trace-303", "event-101")
    assert edge_tr.source_id == "trace-303"
    assert edge_tr.target_id == "event-101"
    assert edge_tr.relation == "TRIGGERED_BY"

    assert len(engine.edges) == 2


def test_cross_modal_semantic_search_with_decay():
    engine = SensoryMemoryGraphEngine(decay_half_life_seconds=100.0)

    # REQ-GRAPH-002 & REQ-GRAPH-003: cross-modal search and temporal decay
    t0 = 1000.0
    # Node 1: Code node matching query
    n1 = engine.add_node(
        node_id="code-1",
        modality=ModalType.CODE,
        label="Auth Token Validator",
        content="def validate_token(t): return True",
        embedding=[1.0, 0.0, 0.0],
    )
    n1.created_at = t0

    # Node 2: Image digest node matching query, but created earlier
    n2 = engine.add_node(
        node_id="image-1",
        modality=ModalType.IMAGE,
        label="Token UI Flow Screenshot",
        content="Screenshot showing token dialog",
        embedding=[0.9, 0.1, 0.0],
    )
    n2.created_at = t0 - 100.0  # 1 half-life older

    # Query embedding aligned with [1.0, 0.0, 0.0]
    query = [1.0, 0.0, 0.0]

    # At t0:
    results_t0 = engine.search_semantic(query, top_k=5, current_time=t0, apply_decay=True)
    assert len(results_t0) == 2
    assert results_t0[0].node.node_id == "code-1"
    assert results_t0[0].temporal_factor == 1.0
    # n2 has decayed by approx 50%
    assert results_t0[1].node.node_id == "image-1"
    assert abs(results_t0[1].temporal_factor - 0.5) < 0.01

    # Search with modality filter
    code_only = engine.search_semantic(query, modality=ModalType.CODE, current_time=t0)
    assert len(code_only) == 1
    assert code_only[0].node.node_id == "code-1"


def test_subgraph_traversal_and_caching():
    engine = SensoryMemoryGraphEngine()

    # Build a linear chain: A -> B -> C -> D
    for char in ["A", "B", "C", "D"]:
        engine.add_node(node_id=char, modality=ModalType.TEXT, label=f"Node {char}", content=f"Content {char}")

    engine.add_edge(edge_id="e_ab", source_id="A", target_id="B", relation="NEXT")
    engine.add_edge(edge_id="e_bc", source_id="B", target_id="C", relation="NEXT")
    engine.add_edge(edge_id="e_cd", source_id="C", target_id="D", relation="NEXT")

    # Traverse depth 1 from A
    trav_d1 = engine.traverse(start_node_id="A", max_depth=1)
    node_ids_d1 = {n["node_id"] for n in trav_d1["nodes"]}
    assert node_ids_d1 == {"A", "B"}

    # Traverse depth 2 from A
    trav_d2 = engine.traverse(start_node_id="A", max_depth=2)
    node_ids_d2 = {n["node_id"] for n in trav_d2["nodes"]}
    assert node_ids_d2 == {"A", "B", "C"}

    # Second traversal should hit LRU cache
    assert ("A", 2, None) in engine._traversal_cache
    trav_d2_cached = engine.traverse(start_node_id="A", max_depth=2)
    assert trav_d2_cached["node_count"] == 3


def test_cryptographic_state_commitment():
    engine = SensoryMemoryGraphEngine(signing_secret="super-secure-test-secret")

    engine.add_node(node_id="n1", modality=ModalType.TEXT, label="L1", content="C1")
    engine.add_node(node_id="n2", modality=ModalType.CODE, label="L2", content="C2")
    engine.add_edge(edge_id="e1", source_id="n1", target_id="n2", relation="CALLS")

    receipt = engine.commit_state(commit_id="commit-alpha")
    assert receipt.commit_id == "commit-alpha"
    assert receipt.node_count == 2
    assert receipt.edge_count == 1
    assert len(receipt.state_root) == 64
    assert len(receipt.signature) == 64

    # Verify receipt signature
    assert engine.verify_commitment(receipt) is True

    # Tamper with receipt
    receipt.state_root = "0" * 64
    assert engine.verify_commitment(receipt) is False


def test_gateway_graph_api_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Create Nodes
    resp1 = client.post("/v1/graph/node/create", json={
        "node_id": "api-node-1",
        "modality": "text",
        "label": "Prompt Input",
        "content": "Generate unit tests for memory graph",
        "embedding": [0.5, 0.5, 0.0],
        "partition_id": "p1",
        "attention_score": 1.2,
    })
    assert resp1.status_code == 200
    assert resp1.json()["ok"] is True
    assert resp1.json()["node"]["node_id"] == "api-node-1"

    resp2 = client.post("/v1/graph/node/create", json={
        "node_id": "api-node-2",
        "modality": "code",
        "label": "Test Code Output",
        "content": "def test_memory(): pass",
        "embedding": [0.48, 0.52, 0.0],
        "partition_id": "p1",
    })
    assert resp2.status_code == 200

    # 2. Create Edge
    resp_edge = client.post("/v1/graph/edge/create", json={
        "edge_id": "api-edge-1",
        "source_id": "api-node-1",
        "target_id": "api-node-2",
        "relation": "GENERATED_CODE",
        "weight": 1.5,
    })
    assert resp_edge.status_code == 200
    assert resp_edge.json()["ok"] is True
    assert resp_edge.json()["edge"]["relation"] == "GENERATED_CODE"

    # 3. Semantic Search
    resp_search = client.post("/v1/graph/search/semantic", json={
        "query_embedding": [0.5, 0.5, 0.0],
        "top_k": 5,
        "partition_id": "p1",
    })
    assert resp_search.status_code == 200
    data = resp_search.json()
    assert data["ok"] is True
    assert data["count"] == 2
    assert data["results"][0]["node"]["node_id"] in ("api-node-1", "api-node-2")

    # 4. Traversal
    resp_trav = client.get("/v1/graph/traverse/api-node-1?max_depth=2")
    assert resp_trav.status_code == 200
    assert resp_trav.json()["ok"] is True
    assert resp_trav.json()["node_count"] == 2
    assert resp_trav.json()["edge_count"] == 1

    # 5. Commit State
    resp_commit = client.post("/v1/graph/commit", json={"commit_id": "test-commit-1"})
    assert resp_commit.status_code == 200
    assert resp_commit.json()["ok"] is True
    assert resp_commit.json()["valid"] is True
    assert resp_commit.json()["receipt"]["commit_id"] == "test-commit-1"
