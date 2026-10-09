"""Integration tests for Milestone v5.5 Quantum Consensus REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_consensus_coin_flip(client):
    resp = client.post("/v1/quantum/consensus/coin/flip", json={
        "round_id": "round-test-1",
        "nodes": ["desk-alpha", "desk-beta"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["coin"]["coin_value"] in (0, 1)


def test_rest_quantum_consensus_round_and_agreement(client):
    # 1. Start round
    start_resp = client.post("/v1/quantum/consensus/round/start", json={
        "nodes": ["desk-alpha", "desk-beta", "desk-gamma"],
    })
    assert start_resp.status_code == 200
    round_id = start_resp.json()["round"]["round_id"]

    # 2. Submit proposals
    client.post("/v1/quantum/consensus/proposal/submit", json={
        "round_id": round_id,
        "node": "desk-alpha",
        "proposal": "VALID_STATE_ROOT",
    })
    client.post("/v1/quantum/consensus/proposal/submit", json={
        "round_id": round_id,
        "node": "desk-beta",
        "proposal": "VALID_STATE_ROOT",
    })
    client.post("/v1/quantum/consensus/proposal/submit", json={
        "round_id": round_id,
        "node": "desk-gamma",
        "proposal": "INVALID_STATE_ROOT",
    })

    # 3. Execute agreement
    exec_resp = client.post("/v1/quantum/consensus/agreement/execute", json={
        "round_id": round_id,
    })
    assert exec_resp.status_code == 200
    res_data = exec_resp.json()
    assert res_data["ok"] is True
    assert res_data["round"]["decision"] == "VALID_STATE_ROOT"
    assert "receipt" in res_data


def test_rest_quantum_consensus_arbitrate_anchor_and_drill(client):
    # 1. Arbitrate
    arb_resp = client.post("/v1/quantum/consensus/arbitrate", json={
        "conflicting_seats": ["desk-alpha", "desk-beta"],
        "resource_id": "res-queue-0",
    })
    assert arb_resp.status_code == 200
    arb_data = arb_resp.json()
    assert arb_data["ok"] is True
    assert arb_data["arbitration"]["awarded_seat"] in ["desk-alpha", "desk-beta"]
    assert "receipt" in arb_data

    # 2. Export anchor
    anchor_resp = client.post("/v1/quantum/consensus/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # 3. Simulate drill
    drill_resp = client.post("/v1/quantum/consensus/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
