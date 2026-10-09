"""Integration tests for Milestone v5.6 Quantum Sensing REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_sensing_noon_estimate(client):
    resp = client.post("/v1/quantum/sensing/noon/estimate", json={
        "true_phase": 1.25,
        "n_photons": 12,
        "detector_noise": 0.005,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["result"]["n_photons"] == 12
    assert data["result"]["heisenberg_limit"] < data["result"]["standard_quantum_limit"]
    assert "receipt" in data


def test_rest_quantum_sensing_clock_sync(client):
    resp = client.post("/v1/quantum/sensing/clock/sync", json={
        "node_a": "desk-alpha",
        "node_b": "desk-gamma",
        "initial_skew_ps": 42.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["sync"]["sync_status"] == "SYNCHRONIZED_SUB_PICOSECOND"
    assert "receipt" in data


def test_rest_quantum_sensing_anchor_and_drill(client):
    # Anchor
    anchor_resp = client.post("/v1/quantum/sensing/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # Drill
    drill_resp = client.post("/v1/quantum/sensing/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
