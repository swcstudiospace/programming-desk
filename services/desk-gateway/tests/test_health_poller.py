"""UpstreamHealthPoller starts with the gateway lifespan and stays off the request path."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from asgi_lifespan import LifespanManager

from desk_gateway.config import Settings
from desk_gateway.health import DEFAULT_POLL_INTERVAL_SEC, UpstreamHealthPoller
from desk_gateway.server import build_app
from desk_gateway.store import Store
from desk_gateway.tools import ToolContext
from desk_gateway.tools.core import doctor
from tests.conftest import PASS, REPO, _settings_env_names

_POLL_TASK = "upstream-health-poller"
_SERVICES = ("greptime", "timescale", "dragonfly", "hindsight", "ragflow")


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "data_dir": tmp_path / "data",
        "repo_dir": REPO,
        "seat_passphrases": dict(PASS),
        "upstream_health_poll_interval_sec": 30.0,
        "upstream_health_check_timeout_sec": 15.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _services_with(health_for: dict[str, object]) -> MagicMock:
    services = MagicMock()
    for name in _SERVICES:
        client = MagicMock()
        client.health = health_for.get(name, AsyncMock(return_value={"ok": True}))
        setattr(services, name, client)
    return services


def _named_poll_tasks() -> list[asyncio.Task[object]]:
    return [task for task in asyncio.all_tasks() if task.get_name() == _POLL_TASK and not task.done()]


@pytest.mark.asyncio
async def test_poller_starts_on_startup_without_blocking_on_a_down_upstream(tmp_path: Path) -> None:
    """Lifespan schedules the loop. A hung upstream does not delay /healthz or /readyz."""
    hung = asyncio.Event()

    async def hang() -> dict[str, object]:
        hung.set()
        await asyncio.sleep(30)
        return {"ok": False, "error": "down"}

    settings = _settings(
        tmp_path,
        upstream_health_poll_interval_sec=21.0,
        upstream_health_check_timeout_sec=30.0,
    )
    app, _ = build_app(settings)
    poller = app.state["health_poller"]
    assert poller is app.state["services"].health_poller
    assert poller.poll_interval_sec == 21.0
    assert poller.check_timeout_sec == 30.0
    assert poller.running is False

    app.state["services"].greptime.health = hang

    started = time.monotonic()
    async with LifespanManager(app):
        entered = time.monotonic() - started
        assert entered < 5, f"startup waited {entered:.2f}s on an upstream check"
        assert poller.running is True
        assert _named_poll_tasks()

        deadline = time.monotonic() + 2
        hindsight = poller.get_record("hindsight")
        while (
            not hung.is_set() or hindsight is None or hindsight.last_checked_at <= 0
        ) and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
            hindsight = poller.get_record("hindsight")
        assert hindsight is not None
        assert hindsight.last_checked_at > 0
        assert hindsight.last_status == "not_configured"
        assert hindsight.healthy is True

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            healthz = await client.get("/healthz")
            readyz = await client.get("/readyz")
        assert healthz.status_code == 200
        assert set(healthz.json()) == {"status", "service", "version", "timestamp"}
        assert healthz.json()["status"] == "ok"
        assert readyz.status_code == 200
        body = readyz.json()
        assert set(body) == {"status", "service", "ready", "checks"}
        assert set(body["checks"]) == {"store", "rosters"}
        assert body["ready"] is True
        # The hung check is still in flight. Probes did not wait for it.
        assert hung.is_set()
        assert poller.get_record("greptime").last_checked_at == 0

        stopping = time.monotonic()

    assert time.monotonic() - stopping < 2, "shutdown waited for the hung upstream"
    assert poller.running is False
    assert _named_poll_tasks() == []


@pytest.mark.asyncio
async def test_poller_stops_on_shutdown_without_leaked_tasks(tmp_path: Path) -> None:
    app, _ = build_app(_settings(tmp_path))
    poller = app.state["health_poller"]
    async with LifespanManager(app):
        task = poller._task
        assert task is not None
        assert task.get_name() == _POLL_TASK
        assert not task.done()
    assert poller._task is None
    assert task.done()
    assert _named_poll_tasks() == []
    assert task not in asyncio.all_tasks()


@pytest.mark.asyncio
async def test_failing_upstream_does_not_kill_poll_loop(caplog: pytest.LogCaptureFixture) -> None:
    secret = "postgres://operator:secret-token@db.internal/desk"  # pragma: allowlist secret (redaction fixture)
    calls = 0

    async def explode() -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise RuntimeError(secret)

    services = _services_with(
        {
            "greptime": explode,
            **{
                name: AsyncMock(return_value={"error": "not_configured", "reason": "absent"})
                for name in _SERVICES
                if name != "greptime"
            },
        }
    )
    poller = UpstreamHealthPoller(
        services,
        poll_interval_sec=0.05,
        failure_threshold=1,
        check_timeout_sec=1.0,
    )
    with caplog.at_level(logging.DEBUG, logger="desk_gateway.health"):
        await poller.start()
        try:
            deadline = time.monotonic() + 2
            while calls < 2 and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert poller.running is True
        finally:
            await poller.stop()

    assert calls >= 2
    assert poller.running is False
    record = poller.get_record("greptime")
    assert record is not None
    assert record.last_status == "down"
    assert record.healthy is False
    assert record.details["error"] == "check_exception"
    assert "secret-token" not in record.details["reason"]
    assert secret not in record.details["reason"]
    assert "secret-token" not in caplog.text
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_hung_upstream_does_not_stall_the_loop() -> None:
    calls = 0

    async def hang() -> dict[str, object]:
        await asyncio.sleep(30)
        return {"ok": False, "error": "down"}

    async def ok() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"ok": True}

    services = _services_with(
        {
            "greptime": hang,
            **{name: ok for name in _SERVICES if name != "greptime"},
        }
    )
    poller = UpstreamHealthPoller(services, poll_interval_sec=0.05, check_timeout_sec=0.05)
    await poller.start()
    try:
        deadline = time.monotonic() + 2
        while calls < 8 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert poller.running is True
    finally:
        await poller.stop()

    assert calls >= 8
    record = poller.get_record("greptime")
    assert record is not None
    assert record.details["error"] == "check_timeout"
    assert poller.running is False
    assert _named_poll_tasks() == []


@pytest.mark.asyncio
async def test_poll_cadence_honours_interval() -> None:
    interval = 0.05
    stamps: list[float] = []

    async def counted() -> dict[str, object]:
        stamps.append(time.monotonic())
        return {"ok": True}

    services = _services_with(
        {
            "greptime": counted,
            **{
                name: AsyncMock(return_value={"ok": True})
                for name in _SERVICES
                if name != "greptime"
            },
        }
    )
    poller = UpstreamHealthPoller(services, poll_interval_sec=interval, check_timeout_sec=1.0)
    await poller.start()
    try:
        deadline = time.monotonic() + 2
        while len(stamps) < 4 and time.monotonic() < deadline:
            await asyncio.sleep(0.005)
    finally:
        await poller.stop()

    assert len(stamps) >= 4
    gaps = [stamps[i + 1] - stamps[i] for i in range(3)]
    assert all(gap >= interval * 0.6 for gap in gaps), gaps
    # A 0.5s sleep still yields four stamps inside the two-second window.
    # interval * 10 is 0.5s, so that sleep fails this bound. Real gaps sit
    # near the interval, with room for scheduler jitter.
    assert all(gap < interval * 10 for gap in gaps), gaps


@pytest.mark.asyncio
async def test_timed_out_probe_does_not_start_another_while_the_worker_runs() -> None:
    """A thread that ignores cancellation must not be joined by a second probe."""
    started = 0
    release = threading.Event()

    def block() -> None:
        release.wait(timeout=2)

    async def hang() -> dict[str, object]:
        nonlocal started
        started += 1
        await asyncio.to_thread(block)
        return {"ok": False, "error": "down"}

    services = _services_with(
        {
            "timescale": hang,
            **{
                name: AsyncMock(return_value={"error": "not_configured", "reason": "absent"})
                for name in _SERVICES
                if name != "timescale"
            },
        }
    )
    poller = UpstreamHealthPoller(
        services,
        poll_interval_sec=0.05,
        failure_threshold=1,
        check_timeout_sec=0.05,
    )
    await poller.start()
    try:
        deadline = time.monotonic() + 1
        while started < 1 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.35)
        assert started == 1
        assert poller.running is True
        record = poller.get_record("timescale")
        assert record is not None
        assert record.details["error"] == "check_timeout"
        assert record.consecutive_failures == 1
        release.set()
        deadline = time.monotonic() + 1
        while started < 2 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert started >= 2
    finally:
        release.set()
        await poller.stop()

    assert poller.running is False
    assert _named_poll_tasks() == []
    leaked = [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("upstream-health-check-") and not task.done()
    ]
    assert leaked == []


@pytest.mark.asyncio
async def test_timescale_health_uses_a_cancellable_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    from desk_gateway.upstreams import Timescale

    entered = asyncio.Event()
    closed: list[type[BaseException] | None] = []
    connect_kwargs: dict[str, object] = {}

    class _Cursor:
        async def __aenter__(self) -> _Cursor:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

        async def execute(self, sql: str) -> None:
            assert sql == "SELECT 1 AS ok"
            entered.set()
            await asyncio.Event().wait()

        async def fetchone(self) -> tuple[int]:
            return (1,)

    class _Conn:
        async def __aenter__(self) -> _Conn:
            return self

        async def __aexit__(self, exc_type: type[BaseException] | None, *_exc: object) -> bool:
            closed.append(exc_type)
            return False

        def cursor(self) -> _Cursor:
            return _Cursor()

    class _AsyncConnection:
        @staticmethod
        async def connect(_url: str, **kwargs: object) -> _Conn:
            connect_kwargs.update(kwargs)
            return _Conn()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(AsyncConnection=_AsyncConnection))
    client = Timescale(SimpleNamespace(pg_url="postgresql://operator@db.internal/desk"))
    absent = await Timescale(SimpleNamespace(pg_url="")).health()
    assert absent["ok"] is False
    assert absent["error"] == "not_configured"

    probe = asyncio.create_task(client.health())
    await asyncio.wait_for(entered.wait(), timeout=1)
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe

    assert closed == [asyncio.CancelledError]
    assert connect_kwargs["connect_timeout"] == Timescale.HEALTH_CONNECT_TIMEOUT_SEC
    options = str(connect_kwargs["options"])
    assert "default_transaction_read_only=on" in options
    assert f"statement_timeout={Timescale.HEALTH_STATEMENT_TIMEOUT_MS}" in options


@pytest.mark.asyncio
async def test_timescale_health_redacts_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from desk_gateway.upstreams import Timescale

    secret = "postgresql://operator:secret-token@db.internal/desk"  # pragma: allowlist secret (redaction fixture)

    class _AsyncConnection:
        @staticmethod
        async def connect(_url: str, **_kwargs: object) -> object:
            raise RuntimeError(secret)

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(AsyncConnection=_AsyncConnection))
    result = await Timescale(SimpleNamespace(pg_url="postgresql://operator@db.internal/desk")).health()
    assert result["ok"] is False
    assert result["error"] == "upstream_error"
    assert "secret-token" not in result["reason"]
    assert secret not in result["reason"]


def test_poll_interval_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _settings_env_names():
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("UPSTREAM_HEALTH_POLL_INTERVAL_SEC", "12.5")
    monkeypatch.setenv("UPSTREAM_HEALTH_CHECK_TIMEOUT_SEC", "4")
    monkeypatch.setenv("DESK_REPO_DIR", str(REPO))
    settings = Settings.from_env()
    assert settings.upstream_health_poll_interval_sec == 12.5
    assert settings.upstream_health_check_timeout_sec == 4.0
    poller = UpstreamHealthPoller.from_settings(MagicMock(), settings)
    assert poller.poll_interval_sec == 12.5
    assert poller.check_timeout_sec == 4.0

    clamped = UpstreamHealthPoller(MagicMock(), poll_interval_sec=0, check_timeout_sec=0)
    assert clamped.poll_interval_sec == DEFAULT_POLL_INTERVAL_SEC
    assert clamped.check_timeout_sec is None


@pytest.mark.asyncio
async def test_doctor_uses_cached_hindsight_without_changing_the_reply(tmp_path: Path) -> None:
    from desk_gateway.rosters import Rosters

    store = Store(tmp_path / "data")
    rosters = Rosters.load(REPO / "contracts")
    seat = rosters.seats["systems"]
    spec = next(iter(seat.tools.values()))

    live = AsyncMock(return_value={"ok": False, "reason": "live-should-not-run"})
    services = MagicMock()
    services.store = store
    services.rosters = rosters
    services.repo.show = AsyncMock(return_value="")
    services.hindsight.http.configured = True
    services.hindsight.health = live
    services.substrate.health = AsyncMock(return_value={"ok": False, "reason": "substrate down"})

    cold = UpstreamHealthPoller(services, poll_interval_sec=30.0, check_timeout_sec=1.0)
    services.health_poller = cold
    ctx = ToolContext(services=services, seat=seat, spec=spec)
    cold_reply = await doctor(ctx, {"action": "check"})
    assert set(cold_reply) == {"green", "seat", "gateway_version", "checks"}
    assert set(cold_reply["checks"]["memory"]) == {"green", "plane", "detail"}
    assert cold_reply["checks"]["memory"]["plane"] == "hindsight"
    assert cold_reply["checks"]["memory"]["green"] is False
    assert cold_reply["checks"]["memory"]["detail"] == "live-should-not-run"
    live.assert_awaited()

    live.reset_mock()
    warm = UpstreamHealthPoller(services, poll_interval_sec=30.0, check_timeout_sec=1.0)
    record = warm.get_record("hindsight")
    assert record is not None
    record.last_checked_at = time.time()
    record.details = {"ok": True, "reason": "cached"}
    services.health_poller = warm
    warm_reply = await doctor(ctx, {"action": "check"})
    assert warm_reply["checks"]["memory"] == {"green": True, "plane": "hindsight", "detail": "cached"}
    live.assert_not_awaited()
