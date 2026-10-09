"""Clients for everything the gateway talks to. Every method returns plain dicts and never raises
past its boundary: reads come back as {"error": <code>, "reason": ...} so a tool can fail open,
writes come back the same way so a tool can fail closed. Secrets never appear in return values.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import re
import shlex
import signal
import time
from typing import Any

import httpx

from desk_gateway.config import RAGFLOW_DATASET_TTL_SEC, Settings
from desk_gateway.problems import problem_details
from desk_gateway.redact import redact_text, redact_value

logger = logging.getLogger("desk_gateway.upstreams")

NOT_CONFIGURED = "not_configured"
UPSTREAM_ERROR = "upstream_error"
UPSTREAM_TIMEOUT = "upstream_timeout"

# A budget wrapper sets this to a one-element list. request() increments it only
# when that budget cancels the task during the HTTP send, not while the task is
# waiting on a local lock. Caller cancellation still propagates as CancelledError.
_budget_http_cancels: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "desk_budget_http_cancels", default=None
)


def push_budget_http_scope() -> contextvars.Token[list[int] | None]:
    return _budget_http_cancels.set([0])


def pop_budget_http_scope(token: contextvars.Token[list[int] | None]) -> None:
    _budget_http_cancels.reset(token)


def budget_cancelled_http() -> bool:
    holder = _budget_http_cancels.get()
    return bool(holder and holder[0])


def _note_budget_http_cancel() -> None:
    holder = _budget_http_cancels.get()
    task = asyncio.current_task()
    if holder is not None and task is not None and task.cancelling():
        holder[0] += 1

READ_ONLY_SQL = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|vacuum|call|do|merge|set\s+role)\b",
    re.IGNORECASE,
)


def not_configured(what: str) -> dict[str, Any]:
    return {"error": NOT_CONFIGURED, "reason": f"{what} is not configured on the gateway; record this under unverified"}


_SQL_LITERAL_OR_COMMENT = re.compile(
    r"'(?:[^']|'')*'"       # single-quoted literal, '' as the escape
    r'|"(?:[^"]|"")*"'      # double-quoted identifier
    r"|--[^\n]*"            # line comment
    r"|/\*.*?\*/",          # block comment
    re.DOTALL,
)


def _sql_code_only(sql: str) -> str:
    """`sql` with literals and comments blanked, so keyword scanning sees operations only.

    Scanning the raw text rejects ordinary reads: SELECT 'delete', or a LIKE '%create%'
    filter, matches the write-keyword pattern inside its own quotes. Blanking rather than
    deleting preserves offsets and cannot join two tokens into a third.
    """
    return _SQL_LITERAL_OR_COMMENT.sub(lambda m: " " * len(m.group()), sql)


def read_only_sql(sql: str) -> str | None:
    code = _sql_code_only(sql)
    if not READ_ONLY_SQL.match(code.lstrip()):
        return "only SELECT or WITH statements are accepted"
    if FORBIDDEN_SQL.search(code):
        return "statement contains a write keyword"
    if ";" in code.strip().rstrip(";"):
        return "one statement per call"
    return None


async def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"text": redact_text(resp.text[:2000])}


class CircuitBreaker:
    """Outbound circuit breaker with closed, open, and half-open states."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.failure_count: int = 0
        self.state: str = "closed"  # closed, open, half-open
        self.last_failure_time: float = 0.0

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        now = time.monotonic()
        if self.state == "open":
            if now - self.last_failure_time >= self.recovery_timeout_sec:
                self.state = "half-open"
                return True
            return False
        # half-open allows trial request
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold or self.state == "half-open":
            self.state = "open"

    def reset(self) -> None:
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = 0.0


