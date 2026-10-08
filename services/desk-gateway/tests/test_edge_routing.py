"""Tests for multi-region edge ingress gateway proxying, latency-based geo-steering, and distributed token-bucket rate limiting (REQ-EDGE-001, REQ-EDGE-002)."""

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
from desk_gateway.edge import (
    DistributedRateLimiter,
    EdgeError,
    EdgeIngressGateway,
    GeoSteeringRouter,
    RateLimitConfig,
    RateLimitExceeded,
    RegionEndpoint,
    TokenBucketPolicer,
    haversine_distance_km,
)
from desk_gateway.server import build_app
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for GeoSteeringRouter & Haversine Distance (REQ-EDGE-001)
# ---------------------------------------------------------------------------


def test_haversine_distance_calculation():
    # NYC to London (~5570 km)
    nyc_lat, nyc_lon = 40.7128, -74.0060
    lon_lat, lon_lon = 51.5074, -0.1278
    dist = haversine_distance_km(nyc_lat, nyc_lon, lon_lat, lon_lon)
    assert 5500 < dist < 5650

    # Same location distance is 0
    assert haversine_distance_km(nyc_lat, nyc_lon, nyc_lat, nyc_lon) == 0.0


def test_geo_steering_router_registration_and_health():
    router = GeoSteeringRouter(latency_threshold_ms=300.0, failure_threshold=2)
    router.register_region(
        region_id="us-east",
        endpoint_url="https://us-east.desk.test",
        latitude=38.9072,
        longitude=-77.0369,
        latency_ms=20.0,
        healthy=True,
    )
    router.register_region(
        region_id="eu-central",
        endpoint_url="https://eu-central.desk.test",
        latitude=50.1109,
        longitude=8.6821,
        latency_ms=90.0,
        healthy=True,
    )

    regions = router.list_regions()
    assert len(regions) == 2

    # Latency breach marks unhealthy
    router.update_health("us-east", healthy=True, latency_ms=350.0)
    assert router.get_region("us-east").healthy is False

    # Recover latency restores health
    router.update_health("us-east", healthy=True, latency_ms=25.0)
    assert router.get_region("us-east").healthy is True

    # Failure threshold triggers unhealthy
    router.update_health("eu-central", healthy=False)
    assert router.get_region("eu-central").healthy is True  # 1 failure < failure_threshold 2
    router.update_health("eu-central", healthy=False)
    assert router.get_region("eu-central").healthy is False


def test_geo_steering_selection_logic():
    router = GeoSteeringRouter()
    router.register_region("us-east", "https://us-east.test", 38.9, -77.0, latency_ms=15.0)
    router.register_region("eu-central", "https://eu-central.test", 50.1, 8.6, latency_ms=85.0)
    router.register_region("ap-southeast", "https://ap-southeast.test", 1.35, 103.8, latency_ms=180.0)

    # 1. Preferred region
    r, reason = router.select_best_region(preferred_region="eu-central")
    assert r.region_id == "eu-central"
    assert reason == "preferred_match"

    # 2. Client observed latencies override server measurement
    r, reason = router.select_best_region(observed_latencies={"us-east": 150.0, "eu-central": 25.0})
    assert r.region_id == "eu-central"
    assert "client_observed_latency" in reason

    # 3. Geodesic distance steering
    # Location near Frankfurt (51.0, 9.0) should pick eu-central
    r, reason = router.select_best_region(client_lat=51.0, client_lon=9.0)
    assert r.region_id == "eu-central"
    assert "geo_proximity" in reason

    # Location near Singapore (1.0, 104.0) should pick ap-southeast
    r, reason = router.select_best_region(client_lat=1.0, client_lon=104.0)
    assert r.region_id == "ap-southeast"
    assert "geo_proximity" in reason

    # 4. Default server lowest latency
    r, reason = router.select_best_region()
    assert r.region_id == "us-east"
    assert "server_latency" in reason

    # 5. Failover when primary fails
    router.update_health("us-east", healthy=False)
    router.update_health("us-east", healthy=False)
    router.update_health("us-east", healthy=False)
    assert router.get_region("us-east").healthy is False

    r, reason = router.select_best_region()
    assert r.region_id == "eu-central"  # Next lowest latency healthy region


# ---------------------------------------------------------------------------
# Unit tests for TokenBucketPolicer & DistributedRateLimiter (REQ-EDGE-002)
# ---------------------------------------------------------------------------


def test_token_bucket_policer():
    policer = TokenBucketPolicer(capacity=10, fill_rate_per_sec=2.0)
    # Initial consume of all 10 tokens
    allowed, retry_after, remaining, reset_epoch = policer.consume(10)
    assert allowed is True
    assert remaining == 0
    assert retry_after == 0.0

    # 11th token rejected
    allowed, retry_after, remaining, reset_epoch = policer.consume(1)
    assert allowed is False
    assert 0.4 <= retry_after <= 0.6  # 1 token / 2.0 per sec = 0.5s


