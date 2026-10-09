"""Integration tests for Hardware & Neuromorphic Mesh REST routes in desk-gateway (Milestone v4.7)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_hardware_substrates_and_compile_routes(client):
    # 1. GET /v1/hardware/substrates
    r1 = client.get("/v1/hardware/substrates")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert len(r1.json()["substrates"]) >= 5

    # 2. POST /v1/hardware/compile
    r2 = client.post(
        "/v1/hardware/compile",
        json={
            "op_type": "gemm",
            "target_substrate": "gpu_cuda",
            "input_shapes": [[1024, 1024], [1024, 1024]],
            "optimization_level": 3,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["kernel"]["target_substrate"] == "gpu_cuda"
    assert "warp_synchronous_reduction" in r2.json()["kernel"]["optimization_passes"]


def test_hardware_dispatch_and_telemetry_routes(client):
    # 1. POST /v1/hardware/dispatch
    r1 = client.post(
        "/v1/hardware/dispatch",
        json={
            "op_type": "spike_propagation",
            "input_shapes": [[128, 1], [128, 512]],
            "priority": 8,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["assignment"]["target_substrate"] == "neuromorphic"
    assert r1.json()["assignment"]["status"] == "DISPATCHED"

    # 2. GET /v1/hardware/telemetry
    r2 = client.get("/v1/hardware/telemetry")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["telemetry"]["total_peak_tops"] > 500.0


def test_neuromorphic_spikes_and_step_routes(client):
    # 1. POST /v1/neuromorphic/spikes/inject
    r1 = client.post(
        "/v1/neuromorphic/spikes/inject",
        json={
            "spikes": [["in_0", 1.5], ["in_1", 1.2]],
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["injected_spikes_count"] == 2

    # 2. POST /v1/neuromorphic/step
    r2 = client.post(
        "/v1/neuromorphic/step",
        json={
            "duration_us": 15.0,
            "step_dt_us": 1.0,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    sim = r2.json()["simulation"]
    assert sim["spikes_fired_in_step"] > 0
    assert sim["total_mesh_spikes"] > 0


def test_neuromorphic_ledger_and_anchor_routes(client):
    # 1. POST /v1/neuromorphic/ledger/receipts
    r1 = client.post(
        "/v1/neuromorphic/ledger/receipts",
        json={
            "mesh_id": "test-nm-ledger",
            "receipt_type": "SYNAPTIC_WEIGHT_UPDATE",
            "payload": {"status": "converged", "alpha": 0.05},
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "receipt_id" in r1.json()["receipt"]
    assert len(r1.json()["receipt"]["hmac_signature"]) == 64

    # 2. POST /v1/neuromorphic/anchor/export
    r2 = client.post("/v1/neuromorphic/anchor/export")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    anchor = r2.json()["anchor"]
    assert anchor["status"] == "CONFIRMED"
    assert "transaction_signature" in anchor


def test_hardware_drill_simulate_route(client):
    r = client.post("/v1/hardware/drill/simulate")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    drill = r.json()["drill"]
    assert drill["drill_status"] == "ALL_CHECKS_PASSED"
