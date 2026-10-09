"""Integration tests for Quantum-Classical Hybrid Mesh REST Endpoints (Milestone v5.0)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_quantum_circuit_simulate_route(client):
    # Test Bell state synthesis via circuit simulate endpoint
    resp = client.post(
        "/v1/quantum/circuit/simulate",
        json={
            "num_qubits": 2,
            "gates": [
                {"gate_type": "H", "target_qubits": [0]},
                {"gate_type": "CNOT", "target_qubits": [0, 1]},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["circuit"]["num_qubits"] == 2
    assert data["circuit"]["gate_count"] == 2
    # Probabilities for Bell state: [0.5, 0.0, 0.0, 0.5]
    probs = data["circuit"]["probabilities"]
    assert probs[0] == pytest.approx(0.5)
    assert probs[3] == pytest.approx(0.5)


def test_quantum_vqe_solve_route(client):
    resp = client.post(
        "/v1/quantum/vqe/solve",
        json={
            "num_qubits": 2,
            "hamiltonian_terms": [
                {"coefficient": -1.0, "pauli_string": "Z Z"},
                {"coefficient": 0.5, "pauli_string": "X X"},
            ],
            "layers": 1,
            "max_iterations": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["vqe"]["converged"] is True
    assert "ground_state_energy" in data["vqe"]


def test_quantum_qaoa_partition_route(client):
    resp = client.post(
        "/v1/quantum/qaoa/partition",
        json={
            "num_qubits": 3,
            "edges": [[[0, 1], 1.0], [[1, 2], 1.0]],
            "gammas": [0.3],
            "betas": [0.4],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["qaoa"]["optimal_bitstring"]) == 3


def test_quantum_schedule_dispatch_route(client):
    resp = client.post(
        "/v1/quantum/schedule/dispatch",
        json={
            "task_name": "qaoa-scheduling-pass",
            "circuit_type": "combinatorial-mixer",
            "num_qubits": 4,
            "params": {"nodes": 4},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["task"]["task_id"].startswith("qtask-")


def test_quantum_surface_code_syndrome_route(client):
    resp = client.post(
        "/v1/quantum/surface-code/syndrome",
        json={
            "distance": 3,
            "inject_errors": [{"row": 1, "col": 1, "error": "X"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["defects_count"] > 0
    assert len(data["corrections"]) > 0
    assert data["resolved"] is True
    assert "receipt" in data


def test_quantum_anchor_and_drill_routes(client):
    # Anchor export
    r1 = client.post("/v1/quantum/anchor/export")
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True
    assert d1["anchor"]["status"] == "CONFIRMED_ON_SOLANA_DEVNET"

    # Drill simulate
    r2 = client.post("/v1/quantum/drill/simulate")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["drill"]["drill_status"] == "ALL_CHECKS_PASSED"
