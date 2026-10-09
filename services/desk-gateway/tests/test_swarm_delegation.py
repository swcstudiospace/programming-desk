"""Tests for Autonomous Hierarchical Subagent Delegation & Byzantine Consensus Receipts (Milestone v2.8 - Phase 23).

Covers:
- REQ-SWARM-006: Recursive subagent task decomposition and delegation protocol supporting nested parent-child task DAGs.
- REQ-SWARM-007: Cryptographic task handoff and acceptance receipts with timestamped nonces and task fingerprinting.
- REQ-SWARM-008: Dual-party signature verification for cross-seat delegation acknowledging receipt before execution state transitions.
- REQ-SWARM-009: Byzantine dispute arbitration and timeout reclamation engine handling unresponsive or conflicting subagent claims.
- REQ-SWARM-010: End-to-end swarm execution audit receipt aggregation validating hierarchical delegation integrity and non-repudiation.
- Starlette HTTP API routes in server.py.
"""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.swarm_delegation import (
    DelegationReceipt,
    DelegationState,
    HierarchicalTaskNode,
    SwarmDelegationMesh,
)


@pytest.fixture
def mesh() -> SwarmDelegationMesh:
    return SwarmDelegationMesh(max_depth=3, default_timeout_seconds=5.0)


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_recursive_task_dag_and_depth_limit(mesh: SwarmDelegationMesh):
    """REQ-SWARM-006: Recursive subagent task decomposition up to depth ceiling."""
    root = mesh.create_root_task(
        task_id="task-root-1",
        title="Root Mission",
        delegator_seat="lead",
        delegatee_seat="systems",
        payload={"scope": "full_deployment"},
    )
    assert root.depth == 0
    assert root.parent_task_id is None

    sub1 = mesh.decompose_subtask(
        parent_task_id="task-root-1",
        subtask_id="task-sub-1",
        title="Subtask Tier 1",
        delegator_seat="systems",
        delegatee_seat="web",
        payload={"scope": "frontend"},
    )
    assert sub1.depth == 1
    assert sub1.parent_task_id == "task-root-1"
    assert "task-sub-1" in mesh.tasks["task-root-1"].subtask_ids

    sub2 = mesh.decompose_subtask(
        parent_task_id="task-sub-1",
        subtask_id="task-sub-2",
        title="Subtask Tier 2",
        delegator_seat="web",
        delegatee_seat="infra",
        payload={"scope": "cdn"},
    )
    assert sub2.depth == 2

    sub3 = mesh.decompose_subtask(
        parent_task_id="task-sub-2",
        subtask_id="task-sub-3",
        title="Subtask Tier 3",
        delegator_seat="infra",
        delegatee_seat="quality",
        payload={"scope": "verify"},
    )
    assert sub3.depth == 3

    # Depth limit exceeded (max_depth=3)
    with pytest.raises(ValueError, match="Maximum task delegation depth"):
        mesh.decompose_subtask(
            parent_task_id="task-sub-3",
            subtask_id="task-sub-4",
            title="Subtask Tier 4",
            delegator_seat="quality",
            delegatee_seat="android",
            payload={"scope": "overflow"},
        )


def test_dual_party_signatures_and_handoff(mesh: SwarmDelegationMesh):
    """REQ-SWARM-007, REQ-SWARM-008: Cryptographic task handoff, nonces, and dual-party signatures."""
    mesh.create_root_task(
        task_id="task-auth-1",
        title="Auth Handshake",
        delegator_seat="lead",
        delegatee_seat="systems",
        payload={"step": "security_check"},
    )

    # 1. Delegator offers task
    offer = mesh.offer_delegation("task-auth-1", delegator_seat="lead", delegatee_seat="systems")
    assert offer.state == DelegationState.OFFERED
    assert offer.delegator_signature is not None
    assert offer.delegatee_signature is None
    assert len(offer.task_fingerprint) == 64

    # 2. Unauthorized delegatee attempt
    with pytest.raises(ValueError, match="Unauthorized delegatee"):
        mesh.accept_delegation("task-auth-1", delegatee_seat="web")

    # 3. Invalid signature rejection
    with pytest.raises(ValueError, match="Invalid delegatee signature"):
        mesh.accept_delegation(
            "task-auth-1",
            delegatee_seat="systems",
            delegatee_signature="invalid_sig_hex_1234",
        )

    # 4. Valid acceptance
    accepted = mesh.accept_delegation("task-auth-1", delegatee_seat="systems")
    assert accepted.state == DelegationState.IN_PROGRESS
    assert accepted.delegatee_signature is not None

    # 5. Complete task
    completed = mesh.complete_delegation("task-auth-1", delegatee_seat="systems")
    assert completed.state == DelegationState.COMPLETED
    assert completed.completed_at is not None


