"""Budgets for desk_docs_search, desk_memory_recall and desk_brief.

Fakes only. Nothing here opens a substrate, Hindsight or RAGflow connection.
Every test in this module fails on 48b3098, where docs_search lists datasets on
each call, banks are awaited one after another, and each upstream request builds
a new HTTP client.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from desk_gateway.config import Settings
from desk_gateway.tools.core import _brief_cache, brief, docs_search, memory_recall
from desk_gateway.upstreams import HttpUpstream, RAGFlow


def _log(name: str, elapsed: float) -> None:
    print(f"PLANE_TIMING {name} {elapsed:.4f}")


class RecordingHttp:
    """Stand-in for HttpUpstream.request. Counts dataset lists and can sleep."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.configured = True
        self.rows = rows if rows is not None else [
            {"name": "programming-desk", "id": "ds-pd"},
            {"name": "agent-substrate", "id": "ds-as"},
        ]
        self.chunks = [
            {"content": "a chunk", "document_keyword": "readme.md", "dataset_id": "ds-pd", "similarity": 0.4}
        ]
        self.lookup_sleep = 0.0
        self.retrieve_sleep = 0.0
        self.unknown_left = 0
        self.calls: list[tuple[str, str]] = []
        self.list_started: asyncio.Event | None = None

    async def request(self, method: str, path: str, **kwargs: object) -> dict:
        short = path.split("?", 1)[0]
        self.calls.append((method.upper(), short))
        if short.startswith("/api/v1/datasets"):
            if self.lookup_sleep:
                if self.list_started is not None:
                    self.list_started.set()
                await asyncio.sleep(self.lookup_sleep)
            return {"ok": True, "status": 200, "body": {"data": [dict(row) for row in self.rows]}}
        if short.startswith("/api/v1/retrieval"):
            if self.retrieve_sleep:
                await asyncio.sleep(self.retrieve_sleep)
            if self.unknown_left:
                self.unknown_left -= 1
                return {"error": "upstream_error", "reason": "unknown dataset", "status": 400, "body": None}
            return {"ok": True, "status": 200, "body": {"data": {"chunks": list(self.chunks)}}}
        return {"error": "upstream_error", "reason": f"unexpected path {short}"}


def _lists(http: RecordingHttp) -> int:
    return sum(1 for _method, path in http.calls if path.startswith("/api/v1/datasets"))


def _retrieves(http: RecordingHttp) -> int:
    return sum(1 for _method, path in http.calls if path.startswith("/api/v1/retrieval"))


def _settings(**overrides: object) -> Settings:
    settings = Settings(ragflow_url="http://ragflow.test", ragflow_api_key="test-key")
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _rag(http: RecordingHttp, settings: Settings) -> RAGFlow:
    rag = RAGFlow(settings)
    rag.http = http  # type: ignore[assignment]
    return rag


def _ctx(*, ragflow: object, settings: Settings, hindsight: object | None = None, substrate: object | None = None, seat: object | None = None) -> SimpleNamespace:
    if hindsight is None:
        hindsight = SimpleNamespace(http=SimpleNamespace(configured=False))
    if substrate is None:
        substrate = SimpleNamespace()
    if seat is None:
        seat = SimpleNamespace(short="systems", memory_own="pd-systems", memory_shared=("pd-desk",), bot_id="bot-01-systems-backend")
    store = SimpleNamespace(
        intake_counts=lambda: None,
        pack_records=lambda short: [],
        touch_seat=lambda short: None,
    )
    services = SimpleNamespace(settings=settings, ragflow=ragflow, hindsight=hindsight, substrate=substrate, store=store)
    return SimpleNamespace(services=services, seat=seat, short=getattr(seat, "short", "systems"))


@pytest.fixture(autouse=True)
def _clear_brief_cache() -> None:
    _brief_cache.clear()


async def test_two_docs_searches_inside_ttl_list_datasets_once() -> None:
    http = RecordingHttp()
    settings = _settings()
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    first = await docs_search(ctx, {"query": "alpha"})
    second = await docs_search(ctx, {"query": "beta"})
    assert first["results"] and second["results"]
    assert first["source"] == "ragflow"
    assert _lists(http) == 1