class _PooledClient:
    """One shared httpx client plus the requests still using it."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.inflight = 0
        self.retire = False
        self.closing = False


class HttpUpstream:
    def __init__(
        self,
        name: str,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
        failure_threshold: int = 5,
        recovery_timeout_sec: float = 30.0,
        *,
        ephemeral: bool = False,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout_sec=recovery_timeout_sec,
        )
        self._etag_cache: dict[str, tuple[str, Any]] = {}
        # One pooled client per upstream. Created on the first request so tests can
        # still inject a transport by patching AsyncClient before that call.
        # ephemeral clients (App Store Connect, pack APIs) are not owned by Services,
        # so each request closes its client once the call finishes or is cancelled.
        self._ephemeral = ephemeral
        self._pooled: _PooledClient | None = None
        self._client_lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    async def _acquire(self) -> _PooledClient:
        async with self._client_lock:
            pooled = self._pooled
            if pooled is None or pooled.retire or pooled.client.is_closed:
                pooled = _PooledClient(httpx.AsyncClient(timeout=self.timeout, headers=self.headers))
                self._pooled = pooled
            pooled.inflight += 1
            return pooled

    async def _release(self, pooled: _PooledClient, *, retire: bool) -> None:
        async with self._client_lock:
            pooled.inflight -= 1
            if retire:
                pooled.retire = True
                if self._pooled is pooled:
                    self._pooled = None
            client = self._claim_close(pooled)
        if client is not None:
            await client.aclose()

    def _claim_close(self, pooled: _PooledClient) -> httpx.AsyncClient | None:
        if pooled.inflight > 0 or not pooled.retire or pooled.closing or pooled.client.is_closed:
            return None
        pooled.closing = True
        return pooled.client

    async def aclose(self) -> None:
        async with self._client_lock:
            pooled = self._pooled
            self._pooled = None
            client = None
            if pooled is not None and not pooled.closing and not pooled.client.is_closed:
                pooled.retire = True
                pooled.closing = True
                client = pooled.client
        if client is not None:
            await client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            return not_configured(self.name)
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = {**self.headers, **(kwargs.pop("headers", None) or {})}

        if not self.circuit_breaker.allow_request():
            detail = f"{self.name} circuit breaker is open (cooling down)"
            prob = problem_details(
                status=503,
                title=f"{self.name} circuit breaker open",
                detail=detail,
                error_code="circuit_breaker_open",
                instance=url,
            )
            return {
                "error": "circuit_breaker_open",
                "reason": detail,
                "status": 503,
                "problem": prob,
                "body": None,
                "circuit_breaker": "open",
            }

        # Conditional request handling with ETag for GET requests
        method_upper = method.upper()
        cache_key = f"{url}?{kwargs.get('params')}" if kwargs.get("params") else url
        if method_upper == "GET" and cache_key in self._etag_cache:
            cached_etag, _ = self._etag_cache[cache_key]
            if "If-None-Match" not in headers:
                headers["If-None-Match"] = cached_etag

        pooled: _PooledClient | None = None
        retire = False
        try:
            try:
                pooled = await self._acquire()
                try:
                    resp = await pooled.client.request(method_upper, url, headers=headers, **kwargs)
                except asyncio.CancelledError:
                    _note_budget_http_cancel()
                    raise
            except httpx.TimeoutException:
                self.circuit_breaker.record_failure()
                retire = self.circuit_breaker.state == "open"
                return {"error": UPSTREAM_TIMEOUT, "reason": f"{self.name} did not answer within {self.timeout:.0f}s"}
            except httpx.HTTPError as exc:
                self.circuit_breaker.record_failure()
                retire = self.circuit_breaker.state == "open"
                return {"error": UPSTREAM_ERROR, "reason": f"{self.name}: {redact_text(str(exc))[:300]}"}

            # HTTP 304 Not Modified: return cached response body
            if resp.status_code == 304 and cache_key in self._etag_cache:
                self.circuit_breaker.record_success()
                cached_etag, cached_body = self._etag_cache[cache_key]
                return {"ok": True, "status": 304, "body": cached_body, "cached": True, "etag": cached_etag}

            body = await _json(resp)
            if resp.status_code >= 400:
                if resp.status_code >= 500:
                    self.circuit_breaker.record_failure()
                    retire = self.circuit_breaker.state == "open"
                else:
                    self.circuit_breaker.record_success()

                status = resp.status_code
                error_code = UPSTREAM_ERROR
                title = f"{self.name} upstream error"
                detail = f"{self.name} returned HTTP {status}"
                extra_fields: dict[str, Any] = {
                    "body": redact_value(body) if isinstance(body, (dict, list)) else body,
                }
                if status in (401, 403):
                    title = f"{self.name} authentication failed"
                    detail = f"{self.name} refused credentials (HTTP {status})"
                problem = problem_details(
                    status=status,
                    title=title,
                    detail=detail,
                    error_code="upstream_401" if status in (401, 403) else error_code,
                    instance=url,
                    **extra_fields,
                )
                return {
                    "error": error_code,
                    "reason": detail,
                    "status": status,
                    "problem": problem,
                    "body": extra_fields["body"],
                }

            self.circuit_breaker.record_success()
            etag_header = resp.headers.get("etag") or resp.headers.get("ETag")
            if method_upper == "GET" and etag_header:
                self._etag_cache[cache_key] = (etag_header, redact_value(body))

            return {"ok": True, "status": resp.status_code, "body": redact_value(body)}
        finally:
            if pooled is not None:
                await self._release(pooled, retire=retire)
            if self._ephemeral:
                await self.aclose()


_MEMORY_WRITE_REFUSED = frozenset({"denied", "quarantined", "rejected"})


def memory_write_refusal(name: str, content: Any) -> dict[str, Any] | None:
    """A memory_write body whose outcome is denied, quarantined or rejected is a failed plane.

    Other tools keep the is_error mapping. The substrate reports these refusals as ordinary
    MCP results, so is_error alone would call the write ok.
    """
    if name != "memory_write":
        return None
    if isinstance(content, list):
        blocks = content
    elif isinstance(content, dict):
        blocks = [content]
    else:
        return None
    for block in blocks:
        if not isinstance(block, dict):
            continue
        outcome = block.get("outcome")
        if not isinstance(outcome, str) or outcome not in _MEMORY_WRITE_REFUSED:
            continue
        reason = block.get("reason")
        writer = block.get("writer")
        reason_text = reason if isinstance(reason, str) and reason else outcome
        writer_text = writer if isinstance(writer, str) and writer else "unknown"
        return {
            "ok": False,
            "error": "memory_denied",
            "reason": redact_text(reason_text)[:300],
            "writer": redact_text(writer_text)[:120],
        }
    return None


class Substrate:
    """substrate-mcp on the VPS loopback: plain HTTP for brief/events, MCP for the rest."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "substrate",
            settings.substrate_url,
            headers={"Authorization": f"Bearer {settings.substrate_token}"} if settings.substrate_token else {},
            timeout=6.0,
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.substrate_url and self.settings.substrate_token)

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/healthz")

    async def brief(self, *, repo: str | None, graph_id: str | None) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        payload = {k: v for k, v in {"repo": repo, "graph_id": graph_id, "surface": "grok-bot"}.items() if v}
        result = await self.http.request("POST", "/brief", json=payload)
        if not result.get("ok"):
            # Graceful degradation fallback when substrate brief fails
            fallback_brief = (
                f"[degraded] Substrate is currently unreachable ({result.get('reason', 'upstream error')}). "
                f"Falling back to basic repository context for repo={repo or 'unknown'} graph_id={graph_id or 'none'}."
            )
            return {
                **result,
                "degraded": True,
                "brief": fallback_brief,
            }
        body = result.get("body")
        brief_text = body.get("brief", "") if isinstance(body, dict) else str(body or "")
        return {"ok": True, "brief": redact_text(brief_text[:20000])}

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        return await self.http.request("POST", "/events", json={"surface": "grok-bot", **event})

    async def call_tool(self, name: str, arguments: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        from mcp.client.client import Client
        from mcp.client.streamable_http import streamable_http_client

        try:
            async with asyncio.timeout(timeout):
                http_client = httpx.AsyncClient(headers=self.http.headers, timeout=timeout)
                async with http_client:
                    transport = streamable_http_client(f"{self.http.base_url}/mcp", http_client=http_client)
                    async with Client(transport, read_timeout_seconds=timeout) as client:
                        result = await client.call_tool(name, arguments)
        except TimeoutError:
            return {"error": UPSTREAM_TIMEOUT, "reason": f"substrate {name} did not answer within {timeout:.0f}s"}
        except Exception as exc:  # the MCP client raises many shapes; none of them may reach a Bot raw
            err_msg = redact_text(str(exc))[:300]
            prob = problem_details(
                status=502,
                title="substrate mcp call failed",
                detail=f"substrate {name}: {err_msg}",
                error_code=UPSTREAM_ERROR,
                instance=f"{self.http.base_url}/mcp",
                tool=name,
            )
            return {"error": UPSTREAM_ERROR, "reason": f"substrate {name}: {err_msg}", "problem": prob}
        content: list[Any] = []
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text is None:
                continue
            try:
                content.append(json.loads(text))
            except ValueError:
                content.append(redact_text(text))
        out: dict[str, Any] = {"ok": not result.is_error, "content": redact_value(content)}
        if result.structured_content is not None:
            out["structured"] = redact_value(result.structured_content)
        refusal = memory_write_refusal(name, content)
        if refusal is None and result.structured_content is not None:
            refusal = memory_write_refusal(name, result.structured_content)
        if refusal:
            out.update(refusal)
        elif result.is_error:
            out["error"] = UPSTREAM_ERROR
            out["reason"] = f"substrate {name} reported an error"
        return out


class AgentBus:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "agent-bus",
            settings.agent_bus_url if settings.agent_bus_token else "",
            headers={"Authorization": f"Bearer {settings.agent_bus_token}"} if settings.agent_bus_token else {},
            timeout=10.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/health")

    async def start_job(self, runtime: str, goal: str, provider: str | None, idempotency_key: str | None) -> dict[str, Any]:
        body = {"runtime": runtime, "goal": goal}
        if provider:
            body["provider"] = provider
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        result = await self.http.request("POST", "/v1/jobs", json=body)
        if not result.get("ok"):
            # Graceful degradation fallback when agent bus is unreachable
            return {
                **result,
                "degraded": True,
                "fallback": {
                    "runtime": runtime,
                    "goal": goal,
                    "status": "queued_local_fallback",
                    "reason": result.get("reason", "agent bus unreachable"),
                },
            }
        return result

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/v1/jobs/{job_id}")

    async def wait_job(self, job_id: str, timeout_sec: int, poll_sec: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, Any] = {}
        while True:
            last = await self.get_job(job_id)
            status = (last.get("body") or {}).get("status") if last.get("ok") else None
            if last.get("error") or status in {"completed", "failed", "error"}:
                return last
            if time.monotonic() >= deadline:
                return {**last, "timed_out": True}
            await asyncio.sleep(poll_sec)


class Greptime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        auth = (settings.greptime_user, settings.greptime_password) if settings.greptime_user else None
        self.auth = auth

    @property
    def configured(self) -> bool:
        return bool(self.settings.greptime_url)

    async def sql(self, sql: str, limit: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("greptime")
        problem = read_only_sql(sql)
        if problem:
            return {"error": "invalid_sql", "reason": problem}
        query = f"SELECT * FROM ({sql.rstrip(';')}) AS q LIMIT {int(limit)}"
        try:
            async with httpx.AsyncClient(timeout=10.0, auth=self.auth) as client:
                resp = await client.post(
                    f"{self.settings.greptime_url}/v1/sql",
                    params={"db": self.settings.greptime_db},
                    data={"sql": query},
                )
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"greptime: {redact_text(str(exc))[:300]}"}
        body = await _json(resp)
        if resp.status_code >= 400:
            return {"error": UPSTREAM_ERROR, "reason": f"greptime returned HTTP {resp.status_code}", "body": redact_value(body)}
        return {"ok": True, "body": redact_value(body)}

    async def health(self) -> dict[str, Any]:
        if not self.configured:
            return not_configured("greptime")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.settings.greptime_url}/health")
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": redact_text(str(exc))[:200]}
        return {"ok": resp.status_code < 400, "status": resp.status_code}


