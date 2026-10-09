"""Alerts and Service Level Objective (SLO) evaluation for Desk Gateway.

Implements REQ-ALERT-001, REQ-ALERT-002, and REQ-ALERT-003:
- SLO evaluation monitoring gateway p99 response time (< 500ms) and intake delivery success (> 99.9%).
- Automated on-call webhook dispatching with deduplication, cooldown, and error handling
  for circuit breaker trips, DLQ threshold breaches, and SLO violations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from desk_gateway.config import Settings
from desk_gateway.telemetry import TelemetryRegistry, telemetry_registry

logger = logging.getLogger("desk_gateway.alerts")


@dataclass
class AlertNotification:
    """Represents an alert triggered by gateway runtime conditions."""

    alert_type: str  # circuit_breaker_trip, dlq_breach, slo_latency_breach, slo_intake_breach, test_alert
    severity: str  # critical, warning, info
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    alert_id: str = ""

    def __post_init__(self) -> None:
        if not self.alert_id:
            self.alert_id = f"{self.alert_type}-{int(self.timestamp)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "summary": self.summary,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class SLOResult:
    """Evaluation result of Service Level Objectives."""

    latency_p99_ms: float
    latency_p99_threshold_ms: float
    latency_slo_met: bool
    intake_success_rate_pct: float
    intake_success_threshold_pct: float
    intake_slo_met: bool
    all_slos_met: bool
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_p99_ms": self.latency_p99_ms,
            "latency_p99_threshold_ms": self.latency_p99_threshold_ms,
            "latency_slo_met": self.latency_slo_met,
            "intake_success_rate_pct": self.intake_success_rate_pct,
            "intake_success_threshold_pct": self.intake_success_threshold_pct,
            "intake_slo_met": self.intake_slo_met,
            "all_slos_met": self.all_slos_met,
            "evaluated_at": self.evaluated_at,
        }


class SLOEvaluator:
    """Evaluates gateway Service Level Objectives (SLOs) (REQ-ALERT-002).

    Thresholds:
    - Gateway p99 response time < 500ms (configurable via settings.slo_latency_p99_max_ms)
    - Intake delivery success > 99.9% (configurable via settings.slo_intake_success_min_pct)
    """

    def __init__(
        self,
        settings: Settings,
        registry: TelemetryRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry or telemetry_registry

    def evaluate(self) -> SLOResult:
        """Run evaluation of current runtime metrics against SLO thresholds."""
        latencies = self.registry.get_gateway_percentiles()
        p99_ms = latencies.get("p99", 0.0)
        p99_threshold = self.settings.slo_latency_p99_max_ms

        intake_stats = self.registry.get_intake_stats()
        intake_pct = intake_stats.get("success_rate_pct", 100.0)
        intake_threshold = self.settings.slo_intake_success_min_pct

        # If there are samples, check thresholds; if zero samples, default to met
        latency_met = (p99_ms <= p99_threshold) if latencies.get("count", 0) > 0 else True
        intake_met = (intake_pct >= intake_threshold) if intake_stats.get("total", 0) > 0 else True
        all_met = latency_met and intake_met

        return SLOResult(
            latency_p99_ms=p99_ms,
            latency_p99_threshold_ms=p99_threshold,
            latency_slo_met=latency_met,
            intake_success_rate_pct=intake_pct,
            intake_success_threshold_pct=intake_threshold,
            intake_slo_met=intake_met,
            all_slos_met=all_met,
        )


class AlertDispatcher:
    """Dispatches on-call alert notifications via webhook with deduplication and cooldown (REQ-ALERT-003)."""

    def __init__(
        self,
        settings: Settings,
        cooldown_sec: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.cooldown_sec = cooldown_sec
        self._client = client
        self._last_alert_time: dict[str, float] = {}  # alert_type -> timestamp
        self._dispatched_alerts: list[AlertNotification] = []

    async def dispatch(self, alert: AlertNotification, force: bool = False) -> bool:
        """Dispatch an alert notification to the configured webhook endpoint.

        Applies deduplication cooldown unless `force` is True.
        Returns True if alert was sent, False if suppressed or skipped.
        """
        now = time.time()
        last_time = self._last_alert_time.get(alert.alert_type, 0.0)
        if not force and (now - last_time < self.cooldown_sec):
            logger.info(
                "Alert %s suppressed due to cooldown (%.1fs remaining)",
                alert.alert_type,
                self.cooldown_sec - (now - last_time),
            )
            return False

        self._last_alert_time[alert.alert_type] = now
        self._dispatched_alerts.append(alert)
        if len(self._dispatched_alerts) > 100:
            self._dispatched_alerts.pop(0)

        webhook_url = self.settings.alert_webhook_url
        if not webhook_url:
            logger.warning("Alert triggered but ALERT_WEBHOOK_URL not configured: %s", alert.summary)
            return False

        payload = {
            "service": "desk-gateway",
            "environment": "vps-production",
            "host": self.settings.public_host,
            "alert": alert.to_dict(),
        }

        try:
            if self._client:
                resp = await self._client.post(webhook_url, json=payload, timeout=5.0)
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(webhook_url, json=payload, timeout=5.0)
            if resp.status_code >= 400:
                logger.error(
                    "Failed to deliver alert webhook to %s: HTTP %s: %s",
                    webhook_url,
                    resp.status_code,
                    resp.text,
                )
                return False
            logger.info("Successfully dispatched alert '%s' to webhook", alert.alert_type)
            return True
        except Exception as exc:
            logger.error("Exception while dispatching alert webhook to %s: %s", webhook_url, exc)
            return False

    def notify_background(self, alert: AlertNotification, force: bool = False) -> None:
        """Schedule dispatch in the running asyncio loop without blocking."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.dispatch(alert, force=force))
        except RuntimeError:
            # Fallback if outside event loop
            pass

    def check_and_alert_circuit_breaker(self, peer_desk_id: str, failure_count: int, reason: str = "") -> None:
        """Trigger alert when a federation circuit breaker trips (REQ-ALERT-003)."""
        alert = AlertNotification(
            alert_type="circuit_breaker_trip",
            severity="critical",
            summary=f"Federation Circuit Breaker tripped for peer desk '{peer_desk_id}'",
            details={
                "peer_desk_id": peer_desk_id,
                "failure_count": failure_count,
                "reason": reason or "Repeated communication failures threshold exceeded",
            },
        )
        self.notify_background(alert)

    def check_and_alert_dlq(self, dlq_count: int) -> None:
        """Trigger alert if DLQ saturation breaches the threshold (REQ-ALERT-003)."""
        threshold = self.settings.dlq_alert_threshold
        if dlq_count >= threshold:
            alert = AlertNotification(
                alert_type="dlq_breach",
                severity="critical",
                summary=f"Dead-Letter Queue threshold breached: {dlq_count} items (threshold: {threshold})",
                details={
                    "dlq_count": dlq_count,
                    "threshold": threshold,
                },
            )
            self.notify_background(alert)

    def check_and_alert_slo(self, slo_result: SLOResult) -> None:
        """Trigger alert if SLO rules are breached (REQ-ALERT-002, REQ-ALERT-003)."""
        if not slo_result.latency_slo_met:
            alert = AlertNotification(
                alert_type="slo_latency_breach",
                severity="warning",
                summary=f"Gateway response latency p99 breach: {slo_result.latency_p99_ms}ms > {slo_result.latency_p99_threshold_ms}ms",
                details=slo_result.to_dict(),
            )
            self.notify_background(alert)

        if not slo_result.intake_slo_met:
            alert = AlertNotification(
                alert_type="slo_intake_breach",
                severity="critical",
                summary=f"Intake delivery success rate breach: {slo_result.intake_success_rate_pct}% < {slo_result.intake_success_threshold_pct}%",
                details=slo_result.to_dict(),
            )
            self.notify_background(alert)

    def get_recent_alerts(self) -> list[dict[str, Any]]:
        """Return list of recent dispatched alerts."""
        return [a.to_dict() for a in self._dispatched_alerts]
