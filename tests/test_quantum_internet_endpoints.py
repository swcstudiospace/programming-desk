"""Integration tests for Milestone v5.4 Quantum Internet REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_internet_routing_and_packet(client):
    # 1. Add link
    link_resp = client.post("/v1/quantum/internet/link/add", json={
        "node_u": "desk-beta",
        "node_v": "desk-gamma",
        "raw_fidelity": 0.97,
        "latency_ms": 2.0,
        "bandwidth_ebits": 1200,
    })
    assert link_resp.status_code == 200
    assert link_resp.json()["ok"] is True

    # 2. Compute route
    route_resp = client.post("/v1/quantum/internet/route/compute", json={
        "source": "desk-alpha",
        "destination": "desk-gamma",
    })
    assert route_resp.status_code == 200
    r_data = route_resp.json()
    assert r_data["ok"] is True
    assert "desk-gamma" in r_data["path"]

    # 3. Send packet
    pkt_resp = client.post("/v1/quantum/internet/packet/send", json={
        "source": "desk-alpha",
        "destination": "desk-gamma",
        "target_fidelity": 0.80,
    })
    assert pkt_resp.status_code == 200
    p_data = pkt_resp.json()
    assert p_data["ok"] is True
    assert p_data["packet"]["delivered"] is True
    assert "receipt" in p_data


def test_rest_quantum_internet_slice_and_drill(client):
    # 1. Allocate slice
    slice_resp = client.post("/v1/quantum/internet/slice/allocate", json={
        "tenant_id": "tenant-quantum-99",
        "allocated_ebits_sec": 800,
        "min_fidelity_guarantee": 0.91,
        "nodes_included": ["desk-alpha", "desk-beta"],
    })
    assert slice_resp.status_code == 200
    s_data = slice_resp.json()
    assert s_data["ok"] is True
    assert s_data["slice"]["allocated_ebits_sec"] == 800
    assert "receipt" in s_data

    # 2. Export anchor
    anchor_resp = client.post("/v1/quantum/internet/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # 3. Run drill
    drill_resp = client.post("/v1/quantum/internet/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
