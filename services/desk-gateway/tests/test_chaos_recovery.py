"""Tests for Synthetic Chaos Injection Harness and Autonomous Self-Healing Supervisor (REQ-CHAOS-001, REQ-CHAOS-002).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from desk_gateway.chaos import ChaosException, ChaosHarness, ChaosRule, FaultType
from desk_gateway.config import SEATS, Settings
from desk_gateway.server import build_app
from desk_gateway.supervisor import (
    SeatHealthStatus,
    SeatRuntimeProfile,
    SelfHealingSupervisor,
)
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for ChaosHarness (REQ-CHAOS-001)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chaos_harness_latency_injection():
    harness = ChaosHarness()
    harness.add_rule(
        target="dragonfly",
        fault_type=FaultType.LATENCY,
        delay_ms=80.0,
        probability=1.0,
    )

    t0 = time.perf_counter()
    await harness.apply_fault("dragonfly")
    t1 = time.perf_counter()

    assert (t1 - t0) >= 0.06  # at least ~60ms


@pytest.mark.asyncio
async def test_chaos_harness_packet_loss():
    harness = ChaosHarness()
    harness.add_rule(
        target="timescale",
        fault_type=FaultType.PACKET_LOSS,
        probability=1.0,
    )

    with pytest.raises(ChaosException) as exc:
        await harness.apply_fault("timescale")
    assert "packet_loss" in exc.value.fault_type
    assert exc.value.target == "timescale"


@pytest.mark.asyncio
async def test_chaos_harness_network_partition():
    harness = ChaosHarness()
    harness.add_rule(
        target="greptime",
        fault_type=FaultType.PARTITION,
        probability=1.0,
        error_message="GreptimeDB cluster connection unreachable",
    )

    with pytest.raises(ChaosException) as exc:
        await harness.apply_fault("greptime")
    assert "partition" in exc.value.fault_type
    assert "GreptimeDB cluster connection unreachable" in exc.value.detail


@pytest.mark.asyncio
async def test_chaos_harness_error_code_injection():
    harness = ChaosHarness()
    harness.add_rule(
        target="hindsight",
        fault_type=FaultType.ERROR_CODE,
        error_code=502,
        error_message="Hindsight gateway upstream bad gateway",
        probability=1.0,
    )

    with pytest.raises(ChaosException) as exc:
        await harness.apply_fault("hindsight")
    assert "error_code" in exc.value.fault_type
    assert "502" in str(exc.value) or "Hindsight gateway upstream bad gateway" in str(exc.value)


@pytest.mark.asyncio
async def test_chaos_harness_ttl_expiration():
    harness = ChaosHarness()
    harness.add_rule(
        target="ragflow",
        fault_type=FaultType.PARTITION,
        probability=1.0,
        duration_sec=0.05,
    )

    # Active immediately
    with pytest.raises(ChaosException):
        await harness.apply_fault("ragflow")

    # Expired after sleep
    await asyncio.sleep(0.06)
    # Should not raise exception when expired
    await harness.apply_fault("ragflow")
    assert len(harness.get_rules()) == 0


# ---------------------------------------------------------------------------
# Unit tests for SelfHealingSupervisor (REQ-CHAOS-002)
# ---------------------------------------------------------------------------


def test_supervisor_seat_profile_tracking():
    supervisor = SelfHealingSupervisor(error_threshold=3)

    # Healthy profile initially
    profile = supervisor.get_profile("systems")
    assert profile is not None
    assert profile.status == SeatHealthStatus.HEALTHY
    assert profile.consecutive_errors == 0

    # Record consecutive errors
    supervisor.record_seat_activity("systems", success=False, error_detail="timeout")
    supervisor.record_seat_activity("systems", success=False, error_detail="conn reset")
    profile = supervisor.get_profile("systems")
    assert profile is not None
    assert profile.status == SeatHealthStatus.DEGRADED
    assert profile.consecutive_errors == 2

    # Third failure exceeds threshold -> triggers automated hot reconstitution
    supervisor.record_seat_activity("systems", success=False, error_detail="service unavailable")
    profile = supervisor.get_profile("systems")
    assert profile is not None
    # Reconstitution resets back to healthy and increments reconstitution count
    assert profile.status == SeatHealthStatus.HEALTHY
    assert profile.consecutive_errors == 0
    assert profile.total_reconstitutions == 1


def test_supervisor_hot_reconstitution():
    from desk_gateway.cutover import EmergencyIsolationManager
    iso_mgr = EmergencyIsolationManager()
    edge_gw = MagicMock()
    edge_gw.limiter = MagicMock()
    lim_cfg = MagicMock()
    lim_cfg.rate_per_min = 120
    lim_cfg.burst_capacity = 30
    edge_gw.limiter.get_config.return_value = lim_cfg

    supervisor = SelfHealingSupervisor(
        isolation_manager=iso_mgr,
        edge_gateway=edge_gw,
        error_threshold=2,
    )

    # Manual quarantine
    iso_mgr.isolate_seat("infra", "chaos testing", actor="test")
    assert iso_mgr.is_isolated("infra") is True

    # Reconstitute seat
    result = supervisor.reconstitute_seat("infra", reason="manual test")
    assert result["ok"] is True
    assert result["seat"] == "infra"
    assert result["profile"]["status"] == SeatHealthStatus.HEALTHY.value
    assert result["profile"]["total_reconstitutions"] == 1

    # Quarantine removed and profile healthy
    assert iso_mgr.is_isolated("infra") is False
    profile = supervisor.get_profile("infra")
    assert profile is not None
    assert profile.status == SeatHealthStatus.HEALTHY
    edge_gw.limiter.configure_seat.assert_called_with(seat="infra", rate_per_min=120, burst_capacity=30)


# ---------------------------------------------------------------------------
# Integration tests for Chaos & Supervisor REST Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chaos_and_supervisor_endpoints(tmp_path: Path):
    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        intake_tokens={"github": INTAKE_TOKEN},
    )
    app, _ = build_app(settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Inspect initial chaos rules
        res = await client.get("/v1/chaos/rules")
        assert res.status_code == 200
        assert res.json()["count"] == 0

        # 2. Non-operator cannot inject chaos (e.g. android seat)
        res = await client.post(
            "/v1/chaos/inject",
            headers={"Authorization": f"Bearer {PASS['android']}"},
            json={
                "target": "timescale",
                "fault_type": "latency",
                "delay_ms": 50.0,
            },
        )
        assert res.status_code == 403

        # 3. Operator (lead) can inject chaos
        res = await client.post(
            "/v1/chaos/inject",
            headers={"Authorization": f"Bearer {PASS['lead']}"},
            json={
                "target": "dragonfly",
                "fault_type": "packet_loss",
                "probability": 0.5,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["ok"] is True
        assert data["rule"]["target"] == "dragonfly"
        assert data["rule"]["fault_type"] == "packet_loss"

        # 4. Check active rules
        res = await client.get("/v1/chaos/rules")
        assert res.status_code == 200
        assert res.json()["count"] == 1

        # 5. Reset chaos rules
        res = await client.post("/v1/chaos/reset")
        assert res.status_code == 200
        assert res.json()["cleared_rules_count"] == 1

        # 6. Check supervisor seats
        res = await client.get("/v1/supervisor/seats")
        assert res.status_code == 200
        seats_data = res.json()
        assert "seats" in seats_data
        assert seats_data["count"] == len(SEATS)

        # 7. Hot reconstitute a seat
        res = await client.post("/v1/supervisor/reconstitute", json={"seat": "systems"})
        assert res.status_code == 200
        reconstitute_data = res.json()
        assert reconstitute_data["ok"] is True
        assert reconstitute_data["seat"] == "systems"
        assert reconstitute_data["profile"]["status"] == "healthy"
