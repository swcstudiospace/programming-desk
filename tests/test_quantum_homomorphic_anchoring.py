"""Unit and integration tests for Quantum Homomorphic Ledger & Solana Anchoring (Phase 85)."""

import pytest

from desk_gateway.quantum_homomorphic_anchoring import (
    QuantumHomomorphicAnchorExporter,
    QuantumHomomorphicDrillSimulator,
    QuantumHomomorphicLedger,
)


def test_quantum_homomorphic_ledger():
    ledger = QuantumHomomorphicLedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event(
        "circ-1",
        "QHE_GATE_EVAL",
        qubits_count=2,
        gates_evaluated=3,
        payload_data={"gate": "H", "keys": [1, 0]},
    )
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumHomomorphicAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 299327000


def test_quantum_homomorphic_drill_simulator():
    drill = QuantumHomomorphicDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_qubit_encryption"] is True
    assert drill["step2_clifford_evaluation"] is True
    assert drill["step3_cnot_entanglement"] is True
    assert drill["step4_t_gate_correction"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