async def test_dataset_name_miss_refreshes_once_then_uses_the_cache() -> None:
    http = RecordingHttp(rows=[{"name": "programming-desk", "id": "ds-pd"}])
    settings = _settings()
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    first = await docs_search(ctx, {"query": "alpha"})
    assert _lists(http) == 2
    assert first["missing_datasets"] == ["agent-substrate"]
    assert first["results"]
    await docs_search(ctx, {"query": "beta"})
    assert _lists(http) == 2


async def test_unknown_dataset_retrieval_refreshes_once() -> None:
    http = RecordingHttp()
    http.unknown_left = 1
    settings = _settings()
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    reply = await docs_search(ctx, {"query": "alpha"})
    assert reply["results"]
    assert _lists(http) == 2
    assert _retrieves(http) == 2


async def test_dataset_cache_expires_with_ttl() -> None:
    http = RecordingHttp()
    settings = _settings(ragflow_dataset_ttl_sec=0.2)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    await docs_search(ctx, {"query": "alpha"})
    await docs_search(ctx, {"query": "beta"})
    assert _lists(http) == 1
    await asyncio.sleep(0.25)
    await docs_search(ctx, {"query": "gamma"})
    assert _lists(http) == 2


async def test_slow_dataset_lookup_names_ragflow_inside_the_tool_deadline() -> None:
    http = RecordingHttp()
    http.lookup_sleep = 1.2
    settings = _settings(docs_lookup_budget_sec=0.2, docs_retrieval_budget_sec=0.2)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    started = time.monotonic()
    reply = await docs_search(ctx, {"query": "alpha"})
    elapsed = time.monotonic() - started
    _log("docs_lookup_timeout", elapsed)
    assert reply["results"] == []
    assert reply.get("error") != "deadline"
    assert "ragflow" in reply["reason"].lower()
    assert "lookup" in reply["reason"].lower()
    assert elapsed < 0.7


async def test_slow_retrieval_names_ragflow_inside_the_tool_deadline() -> None:
    http = RecordingHttp()
    http.retrieve_sleep = 1.2
    settings = _settings(docs_lookup_budget_sec=0.2, docs_retrieval_budget_sec=0.2)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    started = time.monotonic()
    reply = await docs_search(ctx, {"query": "alpha"})
    elapsed = time.monotonic() - started
    _log("docs_retrieval_timeout", elapsed)
    assert reply["results"] == []
    assert reply.get("error") != "deadline"
    assert "ragflow" in reply["reason"].lower()
    assert "retrieval" in reply["reason"].lower()
    assert elapsed < 0.7


async def test_unconfigured_ragflow_does_not_call_substrate_docs_search() -> None:
    class _Substrate:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def call_tool(self, name: str, arguments: dict, timeout: float = 12.0) -> dict:
            self.calls.append(name)
            return {"error": "upstream_error", "reason": f"substrate has no {name} tool"}

    substrate = _Substrate()
    ragflow = SimpleNamespace(http=SimpleNamespace(configured=False))
    ctx = _ctx(ragflow=ragflow, settings=_settings(), substrate=substrate)
    reply = await docs_search(ctx, {"query": "alpha"})
    assert reply["results"] == []
    assert reply["error"] == "not_configured"
    assert reply["state"] == "not_configured"
    assert "not configured" in reply["reason"].lower()
    assert substrate.calls == []


async def test_slow_bank_returns_partial_within_its_budget() -> None:
    class _Hindsight:
        def __init__(self) -> None:
            self.http = SimpleNamespace(configured=True)
            self.started: dict[str, float] = {}

        async def recall(self, bank: str, query: str, limit: int) -> dict:
            self.started[bank] = time.monotonic()
            if bank == "slow":
                await asyncio.sleep(1.5)
            return {"ok": True, "status": 200, "body": {"results": [{"id": bank}]}}

    hindsight = _Hindsight()
    settings = _settings(recall_bank_timeout_sec=0.25)
    seat = SimpleNamespace(short="systems", memory_own="slow", memory_shared=("fast-a", "fast-b"), bot_id="bot-01-systems-backend")
    ctx = _ctx(ragflow=SimpleNamespace(http=SimpleNamespace(configured=False)), settings=settings, hindsight=hindsight, seat=seat)
    started = time.monotonic()
    reply = await memory_recall(ctx, {"query": "current work", "include_shared": True, "limit": 5})
    elapsed = time.monotonic() - started
    _log("recall_partial", elapsed)
    by_bank = {row["bank"]: row for row in reply["results"]}
    assert set(by_bank) == {"slow", "fast-a", "fast-b"}
    assert by_bank["slow"]["status"] == "timeout"
    assert "hindsight" in by_bank["slow"]["reason"].lower() or by_bank["slow"].get("plane") == "hindsight"
    assert by_bank["fast-a"]["status"] == "ok"
    assert by_bank["fast-b"]["status"] == "ok"
    assert max(hindsight.started.values()) - min(hindsight.started.values()) < 0.2
    assert elapsed < 0.75


