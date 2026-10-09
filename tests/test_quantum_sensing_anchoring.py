"""Unit and integration tests for Quantum Sensing Ledger & Solana Anchoring (Phase 79)."""

import pytest

from desk_gateway.quantum_sensing_mesh import QuantumClockSynchronizer
from desk_gateway.quantum_sensing_anchoring import (
    QuantumSensingAnchorExporter,
    QuantumSensingDrillSimulator,
    QuantumSensingLedger,
)


def test_quantum_sensing_ledger():
    ledger = QuantumSensingLedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event("NOON_ESTIMATION", "desk-alpha", 2.5, {"photons": 16})
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumSensingAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 298993000


def test_quantum_sensing_drill_simulator():
    drill = QuantumSensingDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_noon_metrology"] is True
    assert drill["step2_metrology_ledger"] is True
    assert drill["step3_clock_sync"] is True
    assert drill["step4_clock_ledger"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
