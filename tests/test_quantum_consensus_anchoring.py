"""Unit and integration tests for Quantum Arbitration, Consensus Ledger & Solana Anchoring (Phase 77)."""

import pytest

from desk_gateway.quantum_consensus_mesh import QuantumCoinFlipper
from desk_gateway.quantum_consensus_anchoring import (
    EntanglementArbitrationEngine,
    QuantumConsensusAnchorExporter,
    QuantumConsensusDrillSimulator,
    QuantumConsensusLedger,
)


def test_entanglement_arbitration():
    flipper = QuantumCoinFlipper()
    arbitrator = EntanglementArbitrationEngine(flipper)

    conflicting = ["desk-alpha", "desk-beta", "desk-gamma"]
    res = arbitrator.arbitrate_seats(conflicting, "resource-vps-1")

    assert res["awarded_seat"] in conflicting
    assert res["arbitration_method"] == "ENTANGLEMENT_CORRELATION"
    assert "quantum_coin" in res


def test_quantum_consensus_ledger_merkle_root():
    ledger = QuantumConsensusLedger()
    root_0 = ledger.calculate_merkle_root()
    assert len(root_0) == 64

    r1 = ledger.append_event("round-1", "PROPOSAL_A", ["desk-alpha", "desk-beta"], 1, {"test": 1})
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumConsensusAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 298892000


def test_quantum_consensus_drill_simulator():
    drill = QuantumConsensusDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_quantum_coin"] is True
    assert drill["step2_byzantine_agreement"] is True
    assert drill["step3_ledger_receipt"] is True
    assert drill["step4_entanglement_arbitration"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
