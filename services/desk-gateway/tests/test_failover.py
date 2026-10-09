"""Tests for dynamic multi-desk failover routing and upstream health polling (REQ-CUTOVER-002, REQ-CUTOVER-003)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from desk_gateway.config import SEATS, Settings
from desk_gateway.cutover import EmergencyIsolationManager
from desk_gateway.failover import FailoverError, FailoverRouter
from desk_gateway.federation import FederationRegistry, PeerGateway
from desk_gateway.health import UpstreamHealthPoller, UpstreamHealthRecord
from desk_gateway.server import build_app
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for UpstreamHealthPoller (REQ-CUTOVER-003)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upstream_health_poller_status_transitions():
    mock_services = MagicMock()
    mock_services.greptime = MagicMock()
    mock_services.greptime.health = AsyncMock(return_value={"ok": True})

    mock_services.timescale = MagicMock()
    mock_services.timescale.health = AsyncMock(return_value={"ok": False, "error": "db_connection_refused"})

    mock_services.dragonfly = MagicMock()
    mock_services.dragonfly.health = AsyncMock(return_value={"error": "not_configured", "reason": "not configured"})

    mock_services.hindsight = MagicMock()
    mock_services.hindsight.health = AsyncMock(return_value={"ok": True})

    mock_services.ragflow = MagicMock()
    mock_services.ragflow.health = AsyncMock(return_value={"ok": True})

    poller = UpstreamHealthPoller(
        services=mock_services,
        poll_interval_sec=10.0,
        failure_threshold=2,
        success_threshold=1,
    )

    # Initial state
    assert poller.is_all_healthy() is True

    # First poll
    status = await poller.poll_all()
    # timescale failed once: degraded
    ts_rec = poller.get_record("timescale")
    assert ts_rec.last_status == "degraded"
    assert ts_rec.healthy is True  # threshold is 2, not reached yet
    assert ts_rec.consecutive_failures == 1

    # greptime succeeded
    assert poller.get_record("greptime").healthy is True
    assert poller.get_record("greptime").last_status == "ok"

    # dragonfly unconfigured should not trip health
    assert poller.get_record("dragonfly").last_status == "not_configured"
    assert poller.get_record("dragonfly").healthy is True

    # Second poll: timescale fails second time, crosses failure_threshold (2)
    await poller.poll_all()
    ts_rec = poller.get_record("timescale")
    assert ts_rec.last_status == "down"
    assert ts_rec.healthy is False
    assert ts_rec.consecutive_failures == 2
    assert poller.any_degraded() is True

    # Recovery poll
    mock_services.timescale.health = AsyncMock(return_value={"ok": True})
    await poller.poll_all()
    ts_rec = poller.get_record("timescale")
    assert ts_rec.healthy is True
    assert ts_rec.last_status == "ok"
    assert ts_rec.consecutive_failures == 0
    assert ts_rec.consecutive_successes == 1


# ---------------------------------------------------------------------------
# Unit tests for FailoverRouter (REQ-CUTOVER-002)
# ---------------------------------------------------------------------------


def test_failover_router_peer_selection_and_manual_divert():
    settings = Settings(federation_enabled=True)
    registry = FederationRegistry(settings)

    # Register peer desks
    peer1 = registry.register_peer("desk-secondary-01", "https://desk-02.internal", seats=["systems", "lead", "web"])
    peer2 = registry.register_peer("desk-tertiary-02", "https://desk-03.internal", seats=["systems", "quality"])

    poller = MagicMock()
    poller.is_upstream_healthy.return_value = True
    iso_mgr = EmergencyIsolationManager()

    router = FailoverRouter(registry=registry, health_poller=poller, isolation_manager=iso_mgr)

    # Normal healthy state -> no divert
    should_divert, target, reason = router.should_divert_seat("systems")
    assert should_divert is False
    assert target is None

    # Manual divert
    override = router.set_manual_divert("systems", "desk-secondary-01", reason="scheduled maintenance", ttl_sec=60)
    assert override.seat == "systems"
    assert override.target_desk_id == "desk-secondary-01"

    should_divert, target, reason = router.should_divert_seat("systems")
    assert should_divert is True
    assert target == "desk-secondary-01"
    assert "maintenance" in reason

    # Clear divert
    assert router.clear_divert("systems") is True
    should_divert, target, _ = router.should_divert_seat("systems")
    assert should_divert is False


def test_failover_router_on_seat_quarantine_and_upstream_outage():
    settings = Settings(federation_enabled=True)
    registry = FederationRegistry(settings)
    registry.register_peer("peer-desk-east", "https://east.internal", seats=["systems", "web"])

    poller = MagicMock()
    poller.is_upstream_healthy.return_value = True
    iso_mgr = EmergencyIsolationManager()

    router = FailoverRouter(registry=registry, health_poller=poller, isolation_manager=iso_mgr)

    # 1. Test seat quarantine triggers divert to peer
    iso_mgr.isolate_seat("systems", reason="out-of-memory crash", actor="bot-06-quality-security")
    should_divert, target, reason = router.should_divert_seat("systems")
    assert should_divert is True
    assert target == "peer-desk-east"
    assert "isolated" in reason

    # Restore seat
    iso_mgr.restore_seat("systems")
    should_divert, target, _ = router.should_divert_seat("systems")
    assert should_divert is False

    # 2. Test upstream dependency outage triggers divert
    # Systems seat depends on timescale and dragonfly
    def mock_healthy(dep: str) -> bool:
        return dep != "timescale"

    poller.is_upstream_healthy.side_effect = mock_healthy
    should_divert, target, reason = router.should_divert_seat("systems")
    assert should_divert is True
    assert target == "peer-desk-east"
    assert "timescale" in reason


# ---------------------------------------------------------------------------
# Integration tests on Gateway REST API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_upstream_health_and_failover_api(tmp_path: Path):
    s = Settings(
        data_dir=tmp_path / "data",
        repo_dir=REPO,
        seat_passphrases=dict(PASS),
        federation_enabled=True,
    )
    app, _ = build_app(s)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # GET /v1/health/upstreams
        resp = await client.get("/v1/health/upstreams")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "upstreams" in data
        assert "overall" in data["upstreams"]

        # GET /v1/failover/status
        resp = await client.get("/v1/failover/status")
        assert resp.status_code == 200
        fail_data = resp.json()["failover"]
        assert fail_data["enabled"] is True
        assert "routes" in fail_data

        # Register a peer gateway via handshake
        hs_resp = await client.post(
            "/v1/federation/handshake",
            json={
                "desk_id": "desk-backup-cluster",
                "url": "https://backup.internal",
                "public_keys": {},
                "seats": ["systems", "web", "infra"],
            },
        )
        assert hs_resp.status_code == 200

        # Non-lead cannot configure divert
        bad_divert = await client.post(
            "/v1/failover/divert",
            headers={"Authorization": f"Bearer {s.seat_passphrases['systems']}"},
            json={"seat": "systems", "target_desk_id": "desk-backup-cluster"},
        )
        assert bad_divert.status_code == 403

        # Lead configures manual failover divert
        lead_divert = await client.post(
            "/v1/failover/divert",
            headers={"Authorization": f"Bearer {s.seat_passphrases['lead']}"},
            json={
                "seat": "systems",
                "target_desk_id": "desk-backup-cluster",
                "reason": "load-shedding",
            },
        )
        assert lead_divert.status_code == 200
        assert lead_divert.json()["divert"]["target_desk_id"] == "desk-backup-cluster"

        # Check /v1/failover/status reflects active divert
        resp = await client.get("/v1/failover/status")
        assert resp.json()["failover"]["routes"]["systems"]["diverted"] is True
        assert resp.json()["failover"]["routes"]["systems"]["target_desk_id"] == "desk-backup-cluster"

        # Attempting to call systems MCP endpoint should now return 503 seat_diverted problem
        mcp_resp = await client.post(
            "/mcp/systems",
            headers={"Authorization": f"Bearer {s.seat_passphrases['systems']}"},
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
        )
        assert mcp_resp.status_code == 503
        prob = mcp_resp.json()
        assert prob.get("error") == "seat_diverted"
        assert prob.get("failover_target") == "desk-backup-cluster"

        # Clear failover divert
        clear_resp = await client.post(
            "/v1/failover/clear",
            headers={"Authorization": f"Bearer {s.seat_passphrases['lead']}"},
            json={"seat": "systems"},
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["status"] == "cleared"

        # Verify status is back to normal local dispatch
        resp = await client.get("/v1/failover/status")
        assert resp.json()["failover"]["routes"]["systems"]["diverted"] is False

        # Metrics verification
        metrics_resp = await client.get("/metrics")
        assert metrics_resp.status_code == 200
        assert "desk_gateway_failover_enabled 1" in metrics_resp.text
        assert "desk_gateway_upstream_healthy" in metrics_resp.text
