"""Unit and integration tests for CV Entanglement Swapping, Memory Ledger & Solana Anchoring (Phase 71)."""

import pytest

from desk_gateway.quantum_memory_mesh import (
    CVOpticalRouter,
    QuantumMemoryBufferType,
    QuantumMemoryNode,
)
from desk_gateway.quantum_cv_anchoring import (
    CVEntanglementSwapper,
    QuantumMemoryAnchorExporter,
    QuantumMemoryDrillSimulator,
    QuantumMemoryLedger,
)


def test_cv_entanglement_swapping():
    router = CVOpticalRouter()
    swapper = CVEntanglementSwapper(router)

    res = swapper.swap_cv_entanglement(
        node_a="desk-alpha",
        repeater_node="repeater-1",
        node_b="desk-beta",
        squeezing_r=1.2,
        detector_efficiency=0.98,
    )

    assert res["session_id"].startswith("cv-swap-")
    assert res["node_a"] == "desk-alpha"
    assert res["repeater_node"] == "repeater-1"
    assert res["node_b"] == "desk-beta"
    assert res["is_entangled"] is True
    assert res["duan_inseparability_value"] < 2.0
    assert res["swapped_fidelity"] > 0.70


def test_quantum_memory_ledger_merkle_integrity():
    ledger = QuantumMemoryLedger()
    assert len(ledger.calculate_merkle_root()) == 64

    r1 = ledger.append_event("MEMORY_STORE", "desk-alpha", ["desk-alpha"], 0.98, {"item": 1})
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(root_1) == 64

    r2 = ledger.append_event("CV_HOMODYNE_MEASUREMENT", "desk-alpha", ["desk-alpha"], 0.95, {"val": 0.42})
    root_2 = ledger.calculate_merkle_root()
    assert root_2 != root_1
    assert len(ledger.receipts) == 2


def test_quantum_memory_anchor_exporter():
    ledger = QuantumMemoryLedger()
    ledger.append_event("MEMORY_STORE", "desk-alpha", ["desk-alpha"], 0.99, {"test": True})
    exporter = QuantumMemoryAnchorExporter()

    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["slot"] >= 298582000
    assert anchor["event_count"] == 1
    assert anchor["merkle_root"] == ledger.calculate_merkle_root()


def test_quantum_memory_drill_simulator():
    drill = QuantumMemoryDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["mem_step"]["success"] is True
    assert drill["sqz_step"]["success"] is True
    assert drill["bs_step"]["success"] is True
    assert drill["swap_step"]["success"] is True
    assert drill["anchor_step"]["success"] is True
    assert drill["ledger_receipts_count"] >= 3
    assert len(drill["final_merkle_root"]) == 64
