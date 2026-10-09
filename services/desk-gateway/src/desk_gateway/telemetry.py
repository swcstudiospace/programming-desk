"""Telemetry, traceparent propagation, structured logging and redaction filtering.

Supports W3C Trace Context (traceparent / tracestate) extraction and logging
injection (REQ-INTAKE-006), secrets redaction log filtering (REQ-INTAKE-009),
and Prometheus / OpenTelemetry telemetry anchoring verification (REQ-INTAKE-010).
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
from collections import deque
from typing import Any

from desk_gateway.redact import redact_text

# Context variables for W3C trace context propagation
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")
tracestate_var: contextvars.ContextVar[str] = contextvars.ContextVar("tracestate", default="")

# W3C traceparent regex: version(2 hex)-traceid(32 hex)-parentid/spanid(16 hex)-traceflags(2 hex)
TRACEPARENT_RE = re.compile(
    r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
)


def parse_traceparent(header_val: str | None) -> tuple[str, str, str] | None:
    """Parse W3C traceparent header into (trace_id, span_id, trace_flags)."""
    if not header_val:
        return None
    val = header_val.strip().lower()
    match = TRACEPARENT_RE.match(val)
    if not match:
        return None
    version, trace_id, parent_id, flags = match.groups()
    if version == "ff":
        return None
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None
    return trace_id, parent_id, flags


def get_current_trace_context() -> dict[str, str]:
    """Retrieve active trace context."""
    ctx: dict[str, str] = {}
    tid = trace_id_var.get()
    sid = span_id_var.get()
    tstate = tracestate_var.get()
    if tid:
        ctx["trace_id"] = tid
    if sid:
        ctx["span_id"] = sid
    if tstate:
        ctx["tracestate"] = tstate
    return ctx


class StructuredJsonFormatter(logging.Formatter):
    """Structured JSON formatter injecting OTel trace context and redacting secrets."""

    def format(self, record: logging.LogRecord) -> str:
        tid = trace_id_var.get()
        sid = span_id_var.get()
        tstate = tracestate_var.get()

        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": redact_text(record.getMessage()),
        }
        if tid:
            log_data["trace_id"] = tid
        if sid:
            log_data["span_id"] = sid
        if tstate:
            log_data["tracestate"] = tstate

        if record.exc_info:
            log_data["exc_info"] = redact_text(self.formatException(record.exc_info))

        return json.dumps(log_data)


class RedactionFilter(logging.Filter):
    """Logging filter ensuring secrets are redacted from messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_text(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_text(str(v)) if isinstance(v, str) else v for v in record.args)
        return True