class Timescale:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.pg_url

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def query(self, sql: str, limit: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("timescale")
        problem = read_only_sql(sql)
        if problem:
            return {"error": "invalid_sql", "reason": problem}
        try:
            import psycopg
        except ImportError:
            return {"error": NOT_CONFIGURED, "reason": "psycopg is not installed on the gateway (extra: timescale)"}

        def run() -> dict[str, Any]:
            with psycopg.connect(self.url, connect_timeout=5, options="-c default_transaction_read_only=on") as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM ({sql.rstrip(';')}) AS q LIMIT %s", (int(limit),))
                    cols = [d.name for d in cur.description or []]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"ok": True, "columns": cols, "rows": redact_value(json.loads(json.dumps(rows, default=str)))}

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"timescale: {redact_text(str(exc))[:300]}"}

    async def health(self) -> dict[str, Any]:
        result = await self.query("SELECT 1 AS ok", 1)
        return {"ok": bool(result.get("ok")), **({} if result.get("ok") else result)}


TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local fill_rate = tonumber(ARGV[2])
local amount = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_update')
local tokens = tonumber(data[1])
local last_update = tonumber(data[2])

if not tokens or not last_update then
    tokens = capacity
    last_update = now
else
    local delta = math.max(0, now - last_update)
    tokens = math.min(capacity, tokens + delta * fill_rate)
    last_update = now