async def test_brief_runs_substrate_and_recall_concurrently() -> None:
    class _Substrate:
        def __init__(self) -> None:
            self.started = 0.0
            self.finished = 0.0

        async def brief(self, *, repo: str | None, graph_id: str | None) -> dict:
            self.started = time.monotonic()
            await asyncio.sleep(0.4)
            self.finished = time.monotonic()
            return {"ok": True, "brief": "substrate"}

    class _Hindsight:
        def __init__(self) -> None:
            self.http = SimpleNamespace(configured=True)
            self.started = 0.0
            self.finished = 0.0

        async def recall(self, bank: str, query: str, limit: int) -> dict:
            self.started = time.monotonic()
            await asyncio.sleep(0.4)
            self.finished = time.monotonic()
            return {"ok": True, "status": 200, "body": {"results": []}}

    substrate = _Substrate()
    hindsight = _Hindsight()
    settings = _settings(recall_bank_timeout_sec=2.0)
    seat = SimpleNamespace(short="systems", memory_own="pd-systems", memory_shared=(), bot_id="bot-01-systems-backend")
    ctx = _ctx(
        ragflow=SimpleNamespace(http=SimpleNamespace(configured=False)),
        settings=settings,
        hindsight=hindsight,
        substrate=substrate,
        seat=seat,
    )
    started = time.monotonic()
    reply = await brief(ctx, {"graph_id": "ut-mv00tcgl-d8215d3e", "task_id": "SPE-8599", "refresh": True})
    elapsed = time.monotonic() - started
    _log("brief_concurrent", elapsed)
    assert reply["substrate"]["brief"] == "substrate"
    assert reply["recall"]["results"][0]["status"] == "ok"
    assert hindsight.started < substrate.finished
    assert substrate.started < hindsight.finished
    occupied = (substrate.finished - substrate.started) + (hindsight.finished - hindsight.started)
    assert elapsed < occupied - 0.05


async def test_http_upstream_reuses_one_client_and_aclose_closes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[httpx.AsyncClient] = []
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        client = real(*args, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})), **kwargs)  # type: ignore[arg-type]
        made.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    upstream = HttpUpstream("ragflow", "http://ragflow.test", timeout=2.0)
    for i in range(4):
        result = await upstream.request("GET", f"/n/{i}")
        assert result["ok"] is True
    assert len(made) == 1
    await upstream.aclose()
    assert made[0].is_closed


async def test_services_aclose_closes_each_upstream_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from desk_gateway.tools import Services

    made: list[httpx.AsyncClient] = []
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        client = real(*args, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})), **kwargs)  # type: ignore[arg-type]
        made.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    rag = HttpUpstream("ragflow", "http://ragflow.test", timeout=2.0)
    hind = HttpUpstream("hindsight", "http://hindsight.test", timeout=2.0)
    await rag.request("GET", "/a")
    await hind.request("GET", "/b")
    services = SimpleNamespace(
        substrate=SimpleNamespace(http=None),
        agent_bus=SimpleNamespace(http=None),
        greptime=SimpleNamespace(http=None),
        timescale=SimpleNamespace(http=None),
        hindsight=SimpleNamespace(http=hind),
        ragflow=SimpleNamespace(http=rag),
        railway=SimpleNamespace(http=None),
        vercel=SimpleNamespace(http=None),
        greptile=SimpleNamespace(http=None),
        github=SimpleNamespace(http=None),
        play=SimpleNamespace(http=None),
        asc=SimpleNamespace(http=None),
    )
    await Services.aclose(services)  # type: ignore[arg-type]
    assert len(made) == 2
    assert all(client.is_closed for client in made)


