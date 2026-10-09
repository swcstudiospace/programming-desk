"""Pooled, fail-open Dragonfly rate limiter.

No live server. Fakes sleep or raise. The slow and pooling cases fail on the
pre-change limiter, which opened a client and sent the script on every call.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from desk_gateway.config import Settings
from desk_gateway.edge import DistributedRateLimiter
from desk_gateway.server import build_app
from desk_gateway.upstreams import TOKEN_BUCKET_LUA, CircuitBreaker, Dragonfly
from tests.conftest import PASS, REPO

PLACEHOLDER = "configured"


class _Url:
    def __init__(self, url: str = PLACEHOLDER) -> None:
        self.dragonfly_url = url


class _Client:
    def __init__(self, *, delay: float = 0.0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail
        self.loads: list[str] = []
        self.shas = 0
        self.registers = 0
        self.gets = 0
        self.pings = 0
        self.evals = 0
        self.closed = False

    async def eval(self, script: str, *_args: object) -> list[object]:
        """The pre-change limiter sent the script body this way on every call."""
        self.evals += 1
        self.loads.append(script)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("refused")
        return [1, "0", "9"]

    def register_script(self, script: str) -> _Client:
        self.registers += 1
        assert "HMGET" in script
        return self

    async def script_load(self, script: str) -> str:
        self.loads.append(script)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("refused")
        return "sha"

    async def evalsha(self, *_args: object) -> list[object]:
        self.shas += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise ConnectionError("refused")
        await asyncio.sleep(0)
        return [1, "0", "9"]

    async def get(self, _key: str) -> str:
        self.gets += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return "v"

    async def ping(self) -> bool:
        self.pings += 1
        if self.fail:
            raise ConnectionError("refused")
        return True

    async def aclose(self) -> None:
        self.closed = True


def _patch_factory(monkeypatch: pytest.MonkeyPatch, client: _Client | None = None, *, raise_on_create: bool = False) -> list[object]:
    created: list[object] = []

    def from_url(*_args: object, **kwargs: object) -> _Client:
        created.append(kwargs)
        if raise_on_create:
            raise ConnectionError("refused")
        assert client is not None
        return client

    import redis.asyncio as redis_async

    monkeypatch.setattr(redis_async, "from_url", from_url)
    return created


def _limiter(dragonfly: Dragonfly) -> DistributedRateLimiter:
    limiter = DistributedRateLimiter(dragonfly_service=dragonfly)
    limiter.configure_seat("lead", rate_per_min=6000, burst_capacity=100)
    return limiter


def test_defaults_match_the_spec() -> None:
    dragonfly = Dragonfly(_Url())
    assert dragonfly.connect_timeout_sec == 0.5
    assert dragonfly.command_timeout_sec == 0.25
    assert dragonfly.request_budget_sec == 0.15
    assert dragonfly.health_check_interval_sec == 30
    assert dragonfly.socket_keepalive is True
    assert dragonfly.circuit_breaker.failure_threshold == 3
    assert dragonfly.circuit_breaker.recovery_timeout_sec == 30.0
    assert isinstance(dragonfly.circuit_breaker, CircuitBreaker)


@pytest.mark.asyncio
async def test_twenty_slow_checks_finish_inside_one_second(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(delay=2.0)
    created = _patch_factory(monkeypatch, client)
    dragonfly = Dragonfly(_Url())
    limiter = _limiter(dragonfly)

    started = time.monotonic()
    for _ in range(20):
        one = time.monotonic()
        allowed, _retry, _remaining, _reset = await limiter.check_rate_limit("lead")
        assert allowed is True
        assert time.monotonic() - one < 0.3
    elapsed = time.monotonic() - started

    assert elapsed < 1.0
    assert dragonfly.circuit_breaker.state == "open"
    assert limiter.dragonfly_timeout == dragonfly.circuit_breaker.failure_threshold
    assert limiter.status()["mode"] == "breaker_open"
    # The pool is created once; an open breaker makes no further attempts.
    assert len(created) == 1
    borrows_after_open = client.shas + len(client.loads)
    await limiter.check_rate_limit("lead")
    assert client.shas + len(client.loads) == borrows_after_open


@pytest.mark.asyncio
async def test_refused_connections_open_the_breaker_and_then_one_trial_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = _patch_factory(monkeypatch, raise_on_create=True)
    dragonfly = Dragonfly(_Url())
    limiter = _limiter(dragonfly)
    threshold = dragonfly.circuit_breaker.failure_threshold

    for _ in range(threshold):
        await limiter.check_rate_limit("lead")
    assert len(created) == threshold
    assert dragonfly.circuit_breaker.state == "open"

    await limiter.check_rate_limit("lead")
    assert len(created) == threshold

    dragonfly.circuit_breaker.last_failure_time = 0.0
    healthy = _Client()

    def from_url(*_args: object, **_kwargs: object) -> _Client:
        created.append("factory")
        return healthy

    import redis.asyncio as redis_async

    monkeypatch.setattr(redis_async, "from_url", from_url)
    allowed, _retry, remaining, _reset = await limiter.check_rate_limit("lead")
    assert allowed is True
    assert remaining == 9
    assert dragonfly.circuit_breaker.state == "closed"
    assert len(created) == threshold + 1
    assert healthy.loads == [TOKEN_BUCKET_LUA]
    assert healthy.shas == 1


@pytest.mark.asyncio
async def test_half_open_allows_one_trial(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(delay=0.05)
    _patch_factory(monkeypatch, client)
    dragonfly = Dragonfly(_Url())
    await dragonfly.pooled_client()
    dragonfly.circuit_breaker.state = "half-open"
    dragonfly.circuit_breaker.last_failure_time = time.monotonic()
    limiter = _limiter(dragonfly)

    await asyncio.gather(limiter.check_rate_limit("lead"), limiter.check_rate_limit("lead"))

    assert client.shas == 1
    assert dragonfly.circuit_breaker.state == "closed"


@pytest.mark.asyncio
async def test_healthy_pool_loads_the_script_once(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    created = _patch_factory(monkeypatch, client)
    dragonfly = Dragonfly(_Url())
    limiter = _limiter(dragonfly)

    for _ in range(100):
        allowed, _retry, remaining, _reset = await limiter.check_rate_limit("lead")
        assert allowed is True
        assert remaining == 9

    assert len(created) == 1
    options = created[0]
    assert isinstance(options, dict)
    assert options["socket_keepalive"] is True
    assert options["health_check_interval"] == 30
    assert options["socket_connect_timeout"] == 0.5
    assert options["socket_timeout"] == 0.25
    assert options["max_connections"] == 8
    assert client.registers == 1
    assert client.loads == [TOKEN_BUCKET_LUA]
    assert client.shas == 100
    assert limiter.dragonfly_ok == 100
    assert limiter.status()["mode"] == "dragonfly"

    await dragonfly.aclose()
    assert client.closed is True


@pytest.mark.asyncio
async def test_unset_url_stays_on_the_local_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _patch_factory(monkeypatch, _Client())
    dragonfly = Dragonfly(_Url(""))
    limiter = DistributedRateLimiter(dragonfly_service=dragonfly)
    limiter.configure_seat("lead", rate_per_min=60, burst_capacity=2)

    assert (await limiter.check_rate_limit("lead"))[0] is True
    assert (await limiter.check_rate_limit("lead"))[0] is True
    assert (await limiter.check_rate_limit("lead"))[0] is False
    assert created == []
    assert limiter.status()["mode"] == "local"


@pytest.mark.asyncio
async def test_hung_command_returns_inside_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(delay=2.0)
    _patch_factory(monkeypatch, client)
    dragonfly = Dragonfly(_Url())
    dragonfly.request_budget_sec = 0.05

    started = time.monotonic()
    result = await dragonfly.command("get", "desk:cache:a", None, 60)
    elapsed = time.monotonic() - started

    assert elapsed < 0.3
    assert result["error"] == "upstream_error"
    assert "budget" in result["reason"]
    assert PLACEHOLDER not in result["reason"]


@pytest.mark.asyncio
async def test_first_failure_is_logged_once(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    _patch_factory(monkeypatch, raise_on_create=True)
    dragonfly = Dragonfly(_Url())
    limiter = _limiter(dragonfly)
    with caplog.at_level("WARNING"):
        for _ in range(5):
            await limiter.check_rate_limit("lead")
    failures = [rec for rec in caplog.records if "rate limiting failed" in rec.getMessage()]
    assert len(failures) == 1
    assert PLACEHOLDER not in failures[0].getMessage()


@pytest.mark.asyncio
async def test_health_stays_ok_without_dragonfly(tmp_path) -> None:
    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        dragonfly_url="",
    )
    app, _ = build_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["edge"]["limiter"]["mode"] == "local"
    assert body["edge"]["limiter"]["breaker_state"] == "closed"
    assert "redis://" not in response.text


@pytest.mark.asyncio
async def test_services_aclose_closes_the_pool() -> None:
    from desk_gateway.tools import Services

    closed: list[str] = []

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
