"""Integration tests for ZK Proving & Privacy-Preserving REST routes in desk-gateway (Milestone v4.4)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_zk_proof_routes(client):
    # 1. Synthesize Circuit
    resp = client.post(
        "/v1/zk/circuits/synthesize",
        json={
            "circuit_id": "test-mult-circuit",
            "name": "Multiplier",
            "public_wires": ["one", "a", "c"],
            "private_wires": ["b"],
            "constraints": [
                {
                    "constraint_id": "c_mul",
                    "a": {"a": 1.0},
                    "b": {"b": 1.0},
                    "c": {"c": 1.0},
                }
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 2. Generate Proof
    proof_resp = client.post(
        "/v1/zk/proof/generate",
        json={
            "circuit_id": "test-mult-circuit",
            "public_inputs": {"a": 4.0, "c": 20.0},
            "private_witness": {"b": 5.0},
            "proof_type": "GROTH16",
        },
    )
    assert proof_resp.status_code == 200
    proof_data = proof_resp.json()["proof"]

    # 3. Verify Proof
    verify_resp = client.post(
        "/v1/zk/proof/verify",
        json={
            "circuit_id": "test-mult-circuit",
            "proof": proof_data,
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["receipt"]["is_valid"] is True


def test_privacy_and_drill_routes(client):
    # 1. Homomorphic addition
    homo_resp = client.post(
        "/v1/privacy/homomorphic/add",
        json={"val1": 33, "val2": 67},
    )
    assert homo_resp.status_code == 200
    assert homo_resp.json()["decrypted_sum"] == 100

    # 2. TSS Split
    tss_resp = client.post(
        "/v1/privacy/tss/split",
        json={"secret": 554433, "threshold": 2, "total_shares": 4},
    )
    assert tss_resp.status_code == 200
    assert len(tss_resp.json()["shares"]) == 4

    # 3. MPC Infer
    mpc_resp = client.post(
        "/v1/privacy/mpc/infer",
        json={
            "session_id": "mpc-test-gateway",
            "seat_inputs": {
                "lead": [1.0, 2.0],
                "systems": [3.0, 4.0],
                "infra": [2.0, 6.0],
            },
            "weights": [0.5, 1.5],
        },
    )
    assert mpc_resp.status_code == 200
    assert abs(mpc_resp.json()["prediction"] - 7.0) < 1e-5

    # 4. ZK Drill Simulate
    drill_resp = client.post("/v1/zk/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["drill"]["drill_status"] == "SUCCESS"