async def test_app_shutdown_closes_upstream_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.applications import Starlette

    from desk_gateway.server import _install_upstream_shutdown

    made: list[httpx.AsyncClient] = []
    real = httpx.AsyncClient

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        client = real(*args, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})), **kwargs)  # type: ignore[arg-type]
        made.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    upstream = HttpUpstream("ragflow", "http://ragflow.test", timeout=2.0)
    await upstream.request("GET", "/health")

    class _Services:
        async def aclose(self) -> None:
            await upstream.aclose()

    app = Starlette()
    _install_upstream_shutdown(app, _Services())
    async with app.router.lifespan_context(app):
        assert made[0].is_closed is False
    assert made[0].is_closed is True


async def test_cached_names_do_not_wait_on_another_refresh() -> None:
    http = RecordingHttp()
    settings = _settings(docs_lookup_budget_sec=2.0, docs_retrieval_budget_sec=2.0)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    primed = await docs_search(ctx, {"query": "prime"})
    assert primed["results"]
    assert _lists(http) == 1

    http.lookup_sleep = 0.6
    http.list_started = asyncio.Event()

    async def uncached() -> dict:
        return await docs_search(ctx, {"query": "other", "repo": "some-other-repo"})

    async def cached() -> tuple[float, dict]:
        await http.list_started.wait()
        started = time.monotonic()
        reply = await docs_search(ctx, {"query": "cached"})
        return time.monotonic() - started, reply

    _uncached_reply, (elapsed, cached_reply) = await asyncio.gather(uncached(), cached())
    _log("docs_cache_hit_during_refresh", elapsed)
    assert cached_reply["results"]
    assert elapsed < 0.25


async def test_unknown_dataset_after_lookup_window_still_refreshes() -> None:
    http = RecordingHttp()
    http.retrieve_sleep = 0.35
    http.unknown_left = 1
    settings = _settings(docs_lookup_budget_sec=0.15, docs_retrieval_budget_sec=1.0)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    reply = await docs_search(ctx, {"query": "alpha"})
    assert reply["results"]
    assert _lists(http) == 2
    assert _retrieves(http) == 2
    assert reply.get("error") != "deadline"


async def test_oversized_docs_budgets_name_ragflow_before_the_tool_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("desk_gateway.tools.core.TOOL_DEADLINE_SEC", 1.0)
    http = RecordingHttp()
    http.lookup_sleep = 0.55
    http.retrieve_sleep = 1.0
    settings = _settings(docs_lookup_budget_sec=0.7, docs_retrieval_budget_sec=0.7)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)

    async def bounded() -> dict:
        try:
            return await asyncio.wait_for(docs_search(ctx, {"query": "alpha"}), 1.0)
        except TimeoutError:
            return {"results": [], "error": "deadline"}

    reply = await bounded()
    assert reply["results"] == []
    assert reply.get("error") != "deadline"
    assert "ragflow" in str(reply.get("reason") or "").lower()


async def test_large_lookup_budget_still_retrieves_when_lookup_is_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("desk_gateway.tools.core.TOOL_DEADLINE_SEC", 1.0)
    http = RecordingHttp()
    settings = _settings(docs_lookup_budget_sec=1.0, docs_retrieval_budget_sec=0.4)
    ctx = _ctx(ragflow=_rag(http, settings), settings=settings)
    reply = await docs_search(ctx, {"query": "alpha"})
    assert reply["results"]
    assert _retrieves(http) == 1
    assert reply.get("error") != "upstream_timeout"


