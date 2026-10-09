"""Integration tests for Milestone v5.8 Quantum Zero-Knowledge Proof REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_zkp_interactive_proof(client):
    # 1. Init session
    init_resp = client.post("/v1/quantum/zkp/session/init", json={
        "prover_node": "desk-alpha",
        "verifier_node": "verifier-beta",
        "qubits_count": 3,
        "stabilizers": ["+XXX", "+ZZI", "+IZZ"],
        "fidelity": 0.98,
    })
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["ok"] is True
    session_id = init_data["session"]["session_id"]
    assert "receipt" in init_data

    # 2. Challenge
    chal_resp = client.post("/v1/quantum/zkp/challenge/generate", json={
        "session_id": session_id,
    })
    assert chal_resp.status_code == 200
    chal_data = chal_resp.json()
    assert chal_data["ok"] is True
    basis = chal_data["challenge_basis"]
    assert basis in ("X", "Y", "Z")

    # 3. Verify proof
    verify_resp = client.post("/v1/quantum/zkp/proof/verify", json={
        "session_id": session_id,
        "challenge_basis": basis,
    })
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["ok"] is True
    assert v_data["proof"]["verified"] is True
    assert "receipt" in v_data


def test_rest_quantum_zkp_anchor_and_drill(client):
    # Anchor
    anchor_resp = client.post("/v1/quantum/zkp/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # Drill
    drill_resp = client.post("/v1/quantum/zkp/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
