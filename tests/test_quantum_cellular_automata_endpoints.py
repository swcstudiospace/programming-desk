"""Integration tests for Milestone v6.0 Quantum Cellular Automata REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_cellular_walk_and_automaton(client):
    # 1. Walk step
    walk_resp = client.post("/v1/quantum/cellular/walk/step")
    assert walk_resp.status_code == 200
    w_data = walk_resp.json()
    assert w_data["ok"] is True
    assert w_data["state"]["step"] >= 1
    assert "receipt" in w_data

    # 2. Automaton step
    aut_resp = client.post("/v1/quantum/cellular/automaton/step")
    assert aut_resp.status_code == 200
    a_data = aut_resp.json()
    assert a_data["ok"] is True
    assert a_data["automaton"]["step"] >= 1
    assert len(a_data["automaton"]["excitations"]) == 16
    assert "receipt" in a_data


def test_rest_quantum_cellular_anchor_and_drill(client):
    # 1. Anchor export
    anchor_resp = client.post("/v1/quantum/cellular/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # 2. Drill simulate
    drill_resp = client.post("/v1/quantum/cellular/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
