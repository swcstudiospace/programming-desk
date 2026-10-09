"""Tests for Byzantine Consensus Voting & Verifiable On-Chain Attestation (Milestone v3.3 - Phase 33).

Covers:
- REQ-GOV-006: Federated Byzantine fault-tolerant consensus rounds with three-phase commit (PRE-PREPARE, PREPARE, COMMIT).
- REQ-GOV-007: View-change protocol and leader rotation handling Byzantine or unresponsive coordinator desks.
- REQ-GOV-008: Cryptographic Merkle governance receipts linking proposal state transitions, ballot tallies, and execution outcomes.
- REQ-GOV-009: On-chain and external WORM ledger audit export anchoring consensus receipts to distributed ledgers.
- REQ-GOV-010: End-to-end multi-desk governance verification harness and Byzantine attack drill simulator.
- Starlette HTTP API routes in server.py (/v1/consensus/*).
"""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.byzantine_consensus import (
    ByzantineAttackSimulator,
    ByzantineConsensusEngine,
    ConsensusDecision,
    ConsensusMessage,
    ConsensusPhase,
    GovernanceMerkleReceipt,
    GovernanceReceiptMerkleTree,
    LedgerAnchorExporter,
    OnChainAnchor,
    ViewChangeMessage,
)
from desk_gateway.server import build_app


@pytest.fixture
def desks() -> list[str]:
    return ["desk-alpha", "desk-beta", "desk-gamma", "desk-delta"]


@pytest.fixture
def engine(desks: list[str]) -> ByzantineConsensusEngine:
    return ByzantineConsensusEngine(
        desks=desks,
        local_desk_id="desk-alpha",
        secret_key="test-byzantine-secret-key",
    )


@pytest.fixture
def merkle_receipt_tree() -> GovernanceReceiptMerkleTree:
    return GovernanceReceiptMerkleTree(secret_key="test-receipt-secret-key")


@pytest.fixture
def anchor_exporter() -> LedgerAnchorExporter:
    return LedgerAnchorExporter(cluster_id="test-cluster-solana")


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_three_phase_commit_bft_round(engine: ByzantineConsensusEngine):
    """REQ-GOV-006: Federated Byzantine fault-tolerant consensus rounds (PRE-PREPARE, PREPARE, COMMIT)."""
    assert engine.total_nodes == 4
    assert engine.max_faulty == 1
    # Quorum: 2f + 1 = 3 nodes
    assert engine.quorum_size == 3

    proposal_payload = {"action": "upgrade_smart_contract", "version": "v3.3.1"}
    round_id = "round-101"

    # Phase 1: PRE-PREPARE
    pre_prep_msg = engine.start_round(
        round_id=round_id,
        proposal_id="prop-contract-upg",
        proposal_payload=proposal_payload,
    )
    assert pre_prep_msg.phase == ConsensusPhase.PRE_PREPARE
    assert pre_prep_msg.sender_desk == "desk-alpha"
    assert len(pre_prep_msg.signature) == 64
    assert pre_prep_msg.verify_signature("test-byzantine-secret-key") is True

    # Phase 2: PREPARE from 3 nodes
    digest = pre_prep_msg.proposal_digest

    ok1, _, _ = engine.process_prepare(round_id, "desk-alpha", digest, ConsensusDecision.APPROVE)
    assert ok1 is True
    ok2, _, _ = engine.process_prepare(round_id, "desk-beta", digest, ConsensusDecision.APPROVE)
    assert ok2 is True
    ok3, _, commit_msg = engine.process_prepare(round_id, "desk-gamma", digest, ConsensusDecision.APPROVE)
    assert ok3 is True
    # Quorum reached in prepare phase triggers local commit message
    assert commit_msg is not None
    assert commit_msg.phase == ConsensusPhase.COMMIT

    # Phase 3: COMMIT from 3 nodes
    ok_c1, _, fin1 = engine.process_commit(round_id, "desk-alpha", digest, ConsensusDecision.APPROVE)
    assert ok_c1 is True and fin1 is False
    ok_c2, _, fin2 = engine.process_commit(round_id, "desk-beta", digest, ConsensusDecision.APPROVE)
    assert ok_c2 is True and fin2 is False
    ok_c3, msg_c3, finalized = engine.process_commit(round_id, "desk-gamma", digest, ConsensusDecision.APPROVE)
    assert ok_c3 is True and finalized is True
    assert "COMMITTED" in msg_c3

    summary = engine.get_round_summary(round_id)
    assert summary["phase"] == ConsensusPhase.COMMITTED.value
    assert summary["status"] == "committed"
    assert summary["decision"] == "APPROVE"


