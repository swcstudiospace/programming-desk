"""Tests for Automated Split-Brain Protection, Fencing Tokens & Fast RTO Recovery (Milestone v2.9 - Phase 25).

Covers:
- REQ-DR-006: Distributed fencing token allocator preventing split-brain writes during failover.
- REQ-DR-007: Automatic quorum heartbeat evaluator isolating partitioned primary clusters.
- REQ-DR-008: Deterministic state conflict reconciler using vector clock ordering.
- REQ-DR-009: Fast failover recovery orchestrator achieving sub-second recovery time objectives (RTO < 1s).
- REQ-DR-010: End-to-end disaster recovery drill verifier generating non-repudiable audit receipts.
- Starlette HTTP API routes in server.py.
"""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.split_brain_recovery import (
    DisasterRecoveryDrillVerifier,
    FastFailoverOrchestrator,
    FencingTokenAllocator,
    QuorumHeartbeatEvaluator,
    QuorumState,
    VectorClockReconciler,
)


@pytest.fixture
def fencing_allocator() -> FencingTokenAllocator:
    return FencingTokenAllocator(initial_epoch=10, cluster_gen_id="gen-test-1")


@pytest.fixture
def quorum_evaluator() -> QuorumHeartbeatEvaluator:
    return QuorumHeartbeatEvaluator(cluster_nodes=["n1", "n2", "n3"], heartbeat_timeout_s=1.0)


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_fencing_token_allocation_and_rejection(fencing_allocator: FencingTokenAllocator):
    """REQ-DR-006: Fencing token monotonic increment and stale token rejection."""
    assert fencing_allocator.current_epoch == 10

    t1 = fencing_allocator.allocate("node-primary-2")
    assert t1.epoch == 11
    assert t1.allocated_to == "node-primary-2"

    # Validation: Current epoch is valid
    valid, _ = fencing_allocator.validate(11, "gen-test-1")
    assert valid is True

    # Validation: Stale epoch (10) rejected
    valid_stale, reason = fencing_allocator.validate(10, "gen-test-1")
    assert valid_stale is False
    assert "Stale" in reason

    # Validation: Mismatched generation ID rejected
    valid_gen, gen_reason = fencing_allocator.validate(11, "wrong-gen")
    assert valid_gen is False
    assert "Invalid cluster generation ID" in gen_reason


def test_quorum_heartbeat_and_partition_isolation(quorum_evaluator: QuorumHeartbeatEvaluator):
    """REQ-DR-007: Automatic quorum heartbeat drops triggering cluster partition state."""
    state, alive, total = quorum_evaluator.evaluate_quorum()
    assert state == QuorumState.HEALTHY
    assert alive == 3

    # Simulate node n3 silent for 2 seconds (> timeout 1.0s)
    quorum_evaluator.heartbeats["n3"] = time.time() - 2.0
    state_deg, alive_deg, _ = quorum_evaluator.evaluate_quorum()
    assert state_deg == QuorumState.DEGRADED
    assert alive_deg == 2  # Quorum maintained (2/3 > 50%)

    # Simulate node n2 also silent -> Quorum lost (1/3 <= 50%)
    quorum_evaluator.heartbeats["n2"] = time.time() - 2.0
    state_part, alive_part, _ = quorum_evaluator.evaluate_quorum()
    assert state_part == QuorumState.PARTITIONED
    assert alive_part == 1


def test_vector_clock_deterministic_conflict_reconciliation():
    """REQ-DR-008: Deterministic conflict reconciliation using vector clocks."""
    reconciler = VectorClockReconciler()

    entry_a = {"data": "A", "vector_clock": {"n1": 2, "n2": 1}, "timestamp": 100}
    entry_b = {"data": "B", "vector_clock": {"n1": 1, "n2": 1}, "timestamp": 90}
    assert reconciler.reconcile(entry_a, entry_b) == entry_a

    # Concurrent branches (n1 ahead on a, n2 ahead on b) -> tie-break by timestamp
    entry_c = {"data": "C", "vector_clock": {"n1": 3, "n2": 1}, "timestamp": 150}
    entry_d = {"data": "D", "vector_clock": {"n1": 2, "n2": 2}, "timestamp": 200}
    winner = reconciler.reconcile(entry_c, entry_d)
    assert winner["data"] == "D"  # Higher timestamp wins tie-break


