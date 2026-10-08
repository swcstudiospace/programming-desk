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