end

local allowed = 0
local retry_after = 0
if tokens >= amount then
    tokens = tokens - amount
    allowed = 1
else
    retry_after = (amount - tokens) / fill_rate
end

redis.call('HMSET', key, 'tokens', tokens, 'last_update', last_update)
redis.call('EXPIRE', key, math.ceil(capacity / fill_rate) + 60)

return {allowed, tostring(retry_after), tostring(tokens)}
"""


def parse_token_bucket(
    result: Any,
    now: float,
    capacity: int,
    fill_rate: float,
) -> tuple[bool, float, int, float]:
    import math

    allowed = bool(result[0])
    retry_after = float(result[1])
    remaining = int(math.floor(float(result[2])))
    reset_epoch = now + (retry_after if not allowed else max(0.0, (capacity - remaining) / fill_rate))
    return allowed, retry_after, remaining, reset_epoch


def _int_setting(settings: Settings, name: str, default: int) -> int:
    value = getattr(settings, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def _float_setting(settings: Settings, name: str, default: float) -> float:
    value = getattr(settings, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _seconds(settings: Settings, name_ms: str, default_ms: int) -> float:
    return _int_setting(settings, name_ms, default_ms) / 1000.0


class PoolSaturated(Exception):
    """Every pooled connection is in use. This is not an upstream failure."""


def _noscript_error() -> type[BaseException]:
    try:
        from redis.exceptions import NoScriptError
    except ImportError:
        class NoScriptError(Exception):
            pass
        return NoScriptError
    return NoScriptError


def _import_redis() -> Any:
    """Import redis.asyncio, or None when the optional dragonfly extra is absent."""
    try:
        import redis.asyncio as redis
    except ImportError:
        return None
    return redis


class Dragonfly:
    """One shared Redis client for desk_cache and the edge rate limiter.

    A fresh client per call paid the TCP handshake on the request path (about a
    second from the desk host) and then hit a multi-second socket timeout, so
    every seat request waited that out and the local token bucket answered.
    The pool connects once at startup. Commands use a short socket timeout.
    ``request_budget_sec`` is the longest a rate-limit check may wait; the
    caller answers from the local bucket when that budget runs out.
    """

    pool_max_connections = 8
    connect_timeout_sec = 0.5
    command_timeout_sec = 0.25
    request_budget_sec = 0.15
    health_check_interval_sec = 30
    socket_keepalive = True
    breaker_failure_threshold = 3
    breaker_recovery_sec = 30.0

    def __init__(self, settings: Settings) -> None:
        self.url = getattr(settings, "dragonfly_url", "") or ""
        self.connect_timeout_sec = _seconds(settings, "dragonfly_connect_timeout_ms", 500)
        self.command_timeout_sec = _seconds(settings, "dragonfly_command_timeout_ms", 250)
        self.request_budget_sec = _seconds(settings, "dragonfly_rate_limit_budget_ms", 150)
        self.health_check_interval_sec = _int_setting(
            settings, "dragonfly_health_check_interval_sec", self.health_check_interval_sec
        )
        keepalive = getattr(settings, "dragonfly_socket_keepalive", None)
        if isinstance(keepalive, bool):
            self.socket_keepalive = keepalive
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=_int_setting(settings, "dragonfly_breaker_failures", self.breaker_failure_threshold),
            recovery_timeout_sec=_float_setting(
                settings, "dragonfly_breaker_recovery_sec", self.breaker_recovery_sec
            ),
        )
        self._client: Any = None
        self._client_lock = asyncio.Lock()
        self._script: Any = None
        self._script_client: Any = None
        self._sha: str | None = None
        self._trial_in_flight = False
        self._logged_failure = False
        self._inflight = 0
        self._warm_task: asyncio.Task[None] | None = None
        self._script_lock = asyncio.Lock()

    @property
    def warm(self) -> bool:
        return self._client is not None

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def open(self) -> None:
        """Connect and ping outside any seat-request budget.

        The wait covers the connect and the ping. A seat request never awaits this.
        """
        if not self.configured or self._client is not None:
            return
        if _import_redis() is None:
            logger.warning("Dragonfly pool skipped; redis is not installed (extra: dragonfly)")
            return
        if not self.try_acquire():
            return
        client = None
        try:
            client = self._new_client()
            await asyncio.wait_for(
                client.ping(),
                timeout=self.connect_timeout_sec + self.command_timeout_sec,
            )
            async with self._client_lock:
                if self._client is not None:
                    await client.aclose()
                else:
                    self._client = client
                    self._script = None
                    self._script_client = None
                    self._sha = None
                client = None
            self.finish_attempt(ok=True)
        except asyncio.CancelledError:
            self.finish_neutral()
            raise
        except Exception as exc:
            self.finish_attempt(ok=False)
            self.note_failure(type(exc).__name__)
        finally:
            if client is not None:
                await client.aclose()

    def schedule_warm(self) -> None:
        """Retry startup warming on the event loop, not on the request budget."""
        if self._client is not None or not self.configured:
            return
        task = self._warm_task
        if task is not None and not task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._warm_task = loop.create_task(self.open())

    async def nudge_warm(self) -> bool:
        """Start a warm-up if needed. Ready only when that warm-up is already done.

        One event-loop turn lets an instant connect finish. A slow connect keeps
        running in the background and this returns False.
        """
        if self._client is not None:
            return True
        self.schedule_warm()
        await asyncio.sleep(0)
        return self._client is not None

    def try_acquire(self) -> bool:
        """False when the breaker is open, or a half-open trial is already running."""
        if self.circuit_breaker.state == "half-open" and self._trial_in_flight:
            return False
        previous = self.circuit_breaker.state
        allowed = self.circuit_breaker.allow_request()
        self._log_transition(previous)
        if not allowed:
            return False
        if self.circuit_breaker.state == "half-open":
            if self._trial_in_flight:
                return False
            self._trial_in_flight = True
        return True

    def finish_attempt(self, *, ok: bool) -> None:
        previous = self.circuit_breaker.state
        if ok:
            self.circuit_breaker.record_success()
        else:
            self.circuit_breaker.record_failure()
        self._trial_in_flight = False
        self._log_transition(previous)

    def finish_neutral(self) -> None:
        """Release a half-open trial without counting a success or a failure."""
        self._trial_in_flight = False

    def note_failure(self, kind: str) -> None:
        self._note_failure(kind)

    def _reserve(self) -> None:
        if self._inflight >= self.pool_max_connections:
            raise PoolSaturated()
        self._inflight += 1

    def _release_slot(self) -> None:
        if self._inflight:
            self._inflight -= 1

    def _note_failure(self, kind: str) -> None:
        if self._logged_failure:
            return
        self._logged_failure = True
        logger.warning(
            "Dragonfly rate limiting failed (%s); local bucket answers until the circuit changes",
            redact_text(kind),
        )

    def _log_transition(self, previous: str) -> None:
        current = self.circuit_breaker.state
        if current == previous:
            return
        logger.warning("Dragonfly circuit %s -> %s", previous, current)

    async def pooled_client(self) -> Any:
        """Return the shared client. Connecting happens in ``open``, not here."""
        if self._client is None:
            raise PoolSaturated()
        return self._client

    def _new_client(self) -> Any:
        redis = _import_redis()
        if redis is None:
            raise RuntimeError("redis is not installed on the gateway (extra: dragonfly)")
        return redis.from_url(
            self.url,
            socket_timeout=self.command_timeout_sec,
            socket_connect_timeout=self.connect_timeout_sec,
            socket_keepalive=self.socket_keepalive,
            decode_responses=True,
            max_connections=self.pool_max_connections,
            health_check_interval=self.health_check_interval_sec,
        )

    async def aclose(self) -> None:
        current = asyncio.current_task()
        task = self._warm_task
        self._warm_task = None
        if task is not None and task is not current and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        async with self._client_lock:
            client = self._client
            self._client = None
            self._script = None
            self._script_client = None
            self._sha = None
        if client is not None:
            await client.aclose()

    async def command(self, action: str, key: str, value: str | None, ttl_sec: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("dragonfly")
        if action not in {"get", "set", "del", "ping"}:
            return {"error": "invalid_action", "reason": action}
        if _import_redis() is None:
            return {"error": NOT_CONFIGURED, "reason": "redis is not installed on the gateway (extra: dragonfly)"}
        if not await self.nudge_warm():
            return {"error": UPSTREAM_ERROR, "reason": "dragonfly: warming"}
        if not self.try_acquire():
            return {
                "error": "circuit_breaker_open",
                "reason": "dragonfly circuit breaker is open (cooling down)",
                "circuit_breaker": "open",
            }
        try:
            result = await asyncio.wait_for(
                self._execute(action, key, value, ttl_sec),
                timeout=self.command_timeout_sec,
            )
        except asyncio.CancelledError:
            self.finish_neutral()
            raise
        except TimeoutError:
            self.finish_attempt(ok=False)
            self._note_failure("timeout")
            return {"error": UPSTREAM_ERROR, "reason": "dragonfly: command budget exceeded"}
        except PoolSaturated:
            self.finish_neutral()
            return {"error": UPSTREAM_ERROR, "reason": "dragonfly: pool busy"}
        except Exception as exc:
            self.finish_attempt(ok=False)
            self._note_failure(type(exc).__name__)
            return {"error": UPSTREAM_ERROR, "reason": f"dragonfly: {type(exc).__name__}"}
        self.finish_attempt(ok=True)
        return result

    async def _execute(self, action: str, key: str, value: str | None, ttl_sec: int) -> dict[str, Any]:
        self._reserve()
        try:
            client = await self.pooled_client()
            if action == "get":
                return {"ok": True, "value": await client.get(key)}
            if action == "set":
                await client.set(key, value or "", ex=int(ttl_sec))
                return {"ok": True}
            if action == "del":
                return {"ok": True, "deleted": int(await client.delete(key))}
            return {"ok": bool(await client.ping())}
        finally:
            self._release_slot()

    async def eval_token_bucket(
        self,
        key: str,
        capacity: int,
        fill_rate: float,
        amount: int,
    ) -> tuple[bool, float, int, float]:
        """Run the shared token-bucket script. The body is loaded once; later calls are EVALSHA."""
        import time

        self._reserve()
        try:
            client = await self.pooled_client()
            now = time.time()
            redis_key = f"desk:ratelimit:tokenbucket:{key}"
            result = await self._evalsha(
                client,
                redis_key,
                str(capacity),
                str(fill_rate),
                str(amount),
                str(now),
            )
            return parse_token_bucket(result, now, capacity, fill_rate)
        finally:
            self._release_slot()

    async def _evalsha(self, client: Any, redis_key: str, *args: str) -> Any:
        NoScriptError = _noscript_error()
        sha = await self._ensure_sha(client)
        try:
            return await client.evalsha(sha, 1, redis_key, *args)
        except NoScriptError:
            sha = await self._reload_sha(client)
            return await client.evalsha(sha, 1, redis_key, *args)

    async def _ensure_sha(self, client: Any) -> str:
        async with self._script_lock:
            if self._sha is not None and self._script_client is client:
                return self._sha
            sha = await client.script_load(TOKEN_BUCKET_LUA)
            self._script = client.register_script(TOKEN_BUCKET_LUA)
            self._script_client = client
            self._sha = sha
            return sha

    async def _reload_sha(self, client: Any) -> str:
        async with self._script_lock:
            sha = await client.script_load(TOKEN_BUCKET_LUA)
            self._script_client = client
            self._sha = sha
            return sha

    async def health(self) -> dict[str, Any]:
        return await self.command("ping", "health", None, 1)


class Hindsight:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "hindsight",
            settings.hindsight_url if settings.hindsight_api_key else "",
            headers={"Authorization": f"Bearer {settings.hindsight_api_key}"} if settings.hindsight_api_key else {},
            timeout=10.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/health")

    async def retain(self, bank: str, content: str, tags: list[str], context: str | None) -> dict[str, Any]:
        item: dict[str, Any] = {"content": redact_text(content), "tags": tags}
        if context:
            item["context"] = redact_text(context)
        return await self.http.request("POST", f"/v1/default/banks/{bank}/memories", json={"items": [item]})

    async def recall(self, bank: str, query: str, max_results: int) -> dict[str, Any]:
        body = {"query": query, "budget": "mid", "max_tokens": min(4096, 400 * max_results)}
        return await self.http.request("POST", f"/v1/default/banks/{bank}/memories/recall", json=body)


_UNKNOWN_DATASET_MARKERS = (
    "unknown dataset",
    "dataset not found",
    "dataset does not exist",
    "invalid dataset",
    "can't find the dataset",
    "cannot find dataset",
)


def is_unknown_dataset(result: dict[str, Any]) -> bool:
    """True when a retrieval failed because RAGflow does not know a dataset id."""
    if not isinstance(result, dict) or not result.get("error"):
        return False
    parts = [str(result.get("reason") or ""), str(result.get("error") or "")]
    body = result.get("body")
    if isinstance(body, (dict, list)):
        parts.append(json.dumps(body))
    elif isinstance(body, str):
        parts.append(body)
    text = " ".join(parts).lower()
    return any(marker in text for marker in _UNKNOWN_DATASET_MARKERS)


class RAGFlow:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._dataset_ids: dict[str, str] = {}
        self._dataset_absent: set[str] = set()
        self._dataset_listed_at: float = 0.0
        self._dataset_lock = asyncio.Lock()
        self.http = HttpUpstream(
            "ragflow",
            settings.ragflow_url if settings.ragflow_api_key else "",
            headers={"Authorization": f"Bearer {settings.ragflow_api_key}"} if settings.ragflow_api_key else {},
            timeout=12.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/api/v1/datasets", params={"page": 1, "page_size": 1})

    async def datasets(self) -> dict[str, Any]:
        return await self.http.request("GET", "/api/v1/datasets", params={"page": 1, "page_size": 100})

    async def retrieve(self, question: str, dataset_ids: list[str], top_k: int) -> dict[str, Any]:
        body = {"question": question, "dataset_ids": dataset_ids, "top_k": top_k, "page_size": top_k}
        return await self.http.request("POST", "/api/v1/retrieval", json=body)

    def _dataset_ttl(self) -> float:
        return float(getattr(self.settings, "ragflow_dataset_ttl_sec", RAGFLOW_DATASET_TTL_SEC))

    def _dataset_cache_fresh(self) -> bool:
        if self._dataset_listed_at <= 0:
            return False
        return (time.monotonic() - self._dataset_listed_at) < self._dataset_ttl()

    def _clear_dataset_cache(self) -> None:
        self._dataset_listed_at = 0.0
        self._dataset_ids = {}
        self._dataset_absent = set()

    async def _reload_dataset_ids(self) -> dict[str, Any] | None:
        listed = await self.datasets()
        if listed.get("error"):
            return listed
        body = listed.get("body") or {}
        data = body.get("data") if isinstance(body, dict) else None
        ids: dict[str, str] = {}
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                name = row.get("name")
                dataset_id = row.get("id")
                if isinstance(name, str) and name and dataset_id:
                    ids[name] = str(dataset_id)
        self._dataset_ids = ids
        self._dataset_absent -= set(ids)
        self._dataset_listed_at = time.monotonic()
        return None

    def _cached_resolution(self, names: list[str]) -> dict[str, Any] | None:
        if not self._dataset_cache_fresh():
            return None
        if any(name not in self._dataset_ids and name not in self._dataset_absent for name in names):
            return None
        return {
            "ok": True,
            "ids": [self._dataset_ids[name] for name in names if name in self._dataset_ids],
            "missing": [name for name in names if name not in self._dataset_ids],
        }

    async def resolve_dataset_ids(self, names: list[str], *, refresh: bool = False) -> dict[str, Any]:
        """Map dataset names to ids. One list per TTL, plus one refresh on a miss.

        A name that is still missing after that refresh is remembered until the TTL
        expires, so a dataset RAGflow does not have is not listed on every call.
        ``refresh=True`` drops the cache under the same lock before that lookup,
        which is how an unknown-dataset retrieval forces exactly one new list.
        A fresh cache is returned without waiting on a reload another search started.
        """
        if not refresh:
            cached = self._cached_resolution(names)
            if cached is not None:
                return cached
        async with self._dataset_lock:
            if refresh:
                self._clear_dataset_cache()
            else:
                cached = self._cached_resolution(names)
                if cached is not None:
                    return cached
            if not self._dataset_cache_fresh():
                failed = await self._reload_dataset_ids()
                if failed is not None:
                    return failed
            unseen = [name for name in names if name not in self._dataset_ids and name not in self._dataset_absent]
            if unseen:
                failed = await self._reload_dataset_ids()
                if failed is not None:
                    return failed
                for name in names:
                    if name not in self._dataset_ids:
                        self._dataset_absent.add(name)
            ids = [self._dataset_ids[name] for name in names if name in self._dataset_ids]
            missing = [name for name in names if name not in self._dataset_ids]
            return {"ok": True, "ids": ids, "missing": missing}


RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"


class Railway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "railway",
            RAILWAY_GRAPHQL if settings.railway_api_token else "",
            headers={"Authorization": f"Bearer {settings.railway_api_token}"} if settings.railway_api_token else {},
            timeout=15.0,
        )

    def project_id(self, name: str) -> str | None:
        return self.settings.railway_projects.get(name)

    async def gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        result = await self.http.request("POST", "", json={"query": query, "variables": variables})
        if result.get("ok") and isinstance(result.get("body"), dict) and result["body"].get("errors"):
            return {"error": UPSTREAM_ERROR, "reason": "railway graphql errors", "body": result["body"]["errors"]}
        return result

    async def project_status(self, name: str) -> dict[str, Any]:
        pid = self.project_id(name)
        if not pid:
            return not_configured(f"railway project {name}")
        query = """
        query Project($id: String!) {
          project(id: $id) { id name
            services { edges { node { id name
              serviceInstances { edges { node { environmentId latestDeployment { id status createdAt } } } } } } }
            environments { edges { node { id name } } } } }
        """
        result = await self.gql(query, {"id": pid})
        return result

    async def logs(self, deployment_id: str, lines: int) -> dict[str, Any]:
        query = "query Logs($id: String!, $limit: Int) { deploymentLogs(deploymentId: $id, limit: $limit) { timestamp message severity } }"
        return await self.gql(query, {"id": deployment_id, "limit": lines})

    async def variable_names(self, project_id: str, environment_id: str, service_id: str) -> dict[str, Any]:
        query = "query Vars($p: String!, $e: String!, $s: String) { variables(projectId: $p, environmentId: $e, serviceId: $s) }"
        result = await self.gql(query, {"p": project_id, "e": environment_id, "s": service_id})
        if result.get("ok"):
            data = (result.get("body") or {}).get("data") or {}
            names = sorted((data.get("variables") or {}).keys())
            return {"ok": True, "names": names}
        return result

    async def redeploy(self, service_id: str, environment_id: str) -> dict[str, Any]:
        query = "mutation Redeploy($s: String!, $e: String!) { serviceInstanceRedeploy(serviceId: $s, environmentId: $e) }"
        return await self.gql(query, {"s": service_id, "e": environment_id})


class Vercel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "vercel",
            "https://api.vercel.com" if settings.vercel_token else "",
            headers={"Authorization": f"Bearer {settings.vercel_token}"} if settings.vercel_token else {},
            timeout=15.0,
        )

    def allowed(self, project: str) -> bool:
        return project in self.settings.vercel_projects

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(extra or {})
        if self.settings.vercel_team_id:
            params["teamId"] = self.settings.vercel_team_id
        return params

    async def deployments(self, project: str, limit: int) -> dict[str, Any]:
        return await self.http.request("GET", "/v6/deployments", params=self._params({"app": project, "limit": limit}))

    async def deployment(self, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/v13/deployments/{deployment_id}", params=self._params())

    async def promote(self, project: str, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/v10/projects/{project}/promote/{deployment_id}", params=self._params())

    async def rollback(self, project: str, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/v9/projects/{project}/rollback/{deployment_id}", params=self._params())


class Greptile:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        headers = {}
        if settings.greptile_api_key:
            headers["Authorization"] = f"Bearer {settings.greptile_api_key}"
        if settings.greptile_github_token:
            headers["X-GitHub-Token"] = settings.greptile_github_token
        self.http = HttpUpstream("greptile", "https://api.greptile.com/v2" if settings.greptile_api_key else "", headers=headers)

    async def trigger(self, repo: str, pr_number: int) -> dict[str, Any]:
        return await self.http.request("POST", "/reviews", json={"repository": repo, "remote": "github", "prNumber": pr_number})

    async def get(self, review_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/reviews/{review_id}")

    async def comments(self, repo: str, pr_number: int) -> dict[str, Any]:
        return await self.http.request("GET", "/reviews", params={"repository": repo, "prNumber": pr_number})


class GitHub:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "github",
            "https://api.github.com" if settings.github_token else "",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if settings.github_token
            else {},
            timeout=15.0,
        )

    async def comment_on_issue(self, repo: str, number: int, body: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body})

    async def find_issue_comment(
        self, repo: str, number: int, marker: str, *, since: str | None = None, max_pages: int = 5
    ) -> dict[str, Any]:
        """Whether a comment carrying `marker` is already on the issue.

        GitHub lists issue comments oldest-first with no way to reverse them, so on a long
        thread the pages this walks are the *oldest* comments — the least likely to hold a
        marker a caller is asking about. `since` is what makes the search reach it: an
        ISO-8601 instant, narrowing the thread to comments touched after it, so a window
        around when the comment would have been written costs one page whatever the thread's
        length. A caller that omits it on a thread longer than the page budget will not find
        a comment that is there.

        `complete` is the honest part: a `found: false` that ran out of page budget is not
        evidence of absence. A caller using this to decide whether it already posted
        something must not post on `complete: false`.
        """
        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {"per_page": 100, "page": page}
            if since:
                params["since"] = since
            result = await self.http.request("GET", f"/repos/{repo}/issues/{number}/comments", params=params)
            if not result.get("ok"):
                return result
            comments = result.get("body")
            if not isinstance(comments, list):
                return {"error": UPSTREAM_ERROR, "reason": "github returned no comment list for the issue"}
            for comment in comments:
                if isinstance(comment, dict) and marker in (comment.get("body") or ""):
                    return {"ok": True, "found": True, "complete": True}
            if len(comments) < 100:
                return {"ok": True, "found": False, "complete": True}
        return {"ok": True, "found": False, "complete": False}


class PlayConsole:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "play-console",
            "https://androidpublisher.googleapis.com/androidpublisher/v3" if settings.play_access_token else "",
            headers={"Authorization": f"Bearer {settings.play_access_token}"} if settings.play_access_token else {},
            timeout=15.0,
        )

    async def edit(self, package_name: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/applications/{package_name}/edits", json={})

    async def track(self, package_name: str, edit_id: str, track: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/applications/{package_name}/edits/{edit_id}/tracks/{track}")

    async def update_track(self, package_name: str, edit_id: str, track: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self.http.request("PUT", f"/applications/{package_name}/edits/{edit_id}/tracks/{track}", json=body)

    async def commit(self, package_name: str, edit_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/applications/{package_name}/edits/{edit_id}:commit", json={})


class AppStoreConnect:
    """ASC needs an ES256 JWT minted from the .p8 key. The gateway mints one per call when
    PyJWT is installed; without it the tools report not_configured rather than guessing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.asc_key_id and s.asc_issuer_id and s.asc_private_key_path)

    def _token(self) -> str | None:
        if not self.configured:
            return None
        try:
            import jwt
        except ImportError:
            return None
        try:
            key = open(self.settings.asc_private_key_path, encoding="utf-8").read()
        except OSError:
            return None
        now = int(time.time())
        return jwt.encode(
            {"iss": self.settings.asc_issuer_id, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
            key,
            algorithm="ES256",
            headers={"kid": self.settings.asc_key_id},
        )

    def client(self) -> HttpUpstream:
        token = self._token()
        return HttpUpstream(
            "app-store-connect",
            "https://api.appstoreconnect.apple.com/v1" if token else "",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=15.0,
            ephemeral=True,
        )


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Stop a child and reap it, so it cannot outlive the call that started it.

    Signals the whole process group, because the commands here start their own children: a
    gate runs git, and killing only the gate leaves git behind holding an index lock. TERM
    first so git can drop that lock, then KILL. The group exists because run_command starts
    each child in its own session.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):   # gone, or not ours to signal
            with contextlib.suppress(ProcessLookupError):
                proc.kill() if sig == signal.SIGKILL else proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 3)
            return
        except asyncio.TimeoutError:    # still there: fall through to KILL, then give up
            continue


