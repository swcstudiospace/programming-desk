"""Unit and integration tests for QCA Ledger & Solana Anchoring (Phase 87)."""

import pytest

from desk_gateway.quantum_cellular_automata_anchoring import (
    QCAAnchorExporter,
    QCADrillSimulator,
    QCALedger,
)


def test_qca_ledger():
    ledger = QCALedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event(
        "QUANTUM_WALK",
        steps_executed=5,
        metric=12.5,
        payload_data={"steps": 5, "variance": 12.5},
    )
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QCAAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 299438000


def test_qca_drill_simulator():
    drill = QCADrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_quantum_walk"] is True
    assert drill["step2_ballistic_speedup"] is True
    assert drill["step3_margolus_qca"] is True
    assert drill["step4_merkle_receipts"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
