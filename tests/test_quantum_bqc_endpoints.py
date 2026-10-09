"""Integration tests for Milestone v5.3 Blind Quantum Computing REST endpoints."""

import math
import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_bqc_session_and_step_execution(client):
    # 1. Init session
    init_resp = client.post("/v1/quantum/bqc/session/init", json={
        "client_node": "desk-alpha",
        "server_node": "untrusted-server",
        "layers": 2,
        "qubits_per_layer": 3,
    })
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert init_data["ok"] is True
    session_id = init_data["session"]["session_id"]
    assert "receipt" in init_data

    # 2. Execute step
    step_resp = client.post("/v1/quantum/bqc/step/execute", json={
        "session_id": session_id,
        "target_qubit": 0,
        "target_angle_rad": math.pi / 4.0,
    })
    assert step_resp.status_code == 200
    step_data = step_resp.json()
    assert step_data["ok"] is True
    assert step_data["step"]["target_qubit"] == 0
    assert "server_received_theta" in step_data["step"]
    assert "client_unblinded_outcome" in step_data["step"]


def test_rest_bqc_qss_split_and_reconstruct(client):
    split_resp = client.post("/v1/quantum/bqc/qss/split", json={
        "secret": 777,
        "threshold_t": 3,
        "num_shares_n": 5,
    })
    assert split_resp.status_code == 200
    split_data = split_resp.json()
    assert split_data["ok"] is True
    shares = split_data["shares"]
    assert len(shares) == 5

    recon_resp = client.post("/v1/quantum/bqc/qss/reconstruct", json={
        "shares": [shares[0], shares[2], shares[3]],
    })
    assert recon_resp.status_code == 200
    recon_data = recon_resp.json()
    assert recon_data["ok"] is True
    assert recon_data["reconstructed_secret"] == 777


def test_rest_bqc_anchor_and_drill(client):
    # Anchor export
    anchor_resp = client.post("/v1/quantum/bqc/anchor/export")
    assert anchor_resp.status_code == 200
    anchor_data = anchor_resp.json()
    assert anchor_data["ok"] is True
    assert anchor_data["anchor"]["status"] == "confirmed"

    # Drill simulate
    drill_resp = client.post("/v1/quantum/bqc/drill/simulate")
    assert drill_resp.status_code == 200
    drill_data = drill_resp.json()
    assert drill_data["ok"] is True
    assert drill_data["drill"]["all_passed"] is True
