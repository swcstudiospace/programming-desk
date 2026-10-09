import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def test_client():
    app, _ = build_app()
    return TestClient(app)


def test_neural_routing_register_and_status(test_client):
    reg_resp = test_client.post(
        "/v1/neural-routing/register-desk",
        json={
            "desk_id": "desk-test-alpha",
            "seat_ids": ["seat-alpha-0", "seat-alpha-1"],
            "domains": ["systems_backend", "infrastructure"],
            "supported_tools": ["sql_exec", "file_mutate"],
            "capacity_limit": 80,
            "active_load": 10,
            "base_latency_ms": 15.0,
            "cost_per_1k_tokens": 0.0015,
        },
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["ok"] is True

    status_resp = test_client.get("/v1/neural-routing/mesh/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["ok"] is True
    assert "desk-test-alpha" in data["desks"]
    assert data["desks"]["desk-test-alpha"]["circuit_state"] == "HEALTHY"


def test_neural_routing_dispatch_endpoint(test_client):
    test_client.post(
        "/v1/neural-routing/register-desk",
        json={
            "desk_id": "desk-mobile-edge",
            "seat_ids": ["seat-android", "seat-ios"],
            "domains": ["mobile_native"],
            "supported_tools": ["compile_apk", "build_xcarchive"],
            "capacity_limit": 50,
            "active_load": 2,
            "base_latency_ms": 30.0,
            "cost_per_1k_tokens": 0.002,
        },
    )

    dispatch_resp = test_client.post(
        "/v1/neural-routing/dispatch",
        json={
            "task_id": "task-mobile-1",
            "task_text": "Compile Android APK and verify Compose layouts on Kotlin",
            "required_tools": ["compile_apk"],
            "conversation_state": {"step": 1},
        },
    )
    assert dispatch_resp.status_code == 200
    res = dispatch_resp.json()
    assert res["ok"] is True
    assert res["routed"] is True
    assert res["receipt"]["selected_desk_id"] == "desk-mobile-edge"
    assert res["receipt"]["selected_seat_id"] in ["seat-android", "seat-ios"]
    assert res["envelope"] is not None

    receipt_id = res["receipt"]["receipt_id"]
    get_rcpt_resp = test_client.get(f"/v1/neural-routing/receipt/{receipt_id}")
    assert get_rcpt_resp.status_code == 200
    assert get_rcpt_resp.json()["receipt"]["receipt_id"] == receipt_id


def test_neural_routing_probe_circuit_breaker(test_client):
    test_client.post(
        "/v1/neural-routing/register-desk",
        json={
            "desk_id": "desk-flaky",
            "seat_ids": ["flaky-seat"],
            "domains": ["web_edge"],
            "supported_tools": [],
        },
    )

    for _ in range(3):
        probe_resp = test_client.post(
            "/v1/neural-routing/circuit-breaker/probe",
            json={"desk_id": "desk-flaky", "success": False, "latency_ms": 2500.0},
        )
        assert probe_resp.status_code == 200

    assert probe_resp.json()["circuit_state"] == "OPEN"

    status_resp = test_client.get("/v1/neural-routing/mesh/status")
    assert status_resp.json()["desks"]["desk-flaky"]["circuit_state"] == "OPEN"
