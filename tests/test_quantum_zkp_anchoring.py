"""Unit and integration tests for Quantum ZKP Ledger & Solana Anchoring (Phase 83)."""

import pytest

from desk_gateway.quantum_zkp_anchoring import (
    QuantumZKPAnchorExporter,
    QuantumZKPDrillSimulator,
    QuantumZKPLedger,
)


def test_quantum_zkp_ledger():
    ledger = QuantumZKPLedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event(
        "session-1",
        "QZKP_PROOF",
        "prover",
        "verifier",
        0.985,
        {"challenge": "X", "parity": 0},
    )
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumZKPAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 299216000


def test_quantum_zkp_drill_simulator():
    drill = QuantumZKPDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_witness_prep"] is True
    assert drill["step2_commitment_exchange"] is True
    assert drill["step3_verifier_challenge"] is True
    assert drill["step4_prover_verification"] is True
    assert drill["step5_solana_anchoring"] is True
    assert drill["soundness_score"] >= 0.90
    assert len(drill["final_merkle_root"]) == 64
