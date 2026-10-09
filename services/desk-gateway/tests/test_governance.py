"""Unit and integration tests for Decentralized Multi-Desk Governance & Proposal State Machine (Phase 32)."""

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.governance import (
    GovernanceStateMachine,
    ProposalStatus,
    VoteChoice,
    Ballot,
    Proposal,
    QuorumEngine,
    TimelockExecutor,
    EmergencyVetoCircuitBreaker,
)
from desk_gateway.server import build_app


def test_ballot_cryptographic_signing_and_verification():
    """REQ-GOV-003: Cryptographic ballot signing and non-repudiable vote commitments."""
    secret_key = "test-secret-key-42"
    ballot = Ballot(
        proposal_id="prop-001",
        seat="lead",
        desk_id="desk-alpha",
        choice=VoteChoice.YES,
        raw_votes=4.0,
        reputation=1.5,
        reason="Fully reviewed",
    )
    # Quadratic voting weight: sqrt(4.0) * 1.5 = 3.0
    assert abs(ballot.quadratic_voting_power - 3.0) < 1e-5

    # Sign ballot
    sig = ballot.sign(secret_key)
    assert len(sig) == 64
    assert ballot.verify_signature(secret_key) is True
    assert ballot.verify_signature("wrong-key") is False

    # Tampering with ballot payload invalidates signature
    ballot.raw_votes = 16.0
    assert ballot.verify_signature(secret_key) is False


def test_quorum_evaluation_and_quadratic_voting():
    """REQ-GOV-002: Weighted multi-seat quorum evaluation supporting threshold governance and quadratic voting."""
    quorum_engine = QuorumEngine(
        seat_reputations={
            "lead": 1.5,
            "security": 1.5,
            "quality": 1.0,
            "infra": 1.0,
            "systems": 1.0,
        }
    )

    prop = Proposal(
        proposal_id="prop-params-1",
        proposer_seat="lead",
        proposer_desk_id="desk-alpha",
        title="Upgrade Core Runtime",
        description="Upgrade runtime to v3.3.0",
        action_payload={"runtime_version": "v3.3.0"},
        quorum_threshold=0.5,     # Requires >= 50% participation
        approval_threshold=0.66,  # Requires >= 66% yes votes
    )

    # 1. Below quorum: only 2 out of 7 seats participate (28.5%)
    prop.ballots["desk-alpha:lead"] = Ballot(
        "prop-params-1", "lead", "desk-alpha", VoteChoice.YES, raw_votes=9.0, reputation=1.5
    )
    prop.ballots["desk-alpha:infra"] = Ballot(
        "prop-params-1", "infra", "desk-alpha", VoteChoice.YES, raw_votes=4.0, reputation=1.0
    )

    res1 = quorum_engine.evaluate_quorum(prop, total_possible_seats=7)
    assert res1.quorum_reached is False
    assert res1.approved is False
    assert res1.total_participants == 2

    # 2. Add 2 more seats -> 4 out of 7 seats (57.1% >= 50% quorum reached)
    prop.ballots["desk-beta:quality"] = Ballot(
        "prop-params-1", "quality", "desk-beta", VoteChoice.YES, raw_votes=1.0, reputation=1.0
    )
    prop.ballots["desk-beta:security"] = Ballot(
        "prop-params-1", "security", "desk-beta", VoteChoice.YES, raw_votes=4.0, reputation=1.5
    )

    res2 = quorum_engine.evaluate_quorum(prop, total_possible_seats=7)
    assert res2.quorum_reached is True
    assert res2.approved is True
    assert res2.approval_ratio == 1.0

    # 3. Add heavy dissenting vote
    prop.ballots["desk-gamma:systems"] = Ballot(
        "prop-params-1", "systems", "desk-gamma", VoteChoice.NO, raw_votes=100.0, reputation=1.0
    )
    # systems has sqrt(100) * 1.0 = 10.0 NO weight
    res3 = quorum_engine.evaluate_quorum(prop, total_possible_seats=7)
    assert res3.quorum_reached is True
    assert res3.approval_ratio < 0.66
    assert res3.approved is False


def test_proposal_lifecycle_and_timelock():
    """REQ-GOV-001 & REQ-GOV-004: Proposal lifecycle engine and timelock buffer enforcement."""
    gov = GovernanceStateMachine(secret_key="mesh-gov-secret")

    # 1. Create proposal
    prop = gov.create_proposal(
        proposal_id="prop-timelock-1",
        proposer_seat="lead",
        proposer_desk_id="desk-1",
        title="Deploy Canary Cluster",
        description="Launch 3 additional gateway workers",
        action_payload={"replicas": 3},
        timelock_delay_seconds=60.0,
        quorum_threshold=0.4,
        approval_threshold=0.5,
    )
    assert prop.status == ProposalStatus.ACTIVE

    # 2. Start voting
    gov.start_voting("prop-timelock-1")
    assert prop.status == ProposalStatus.VOTING

    # 3. Cast votes
    gov.cast_vote("prop-timelock-1", seat="lead", desk_id="desk-1", choice=VoteChoice.YES, raw_votes=4.0)
    gov.cast_vote("prop-timelock-1", seat="infra", desk_id="desk-1", choice=VoteChoice.YES, raw_votes=4.0)
    gov.cast_vote("prop-timelock-1", seat="security", desk_id="desk-2", choice=VoteChoice.YES, raw_votes=4.0)

    # 4. Tally and resolve
    res = gov.tally_and_resolve("prop-timelock-1", total_possible_seats=7)
    assert res.approved is True
    assert prop.status == ProposalStatus.APPROVED

    # 5. Queue for execution
    gov.queue_for_execution("prop-timelock-1")
    assert prop.status == ProposalStatus.QUEUED

    # 6. Attempt immediate execution -> blocked by timelock buffer
    now = prop.queued_at or time.time()
    with pytest.raises(PermissionError, match="Timelock buffer active"):
        gov.execute_proposal("prop-timelock-1", executor_seat="lead", current_time=now + 10.0)

    # 7. Execute after timelock delay satisfied (>= 60s)
    receipt = gov.execute_proposal("prop-timelock-1", executor_seat="lead", current_time=now + 65.0)
    assert receipt["status"] == "EXECUTED"
    assert prop.status == ProposalStatus.EXECUTED
    assert "receipt_sig" in receipt


