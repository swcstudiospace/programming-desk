"""Tests for Quantum Reservoir Computing (QRC) & QELM Mesh (Milestone v6.3 - Phases 92 & 93)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_reservoir_comp_mesh import (
    QuantumExtremeLearningMachine,
    QuantumReservoirNode,
    QuantumReservoirState,
)
from desk_gateway.quantum_reservoir_comp_anchoring import (
    QuantumReservoirMerkleLedger,
    QuantumReservoirReceipt,
    QuantumReservoirSolanaAnchorExporter,
    QuantumReservoirVerificationDrill,
)
from desk_gateway.server import build_app


def test_quantum_reservoir_node_dynamics():
    node = QuantumReservoirNode(num_qubits=4, coupling_strength=0.8)
    assert node.num_qubits == 4
    assert len(node.J_couplings) == 6  # 4 * 3 / 2 = 6 pairs

    # Inject input sequence
    inputs = [0.2, -0.4, 0.6, 0.1]
    states = []
    for u in inputs:
        st = node.inject_input(u)
        assert isinstance(st, QuantumReservoirState)
        assert len(st.spin_expectations) == 4
        assert len(st.pairwise_correlations) == 6
        assert st.reservoir_entropy >= 0.0
        states.append(st)

    assert node.current_step == 4
    # Ensure dynamics are non-trivial
    assert states[0].spin_expectations != states[1].spin_expectations


def test_quantum_elm_regression():
    # Synthetic dataset
    X = [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
        [-0.2, 0.1, 0.0],
        [0.8, -0.1, 0.5],
        [0.3, 0.3, 0.3],
    ]
    y = [0.5, 1.1, -0.1, 1.2, 0.7]

    elm = QuantumExtremeLearningMachine(feature_dim=3, regularization=1e-3)
    weights = elm.fit(X, y)
    assert len(weights) == 3

    # Prediction
    pred = elm.predict([0.1, 0.2, 0.3])
    assert abs(pred - 0.5) < 0.2


def test_quantum_reservoir_ledger_and_receipt():
    ledger = QuantumReservoirMerkleLedger()
    empty_root = ledger.get_merkle_root()
    assert len(empty_root) == 64

    rcpt1 = QuantumReservoirReceipt(
        receipt_id="r1",
        num_qubits=4,
        num_steps=10,
        mean_reservoir_entropy=0.82,
        readout_norm=1.45,
        prediction_mse=0.012,
        state_merkle_root="abc1",
    )
    h1 = ledger.add_receipt(rcpt1)
    assert h1 == rcpt1.compute_hash()
    assert ledger.get_merkle_root() == h1

    rcpt2 = QuantumReservoirReceipt(
        receipt_id="r2",
        num_qubits=4,
        num_steps=20,
        mean_reservoir_entropy=0.79,
        readout_norm=1.80,
        prediction_mse=0.009,
        state_merkle_root="abc2",
    )
    ledger.add_receipt(rcpt2)
    root2 = ledger.get_merkle_root()
    assert root2 != h1
    assert len(root2) == 64


def test_quantum_reservoir_solana_exporter():
    exporter = QuantumReservoirSolanaAnchorExporter()
    program = exporter.export_anchor_program()
    assert "quantum_reservoir_anchoring" in program
    assert "record_reservoir_root" in program

    payload = exporter.generate_instruction_payload(
        merkle_root="11" * 32,
        num_receipts=2,
        mean_entropy=0.85,
        prediction_mse=0.005,
    )
    assert payload["program_id"] == "QRes111111111111111111111111111111111111111"
    assert payload["mean_entropy_scaled"] == 850000
    assert payload["prediction_mse_scaled"] == 5000


def test_quantum_reservoir_verification_drill():
    drill = QuantumReservoirVerificationDrill(num_qubits=4)
    res = drill.run_drill()
    assert res["passed"] is True
    assert "stage_1_dynamics" in res["stages"]
    assert "stage_2_memory_capacity" in res["stages"]
    assert "stage_3_prediction_mse" in res["stages"]
    assert "stage_4_merkle_ledger" in res["stages"]
    assert "stage_5_solana_anchoring" in res["stages"]


def test_quantum_reservoir_http_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Step route
    resp = client.post("/v1/quantum/reservoir/step", json={"input_val": 0.75})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "spin_expectations" in data["state"]

    # 2. Train route
    resp = client.post(
        "/v1/quantum/reservoir/elm/train",
        json={"inputs": [0.1, -0.3, 0.5, 0.2], "targets": [0.2, -0.1, 0.4, 0.3]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "weights" in data
    assert "merkle_root" in data

    # 3. Anchor export route
    resp = client.post("/v1/quantum/reservoir/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["anchor"]["instruction"] == "record_reservoir_root"

    # 4. Drill simulate route
    resp = client.post("/v1/quantum/reservoir/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["drill"]["passed"] is True