def test_view_change_protocol_and_leader_rotation(engine: ByzantineConsensusEngine):
    """REQ-GOV-007: View-change protocol and leader rotation handling unresponsive coordinator desks."""
    round_id = "round-view-change-1"
    engine.start_round(
        round_id=round_id,
        proposal_id="prop-timeout",
        proposal_payload={"action": "rebalance_shards"},
    )
    initial_view = engine.current_view
    assert initial_view == 0
    assert engine.current_leader == "desk-alpha"

    # Simulate 3 desks voting for view change (reaching 2f + 1 quorum)
    ok1, _, v1 = engine.request_view_change(round_id, "desk-beta", "Leader unresponsive")
    assert ok1 is True and v1 == 0

    ok2, _, v2 = engine.request_view_change(round_id, "desk-gamma", "Leader unresponsive")
    assert ok2 is True and v2 == 0

    ok3, msg3, v3 = engine.request_view_change(round_id, "desk-delta", "Leader unresponsive")
    assert ok3 is True and v3 == 1
    assert "View change successful" in msg3
    assert engine.current_view == 1
    assert engine.current_leader == "desk-beta"  # Rotated to next peer desk


def test_governance_merkle_receipt_linking_and_verification(merkle_receipt_tree: GovernanceReceiptMerkleTree):
    """REQ-GOV-008: Cryptographic Merkle governance receipts linking transitions, tallies, and outcomes."""
    transitions = [
        {"from": "DRAFT", "to": "ACTIVE", "ts": 1000.0},
        {"from": "ACTIVE", "to": "VOTING", "ts": 1005.0},
        {"from": "VOTING", "to": "APPROVED", "ts": 1050.0},
    ]
    tally = {
        "yes_weight": 5.5,
        "no_weight": 0.0,
        "quorum_reached": True,
        "approval_ratio": 1.0,
    }
    execution = {
        "executor": "lead",
        "action": "upgrade_parameter",
        "result": "success",
        "tx_hash": "0x1234abcd",
    }

    receipt = merkle_receipt_tree.build_receipt(
        round_id="round-receipt-1",
        proposal_id="prop-rec-42",
        proposal_digest="abcdef0123456789" * 4,
        state_transitions=transitions,
        ballot_tallies=tally,
        execution_outcome=execution,
        signers=["desk-alpha", "desk-beta", "desk-gamma"],
    )

    assert receipt.receipt_id.startswith("grec-round-receipt-1-")
    assert len(receipt.merkle_root) == 64
    assert len(receipt.aggregate_signature) == 64
    assert merkle_receipt_tree.verify_receipt(receipt) is True

    # Tampering with transition hash breaks Merkle proof verification
    receipt.transition_hash = "0" * 64
    assert merkle_receipt_tree.verify_receipt(receipt) is False


def test_on_chain_worm_ledger_audit_export(
    merkle_receipt_tree: GovernanceReceiptMerkleTree,
    anchor_exporter: LedgerAnchorExporter,
):
    """REQ-GOV-009: On-chain and external WORM ledger audit export anchoring consensus receipts."""
    receipt = merkle_receipt_tree.build_receipt(
        round_id="round-anchor-1",
        proposal_id="prop-anc-99",
        proposal_digest="11223344" * 8,
        state_transitions=[{"step": 1}],
        ballot_tallies={"yes": 3},
        execution_outcome={"status": "executed"},
        signers=["desk-alpha", "desk-beta"],
    )

    anchor = anchor_exporter.anchor_receipt(receipt, target_ledger="solana_devnet")
    assert anchor.target_ledger == "solana_devnet"
    assert anchor.merkle_root == receipt.merkle_root
    assert anchor.receipt_id == receipt.receipt_id
    assert anchor.block_or_slot >= 100_000
    assert len(anchor.tx_signature) == 64

    # Verify anchor on-chain representation
    valid, msg = anchor_exporter.verify_anchor(anchor.anchor_id, receipt.merkle_root)
    assert valid is True
    assert "Anchor cryptographically verified" in msg

    # Mismatch root fails
    invalid, reason = anchor_exporter.verify_anchor(anchor.anchor_id, "bad_merkle_root")
    assert invalid is False
    assert "mismatch" in reason