def test_autonomous_emergency_veto_and_circuit_breaker():
    """REQ-GOV-005: Autonomous emergency veto and circuit-breaker abort triggers."""
    gov = GovernanceStateMachine(secret_key="mesh-gov-secret")

    # 1. Automated circuit-breaker triggers on forbidden security action
    prop_anomalous = gov.create_proposal(
        proposal_id="prop-bad-actor",
        proposer_seat="lead",
        proposer_desk_id="desk-compromised",
        title="Bypass Auth Gate",
        description="Disable token enforcement",
        action_payload={"action": "bypass_auth"},
    )
    assert prop_anomalous.status == ProposalStatus.VETOED
    assert "Forbidden action 'bypass_auth' detected" in str(prop_anomalous.veto_reason)

    # 2. Automated circuit-breaker on destructive op lacking quality tag
    prop_destructive = gov.create_proposal(
        proposal_id="prop-destructive-unverified",
        proposer_seat="lead",
        proposer_desk_id="desk-alpha",
        title="Truncate Ledger Cache",
        description="Clear historical ledger indices",
        action_payload={"action": "truncate_cache", "destructive_operation": True},
        tags=["infra"],  # Missing 'quality' tag
    )
    assert prop_destructive.status == ProposalStatus.VETOED
    assert "quality oversight" in str(prop_destructive.veto_reason)

    # 3. Manual emergency veto by authorized seat
    prop_valid = gov.create_proposal(
        proposal_id="prop-to-veto",
        proposer_seat="infra",
        proposer_desk_id="desk-alpha",
        title="Adjust Ingress Bandwidth",
        description="Throttle traffic limit",
        action_payload={"action": "adjust_bandwidth", "limit_kbps": 5000},
    )
    assert prop_valid.status == ProposalStatus.ACTIVE

    # Unauthorized seat cannot veto
    with pytest.raises(PermissionError, match="not authorized to exercise emergency veto power"):
        gov.emergency_veto("prop-to-veto", veto_seat="frontend", reason="Dislike change")

    # Security seat exercises veto
    gov.emergency_veto("prop-to-veto", veto_seat="security", reason="Potential DDoS vector")
    assert prop_valid.status == ProposalStatus.VETOED
    assert "Manual emergency veto by security" in str(prop_valid.veto_reason)


def test_governance_rest_endpoints():
    """Integration test for governance REST endpoints."""
    app, _ = build_app()
    client = TestClient(app)

    # 1. Create proposal via REST
    resp = client.post(
        "/v1/governance/proposal/create",
        json={
            "proposal_id": "prop-rest-101",
            "proposer_seat": "lead",
            "proposer_desk_id": "desk-1",
            "title": "Provision MicroVM Enclave",
            "description": "Allocate 4 cores for secure computation",
            "action_payload": {"action": "provision_enclave", "cores": 4},
            "timelock_delay_seconds": 30.0,
            "quorum_threshold": 0.4,
            "approval_threshold": 0.5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["proposal"]["status"] == "ACTIVE"

    # 2. Read proposal via GET
    get_resp = client.get("/v1/governance/proposal/prop-rest-101")
    assert get_resp.status_code == 200
    assert get_resp.json()["proposal"]["proposal_id"] == "prop-rest-101"

    # 3. Start voting
    start_resp = client.post("/v1/governance/proposal/start_voting", json={"proposal_id": "prop-rest-101"})
    assert start_resp.status_code == 200
    assert start_resp.json()["proposal"]["status"] == "VOTING"

    # 4. Cast votes
    v1 = client.post(
        "/v1/governance/vote",
        json={"proposal_id": "prop-rest-101", "seat": "lead", "choice": "YES", "raw_votes": 4.0},
    )
    assert v1.status_code == 200
    assert v1.json()["ballot"]["quadratic_voting_power"] > 0

    v2 = client.post(
        "/v1/governance/vote",
        json={"proposal_id": "prop-rest-101", "seat": "infra", "choice": "YES", "raw_votes": 1.0},
    )
    assert v2.status_code == 200

    v3 = client.post(
        "/v1/governance/vote",
        json={"proposal_id": "prop-rest-101", "seat": "security", "choice": "YES", "raw_votes": 1.0},
    )
    assert v3.status_code == 200

    # 5. Tally
    tally_resp = client.post("/v1/governance/tally", json={"proposal_id": "prop-rest-101", "total_possible_seats": 7})
    assert tally_resp.status_code == 200
    tally_data = tally_resp.json()["result"]
    assert tally_data["quorum_reached"] is True
    assert tally_data["approved"] is True

    # 6. Queue
    q_resp = client.post("/v1/governance/queue", json={"proposal_id": "prop-rest-101"})
    assert q_resp.status_code == 200
    assert q_resp.json()["proposal"]["status"] == "QUEUED"

    # 7. Execute after simulated timelock
    now = time.time()
    exec_resp = client.post(
        "/v1/governance/execute",
        json={"proposal_id": "prop-rest-101", "executor_seat": "lead", "current_time": now + 40.0},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["receipt"]["status"] == "EXECUTED"
