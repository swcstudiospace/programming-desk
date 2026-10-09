"""Test suite for Phase 17 Inter-Desk Agent Mesh & Distributed Work Distribution (REQ-MESH-001 to REQ-MESH-005)."""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.config import Settings
from desk_gateway.mesh import (
    AgentBusRPC,
    CoSignVerificationError,
    CoSignedReceipt,
    DelegatedTaskStateMachine,
    DelegationState,
    DeskNotFoundError,
    DeskType,
    InvalidDelegationTransitionError,
    MeshDiscoveryRegistry,
    ReceiptCoSigner,
)
from desk_gateway.server import build_app


@pytest.fixture
def mesh_registry() -> MeshDiscoveryRegistry:
    return MeshDiscoveryRegistry(heartbeat_timeout_sec=5.0)


@pytest.fixture
def client(tmp_path) -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_mesh_discovery_registration_and_heartbeat(mesh_registry: MeshDiscoveryRegistry):
    """REQ-MESH-001: Register autonomous desk instances and verify capabilities and heartbeat."""
    # Register recruitment desk
    recruitment_node = mesh_registry.register_desk(
        desk_id="recruitment-desk-01",
        desk_type=DeskType.RECRUITMENT,
        tailnet_ip="100.64.0.12",
        port=8791,
        capabilities=["candidate_sourcing", "interview_scheduling"],
    )
    assert recruitment_node.desk_id == "recruitment-desk-01"
    assert recruitment_node.desk_type == DeskType.RECRUITMENT
    assert recruitment_node.status == "active"

    # Register trading desk
    trading_node = mesh_registry.register_desk(
        desk_id="trading-desk-01",
        desk_type="trading",
        tailnet_ip="100.64.0.13",
        port=8791,
        capabilities=["order_routing", "market_making"],
    )
    assert trading_node.desk_type == DeskType.TRADING

    # List desks filtered by type
    rec_desks = mesh_registry.list_desks(desk_type=DeskType.RECRUITMENT)
    assert len(rec_desks) == 1
    assert rec_desks[0].desk_id == "recruitment-desk-01"

    # Heartbeat
    hb = mesh_registry.heartbeat("recruitment-desk-01")
    assert hb.status == "active"

    # Unknown desk
    with pytest.raises(DeskNotFoundError):
        mesh_registry.get_desk("nonexistent-desk")


def test_agent_bus_rpc_dispatch_and_progress(mesh_registry: MeshDiscoveryRegistry):
    """REQ-MESH-002: Asynchronous inter-desk RPC protocol via VPS Agent Bus."""
    mesh_registry.register_desk("programming-desk", DeskType.PROGRAMMING, "100.64.0.1")
    mesh_registry.register_desk("recruitment-desk", DeskType.RECRUITMENT, "100.64.0.2")

    bus = AgentBusRPC(mesh_registry)

    # Dispatch task handoff from programming to recruitment
    msg = bus.dispatch_task(
        source_desk="programming-desk",
        target_desk="recruitment-desk",
        task_id="TICKET-890",
        method="schedule_technical_interview",
        payload={"candidate": "Alice", "role": "Backend Engineer"},
    )
    assert msg.status == "pending"
    assert msg.progress_pct == 0.0
    assert msg.task_id == "TICKET-890"

    # Update progress
    updated = bus.update_progress(msg.message_id, progress_pct=50.0, status="in_progress")
    assert updated.progress_pct == 50.0
    assert updated.status == "in_progress"

    # Complete
    completed = bus.update_progress(
        msg.message_id,
        progress_pct=100.0,
        status="completed",
        result={"interview_slot": "2026-10-15T14:00:00Z", "interviewer": "bot-01"},
    )
    assert completed.status == "completed"
    assert completed.result["interviewer"] == "bot-01"

    # Query by task_id
    tasks = bus.get_by_task_id("TICKET-890")
    assert len(tasks) == 1
    assert tasks[0].message_id == msg.message_id


def test_receipt_cosigning_protocol():
    """REQ-MESH-003: Dual-party cryptographic receipt co-signing protocol."""
    secret = "shared-mesh-secret-between-desks"
    desk_a = ReceiptCoSigner(local_desk_id="desk-a", signing_secret=secret)
    desk_b = ReceiptCoSigner(local_desk_id="desk-b", signing_secret=secret)

    task_result = {"status": "success", "commits": ["a1b2c3d"], "tests_passed": 42}

    # Desk A creates signed proposal
    proposal = desk_a.sign_source(task_id="TASK-444", target_desk="desk-b", task_result=task_result)
    assert "source_signature" in proposal
    assert proposal["source_desk"] == "desk-a"

    # Desk B co-signs proposal
    cosigned = desk_b.cosign_target(proposal, task_result)
    assert cosigned.target_signature is not None
    assert cosigned.status == "verified"

    # Verify cosigned receipt
    assert desk_a.verify_cosigned_receipt(cosigned) is True
    assert desk_b.verify_cosigned_receipt(cosigned) is True

    # Tampered result rejected
    tampered_result = dict(task_result)
    tampered_result["tests_passed"] = 43
    with pytest.raises(CoSignVerificationError, match="Payload hash does not match"):
        desk_b.cosign_target(proposal, tampered_result)