class TelemetryRegistry:
    """In-memory telemetry metric tracking for Prometheus exposition and SLO evaluation.

    Tracks:
    - Per-seat invocation latencies (p50, p90, p99 percentiles, sum, count) (REQ-ALERT-001)
    - Gateway request latencies (all gateway endpoints)
    - Intake delivery successes and failures (for SLO calculation) (REQ-ALERT-002)
    - Federated signature verification failure counts (REQ-ALERT-001)
    """

    def __init__(self, max_samples: int = 5000) -> None:
        self._max_samples = max_samples
        self._lock = threading.Lock()
        # Seat -> deque of latency measurements in ms
        self._seat_latencies: dict[str, deque[float]] = {}
        # Seat -> (count, total_ms)
        self._seat_latency_totals: dict[str, list[float]] = {}
        # General gateway response latencies in ms
        self._gateway_latencies: deque[float] = deque(maxlen=max_samples)
        self._gateway_latency_count: int = 0
        self._gateway_latency_sum_ms: float = 0.0

        # Intake request counters: total and successful
        self._intake_total_count: int = 0
        self._intake_success_count: int = 0
        self._intake_failure_count: int = 0

        # Federation signature verification failure counter
        self._federation_signature_failures: int = 0

    def record_seat_latency(self, seat: str, ms: float) -> None:
        """Record latency in milliseconds for a seat invocation."""
        with self._lock:
            if seat not in self._seat_latencies:
                self._seat_latencies[seat] = deque(maxlen=self._max_samples)
                self._seat_latency_totals[seat] = [0.0, 0.0]  # count, total_ms
            self._seat_latencies[seat].append(ms)
            self._seat_latency_totals[seat][0] += 1
            self._seat_latency_totals[seat][1] += ms

            self._gateway_latencies.append(ms)
            self._gateway_latency_count += 1
            self._gateway_latency_sum_ms += ms

    def record_gateway_latency(self, ms: float) -> None:
        """Record a general gateway request latency in milliseconds."""
        with self._lock:
            self._gateway_latencies.append(ms)
            self._gateway_latency_count += 1
            self._gateway_latency_sum_ms += ms

    def record_intake_result(self, success: bool) -> None:
        """Record an intake delivery outcome."""
        with self._lock:
            self._intake_total_count += 1
            if success:
                self._intake_success_count += 1
            else:
                self._intake_failure_count += 1

    def record_federation_signature_failure(self) -> None:
        """Record a federated token signature verification failure."""
        with self._lock:
            self._federation_signature_failures += 1

    def get_seat_percentiles(self, seat: str) -> dict[str, float]:
        """Compute p50, p90, p99 latencies (ms) for a given seat."""
        with self._lock:
            samples = list(self._seat_latencies.get(seat, []))
        if not samples:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0, "count": 0, "sum_ms": 0.0}
        samples.sort()
        n = len(samples)
        p50 = samples[min(int(0.50 * n), n - 1)]
        p90 = samples[min(int(0.90 * n), n - 1)]
        p99 = samples[min(int(0.99 * n), n - 1)]
        totals = self._seat_latency_totals.get(seat, [0.0, 0.0])
        return {
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "p99": round(p99, 2),
            "count": int(totals[0]),
            "sum_ms": round(totals[1], 2),
        }

    def get_all_seat_percentiles(self) -> dict[str, dict[str, float]]:
        """Compute percentiles across all recorded seats."""
        with self._lock:
            seats = list(self._seat_latencies.keys())
        return {seat: self.get_seat_percentiles(seat) for seat in sorted(seats)}

    def get_gateway_percentiles(self) -> dict[str, float]:
        """Compute overall gateway response latency percentiles (ms)."""
        with self._lock:
            samples = list(self._gateway_latencies)
            cnt = self._gateway_latency_count
            tot = self._gateway_latency_sum_ms
        if not samples:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0, "count": 0, "sum_ms": 0.0}
        samples.sort()
        n = len(samples)
        p50 = samples[min(int(0.50 * n), n - 1)]
        p90 = samples[min(int(0.90 * n), n - 1)]
        p99 = samples[min(int(0.99 * n), n - 1)]
        return {
            "p50": round(p50, 2),
            "p90": round(p90, 2),
            "p99": round(p99, 2),
            "count": cnt,
            "sum_ms": round(tot, 2),
        }

    def get_intake_stats(self) -> dict[str, Any]:
        """Get intake success rate stats."""
        with self._lock:
            total = self._intake_total_count
            success = self._intake_success_count
            failure = self._intake_failure_count
        success_rate = (success / total * 100.0) if total > 0 else 100.0
        return {
            "total": total,
            "success": success,
            "failure": failure,
            "success_rate_pct": round(success_rate, 4),
        }

    def get_federation_signature_failures(self) -> int:
        """Return cumulative federated signature failure count."""
        with self._lock:
            return self._federation_signature_failures

    def reset_for_test(self) -> None:
        """Helper for testing to reset metrics."""
        with self._lock:
            self._seat_latencies.clear()
            self._seat_latency_totals.clear()
            self._gateway_latencies.clear()
            self._gateway_latency_count = 0
            self._gateway_latency_sum_ms = 0.0
            self._intake_total_count = 0
            self._intake_success_count = 0
            self._intake_failure_count = 0
            self._federation_signature_failures = 0


# Global telemetry registry instance
telemetry_registry = TelemetryRegistry()

