"""Unit tests for Phase 41: Multi-Seat Synthesis Consensus & Cryptographic Proof Receipt Ledger."""

import pytest
from desk_gateway.formal_verification import (
    FormalVerificationCertificate,
    StaticAnalysisReport,
    DynamicPropertyReport,
    VerificationVerdict,
)
from desk_gateway.synthesis_proving import (
    MultiSeatConsensusEngine,
    ProofReceiptLedger,
    CrossDeskProofExporter,
    FormalVerificationDrillSimulator,
    ReviewVote,
    PromotionState,
    ConsensusReceipt,
    SeatReviewBallot,
)


@pytest.fixture
def mock_certificate():
    return FormalVerificationCertificate(
        certificate_id="cert-unit-test-12345",
        tool_name="unit_tool",
        version="1.0.0",
        author_seat_id="systems",
        code_hash="abcdef0123456789",
        verdict=VerificationVerdict.PROVED,
        static_report=StaticAnalysisReport(
            is_sound=True,
            loop_termination_proved=True,
            memory_safety_proved=True,
            non_nullability_proved=True,
        ),
        dynamic_report=DynamicPropertyReport(
            total_trials=20,
            passed_trials=20,
            verdict=VerificationVerdict.PROVED,
        ),
        contracts_evaluated=2,
        attestation_signature="sig-1234567890",
    )


def test_merkle_proof_ledger_append_and_verify():
    ledger = ProofReceiptLedger()

    receipt_1 = ConsensusReceipt(
        consensus_id="c-1",
        certificate_id="cert-1",
        tool_name="tool_1",
        version="1.0.0",
        state=PromotionState.APPROVED,
        total_voting_weight=6.5,
        approval_weight=6.5,
        rejection_weight=0.0,
        threshold_required=3.9,
        ballots=[],
        aggregate_hash="hash-1",
    )
    receipt_2 = ConsensusReceipt(
        consensus_id="c-2",
        certificate_id="cert-2",
        tool_name="tool_2",
        version="1.0.0",
        state=PromotionState.REJECTED,
        total_voting_weight=6.5,
        approval_weight=2.0,
        rejection_weight=4.5,
        threshold_required=3.9,
        ballots=[],
        aggregate_hash="hash-2",
    )

    idx1 = ledger.append_receipt(receipt_1)
    idx2 = ledger.append_receipt(receipt_2)
    assert idx1 == 0
    assert idx2 == 1

    root = ledger.compute_root()
    assert isinstance(root, str)
    assert len(root) == 64

    # Verify Merkle proof for leaf 0
    proof_0 = ledger.generate_proof(0)
    assert proof_0.leaf_index == 0
    assert proof_0.root_hash == root
    assert ProofReceiptLedger.verify_proof(proof_0) is True

    # Verify Merkle proof for leaf 1
    proof_1 = ledger.generate_proof(1)
    assert ProofReceiptLedger.verify_proof(proof_1) is True


def test_multi_seat_consensus_engine_approval(mock_certificate):
    engine = MultiSeatConsensusEngine()
    session_id = engine.initiate_review(mock_certificate, threshold_ratio=0.60)

    # Cast ballots
    b_lead = engine.cast_ballot(session_id, "lead", ReviewVote.APPROVE, "All clear")
    b_quality = engine.cast_ballot(session_id, "quality", ReviewVote.APPROVE, "Security audit passed")
    b_systems = engine.cast_ballot(session_id, "systems", ReviewVote.APPROVE, "Performance validated")

    assert b_lead.signature != ""
    assert b_quality.weight == 2.5

    receipt = engine.tally_and_finalize(session_id)
    assert receipt.state == PromotionState.APPROVED
    assert receipt.approval_weight == 2.0 + 2.5 + 2.0  # 6.5
    assert len(receipt.ballots) == 3


def test_multi_seat_consensus_engine_rejection(mock_certificate):
    engine = MultiSeatConsensusEngine()
    session_id = engine.initiate_review(mock_certificate, threshold_ratio=0.60)

    engine.cast_ballot(session_id, "lead", ReviewVote.REJECT, "Architecture mismatch")
    engine.cast_ballot(session_id, "quality", ReviewVote.REJECT, "Boundary concern")
    engine.cast_ballot(session_id, "systems", ReviewVote.APPROVE, "Looks fine")

    receipt = engine.tally_and_finalize(session_id)
    assert receipt.state == PromotionState.REJECTED
    assert receipt.rejection_weight == 4.5
    assert receipt.approval_weight == 2.0


def test_cross_desk_proof_exporter():
    exporter = CrossDeskProofExporter()
    receipt = ConsensusReceipt(
        consensus_id="consensus-demo",
        certificate_id="cert-demo",
        tool_name="demo_tool",
        version="1.0.0",
        state=PromotionState.APPROVED,
        total_voting_weight=6.5,
        approval_weight=6.5,
        rejection_weight=0.0,
        threshold_required=3.9,
        ballots=[],
        aggregate_hash="agg-hash-demo",
    )
    anchor = exporter.export_solana_anchor(receipt, "merkle-root-demo-hash")
    assert anchor["target"] == "solana_devnet"
    assert anchor["status"] == "finalized"
    assert anchor["consensus_id"] == "consensus-demo"
    assert "merkle_root" in anchor


def test_formal_verification_drill_simulator():
    engine = MultiSeatConsensusEngine()
    drill = FormalVerificationDrillSimulator.run_synthesis_consensus_drill(engine)

    assert drill["all_drills_passed"] is True
    assert drill["sound_tool_verdict"] == "APPROVED"
    assert drill["flawed_tool_verdict"] == "REJECTED"
    assert drill["ledger_receipts_count"] >= 2
    assert "merkle_root" in drill
    assert drill["solana_anchor"]["target"] == "solana_devnet"