@pytest.mark.asyncio
async def test_distributed_rate_limiter_in_memory_and_burst():
    limiter = DistributedRateLimiter(dragonfly_service=None)
    limiter.configure_seat("systems", rate_per_min=60, burst_capacity=5)

    # Consume up to burst capacity
    for _ in range(5):
        allowed, retry_after, remaining, _ = await limiter.check_rate_limit("systems")
        assert allowed is True

    # 6th request rejected
    allowed, retry_after, remaining, reset_epoch = await limiter.check_rate_limit("systems")
    assert allowed is False
    assert retry_after > 0.0


@pytest.mark.asyncio
async def test_distributed_rate_limiter_dragonfly_fallback():
    # Mock Dragonfly service raising exception
    mock_dragonfly = MagicMock()
    mock_dragonfly.configured = True
    mock_dragonfly.url = "redis://invalid.dragonfly.cluster:6379"

    limiter = DistributedRateLimiter(dragonfly_service=mock_dragonfly)
    limiter.configure_seat("lead", rate_per_min=60, burst_capacity=2)

    # Should fall back cleanly to in-memory policer without error
    allowed1, _, rem1, _ = await limiter.check_rate_limit("lead")
    assert allowed1 is True
    allowed2, _, rem2, _ = await limiter.check_rate_limit("lead")
    assert allowed2 is True
    allowed3, retry_after, rem3, _ = await limiter.check_rate_limit("lead")
    assert allowed3 is False
    assert retry_after > 0.0


# ---------------------------------------------------------------------------
# Integration tests for Edge Endpoints & MCP Middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edge_endpoints_and_routing(tmp_path: Path):
    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        intake_tokens={"github": INTAKE_TOKEN},
        edge_default_region="us-east",
    )
    app, _ = build_app(settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Unauthenticated /v1/edge/regions rejected
        res = await client.get("/v1/edge/regions")
        assert res.status_code == 401

        # 2. Authenticated /v1/edge/regions returns seeded regions
        res = await client.get("/v1/edge/regions", headers={"Authorization": f"Bearer {PASS['lead']}"})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["regions_count"] == 3
        region_ids = [r["region_id"] for r in data["regions"]]
        assert "us-east" in region_ids
        assert "eu-central" in region_ids
        assert "ap-southeast" in region_ids

        # 3. Geo-steering POST /v1/edge/route
        route_res = await client.post(
            "/v1/edge/route",
            json={"latitude": 48.8566, "longitude": 2.3522},  # Paris -> eu-central
        )
        assert route_res.status_code == 200
        r_data = route_res.json()
        assert r_data["ok"] is True
        assert r_data["selected_region"] == "eu-central"

        # 4. Update health POST /v1/edge/regions/{region_id}/health
        h_res = await client.post(
            "/v1/edge/regions/eu-central/health",
            json={"healthy": False, "latency_ms": 600.0},
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert h_res.status_code == 200
        assert h_res.json()["region"]["healthy"] is False

        # 5. Route again -> failover avoids eu-central
        route_res2 = await client.post(
            "/v1/edge/route",
            json={"latitude": 48.8566, "longitude": 2.3522},
        )
        assert route_res2.status_code == 200
        assert route_res2.json()["selected_region"] != "eu-central"

        # 6. Edge limits endpoint
        lim_res = await client.get("/v1/edge/limits", headers={"Authorization": f"Bearer {PASS['lead']}"})
        assert lim_res.status_code == 200
        lim_data = lim_res.json()
        assert lim_data["ok"] is True
        assert "systems" in lim_data["seats"]
        assert lim_data["seats"]["systems"]["burst_capacity"] == 240


@pytest.mark.asyncio
async def test_edge_rate_limiting_middleware(client):
    app = client._transport.app
    edge_gw = app.state["edge_gateway"]
    # Reconfigure systems seat burst to 3 for rapid test
    edge_gw.limiter.configure_seat("systems", rate_per_min=60, burst_capacity=3)

    # First 3 requests should pass rate limiter
    for i in range(3):
        res = await client.post(
            "/mcp/systems",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": i + 1, "params": {}},
            headers={"x-connector-key": PASS["systems"]},
        )
        assert res.status_code != 429

    # 4th request exceeds burst ceiling -> HTTP 429 Rate Limit Exceeded
    res4 = await client.post(
        "/mcp/systems",
        json={"jsonrpc": "2.0", "method": "tools/list", "id": 4, "params": {}},
        headers={"x-connector-key": PASS["systems"]},
    )
    assert res4.status_code == 429
    prob = res4.json()
    assert prob["error"] == "rate_limit_exceeded"
    assert "x-ratelimit-limit" in res4.headers
    assert "retry-after" in res4.headers
