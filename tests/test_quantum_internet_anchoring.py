"""Unit and integration tests for Quantum Internet Slicing, Merkle Ledger & Solana Anchoring (Phase 75)."""

import pytest

from desk_gateway.quantum_internet_mesh import EntanglementRoutingEngine
from desk_gateway.quantum_internet_anchoring import (
    QuantumInternetAnchorExporter,
    QuantumInternetDrillSimulator,
    QuantumInternetLedger,
    QuantumVirtualNetworkSlice,
)


def test_quantum_virtual_network_slice():
    q_slice = QuantumVirtualNetworkSlice(
        slice_id="qslice-01",
        tenant_id="tenant-1",
        allocated_ebits_sec=1000,
        min_fidelity_guarantee=0.92,
        nodes_included=["desk-alpha", "q-router-1", "desk-beta"],
    )
    data = q_slice.to_dict()
    assert data["slice_id"] == "qslice-01"
    assert data["allocated_ebits_sec"] == 1000
    assert data["active"] is True


def test_quantum_internet_ledger_merkle_root():
    ledger = QuantumInternetLedger()
    root_genesis = ledger.calculate_merkle_root()
    assert len(root_genesis) == 64

    r1 = ledger.append_event("PACKET_FORWARD", "desk-alpha", "desk-beta", 0.95, {"hops": 3})
    root_1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root_1
    assert len(ledger.receipts) == 1

    exporter = QuantumInternetAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root_1
    assert anchor["slot"] >= 298789000


def test_quantum_internet_drill_simulator():
    drill = QuantumInternetDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_topology_build"] is True
    assert drill["step2_path_computation"] is True
    assert drill["step3_packet_dispatch"] is True
    assert drill["step4_virtual_slicing"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
