"""Unit tests for Phase 45: Lattice-Attested Multi-Desk Ledger & Quantum-Resistant Audit Anchors."""

import pytest
from desk_gateway.post_quantum import (
    HybridSignatureEngine,
)
from desk_gateway.lattice_ledger import (
    PQCMerkleLedger,
    PQCIdentityAuthority,
    CrossDeskLatticeVerifier,
    PQCAnchorExporter,
    QuantumAttackDrillSimulator,
)


def test_pqc_merkle_ledger_and_integrity():
    ledger = PQCMerkleLedger()

    e1 = ledger.append_entry("desk-east", "register_skill", {"name": "quantum_audit"})
    e2 = ledger.append_entry("desk-west", "vote_governance", {"proposal_id": "prop-1"})

    assert len(ledger.entries) == 2
    assert e2.previous_hash == e1.compute_leaf_hash()

    root = ledger.compute_merkle_root()
    assert len(root) == 64
    assert ledger.verify_ledger_integrity() is True

    # Tamper test
    ledger.entries[0].action = "tampered_action"
    assert ledger.verify_ledger_integrity() is False


def test_pqc_identity_authority_and_lattice_verifier():
    ca = PQCIdentityAuthority()
    verifier = CrossDeskLatticeVerifier(ca)

    passport = ca.issue_passport(seat_id="lead", desk_id="desk-primary-1", roles=["LEAD", "PQC_OPERATOR"])
    assert passport.seat_id == "lead"
    assert ca.verify_passport(passport) is True

    # Verifier validation
    v_res = verifier.verify_remote_peer(passport)
    assert v_res["verified"] is True
    assert v_res["quantum_level"] == "HYBRID_LATTICE_NIST_L3"

    # Multi-seat quorum
    passports = [
        passport,
        ca.issue_passport(seat_id="systems", desk_id="desk-primary-1"),
        ca.issue_passport(seat_id="quality", desk_id="desk-primary-1"),
    ]
    assert verifier.verify_multi_seat_quorum(passports, min_required=3) is True


def test_pqc_anchor_exporter_and_drill_simulator():
    ledger = PQCMerkleLedger()
    ledger.append_entry("desk-eu", "checkpoint", {"status": "ok"})

    exporter = PQCAnchorExporter()
    anchor = exporter.export_anchor(ledger)

    assert anchor["status"] == "CONFIRMED"
    assert anchor["entry_count"] == 1
    assert "solana_devnet" in anchor["target"]

    # Drill simulator
    drill = QuantumAttackDrillSimulator.run_quantum_attack_drill()
    assert drill["status"] == "PASS"
    assert drill["test_cases"]["downgrade_attack_mitigation"]["passed"] is True
    assert drill["test_cases"]["classical_tamper_rejection"]["passed"] is True
    assert drill["test_cases"]["lattice_tamper_rejection"]["passed"] is True
    assert drill["test_cases"]["session_replay_mitigation"]["passed"] is True
    assert drill["test_cases"]["merkle_ledger_immutability"]["passed"] is True
