"""Pooled Dragonfly client: one connection, a short budget, and a circuit breaker.

The rate limiter used to open a Redis client on every request with a 2 s
socket timeout. These tests cover an unreachable pool, a slow command, and a
flapping server without a live Dragonfly.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from desk_gateway.edge import DistributedRateLimiter
from desk_gateway.upstreams import CircuitBreaker, Dragonfly


class _Settings:
    def __init__(self, url: str) -> None:
        self.dragonfly_url = url


class _ScriptedRedis:
    def __init__(self) -> None:
        self.evals = 0
        self.closed = False
        self.mode = "fail"
        self.delay = 0.0

    async def eval(self, *_args: object, **_kwargs: object) -> list[object]:
        self.evals += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.mode == "fail":
            raise ConnectionError("dragonfly unreachable")
        return [1, "0", "9"]

    async def aclose(self) -> None:
        self.closed = True


class _Pool:
    def __init__(self, client: _ScriptedRedis, breaker: CircuitBreaker, budget: float) -> None:
        self.configured = True
        self.url = "redis://pool.invalid:6379"
        self.circuit_breaker = breaker
        self.request_budget_sec = budget
        self._client = client
        self.borrows = 0

    async def pooled_client(self) -> _ScriptedRedis:
        self.borrows += 1
        return self._client


def _limiter(pool: _Pool) -> DistributedRateLimiter:
    limiter = DistributedRateLimiter(dragonfly_service=pool)
    limiter.configure_seat("lead", rate_per_min=60, burst_capacity=10)
    return limiter


@pytest.mark.asyncio
async def test_unreachable_dragonfly_falls_back_without_raising() -> None:
    client = _ScriptedRedis()
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_sec=30.0)
    pool = _Pool(client, breaker, budget=0.40)
    limiter = _limiter(pool)

    started = time.monotonic()
    allowed, retry_after, _remaining, _reset = await limiter.check_rate_limit("lead")
    elapsed = time.monotonic() - started

    assert allowed is True
    assert retry_after == 0.0
    assert client.evals == 1
    assert client.closed is False
    assert breaker.failure_count == 1
    assert breaker.state == "closed"
    assert elapsed < 0.40


@pytest.mark.asyncio
async def test_slow_dragonfly_loses_to_the_request_budget() -> None:
    client = _ScriptedRedis()
    client.mode = "ok"
    client.delay = 2.0
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_sec=30.0)
    pool = _Pool(client, breaker, budget=0.05)
    limiter = _limiter(pool)

    started = time.monotonic()
    allowed, _retry, _remaining, _reset = await limiter.check_rate_limit("lead")
    elapsed = time.monotonic() - started

    assert allowed is True
    assert elapsed < 0.30
    assert breaker.failure_count == 1
    assert client.closed is False


@pytest.mark.asyncio
async def test_flapping_dragonfly_is_skipped_while_the_circuit_is_open() -> None:
    client = _ScriptedRedis()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=30.0)
    pool = _Pool(client, breaker, budget=0.40)
    limiter = _limiter(pool)

    await limiter.check_rate_limit("lead")
    await limiter.check_rate_limit("lead")
    assert client.evals == 2
    assert breaker.state == "open"

    await limiter.check_rate_limit("lead")
    assert client.evals == 2
    assert pool.borrows == 2

    breaker.last_failure_time = 0.0
    client.mode = "ok"
    allowed, _retry, remaining, _reset = await limiter.check_rate_limit("lead")
    assert allowed is True
    assert remaining == 9
    assert client.evals == 3
    assert breaker.state == "closed"

    breaker.state = "half-open"
    client.mode = "fail"
    await limiter.check_rate_limit("lead")
    assert breaker.state == "open"
    skipped_at = client.evals
    await limiter.check_rate_limit("lead")
    assert client.evals == skipped_at


@pytest.mark.asyncio
async def test_open_circuit_does_not_borrow_the_pool() -> None:
    client = _ScriptedRedis()
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_sec=60.0)
    breaker.record_failure()
    pool = _Pool(client, breaker, budget=0.40)
    limiter = _limiter(pool)

    allowed, _retry, _remaining, _reset = await limiter.check_rate_limit("lead")

    assert allowed is True
    assert pool.borrows == 0
    assert client.evals == 0


class _FakeRedis:
    def __init__(self) -> None:
        self.gets = 0
        self.pings = 0
        self.closed = False

    async def get(self, _key: str) -> str:
        self.gets += 1
        return "v"

    async def ping(self) -> bool:
        self.pings += 1
        return True

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_command_reuses_one_client_until_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeRedis] = []
    kwargs_seen: list[dict[str, object]] = []

    def from_url(*_args: object, **kwargs: object) -> _FakeRedis:
        client = _FakeRedis()
        created.append(client)
        kwargs_seen.append(kwargs)
        return client

    import redis.asyncio as redis_async

    monkeypatch.setattr(redis_async, "from_url", from_url)
    dragonfly = Dragonfly(_Settings("redis://127.0.0.1:1/0"))

    await dragonfly.open()
    first = await dragonfly.command("get", "desk:cache:a", None, 60)
    second = await dragonfly.command("get", "desk:cache:b", None, 60)

    assert first == {"ok": True, "value": "v"}
    assert second == {"ok": True, "value": "v"}
    assert len(created) == 1
    assert created[0].gets == 2
    assert created[0].pings == 1
    assert created[0].closed is False
    assert kwargs_seen[0]["socket_timeout"] == Dragonfly.command_timeout_sec
    assert kwargs_seen[0]["socket_connect_timeout"] == Dragonfly.connect_timeout_sec
    assert kwargs_seen[0]["max_connections"] == Dragonfly.pool_max_connections
    assert Dragonfly.command_timeout_sec < 2.0
    assert Dragonfly.request_budget_sec < 2.0

    await dragonfly.aclose()
    assert created[0].closed is True
    await dragonfly.aclose()


@pytest.mark.asyncio
async def test_open_breaker_skips_cache_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[_FakeRedis] = []

    def from_url(*_args: object, **_kwargs: object) -> _FakeRedis:
        client = _FakeRedis()
        created.append(client)
        return client

    import redis.asyncio as redis_async

    monkeypatch.setattr(redis_async, "from_url", from_url)
    dragonfly = Dragonfly(_Settings("redis://127.0.0.1:1/0"))
    dragonfly.circuit_breaker.failure_threshold = 1
    dragonfly.circuit_breaker.record_failure()

    result = await dragonfly.command("get", "desk:cache:a", None, 60)

    assert result["error"] == "circuit_breaker_open"
    assert result["circuit_breaker"] == "open"
    assert created == []


@pytest.mark.asyncio
async def test_services_aclose_closes_the_dragonfly_pool() -> None:
    from desk_gateway.tools import Services

    closed = []

    class _Dragonfly:
        async def aclose(self) -> None:
            closed.append("dragonfly")

    services = SimpleNamespace(
        substrate=SimpleNamespace(http=None),
        agent_bus=SimpleNamespace(http=None),
        greptime=SimpleNamespace(http=None),
        timescale=SimpleNamespace(http=None),
        hindsight=SimpleNamespace(http=None),
        ragflow=SimpleNamespace(http=None),
        railway=SimpleNamespace(http=None),
        vercel=SimpleNamespace(http=None),
        greptile=SimpleNamespace(http=None),
        github=SimpleNamespace(http=None),
        play=SimpleNamespace(http=None),
        asc=SimpleNamespace(http=None),
        dragonfly=_Dragonfly(),
    )
    await Services.aclose(services)  # type: ignore[arg-type]
    assert closed == ["dragonfly"]


@pytest.mark.asyncio
async def test_lifespan_opens_the_pool_before_serving() -> None:
    from starlette.applications import Starlette

    from desk_gateway.server import _install_upstream_shutdown

    events: list[str] = []

    class _Dragonfly:
        async def open(self) -> None:
            events.append("open")

        async def aclose(self) -> None:
            events.append("aclose")

    class _Services:
        def __init__(self) -> None:
            self.dragonfly = _Dragonfly()

        async def aclose(self) -> None:
            events.append("services")
            await self.dragonfly.aclose()

    app = Starlette()
    _install_upstream_shutdown(app, _Services())
    async with app.router.lifespan_context(app):
        assert events == ["open"]
    assert events == ["open", "services", "aclose"]
