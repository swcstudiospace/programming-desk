"""Integration tests for Milestone v5.1 Quantum Teleportation and QKD REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_bell_pair_create_and_purify(client):
    # 1. Create two pairs
    r1 = client.post("/v1/quantum/teleportation/bell-pair/create", json={
        "node_a": "desk-alpha",
        "node_b": "desk-beta",
        "state_type": "PHI_PLUS",
        "initial_fidelity": 0.91,
    })
    assert r1.status_code == 200
    p1 = r1.json()["bell_pair"]

    r2 = client.post("/v1/quantum/teleportation/bell-pair/create", json={
        "node_a": "desk-alpha",
        "node_b": "desk-beta",
        "state_type": "PHI_PLUS",
        "initial_fidelity": 0.93,
    })
    assert r2.status_code == 200
    p2 = r2.json()["bell_pair"]

    # 2. Purify
    r_pur = client.post("/v1/quantum/teleportation/purify", json={
        "pair_id_1": p1["pair_id"],
        "pair_id_2": p2["pair_id"],
    })
    assert r_pur.status_code == 200
    res_pur = r_pur.json()
    assert res_pur["ok"] is True
    assert res_pur["purified_pair"]["fidelity"] > 0.91


def test_rest_quantum_repeater_route(client):
    resp = client.post("/v1/quantum/repeater/route", json={
        "node_path": ["desk-alpha", "repeater-1", "desk-beta"],
        "base_fidelity": 0.98,
        "purify": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["bell_pair"]["node_a"] == "desk-alpha"
    assert data["bell_pair"]["node_b"] == "desk-beta"
    assert len(data["logs"]) > 0


def test_rest_quantum_teleportation(client):
    resp = client.post("/v1/quantum/teleportation/teleport", json={
        "source_node": "desk-alpha",
        "target_node": "desk-gamma",
        "alpha": {"real": 0.6, "imag": 0.0},
        "beta": {"real": 0.8, "imag": 0.0},
        "intermediate_hops": ["repeater-1"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["result"]["success"] is True
    assert data["receipt"]["merkle_root"] is not None


def test_rest_qkd_bb84_and_e91(client):
    # BB84 clean
    r_bb84 = client.post("/v1/quantum/qkd/bb84", json={
        "sender": "desk-alpha",
        "receiver": "desk-beta",
        "bit_length": 64,
        "intercept_ratio": 0.0,
    })
    assert r_bb84.status_code == 200
    d_bb84 = r_bb84.json()
    assert d_bb84["ok"] is True
    assert d_bb84["session"]["eavesdropping_detected"] is False

    # E91
    r_e91 = client.post("/v1/quantum/qkd/e91", json={
        "sender": "desk-alpha",
        "receiver": "desk-beta",
        "pair_count": 64,
        "noise_level": 0.01,
    })
    assert r_e91.status_code == 200
    d_e91 = r_e91.json()
    assert d_e91["ok"] is True


def test_rest_teleportation_anchor_and_drill(client):
    r_anchor = client.post("/v1/quantum/teleportation/anchor/export")
    assert r_anchor.status_code == 200
    d_anchor = r_anchor.json()
    assert d_anchor["ok"] is True
    assert d_anchor["anchor"]["status"] == "confirmed"

    r_drill = client.post("/v1/quantum/teleportation/drill/simulate")
    assert r_drill.status_code == 200
    d_drill = r_drill.json()
    assert d_drill["ok"] is True
    assert d_drill["drill"]["all_passed"] is True