def test_byzantine_dispute_and_timeout_reclamation(mesh: SwarmDelegationMesh):
    """REQ-SWARM-009: Byzantine dispute arbitration and timeout reclamation."""
    mesh.create_root_task(
        task_id="task-byz-1",
        title="Unstable Worker Task",
        delegator_seat="lead",
        delegatee_seat="ios",
        payload={"test": "dispute"},
    )
    mesh.offer_delegation("task-byz-1", delegator_seat="lead", delegatee_seat="ios")

    # Raise dispute
    disputed = mesh.raise_dispute(
        task_id="task-byz-1",
        reporter_seat="quality",
        reason="Conflicting payload hash submitted",
    )
    assert disputed.state == DelegationState.DISPUTED
    assert "quality" in disputed.dispute_reason

    # Arbitrate dispute
    arbitrated = mesh.arbitrate_dispute(
        task_id="task-byz-1",
        ruling="Revoke assignment and assign to fallback seat",
        arbitrator_seat="lead",
    )
    assert arbitrated.state == DelegationState.RECLAIMED
    assert "Revoke assignment" in arbitrated.ruling

    # Timeout reclamation
    mesh.create_root_task(
        task_id="task-timeout-1",
        title="Orphan Task",
        delegator_seat="lead",
        delegatee_seat="android",
        payload={"action": "sleep"},
    )
    receipt = mesh.offer_delegation("task-timeout-1", delegator_seat="lead", delegatee_seat="android")
    # Simulate past timestamp
    receipt.timestamp = time.time() - 10.0

    reclaimed_ids = mesh.reclaim_timed_out_tasks(timeout_seconds=5.0)
    assert "task-timeout-1" in reclaimed_ids
    assert mesh.receipts["task-timeout-1"].state == DelegationState.RECLAIMED


def test_tree_audit_receipt_merkle_aggregation(mesh: SwarmDelegationMesh):
    """REQ-SWARM-010: Swarm execution audit receipt aggregation and Merkle proof."""
    mesh.create_root_task(
        task_id="task-tree-root",
        title="Root Plan",
        delegator_seat="lead",
        delegatee_seat="systems",
        payload={"plan": "full"},
    )
    mesh.offer_delegation("task-tree-root", "lead", "systems")
    mesh.accept_delegation("task-tree-root", "systems")

    mesh.decompose_subtask(
        parent_task_id="task-tree-root",
        subtask_id="task-tree-sub1",
        title="Subtask 1",
        delegator_seat="systems",
        delegatee_seat="web",
        payload={"sub": "1"},
    )
    mesh.offer_delegation("task-tree-sub1", "systems", "web")
    mesh.accept_delegation("task-tree-sub1", "web")
    mesh.complete_delegation("task-tree-sub1", "web")

    proof = mesh.generate_tree_audit_receipt("task-tree-root")
    assert proof["root_task_id"] == "task-tree-root"
    assert proof["total_tasks"] == 2
    assert proof["total_receipts"] == 2
    assert len(proof["merkle_root"]) == 64
    assert len(proof["receipts"]) == 2
    assert proof["receipts"][0]["has_dual_signature"] is True


def test_gateway_swarm_delegation_endpoints(client: TestClient):
    """Starlette API routes for hierarchical swarm delegation."""
    # 1. Create root task & offer
    r = client.post("/v1/swarm/delegation/create", json={
        "task_id": "api-task-root",
        "title": "API Root Task",
        "delegator_seat": "lead",
        "delegatee_seat": "systems",
        "payload": {"version": 2},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["task_id"] == "api-task-root"
    assert data["depth"] == 0

    # 2. Accept delegation
    r_acc = client.post("/v1/swarm/delegation/accept", json={
        "task_id": "api-task-root",
        "delegatee_seat": "systems",
    })
    assert r_acc.status_code == 200
    acc_data = r_acc.json()
    assert acc_data["ok"] is True
    assert acc_data["state"] == "in_progress"

    # 3. Create subtask
    r_sub = client.post("/v1/swarm/delegation/create", json={
        "task_id": "api-task-sub",
        "parent_task_id": "api-task-root",
        "title": "API Subtask",
        "delegator_seat": "systems",
        "delegatee_seat": "web",
        "payload": {"ui": True},
    })
    assert r_sub.status_code == 200
    assert r_sub.json()["depth"] == 1

    # 4. Fetch tree audit
    r_audit = client.get("/v1/swarm/delegation/audit/api-task-root")
    assert r_audit.status_code == 200
    audit_data = r_audit.json()
    assert audit_data["ok"] is True
    assert audit_data["total_tasks"] == 2
    assert "merkle_root" in audit_data

    # 5. Complete subtask
    client.post("/v1/swarm/delegation/accept", json={"task_id": "api-task-sub", "delegatee_seat": "web"})
    r_comp = client.post("/v1/swarm/delegation/complete", json={"task_id": "api-task-sub", "delegatee_seat": "web"})
    assert r_comp.status_code == 200
    assert r_comp.json()["state"] == "completed"