def test_delegated_task_state_machine_and_recall():
    """REQ-MESH-004: Decentralized task delegation state machine handling timeout and recall."""
    sm = DelegatedTaskStateMachine()

    task = sm.initiate_delegation(
        task_id="TASK-501",
        originating_desk="programming-desk",
        assigned_desk="trading-desk",
        timeout_sec=0.1,  # short timeout for test
    )
    assert task.state == DelegationState.INITIATED

    # Advance to ACCEPTED
    task = sm.advance_state(task.delegation_id, DelegationState.ACCEPTED)
    assert task.state == DelegationState.ACCEPTED

    # Advance to IN_PROGRESS
    task = sm.advance_state(task.delegation_id, DelegationState.IN_PROGRESS)
    assert task.state == DelegationState.IN_PROGRESS

    # Invalid jump (IN_PROGRESS directly to INITIATED)
    with pytest.raises(InvalidDelegationTransitionError):
        sm.advance_state(task.delegation_id, DelegationState.INITIATED)

    # Let timeout expire and check
    time.sleep(0.15)
    timed_out = sm.check_timeouts()
    assert len(timed_out) == 1
    assert timed_out[0].state == DelegationState.TIMED_OUT

    # Automated recall after timeout
    recalled = sm.recall_to_origin(task.delegation_id, reason="Timeout reached on peer desk")
    assert recalled.state == DelegationState.RECALLED
    assert len(recalled.history) >= 4


def test_gateway_mesh_rest_api_lifecycle(client: TestClient):
    """REQ-MESH-005: Continuous inter-desk mesh verification via Gateway endpoints."""
    # 1. Register recruitment peer
    resp = client.post(
        "/v1/mesh/register",
        json={
            "desk_id": "recruitment-desk-v2",
            "desk_type": "recruitment",
            "tailnet_ip": "100.64.0.50",
            "capabilities": ["recruiting", "screening"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True

    # 2. List desks
    resp = client.get("/v1/mesh/desks")
    assert resp.status_code == 200
    desks = resp.json()["desks"]
    assert any(d["desk_id"] == "recruitment-desk-v2" for d in desks)

    # 3. Dispatch RPC task
    resp = client.post(
        "/v1/mesh/rpc/dispatch",
        json={
            "source_desk": "testserver",
            "target_desk": "recruitment-desk-v2",
            "task_id": "TICKET-777",
            "method": "screen_resume",
            "payload": {"applicant_id": "app-123"},
        },
    )
    assert resp.status_code == 202
    msg_id = resp.json()["message"]["message_id"]

    # 4. Update progress
    resp = client.post(
        "/v1/mesh/rpc/tasks/TICKET-777",
        json={"message_id": msg_id, "progress_pct": 100.0, "status": "completed", "result": {"score": 95}},
    )
    assert resp.status_code == 200
    assert resp.json()["message"]["progress_pct"] == 100.0

    # 5. Co-sign receipt
    # Generate proposal from local cosigner
    app_state = client.app.state
    cosigner: ReceiptCoSigner = app_state["receipt_cosigner"]
    task_res = {"score": 95}
    proposal = cosigner.sign_source(task_id="TICKET-777", target_desk="recruitment-desk-v2", task_result=task_res)

    resp = client.post(
        "/v1/mesh/receipts/cosign",
        json={"proposal": proposal, "task_result": task_res},
    )
    assert resp.status_code == 200
    cosigned_rcpt = resp.json()["receipt"]
    assert cosigned_rcpt["target_signature"] != ""

    # 6. Verify receipt
    resp = client.post("/v1/mesh/receipts/verify", json=cosigned_rcpt)
    assert resp.status_code == 200
    assert resp.json()["verified"] is True

    # 7. Delegation state machine advance & recall
    sm: DelegatedTaskStateMachine = app_state["delegation_sm"]
    del_task = sm.initiate_delegation("TICKET-777", "testserver", "recruitment-desk-v2")

    resp = client.post(
        "/v1/mesh/delegation/advance",
        json={"delegation_id": del_task.delegation_id, "state": "rejected", "reason": "No interviewers free"},
    )
    assert resp.status_code == 200
    assert resp.json()["delegation"]["state"] == "rejected"

    resp = client.post(
        "/v1/mesh/delegation/recall",
        json={"delegation_id": del_task.delegation_id, "reason": "Reclaiming rejected delegation"},
    )
    assert resp.status_code == 200
    assert resp.json()["recalled"] is True
    assert resp.json()["delegation"]["state"] == "recalled"

    # 8. End-to-end verification endpoint
    resp = client.get("/v1/mesh/verify")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