async def test_hindsight_http_timeout_is_a_bank_timeout() -> None:
    class _Hindsight:
        def __init__(self) -> None:
            self.http = SimpleNamespace(configured=True)

        async def recall(self, bank: str, query: str, limit: int) -> dict:
            if bank == "slow":
                return {"error": "upstream_timeout", "reason": "hindsight did not answer within 10s"}
            return {"ok": True, "status": 200, "body": {"results": []}}

    hindsight = _Hindsight()
    settings = _settings(recall_bank_timeout_sec=30.0)
    seat = SimpleNamespace(short="systems", memory_own="slow", memory_shared=("fast",), bot_id="bot-01-systems-backend")
    ctx = _ctx(ragflow=SimpleNamespace(http=SimpleNamespace(configured=False)), settings=settings, hindsight=hindsight, seat=seat)
    reply = await memory_recall(ctx, {"query": "current work", "include_shared": True, "limit": 5})
    by_bank = {row["bank"]: row for row in reply["results"]}
    assert by_bank["slow"]["status"] == "timeout"
    assert by_bank["slow"]["error"] == "upstream_timeout"
    assert by_bank["fast"]["status"] == "ok"


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patch_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.AsyncBaseTransport) -> list[httpx.AsyncClient]:
    made: list[httpx.AsyncClient] = []

    def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        client = _REAL_ASYNC_CLIENT(*args, **kwargs)  # type: ignore[arg-type]
        made.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return made