def test_byzantine_attack_drill_simulator(engine: ByzantineConsensusEngine):
    """REQ-GOV-010: End-to-end multi-desk governance verification harness and Byzantine attack drill simulator."""
    simulator = ByzantineAttackSimulator(engine)
    drill_results = simulator.run_full_byzantine_resilience_suite({
        "action": "critical_param_override",
        "threshold": 0.99,
    })

    assert drill_results["total_nodes"] == 4
    assert drill_results["max_faulty_tolerated"] == 1
    assert drill_results["sybil_drill"]["mitigation_success"] is True
    assert drill_results["sybil_drill"]["prepare_blocked"] is True
    assert drill_results["tamper_drill"]["mitigation_success"] is True
    assert drill_results["tamper_drill"]["prepare_blocked"] is True
    assert drill_results["view_change_drill"]["mitigation_success"] is True
    assert drill_results["all_mitigations_verified"] is True


def test_consensus_rest_api_endpoints(client: TestClient):
    """Starlette REST API integration for Byzantine Consensus routes (/v1/consensus/*)."""
    # 1. Start consensus round
    start_resp = client.post(
        "/v1/consensus/round/start",
        json={
            "round_id": "api-round-1",
            "proposal_id": "api-prop-1",
            "proposal_payload": {"param": "alpha", "val": 100},
            "leader_desk": "desk-alpha",
        },
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert start_data["ok"] is True
    digest = start_data["message"]["proposal_digest"]

    # 2. Prepare phase votes
    p1 = client.post(
        "/v1/consensus/round/prepare",
        json={"round_id": "api-round-1", "sender_desk": "desk-alpha", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert p1.status_code == 200

    p2 = client.post(
        "/v1/consensus/round/prepare",
        json={"round_id": "api-round-1", "sender_desk": "desk-beta", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert p2.status_code == 200

    p3 = client.post(
        "/v1/consensus/round/prepare",
        json={"round_id": "api-round-1", "sender_desk": "desk-gamma", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert p3.status_code == 200
    assert p3.json()["commit_msg"] is not None

    # 3. Commit phase votes
    c1 = client.post(
        "/v1/consensus/round/commit",
        json={"round_id": "api-round-1", "sender_desk": "desk-alpha", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert c1.status_code == 200 and c1.json()["finalized"] is False

    c2 = client.post(
        "/v1/consensus/round/commit",
        json={"round_id": "api-round-1", "sender_desk": "desk-beta", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert c2.status_code == 200 and c2.json()["finalized"] is False

    c3 = client.post(
        "/v1/consensus/round/commit",
        json={"round_id": "api-round-1", "sender_desk": "desk-gamma", "proposal_digest": digest, "decision": "APPROVE"},
    )
    assert c3.status_code == 200 and c3.json()["finalized"] is True

    # 4. Round summary
    sum_resp = client.get("/v1/consensus/round/api-round-1")
    assert sum_resp.status_code == 200
    assert sum_resp.json()["round"]["status"] == "committed"

    # 5. Build Merkle receipt
    rec_resp = client.post(
        "/v1/consensus/receipt/build",
        json={
            "round_id": "api-round-1",
            "proposal_id": "api-prop-1",
            "proposal_digest": digest,
            "state_transitions": [{"from": "NEW", "to": "COMMITTED"}],
            "ballot_tallies": {"approved": True, "quorum": 3},
            "execution_outcome": {"status": "success"},
            "signers": ["desk-alpha", "desk-beta", "desk-gamma"],
        },
    )
    assert rec_resp.status_code == 200
    receipt_obj = rec_resp.json()["receipt"]

    # 6. Verify receipt
    ver_resp = client.post("/v1/consensus/receipt/verify", json={"receipt": receipt_obj})
    assert ver_resp.status_code == 200
    assert ver_resp.json()["valid"] is True

    # 7. Anchor to Solana devnet
    anc_resp = client.post(
        "/v1/consensus/anchor/export",
        json={"receipt": receipt_obj, "target_ledger": "solana_devnet"},
    )
    assert anc_resp.status_code == 200
    anchor_obj = anc_resp.json()["anchor"]
    assert anchor_obj["target_ledger"] == "solana_devnet"
    assert anchor_obj["merkle_root"] == receipt_obj["merkle_root"]

    # 8. Simulate Byzantine drill
    drill_resp = client.post("/v1/consensus/drill/simulate", json={"payload": {"safe_mode": True}})
    assert drill_resp.status_code == 200
    assert drill_resp.json()["drill"]["all_mitigations_verified"] is True
