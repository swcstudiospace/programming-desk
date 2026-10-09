"""Tests for Telemetry Latencies, DLQ metrics, SLO evaluation, and Alert Dispatching (REQ-ALERT-001, REQ-ALERT-002, REQ-ALERT-003)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from desk_gateway.alerts import AlertDispatcher, AlertNotification, SLOEvaluator, SLOResult
from desk_gateway.config import SEATS, Settings
from desk_gateway.server import build_app
from desk_gateway.telemetry import TelemetryRegistry, telemetry_registry
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for TelemetryRegistry (REQ-ALERT-001)
# ---------------------------------------------------------------------------


def test_telemetry_registry_percentiles():
    reg = TelemetryRegistry()
    reg.reset_for_test()

    # Record 100 sample latencies for seat 'systems'
    # 1ms to 100ms
    for i in range(1, 101):
        reg.record_seat_latency("systems", float(i))

    stats = reg.get_seat_percentiles("systems")
    assert stats["count"] == 100
    assert stats["sum_ms"] == 5050.0
    # p50 is ~50, p90 is ~90, p99 is ~99
    assert 49.0 <= stats["p50"] <= 51.0
    assert 89.0 <= stats["p90"] <= 91.0
    assert 98.0 <= stats["p99"] <= 100.0

    all_stats = reg.get_all_seat_percentiles()
    assert "systems" in all_stats
    assert all_stats["systems"]["count"] == 100

    gw_stats = reg.get_gateway_percentiles()
    assert gw_stats["count"] == 100
    assert 49.0 <= gw_stats["p50"] <= 51.0


def test_telemetry_registry_intake_and_federation():
    reg = TelemetryRegistry()
    reg.reset_for_test()

    for _ in range(99):
        reg.record_intake_result(success=True)
    reg.record_intake_result(success=False)

    stats = reg.get_intake_stats()
    assert stats["total"] == 100
    assert stats["success"] == 99
    assert stats["failure"] == 1
    assert stats["success_rate_pct"] == 99.0

    assert reg.get_federation_signature_failures() == 0
    reg.record_federation_signature_failure()
    reg.record_federation_signature_failure()
    assert reg.get_federation_signature_failures() == 2


# ---------------------------------------------------------------------------
# Unit tests for SLOEvaluator (REQ-ALERT-002)
# ---------------------------------------------------------------------------


def test_slo_evaluator_thresholds(tmp_path: Path):
    reg = TelemetryRegistry()
    reg.reset_for_test()

    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        slo_latency_p99_max_ms=500.0,
        slo_intake_success_min_pct=99.9,
    )
    evaluator = SLOEvaluator(settings, registry=reg)

    # Empty stats -> all met by default
    res = evaluator.evaluate()
    assert res.all_slos_met is True
    assert res.latency_slo_met is True
    assert res.intake_slo_met is True

    # Record healthy latencies (< 500ms) and intake (1000 success)
    for _ in range(100):
        reg.record_seat_latency("architect", 120.0)
    for _ in range(1000):
        reg.record_intake_result(success=True)

    res = evaluator.evaluate()
    assert res.all_slos_met is True
    assert res.latency_slo_met is True
    assert res.intake_slo_met is True

    # Violate latency SLO: record p99 > 500ms
    for _ in range(50):
        reg.record_seat_latency("architect", 800.0)
    res = evaluator.evaluate()
    assert res.latency_p99_ms > 500.0
    assert res.latency_slo_met is False
    assert res.all_slos_met is False

    # Violate intake SLO: record failures
    for _ in range(10):
        reg.record_intake_result(success=False)
    res = evaluator.evaluate()
    assert res.intake_success_rate_pct < 99.9
    assert res.intake_slo_met is False
    assert res.all_slos_met is False


# ---------------------------------------------------------------------------
# Unit tests for AlertDispatcher (REQ-ALERT-003)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alert_dispatcher_cooldown_and_dispatch(tmp_path: Path):
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client.post = AsyncMock(return_value=mock_resp)

    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        alert_webhook_url="https://hooks.example.com/alerts",
        dlq_alert_threshold=5,
    )
    dispatcher = AlertDispatcher(settings, cooldown_sec=2.0, client=mock_client)

    alert1 = AlertNotification(
        alert_type="circuit_breaker_trip",
        severity="critical",
        summary="Peer desk-b circuit breaker tripped",
        details={"peer": "desk-b"},
    )

    # First dispatch succeeds
    dispatched = await dispatcher.dispatch(alert1)
    assert dispatched is True
    assert mock_client.post.call_count == 1

    # Second immediate dispatch with same type is suppressed by cooldown
    alert2 = AlertNotification(
        alert_type="circuit_breaker_trip",
        severity="critical",
        summary="Peer desk-b circuit breaker tripped again",
    )
    dispatched2 = await dispatcher.dispatch(alert2)
    assert dispatched2 is False
    assert mock_client.post.call_count == 1

    # Force dispatch bypasses cooldown
    dispatched_forced = await dispatcher.dispatch(alert2, force=True)
    assert dispatched_forced is True
    assert mock_client.post.call_count == 2

    recent = dispatcher.get_recent_alerts()
    assert len(recent) == 2


@pytest.mark.asyncio
async def test_alert_dispatcher_dlq_and_circuit_breaker_helpers(tmp_path: Path):
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client.post = AsyncMock(return_value=mock_resp)

    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        alert_webhook_url="https://hooks.example.com/alerts",
        dlq_alert_threshold=5,
    )
    dispatcher = AlertDispatcher(settings, cooldown_sec=0.01, client=mock_client)

    # Below threshold: no alert
    dispatcher.check_and_alert_dlq(3)
    await asyncio.sleep(0.05)
    assert len(dispatcher.get_recent_alerts()) == 0

    # At or above threshold: triggers alert
    dispatcher.check_and_alert_dlq(5)
    await asyncio.sleep(0.05)
    assert len(dispatcher.get_recent_alerts()) == 1
    assert dispatcher.get_recent_alerts()[0]["alert_type"] == "dlq_breach"

    # Circuit breaker trigger
    dispatcher.check_and_alert_circuit_breaker("desk-west", 6, "timeouts")
    await asyncio.sleep(0.05)
    assert len(dispatcher.get_recent_alerts()) == 2
    assert dispatcher.get_recent_alerts()[1]["alert_type"] == "circuit_breaker_trip"


# ---------------------------------------------------------------------------
# Gateway API & Prometheus exposition tests (REQ-ALERT-001, REQ-ALERT-002, REQ-ALERT-003)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gateway_alerts_api_and_metrics(tmp_path: Path):
    telemetry_registry.reset_for_test()

    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        alert_webhook_url="https://hooks.example.com/alerts",
        slo_latency_p99_max_ms=500.0,
        slo_intake_success_min_pct=99.9,
        dlq_alert_threshold=5,
    )
    app, _ = build_app(settings)

    # Record some seat latency and signature failure
    telemetry_registry.record_seat_latency("systems", 45.0)
    telemetry_registry.record_seat_latency("systems", 85.0)
    telemetry_registry.record_federation_signature_failure()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Inspect Prometheus metrics
        resp_metrics = await client.get("/metrics")
        assert resp_metrics.status_code == 200
        text = resp_metrics.text
        assert "desk_gateway_seat_latency_seconds{" in text
        assert "desk_gateway_dlq_saturation" in text
        assert "desk_gateway_federation_signature_failures_total 1" in text
        assert "desk_gateway_slo_latency_met 1" in text
        assert "desk_gateway_slo_intake_met 1" in text
        assert "desk_gateway_slo_all_met 1" in text

        # 2. Inspect /v1/alerts/status unauthorized
        resp_unauth = await client.get("/v1/alerts/status")
        assert resp_unauth.status_code == 401

        # 3. Inspect /v1/alerts/status authorized
        resp_status = await client.get(
            "/v1/alerts/status",
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert resp_status.status_code == 200
        data = resp_status.json()
        assert data["ok"] is True
        assert data["slo"]["all_slos_met"] is True
        assert data["thresholds"]["slo_latency_p99_max_ms"] == 500.0
        assert data["thresholds"]["webhook_configured"] is True

        # 4. Non-lead attempts to trigger test alert -> 403 Forbidden
        resp_test_forbid = await client.post(
            "/v1/alerts/test",
            headers={"Authorization": f"Bearer {PASS['systems']}"},
            json={"message": "Forbidden test"},
        )
        assert resp_test_forbid.status_code == 403

        # 5. Lead triggers test alert (mocked transport doesn't make outbound network call so dispatch fails safely with 502 or ok)
        resp_test_lead = await client.post(
            "/v1/alerts/test",
            headers={"Authorization": f"Bearer {PASS['lead']}"},
            json={"message": "Manual test notification"},
        )
        # Without real external network connectivity, dispatch returns False and status is 502 (or 200 if webhook is mocked)
        assert resp_test_lead.status_code in (200, 502)
        test_data = resp_test_lead.json()
        assert test_data["alert"]["alert_type"] == "test_alert"
        assert test_data["alert"]["summary"] == "Manual test notification"