async def run_command(
    argv: list[str],
    *,
    cwd: str | None = None,
    timeout: float = 15.0,
    input_text: str | None = None,
    max_out: int = 6000,
    run_as: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Run a command and return its exit code and (redacted) output.

    `run_as` is a (uid, gid) the child is dropped to before exec. Dropping needs the gateway
    to be root, so a failure to apply it is reported as a failed command rather than ignored:
    a gate that was meant to run unprivileged must not quietly run as root instead.
    """
    creds: dict[str, Any] = {"user": run_as[0], "group": run_as[1], "extra_groups": []} if run_as else {}
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # its own process group, so a timeout can kill the tree
            **creds,
        )
    except FileNotFoundError:
        return {"exit_code": 127, "stdout": "", "stderr": f"{argv[0]}: not found", "cmd": shlex.join(argv)}
    except (PermissionError, OSError, ValueError) as exc:
        detail = f" as uid {run_as[0]}" if run_as else ""
        return {"exit_code": 126, "stdout": "", "stderr": f"{argv[0]}: could not start{detail}: {redact_text(str(exc))[:200]}", "cmd": shlex.join(argv)}
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input_text.encode() if input_text is not None else None), timeout
        )
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        # wait_for only stops waiting; the child keeps running. Gate and git commands here
        # can be slow, and the unit runs as root, so an unreaped child per timeout
        # accumulates processes holding the export tree open. Kill and reap before
        # returning, and re-raise a cancellation rather than reporting it as a timeout.
        await _terminate(proc)
        if isinstance(exc, asyncio.CancelledError):
            raise
        return {"exit_code": 124, "stdout": "", "stderr": f"timed out after {timeout:.0f}s", "cmd": shlex.join(argv)}
    return {
        "exit_code": proc.returncode,
        "stdout": redact_text(out.decode(errors="replace")[-max_out:]),
        "stderr": redact_text(err.decode(errors="replace")[-3000:]),
        "cmd": shlex.join(argv),
    }
