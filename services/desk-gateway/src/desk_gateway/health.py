"""Upstream health polling across Railway datastores and AI services (REQ-CUTOVER-003).

Provides continuous or on-demand health assessment across:
- GreptimeDB (timeseries & metrics)
- TimescaleDB (PostgreSQL relational storage)
- DragonflyDB (Redis-compatible fast cache)
- Hindsight (memory bank service)
- RAGFlow (retrieval and dataset service)

Tracks consecutive health checks, failure thresholds, degradation states,
and exposes aggregate upstream health to inform gateway routing tables.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from desk_gateway.config import Settings

logger = logging.getLogger("desk_gateway.health")

DEFAULT_SERVICES = ["greptime", "timescale", "dragonfly", "hindsight", "ragflow"]


@dataclass
class UpstreamHealthRecord:
    name: str
    healthy: bool = True
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    last_status: str = "ok"  # ok, degraded, down, not_configured
    last_latency_ms: float = 0.0
    last_checked_at: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "last_status": self.last_status,
            "last_latency_ms": round(self.last_latency_ms, 2),
            "last_checked_at": self.last_checked_at,
            "details": self.details,
        }


class UpstreamHealthPoller:
    """Actively polls Railway backing services and informs routing state (REQ-CUTOVER-003)."""

    def __init__(
        self,
        services: Any,
        poll_interval_sec: float = 30.0,
        failure_threshold: int = 3,
        success_threshold: int = 2,
    ) -> None:
        self.services = services
        self.poll_interval_sec = poll_interval_sec
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self._lock = threading.RLock()
        self._records: dict[str, UpstreamHealthRecord] = {
            svc: UpstreamHealthRecord(name=svc) for svc in DEFAULT_SERVICES
        }
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    def get_record(self, name: str) -> UpstreamHealthRecord | None:
        with self._lock:
            return self._records.get(name)

    def is_upstream_healthy(self, name: str) -> bool:
        with self._lock:
            rec = self._records.get(name)
            return rec.healthy if rec else False

    def is_all_healthy(self) -> bool:
        with self._lock:
            return all(rec.healthy for rec in self._records.values())

    def any_degraded(self) -> bool:
        with self._lock:
            return any(not rec.healthy for rec in self._records.values())

    def get_status(self) -> dict[str, Any]:
        """Aggregate upstream health snapshot for routing table consumption."""
        with self._lock:
            records = {k: v.to_dict() for k, v in self._records.items()}
            healthy_count = sum(1 for v in self._records.values() if v.healthy)
            total = len(self._records)
            overall = "healthy" if healthy_count == total else ("degraded" if healthy_count > 0 else "down")
            return {
                "overall": overall,
                "healthy_count": healthy_count,
                "total_count": total,
                "services": records,
                "timestamp": time.time(),
            }

    async def check_service(self, name: str) -> dict[str, Any]:
        """Check a single upstream service directly and update its health state."""
        svc_client = getattr(self.services, name, None)
        if svc_client is None:
            return {"ok": False, "error": "unknown_service", "reason": f"No client for {name}"}

        start = time.monotonic()
        try:
            if hasattr(svc_client, "health") and callable(svc_client.health):
                res = await svc_client.health()
            else:
                res = {"ok": True, "note": "no explicit health check implemented"}
        except Exception as exc:
            res = {"ok": False, "error": "check_exception", "reason": str(exc)}
        latency_ms = (time.monotonic() - start) * 1000

        is_ok = bool(res.get("ok"))
        is_unconfigured = res.get("error") == "not_configured"

        with self._lock:
            rec = self._records.setdefault(name, UpstreamHealthRecord(name=name))
            rec.last_latency_ms = latency_ms
            rec.last_checked_at = time.time()
            rec.details = res

            if is_unconfigured:
                rec.last_status = "not_configured"
                rec.healthy = True  # unconfigured services in test/local environments do not trip failover
                rec.consecutive_failures = 0
            elif is_ok:
                rec.consecutive_successes += 1
                rec.consecutive_failures = 0
                if rec.consecutive_successes >= self.success_threshold or rec.healthy:
                    rec.healthy = True
                    rec.last_status = "ok"
            else:
                rec.consecutive_failures += 1
                rec.consecutive_successes = 0
                if rec.consecutive_failures >= self.failure_threshold:
                    rec.healthy = False
                    rec.last_status = "down"
                else:
                    rec.last_status = "degraded"

            logger.debug(
                "Upstream %s health check: ok=%s status=%s (failures=%d, latency=%.1fms)",
                name,
                is_ok,
                rec.last_status,
                rec.consecutive_failures,
                latency_ms,
            )

        return res

    async def poll_all(self) -> dict[str, Any]:
        """Poll all configured upstream services concurrently."""
        tasks = [self.check_service(name) for name in list(self._records.keys())]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self.get_status()

    async def start(self) -> None:
        """Start background polling loop."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop background polling loop."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.poll_all()
            except Exception as exc:
                logger.error("Error during upstream health poll loop: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_sec)
            except asyncio.TimeoutError:
                pass
