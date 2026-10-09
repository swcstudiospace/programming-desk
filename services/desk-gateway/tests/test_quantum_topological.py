"""Tests for Topological Quantum Computing & Anyonic Braiding Mesh (Milestone v6.4 - Phases 94 & 95)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_anyon_braiding_mesh import (
    AnyonSpecies,
    BraidOperation,
    NonAbelianAnyon,
    QuantumTopologicalBraidingMesh,
    TopologicalProtectedQubit,
)
from desk_gateway.quantum_anyon_braiding_anchoring import (
    TopologicalBraidMerkleLedger,
    TopologicalBraidReceipt,
    TopologicalSolanaAnchorExporter,
    TopologicalVerificationDrill,
)
from desk_gateway.server import build_app


def test_anyon_properties_and_r_matrix():
    mesh = QuantumTopologicalBraidingMesh(species=AnyonSpecies.MAJORANA)
    r_mat = mesh.engine.compute_r_matrix(clockwise=True)
    assert len(r_mat) == 2
    assert len(r_mat[0]) == 2
    # Diagonal check
    assert abs(r_mat[0][1]) == 0.0
    assert abs(r_mat[1][0]) == 0.0
    # Unitary phase check
    assert abs(abs(r_mat[0][0]) - 1.0) < 1e-6
    assert abs(abs(r_mat[1][1]) - 1.0) < 1e-6

    # Fibonacci anyon check
    fib_mesh = QuantumTopologicalBraidingMesh(species=AnyonSpecies.FIBONACCI_TAU)
    fib_r = fib_mesh.engine.compute_r_matrix(clockwise=True)
    fib_f = fib_mesh.engine.compute_f_matrix()
    assert len(fib_r) == 2
    assert len(fib_f) == 2
    assert fib_mesh.engine.verify_yang_baxter() is True


def test_topological_qubit_creation_and_braiding():
    mesh = QuantumTopologicalBraidingMesh(species=AnyonSpecies.MAJORANA)
    qubit = mesh.create_qubit("topo-q1")
    assert qubit.qubit_id == "topo-q1"
    assert len(qubit.anyon_ids) == 4
    assert qubit.braid_depth == 0
    assert qubit.fidelity >= 0.999

    # Apply braid sigma_1
    q_braided = mesh.apply_braid("topo-q1", generator_index=1, clockwise=True)
    assert q_braided.braid_depth == 1
    assert len(mesh.braid_history) == 1

    # Apply braid sigma_2 (mixing)
    mesh.apply_braid("topo-q1", generator_index=2, clockwise=True)
    assert q_braided.braid_depth == 2

    # Measure topological charge parity
    meas = mesh.measure_topological_charge("topo-q1")
    assert meas["qubit_id"] == "topo-q1"
    assert meas["measured_parity"] in (0, 1)
    assert meas["topological_protection_intact"] is True


def test_topological_merkle_ledger():
    ledger = TopologicalBraidMerkleLedger()
    root_empty = ledger.get_merkle_root()
    assert len(root_empty) == 64

    rcpt1 = TopologicalBraidReceipt(
        receipt_id="rcpt-topo-01",
        qubit_id="topo-q0",
        species="majorana",
        num_braids=2,
        braid_depth=2,
        final_fidelity=0.9998,
        measured_parity=0,
        state_merkle_root="abc123state",
    )
    root1 = ledger.add_receipt(rcpt1)
    assert root1 != root_empty
    assert ledger.verify_receipt("rcpt-topo-01") is True

    rcpt2 = TopologicalBraidReceipt(
        receipt_id="rcpt-topo-02",
        qubit_id="topo-q0",
        species="majorana",
        num_braids=3,
        braid_depth=3,
        final_fidelity=0.9997,
        measured_parity=1,
        state_merkle_root="def456state",
    )
    root2 = ledger.add_receipt(rcpt2)
    assert root2 != root1


def test_topological_solana_anchor_exporter():
    payload = TopologicalSolanaAnchorExporter.generate_instruction_payload(
        merkle_root="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        num_receipts=5,
        qubit_id="topo-test",
        final_fidelity=0.9995,
    )
    assert payload["instruction"] == "record_braiding_root"
    assert payload["data"]["num_receipts"] == 5
    assert payload["data"]["final_fidelity_bps"] == 9995

    idl_str = TopologicalSolanaAnchorExporter.export_anchor_program()
    assert "pub mod topological_braid_anchoring" in idl_str
    assert "TopologicalLedgerAccount" in idl_str


def test_topological_verification_drill():
    drill = TopologicalVerificationDrill(species=AnyonSpecies.MAJORANA)
    res = drill.run_drill()
    assert res["passed"] is True
    assert "stage_1_encoding" in res["stages"]
    assert "stage_2_braiding" in res["stages"]
    assert "stage_3_yang_baxter_consistency" in res["stages"]
    assert "stage_4_merkle_ledger" in res["stages"]
    assert "stage_5_solana_anchoring" in res["stages"]


def test_topological_http_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Create qubit route
    resp = client.post("/v1/quantum/topological/qubit/create", json={"qubit_id": "test-topo-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["qubit"]["qubit_id"] == "test-topo-01"

    # 2. Braid route
    resp = client.post(
        "/v1/quantum/topological/braid",
        json={"qubit_id": "test-topo-01", "generator_index": 1, "clockwise": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["qubit"]["braid_depth"] >= 1
    assert "receipt" in data
    assert "merkle_root" in data

    # 3. Charge measure route
    resp = client.post("/v1/quantum/topological/charge/measure", json={"qubit_id": "test-topo-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "measured_parity" in data["charge"]

    # 4. Anchor export route
    resp = client.post("/v1/quantum/topological/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["anchor"]["instruction"] == "record_braiding_root"

    # 5. Drill simulate route
    resp = client.post("/v1/quantum/topological/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["drill"]["passed"] is True
