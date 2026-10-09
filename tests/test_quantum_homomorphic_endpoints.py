"""Integration tests for Milestone v5.9 Quantum Homomorphic Encryption REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_homomorphic_qubit_and_gates(client):
    # 1. Encrypt qubit 0 and qubit 1
    r0 = client.post("/v1/quantum/homomorphic/qubit/encrypt", json={
        "qubit_index": 0,
        "alpha": {"real": 1.0, "imag": 0.0},
        "beta": {"real": 0.0, "imag": 0.0},
    })
    assert r0.status_code == 200
    assert r0.json()["ok"] is True
    assert "receipt" in r0.json()

    r1 = client.post("/v1/quantum/homomorphic/qubit/encrypt", json={
        "qubit_index": 1,
        "alpha": {"real": 0.0, "imag": 0.0},
        "beta": {"real": 1.0, "imag": 0.0},
    })
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # 2. Apply Hadamard to qubit 0
    h_resp = client.post("/v1/quantum/homomorphic/gate/apply", json={
        "gate_type": "H",
        "qubit_index": 0,
    })
    assert h_resp.status_code == 200
    assert h_resp.json()["ok"] is True
    assert h_resp.json()["evaluation"]["gate"] == "H"

    # 3. Apply CNOT between 0 and 1
    cnot_resp = client.post("/v1/quantum/homomorphic/gate/apply", json={
        "gate_type": "CNOT",
        "qubit_index": 0,
        "target_index": 1,
    })
    assert cnot_resp.status_code == 200
    assert cnot_resp.json()["ok"] is True
    assert cnot_resp.json()["evaluation"]["gate"] == "CNOT"

    # 4. Apply T gate to qubit 1
    t_resp = client.post("/v1/quantum/homomorphic/gate/apply", json={
        "gate_type": "T",
        "qubit_index": 1,
    })
    assert t_resp.status_code == 200
    assert t_resp.json()["ok"] is True
    assert "correction" in t_resp.json()["evaluation"]


def test_rest_quantum_homomorphic_anchor_and_drill(client):
    # Anchor export
    anchor_resp = client.post("/v1/quantum/homomorphic/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # Drill simulate
    drill_resp = client.post("/v1/quantum/homomorphic/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