def test_fast_failover_and_subsecond_rto(
    fencing_allocator: FencingTokenAllocator,
    quorum_evaluator: QuorumHeartbeatEvaluator,
):
    """REQ-DR-009: Fast failover achieving sub-second recovery time objectives (RTO < 1s)."""
    orchestrator = FastFailoverOrchestrator(
        fencing_allocator=fencing_allocator,
        quorum_evaluator=quorum_evaluator,
    )

    result = orchestrator.execute_failover(candidate_node="n2")
    assert result["ok"] is True
    assert result["new_primary"] == "n2"
    assert result["rto_ms"] < 1000.0  # RTO strictly under 1000ms
    assert result["fencing_token"]["epoch"] > 10

    # If cluster is partitioned, failover must be safely blocked
    quorum_evaluator.heartbeats["n1"] = time.time() - 5.0
    quorum_evaluator.heartbeats["n2"] = time.time() - 5.0
    with pytest.raises(RuntimeError, match="Cluster is partitioned"):
        orchestrator.execute_failover(candidate_node="n3")


def test_disaster_recovery_drill_verification(
    fencing_allocator: FencingTokenAllocator,
    quorum_evaluator: QuorumHeartbeatEvaluator,
):
    """REQ-DR-010: Automated disaster recovery drill with signed audit receipts."""
    orchestrator = FastFailoverOrchestrator(
        fencing_allocator=fencing_allocator,
        quorum_evaluator=quorum_evaluator,
    )
    verifier = DisasterRecoveryDrillVerifier(orchestrator=orchestrator)

    receipt = verifier.run_drill(drill_id="drill-alpha", candidate_node="n2")
    assert receipt.drill_id == "drill-alpha"
    assert receipt.promoted_node == "n2"
    assert receipt.passed is True
    assert receipt.rto_ms < 1000.0
    assert receipt.rpo_loss_blocks == 0
    assert len(receipt.receipt_hash) == 64
    assert len(receipt.signature) == 64

    # Verification must confirm receipt authenticity
    assert verifier.verify_receipt(receipt) is True


def test_dr_split_brain_gateway_endpoints(client: TestClient):
    """Starlette API integration tests for split-brain protection and drill runner."""
    # 1. Allocate fencing token
    r_alloc = client.post("/v1/dr/fencing/allocate", json={"node_id": "api-primary-node"})
    assert r_alloc.status_code == 200
    alloc_data = r_alloc.json()
    assert alloc_data["ok"] is True
    epoch = alloc_data["token"]["epoch"]
    gen_id = alloc_data["token"]["cluster_gen_id"]

    # 2. Validate fencing token
    r_val = client.post("/v1/dr/fencing/validate", json={"epoch": epoch, "cluster_gen_id": gen_id})
    assert r_val.status_code == 200
    assert r_val.json()["valid"] is True

    # 3. Quorum heartbeat
    r_hb = client.post("/v1/dr/quorum/heartbeat", json={"node_id": "node-1"})
    assert r_hb.status_code == 200
    assert r_hb.json()["ok"] is True
    assert "quorum_state" in r_hb.json()

    # 4. Vector clock reconciliation
    r_rec = client.post("/v1/dr/reconcile", json={
        "entry_a": {"val": 10, "vector_clock": {"x": 2}},
        "entry_b": {"val": 5, "vector_clock": {"x": 1}},
    })
    assert r_rec.status_code == 200
    assert r_rec.json()["winner"]["val"] == 10

    # 5. Execute DR drill
    r_drill = client.post("/v1/dr/drill/run", json={"candidate_node": "node-2"})
    assert r_drill.status_code == 200
    drill_data = r_drill.json()
    assert drill_data["ok"] is True
    assert drill_data["valid"] is True
    assert drill_data["receipt"]["passed"] is True
    assert drill_data["receipt"]["rto_ms"] < 1000.0
