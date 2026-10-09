"""Unit and integration tests for Quantum Model Ledger & Solana Anchoring (Phase 81)."""

import pytest

from desk_gateway.quantum_ml_anchoring import (
    QuantumMLDrillSimulator,
    QuantumModelAnchorExporter,
    QuantumModelLedger,
)


def test_quantum_model_ledger():
    ledger = QuantumModelLedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event("QNN_WEIGHTS_UPDATE", "model-1", 0.05, [0.1, 0.2, 0.3], {"epoch": 1})
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumModelAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 299105000


def test_quantum_ml_drill_simulator():
    drill = QuantumMLDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_forward_inference"] is True
    assert drill["step2_parameter_shift_training"] is True
    assert drill["step3_model_checkpoint_receipt"] is True
    assert drill["step4_prediction_improvement"] is True
    assert drill["step5_solana_anchoring"] is True
    assert drill["final_loss"] < drill["initial_loss"]
    assert len(drill["final_merkle_root"]) == 64