async def test_ephemeral_upstream_closes_on_success_and_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    from desk_gateway.tools.packs import _api
    from desk_gateway.upstreams import AppStoreConnect

    made = _patch_client(monkeypatch, httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})))
    upstream = HttpUpstream("pack api", "http://pack.test", timeout=2.0, ephemeral=True)
    first = await upstream.request("GET", "/health")
    assert first["ok"] is True
    assert made[0].is_closed
    second = await upstream.request("GET", "/health")
    assert second["ok"] is True
    assert len(made) == 2
    assert made[1].is_closed

    class _Hang(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.started.set()
            await asyncio.Event().wait()
            return httpx.Response(200, json={"ok": True})

    hang = _Hang()
    hung_clients = _patch_client(monkeypatch, hang)
    hanging = HttpUpstream("pack api", "http://pack.test", timeout=5.0, ephemeral=True)
    task = asyncio.create_task(hanging.request("GET", "/health"))
    await hang.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hung_clients[0].is_closed

    class _Ctx:
        spec = SimpleNamespace(pack="demo")
        services = SimpleNamespace(settings=SimpleNamespace(pack_api_bases={"demo": "http://pack.test"}))

    assert _api(_Ctx())._ephemeral is True  # type: ignore[arg-type]
    asc = AppStoreConnect(SimpleNamespace(asc_key_id="", asc_issuer_id="", asc_private_key_path=""))  # type: ignore[arg-type]
    assert asc.client()._ephemeral is True


async def test_open_breaker_lets_an_inflight_sibling_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Gate(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.slow_entered = asyncio.Event()
            self.release_slow = asyncio.Event()
            self.slow_finished = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == "/slow":
                self.slow_entered.set()
                await self.release_slow.wait()
                self.slow_finished = True
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(500, json={"error": "boom"})

    gate = _Gate()
    made = _patch_client(monkeypatch, gate)
    upstream = HttpUpstream(
        "hindsight",
        "http://hindsight.test",
        timeout=5.0,
        failure_threshold=1,
        recovery_timeout_sec=30.0,
    )
    slow_task = asyncio.create_task(upstream.request("GET", "/slow"))
    await gate.slow_entered.wait()
    failed = await upstream.request("GET", "/boom")
    assert failed["status"] == 500
    assert upstream.circuit_breaker.state == "open"
    assert made[0].is_closed is False
    gate.release_slow.set()
    slow = await slow_task
    assert slow["ok"] is True
    assert gate.slow_finished is True
    assert made[0].is_closed is True


class _Hang(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.started.set()
        await asyncio.Event().wait()
        return httpx.Response(200, json={"ok": True})


async def test_docs_budget_timeout_opens_the_circuit_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _Hang())
    settings = _settings(docs_lookup_budget_sec=0.15, docs_retrieval_budget_sec=0.15)
    rag = RAGFlow(settings)
    rag.http.circuit_breaker.failure_threshold = 1
    ctx = _ctx(ragflow=rag, settings=settings)
    first = await docs_search(ctx, {"query": "alpha"})
    assert first["results"] == []
    assert first.get("error") == "upstream_timeout"
    assert rag.http.circuit_breaker.state == "open"
    started = time.monotonic()
    second = await docs_search(ctx, {"query": "beta"})
    assert time.monotonic() - started < 0.05
    assert second.get("error") == "circuit_breaker_open"


async def test_recall_budget_timeout_opens_the_circuit_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _Hang())
    http = HttpUpstream(
        "hindsight",
        "http://hindsight.test",
        timeout=30.0,
        failure_threshold=1,
        recovery_timeout_sec=30.0,
    )

    class _Hindsight:
        def __init__(self) -> None:
            self.http = http

        async def recall(self, bank: str, query: str, limit: int) -> dict:
            return await self.http.request("POST", f"/banks/{bank}", json={"query": query})

    settings = _settings(recall_bank_timeout_sec=0.15)
    seat = SimpleNamespace(short="systems", memory_own="pd-systems", memory_shared=(), bot_id="bot-01-systems-backend")
    ctx = _ctx(
        ragflow=SimpleNamespace(http=SimpleNamespace(configured=False)),
        settings=settings,
        hindsight=_Hindsight(),
        seat=seat,
    )
    first = await memory_recall(ctx, {"query": "current work", "include_shared": False, "limit": 1})
    assert first["results"][0]["status"] == "timeout"
    assert http.circuit_breaker.state == "open"
    started = time.monotonic()
    second = await memory_recall(ctx, {"query": "current work", "include_shared": False, "limit": 1})
    assert time.monotonic() - started < 0.05
    assert second["results"][0]["error"] == "circuit_breaker_open"


class _HoldFirstList(httpx.AsyncBaseTransport):
    """The first dataset list holds the RAGFlow lock. Later lists answer."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.lists = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/api/v1/datasets"):
            self.lists += 1
            if self.lists == 1:
                self.entered.set()
                await self.release.wait()
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"name": "programming-desk", "id": "ds-pd"},
                        {"name": "agent-substrate", "id": "ds-as"},
                    ]
                },
            )
        return httpx.Response(200, json={"data": {"chunks": []}})


async def test_lock_wait_budget_timeout_does_not_open_the_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _HoldFirstList()
    _patch_client(monkeypatch, transport)
    settings = _settings(docs_lookup_budget_sec=0.15, docs_retrieval_budget_sec=0.15)
    rag = RAGFlow(settings)
    rag.http.circuit_breaker.failure_threshold = 5
    holder = asyncio.create_task(rag.resolve_dataset_ids(["programming-desk", "agent-substrate"]))
    await transport.entered.wait()
    ctx = _ctx(ragflow=rag, settings=settings)
    waiters = await asyncio.gather(*(docs_search(ctx, {"query": f"queued-{i}"}) for i in range(5)))
    assert [row.get("error") for row in waiters] == ["upstream_timeout"] * 5
    assert rag.http.circuit_breaker.failure_count == 0
    assert rag.http.circuit_breaker.state == "closed"
    transport.release.set()
    resolved = await holder
    assert resolved.get("ok") is True
    assert rag.http.circuit_breaker.state == "closed"


async def test_caller_cancel_does_not_record_an_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    hang = _Hang()
    _patch_client(monkeypatch, hang)
    settings = _settings(
        docs_lookup_budget_sec=30,
        docs_retrieval_budget_sec=30,
        recall_bank_timeout_sec=30,
    )
    rag = RAGFlow(settings)
    http = HttpUpstream("hindsight", "http://hindsight.test", timeout=30.0, failure_threshold=1)

    class _Hindsight:
        def __init__(self) -> None:
            self.http = http

        async def recall(self, bank: str, query: str, limit: int) -> dict:
            return await self.http.request("POST", f"/banks/{bank}", json={"query": query})

    seat = SimpleNamespace(short="systems", memory_own="pd-systems", memory_shared=(), bot_id="bot-01-systems-backend")
    ctx = _ctx(ragflow=rag, settings=settings, hindsight=_Hindsight(), seat=seat)

    docs_task = asyncio.create_task(docs_search(ctx, {"query": "alpha"}))
    await hang.started.wait()
    docs_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await docs_task
    assert rag.http.circuit_breaker.failure_count == 0
    assert rag.http.circuit_breaker.state == "closed"

    hang.started.clear()
    recall_task = asyncio.create_task(memory_recall(ctx, {"query": "current work", "include_shared": False, "limit": 1}))
    await hang.started.wait()
    recall_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await recall_task
    assert http.circuit_breaker.failure_count == 0
    assert http.circuit_breaker.state == "closed"
