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
from desk_gateway.redact import redact_text

logger = logging.getLogger("desk_gateway.health")

DEFAULT_SERVICES = ["greptime", "timescale", "dragonfly", "hindsight", "ragflow"]
DEFAULT_POLL_INTERVAL_SEC = 30.0
DEFAULT_CHECK_TIMEOUT_SEC = 15.0
_TASK_NAME = "upstream-health-poller"


def _positive_interval(value: float) -> float:
    """A non-positive or unreadable cadence would busy-loop the process."""
    try:
        interval = float(value)
    except (TypeError, ValueError):
        return DEFAULT_POLL_INTERVAL_SEC
    if interval <= 0:
        return DEFAULT_POLL_INTERVAL_SEC
    return interval


def _positive_timeout(value: float | None) -> float | None:
    """``None`` or a non-positive value disables the per-check deadline."""
    if value is None:
        return None
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CHECK_TIMEOUT_SEC
    if timeout <= 0:
        return None
    return timeout


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
        poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        check_timeout_sec: float | None = DEFAULT_CHECK_TIMEOUT_SEC,
    ) -> None:
        self.services = services
        self.poll_interval_sec = _positive_interval(poll_interval_sec)
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.check_timeout_sec = _positive_timeout(check_timeout_sec)
        self._lock = threading.RLock()
        self._records: dict[str, UpstreamHealthRecord] = {
            svc: UpstreamHealthRecord(name=svc) for svc in DEFAULT_SERVICES
        }
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # One live health task per service. wait_for() gives up on the deadline,
        # but a worker that ignores cancellation (asyncio.to_thread) keeps running.
        # The next poll must not submit another probe until that task finishes.
        self._inflight: dict[str, asyncio.Task[Any]] = {}
        # Counters from just before a deadline, so the real result replaces that
        # provisional failure instead of stacking on it.
        self._before_timeout: dict[str, tuple[int, int, bool, str]] = {}

    @classmethod
    def from_settings(cls, services: Any, settings: Settings) -> UpstreamHealthPoller:
        """Build a poller from gateway settings, including the env-configured cadence."""
        interval = getattr(settings, "upstream_health_poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
        timeout = getattr(settings, "upstream_health_check_timeout_sec", DEFAULT_CHECK_TIMEOUT_SEC)
        return cls(services, poll_interval_sec=interval, check_timeout_sec=timeout)

    @property
    def running(self) -> bool:
        task = self._task
        return task is not None and not task.done()

    def cached_details(self, name: str) -> dict[str, Any] | None:
        """Last health() payload for ``name``, once a check has actually finished.

        The initial record is optimistic and has never been checked. Callers that
        would otherwise hit the upstream live should keep doing that until
        ``last_checked_at`` is set, so a cold cache cannot report a false ok.
        """
        with self._lock:
            rec = self._records.get(name)
            if rec is None or rec.last_checked_at <= 0 or not isinstance(rec.details, dict):
                return None
            return dict(rec.details)

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

    def _exception_result(self, exc: BaseException) -> dict[str, Any]:
        # Exception text can carry a connection URL. Keep the type, redact the rest.
        return {
            "ok": False,
            "error": "check_exception",
            "reason": redact_text(f"{type(exc).__name__}: {exc}")[:300],
        }

    def _timeout_result(self, name: str) -> dict[str, Any]:
        limit = self.check_timeout_sec
        reason = (
            f"{name} health check exceeded {limit:.0f}s"
            if limit is not None
            else f"{name} health check timed out"
        )
        return {"ok": False, "error": "check_timeout", "reason": reason}

    @staticmethod
    async def _call_health(svc_client: Any) -> Any:
        if hasattr(svc_client, "health") and callable(svc_client.health):
            return await svc_client.health()
        return {"ok": True, "note": "no explicit health check implemented"}

    def _commit_result(self, name: str, res: Any, started: float, *, source: str) -> None:
        if not isinstance(res, dict):
            res = {"ok": False, "error": "check_exception", "reason": "health check returned a non-object"}
        latency_ms = (time.monotonic() - started) * 1000
        is_ok = bool(res.get("ok"))
        is_unconfigured = res.get("error") == "not_configured"

        with self._lock:
            rec = self._records.setdefault(name, UpstreamHealthRecord(name=name))
            # A deadline records one failure while the probe is still running.
            # The real result is applied to the counters from before that deadline.
            if source == "finished" and name in self._before_timeout:
                successes, failures, healthy, status = self._before_timeout.pop(name)
                rec.consecutive_successes = successes
                rec.consecutive_failures = failures
                rec.healthy = healthy
                rec.last_status = status
            elif source == "timeout" and name not in self._before_timeout:
                self._before_timeout[name] = (
                    rec.consecutive_successes,
                    rec.consecutive_failures,
                    rec.healthy,
                    rec.last_status,
                )
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

    def _on_check_done(self, name: str, task: asyncio.Task[Any], started: float) -> None:
        try:
            if task.cancelled():
                with self._lock:
                    self._before_timeout.pop(name, None)
                return
            exc = task.exception()
            res: Any = self._exception_result(exc) if exc is not None else task.result()
            self._commit_result(name, res, started, source="finished")
        except Exception as exc:
            logger.error(
                "Upstream %s health check result was discarded: %s",
                name,
                redact_text(f"{type(exc).__name__}: {exc}")[:300],
            )
        finally:
            with self._lock:
                if self._inflight.get(name) is task:
                    self._inflight.pop(name, None)

    async def check_service(self, name: str) -> dict[str, Any]:
        """Check one upstream and update its health state.

        A probe that is still running from an earlier deadline is left alone.
        Starting another one would pile work onto the shared thread pool when
        the client cannot be cancelled.
        """
        with self._lock:
            existing = self._inflight.get(name)
            if existing is not None and not existing.done():
                return {
                    "ok": False,
                    "error": "check_in_flight",
                    "reason": f"{name} health check still running",
                }

        svc_client = getattr(self.services, name, None)
        if svc_client is None:
            res = {"ok": False, "error": "unknown_service", "reason": f"No client for {name}"}
            self._commit_result(name, res, time.monotonic(), source="finished")
            return res

        started = time.monotonic()
        task = asyncio.create_task(self._call_health(svc_client), name=f"upstream-health-check-{name}")
        task.add_done_callback(lambda done, name=name, started=started: self._on_check_done(name, done, started))
        with self._lock:
            raced = self._inflight.get(name)
            if raced is not None and not raced.done():
                task.cancel()
                return {
                    "ok": False,
                    "error": "check_in_flight",
                    "reason": f"{name} health check still running",
                }
            self._inflight[name] = task

        try:
            if self.check_timeout_sec is not None:
                # shield: the deadline ends the wait. It does not cancel the probe.
                res = await asyncio.wait_for(asyncio.shield(task), timeout=self.check_timeout_sec)
            else:
                res = await task
        except TimeoutError:
            if task.done() and not task.cancelled():
                exc = task.exception()
                res = self._exception_result(exc) if exc is not None else task.result()
            else:
                res = self._timeout_result(name)
                self._commit_result(name, res, started, source="timeout")
                return res
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The done callback already recorded this. Do not count it twice.
            return self._exception_result(exc)
        if not isinstance(res, dict):
            res = {"ok": False, "error": "check_exception", "reason": "health check returned a non-object"}
        return res

    async def poll_all(self) -> dict[str, Any]:
        """Poll all configured upstream services concurrently."""
        with self._lock:
            names = list(self._records.keys())
        results = await asyncio.gather(
            *(self.check_service(name) for name in names),
            return_exceptions=True,
        )
        for name, result in zip(names, results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                logger.error(
                    "Upstream %s health check failed: %s",
                    name,
                    redact_text(f"{type(result).__name__}: {result}")[:300],
                )
        return self.get_status()

    async def start(self) -> None:
        """Schedule the background loop. Does not wait for the first poll.

        A down or unconfigured upstream must not block the caller. The loop
        records that outcome and keeps the previous snapshot until it finishes.
        """
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop(), name=_TASK_NAME)
        logger.info("upstream health poller started (interval=%.1fs)", self.poll_interval_sec)

    async def stop(self) -> None:
        """Cancel the background loop and any probe it has not finished."""
        self._stop_event.set()
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if self._task is task:
                self._task = None
        with self._lock:
            pending = [item for item in self._inflight.values() if not item.done()]
        for item in pending:
            item.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        with self._lock:
            self._inflight.clear()
            self._before_timeout.clear()

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.poll_all()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "Error during upstream health poll loop: %s",
                    redact_text(f"{type(exc).__name__}: {exc}")[:300],
                )
            if self._stop_event.is_set():
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_sec)
            except TimeoutError:
                pass
