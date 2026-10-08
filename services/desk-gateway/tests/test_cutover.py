"""Tests for live production cutover, canary traffic splitting, and automated emergency seat isolation (REQ-CUTOVER-001, REQ-CUTOVER-004, REQ-CUTOVER-005)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from desk_gateway.config import SEATS, Settings
from desk_gateway.cutover import (
    CanaryRouter,
    CutoverError,
    CutoverOrchestrator,
    EmergencyIsolationManager,
    SeatIsolatedError,
)
from desk_gateway.server import build_app
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for cutover.py components
# ---------------------------------------------------------------------------


def test_canary_router_bounds_and_determinism():
    router = CanaryRouter(canary_percentage=25)
    assert router.percentage == 25

    # Boundary tests
    with pytest.raises(CutoverError) as exc_info:
        router.set_percentage(-1)
    assert exc_info.value.code == "invalid_percentage"

    with pytest.raises(CutoverError):
        router.set_percentage(101)

    # Determinism with same partition key
    result1 = router.should_route_to_canary("github:webhook-pr-1234")
    result2 = router.should_route_to_canary("github:webhook-pr-1234")
    assert result1 == result2

    # At 0%, nothing routes to canary
    router.set_percentage(0)
    for i in range(50):
        assert router.should_route_to_canary(f"key-{i}") is False

    # At 100%, everything routes to canary
    router.set_percentage(100)
    for i in range(50):
        assert router.should_route_to_canary(f"key-{i}") is True


def test_canary_router_statistical_split():
    # 50% split should partition roughly evenly over 1,000 distinct items
    router = CanaryRouter(50)
    samples = 1000
    canary_count = sum(1 for i in range(samples) if router.should_route_to_canary(f"sample-key-{i}"))
    assert 450 <= canary_count <= 550, f"Expected ~50% split, got {canary_count}/{samples}"


def test_emergency_isolation_manager():
    mgr = EmergencyIsolationManager()
    assert mgr.list_isolated() == []
    assert mgr.is_isolated("systems") is False

    # Isolate systems seat
    record = mgr.isolate_seat("systems", reason="memory spike anomaly", actor="bot-06-quality-security")
    assert record.seat == "systems"
    assert record.actor == "bot-06-quality-security"
    assert record.reason == "memory spike anomaly"
    assert mgr.is_isolated("systems") is True

    # Unknown seat rejection
    with pytest.raises(CutoverError) as exc_info:
        mgr.isolate_seat("nonexistent_seat")
    assert exc_info.value.code == "unknown_seat"

    # Restore systems seat
    restored = mgr.restore_seat("systems", actor="bot-00-programming-lead")
    assert restored is True
    assert mgr.is_isolated("systems") is False

    # Double restore returns False
    assert mgr.restore_seat("systems") is False


def test_cutover_orchestrator_state_transitions(tmp_path: Path):
    s = Settings(cutover_enabled=False, canary_percentage=0)
    orch = CutoverOrchestrator(s)
    assert orch.is_enabled is False
    assert orch.phase == "legacy"
    assert orch.ingress_target == "legacy_stub"

    # Transition to canary at 30%
    status = orch.set_cutover_state(enabled=True, canary_percentage=30, reason="canary test phase")
    assert status["cutover_enabled"] is True
    assert status["phase"] == "canary"
    assert status["ingress_target"] == "vps_gateway"
    assert status["canary_percentage"] == 30

    # Transition to full live
    status = orch.set_cutover_state(enabled=True, canary_percentage=100, reason="full cutover")
    assert status["phase"] == "live"
    assert status["canary_percentage"] == 100

    # Emergency rollback
    status = orch.rollback(reason="anomaly trigger")
    assert status["cutover_enabled"] is False
    assert status["phase"] == "rollback"
    assert status["ingress_target"] == "legacy_stub"
    assert status["canary_percentage"] == 0


# ---------------------------------------------------------------------------
# Integration tests against Desk Gateway server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cutover_status_and_canary_endpoints(client):
    # GET /v1/cutover/status requires auth
    unauth_resp = await client.get("/v1/cutover/status")
    assert unauth_resp.status_code == 401

    # Authorized GET /v1/cutover/status with seat passphrase
    auth_headers = {"Authorization": f"Bearer {PASS['lead']}"}
    status_resp = await client.get("/v1/cutover/status", headers=auth_headers)
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "cutover_enabled" in data
    assert "phase" in data
    assert "canary_percentage" in data
    assert "isolated_seats" in data

    # POST /v1/cutover/canary requires lead authorization
    non_lead_headers = {"Authorization": f"Bearer {PASS['systems']}"}
    forbidden_resp = await client.post(
        "/v1/cutover/canary",
        headers=non_lead_headers,
        json={"enabled": True, "percentage": 25},
    )
    assert forbidden_resp.status_code == 403

    # Lead updates canary percentage to 50%
    canary_resp = await client.post(
        "/v1/cutover/canary",
        headers=auth_headers,
        json={"enabled": True, "percentage": 50, "reason": "graduated canary intake"},
    )
    assert canary_resp.status_code == 200
    res_data = canary_resp.json()
    assert res_data["cutover_enabled"] is True
    assert res_data["canary_percentage"] == 50
    assert res_data["phase"] == "canary"


@pytest.mark.asyncio
async def test_canary_intake_traffic_splitting(client):
    auth_lead = {"Authorization": f"Bearer {PASS['lead']}"}

    # Set canary percentage to 0% -> all intake goes to legacy stub
    await client.post(
        "/v1/cutover/canary",
        headers=auth_lead,
        json={"enabled": False, "percentage": 0},
    )

    intake_headers = {"Authorization": f"Bearer {INTAKE_TOKEN}"}
    payload = {
        "title": "Legacy intake test item",
        "ask": "This intake should route to legacy stub when canary percentage is 0",
    }
    resp_0 = await client.post("/v1/intake", headers=intake_headers, json=payload)
    assert resp_0.status_code == 202
    res_0_data = resp_0.json()
    assert res_0_data["canary_routed"] is False
    assert res_0_data["state"] == "legacy_stub"

    # Set canary percentage to 100% -> all intake goes to VPS gateway store
    await client.post(
        "/v1/cutover/canary",
        headers=auth_lead,
        json={"enabled": True, "percentage": 100},
    )

    payload_canary = {
        "title": "Live canary intake test item",
        "ask": "This intake should route to live VPS gateway when canary percentage is 100",
    }
    resp_100 = await client.post("/v1/intake", headers=intake_headers, json=payload_canary)
    assert resp_100.status_code == 202
    res_100_data = resp_100.json()
    assert res_100_data.get("canary_routed") is None or res_100_data.get("canary_routed") is not False
    assert res_100_data["state"] == "queued"
    assert "intake_id" in res_100_data
    assert not res_100_data["intake_id"].startswith("legacy-")


@pytest.mark.asyncio
async def test_emergency_seat_quarantine_and_restoration(client):
    lead_headers = {"Authorization": f"Bearer {PASS['lead']}"}
    systems_headers = {"Authorization": f"Bearer {PASS['systems']}"}

    # Initially systems seat responds normally
    resp_init = await client.post(
        "/mcp/systems",
        headers={"x-connector-key": PASS["systems"]},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert resp_init.status_code == 200

    # Emergency Isolation: Trigger quarantine on 'systems' seat
    isolate_resp = await client.post(
        "/v1/cutover/isolate",
        headers=lead_headers,
        json={
            "seat": "systems",
            "reason": "rogue process anomaly detected",
            "metadata": {"cpu_percent": 99.8, "alert_id": "ALT-9912"},
        },
    )
    assert isolate_resp.status_code == 200
    iso_body = isolate_resp.json()
    assert iso_body["ok"] is True
    assert iso_body["isolation"]["seat"] == "systems"

    # Seat router immediately isolates 'systems' with HTTP 503 within <5 seconds
    resp_blocked = await client.post(
        "/mcp/systems",
        headers={"x-connector-key": PASS["systems"]},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert resp_blocked.status_code == 503
    blocked_prob = resp_blocked.json()
    assert blocked_prob["error"] == "seat_isolated"
    assert "systems" in blocked_prob["detail"]

    # Verify other seats remain untouched and healthy
    resp_web = await client.post(
        "/mcp/web",
        headers={"x-connector-key": PASS["web"]},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )
    assert resp_web.status_code == 200

    # Status shows isolated seat
    status_resp = await client.get("/v1/cutover/status", headers=lead_headers)
    status_data = status_resp.json()
    isolated_seats = [r["seat"] for r in status_data["isolated_seats"]]
    assert "systems" in isolated_seats

    # Non-lead cannot restore quarantined seat
    forbidden_restore = await client.post(
        "/v1/cutover/restore",
        headers=systems_headers,
        json={"seat": "systems"},
    )
    assert forbidden_restore.status_code == 403

    # Lead restores systems seat
    restore_resp = await client.post(
        "/v1/cutover/restore",
        headers=lead_headers,
        json={"seat": "systems"},
    )
    assert restore_resp.status_code == 200
    restore_data = restore_resp.json()
    assert restore_data["ok"] is True
    assert restore_data["seat"] == "systems"
    assert restore_data["status"] == "restored"

    # Systems seat is now unblocked and healthy again
    resp_unblocked = await client.post(
        "/mcp/systems",
        headers={"x-connector-key": PASS["systems"]},
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
    )
    assert resp_unblocked.status_code == 200


@pytest.mark.asyncio
async def test_health_and_metrics_reflect_cutover_and_isolation(client):
    lead_headers = {"Authorization": f"Bearer {PASS['lead']}"}

    # Quarantine infra seat
    await client.post(
        "/v1/cutover/isolate",
        headers=lead_headers,
        json={"seat": "infra", "reason": "disk failure"},
    )

    # Check /health endpoint
    health_resp = await client.get("/health")
    assert health_resp.status_code == 200
    health_body = health_resp.json()
    assert "cutover" in health_body
    assert health_body["cutover"]["isolated_seats_count"] >= 1

    # Check /metrics exposition format
    metrics_resp = await client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text
    assert "desk_gateway_cutover_enabled" in metrics_text
    assert "desk_gateway_canary_percentage" in metrics_text
    assert "desk_gateway_isolated_seats_total" in metrics_text
    assert 'desk_gateway_seat_isolated{seat="infra"} 1' in metrics_text

    # Restore infra seat
    await client.post(
        "/v1/cutover/restore",
        headers=lead_headers,
        json={"seat": "infra"},
    )
