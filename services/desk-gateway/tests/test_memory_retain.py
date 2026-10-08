"""Honest desk_memory_retain: kind follows scope, and each plane reports its own verdict.

Fakes only. Nothing in this module opens a substrate, Hindsight or RAGflow connection.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from desk_gateway.config import Settings
from desk_gateway.tools.core import memory_retain
from desk_gateway.upstreams import Substrate

FACT = "retain-body-marker-do-not-log-9efe"
GRAPH_ID = "ut-mv00tcgl-d8215d3e"
SOURCE = "https://example.com/spe-8594"
RECEIPT = ".receipts/bot-01-systems-backend/spe-8594-honest-memory-retain.json"


class _Http:
    def __init__(self, configured: bool) -> None:
        self.configured = configured


class FakeHindsight:
    def __init__(self, *, configured: bool = True, result: dict | None = None) -> None:
        self.http = _Http(configured)
        self.result = {"ok": True, "status": 200} if result is None else result
        self.calls: list[dict] = []

    async def retain(self, bank: str, content: str, tags: list[str], context: str | None = None) -> dict:
        self.calls.append({"bank": bank, "content": content, "tags": list(tags), "context": context})
        return self.result


class FakeSubstrate:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def call_tool(self, name: str, arguments: dict, timeout: float = 12.0) -> dict:
        self.calls.append({"name": name, "arguments": dict(arguments), "timeout": timeout})
        return self.result


def _ctx(hindsight: FakeHindsight, substrate: FakeSubstrate | Substrate) -> SimpleNamespace:
    seat = SimpleNamespace(short="systems", memory_own="pd-systems", bot_id="bot-01-systems-backend")
    return SimpleNamespace(services=SimpleNamespace(hindsight=hindsight, substrate=substrate), seat=seat, short="systems")


def _by_plane(reply: dict) -> dict[str, dict]:
    return {verdict["plane"]: verdict for verdict in reply["verdicts"]}


class _Block:
    def __init__(self, text: str | None) -> None:
        self.text = text


class _ToolResult:
    def __init__(self, payload: dict | None, *, is_error: bool = False, structured: dict | None = None, empty: bool = False) -> None:
        self.is_error = is_error
        self.structured_content = structured
        self.content = [] if empty else [_Block(json.dumps(payload or {}))]


class _Client:
    holder: dict = {}

    def __init__(self, transport, read_timeout_seconds=None) -> None:
        self.transport = transport

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def call_tool(self, name, arguments):
        _Client.holder["calls"].append({"name": name, "arguments": arguments})
        return _Client.holder["result"]


def _transport(url, http_client=None):
    _Client.holder["urls"].append(url)
    return object()


@pytest.fixture
def mcp_substrate(monkeypatch):
    """A configured Substrate whose MCP client never leaves the process."""
    _Client.holder = {"calls": [], "urls": [], "result": _ToolResult({})}
    monkeypatch.setattr("mcp.client.client.Client", _Client)
    monkeypatch.setattr("mcp.client.streamable_http.streamable_http_client", _transport)
    settings = Settings(substrate_url="http://127.0.0.1:9", substrate_token="test-token")
    return Substrate(settings)


async def test_agent_scope_sends_kind_fact():
    hindsight = FakeHindsight()
    substrate = FakeSubstrate({"ok": True, "content": [{"id": "mem-1"}]})
    reply = await memory_retain(_ctx(hindsight, substrate), {"content": FACT, "source": SOURCE, "task_id": "SPE-8594"})
    assert substrate.calls[0]["name"] == "memory_write"
    sent = substrate.calls[0]["arguments"]
    assert sent["scope"] == "agent:grok-bot"
    assert sent["kind"] == "fact"
    assert sent["trust"] == "agent-claimed"
    assert sent["ttl"] == "permanent"
    assert sent["text"] == f"[pd-systems] {FACT}"
    assert substrate.calls[0]["timeout"] == 8
    tags = hindsight.calls[0]["tags"]
    assert "seat:systems" in tags
    assert f"source:{SOURCE}" in tags
    assert f"task_id:SPE-8594" in tags
    assert reply["ok"] is True
    assert reply["partial"] is False
    assert _by_plane(reply)["substrate"]["state"] == "stored"


async def test_graph_scope_sends_kind_decision():
    hindsight = FakeHindsight()
    substrate = FakeSubstrate({"ok": True, "content": [{"id": "mem-2"}]})
    reply = await memory_retain(
        _ctx(hindsight, substrate),
        {"content": FACT, "receipt_path": RECEIPT, "graph_id": GRAPH_ID},
    )
    sent = substrate.calls[0]["arguments"]
    assert sent["scope"] == f"graph:{GRAPH_ID}"
    assert sent["kind"] == "decision"
    assert sent["trust"] == "agent-claimed"
    assert sent["ttl"] == "permanent"
    tags = hindsight.calls[0]["tags"]
    assert f"graph_id:{GRAPH_ID}" in tags
    assert f"receipt_path:{RECEIPT}" in tags
    assert reply["ok"] is True
    assert _by_plane(reply)["substrate"]["state"] == "stored"


async def test_denied_substrate_is_partial_and_logged(caplog, mcp_substrate):
    hindsight = FakeHindsight()
    _Client.holder["result"] = _ToolResult(
        {"outcome": "denied", "reason": "rbac.no-grant", "writer": "unknown", "text": FACT}
    )
    with caplog.at_level(logging.WARNING, logger="desk_gateway.tools.core"):
        reply = await memory_retain(
            _ctx(hindsight, mcp_substrate),
            {"content": FACT, "source": SOURCE},
        )
    assert reply["ok"] is True
    assert reply["partial"] is True
    planes = _by_plane(reply)
    assert planes["hindsight"]["state"] == "stored"
    assert planes["substrate"]["state"] == "denied"
    assert planes["substrate"]["reason"] == "rbac.no-grant"
    assert planes["substrate"]["writer"] == "unknown"
    assert reply["results"]["substrate"]["error"] == "memory_denied"
    assert reply["results"]["substrate"]["writer"] == "unknown"
    text = caplog.text
    assert "systems" in text
    assert "substrate" in text
    assert "rbac.no-grant" in text
    assert "unknown" in text
    assert FACT not in text
    assert all(FACT not in str(record.args) for record in caplog.records)


@pytest.mark.parametrize("outcome", ["denied", "quarantined", "rejected"])
async def test_call_tool_maps_refused_memory_write(mcp_substrate, outcome):
    _Client.holder["result"] = _ToolResult({"outcome": outcome, "reason": "rbac.no-grant", "writer": "unknown"})
    out = await mcp_substrate.call_tool("memory_write", {"scope": "agent:grok-bot", "kind": "fact", "text": FACT}, timeout=8)
    assert out["ok"] is False
    assert out["error"] == "memory_denied"
    assert out["reason"] == "rbac.no-grant"
    assert out["writer"] == "unknown"
    _Client.holder["result"] = _ToolResult({"outcome": "denied", "reason": "rbac.no-grant", "writer": "unknown"})
    other = await mcp_substrate.call_tool("graph_heartbeat", {"lease_id": "lease-1"}, timeout=8)
    assert other["ok"] is True
    assert other.get("error") != "memory_denied"


async def test_call_tool_protocol_error_with_denial_is_memory_denied(mcp_substrate):
    _Client.holder["result"] = _ToolResult(
        {"outcome": "denied", "reason": "rbac.no-grant", "writer": "unknown"},
        is_error=True,
    )
    out = await mcp_substrate.call_tool("memory_write", {"text": FACT}, timeout=8)
    assert out["error"] == "memory_denied"
    assert out["ok"] is False
    assert out["writer"] == "unknown"


async def test_call_tool_structured_denial_without_text_content(mcp_substrate):
    _Client.holder["result"] = _ToolResult(None, empty=True, structured={"outcome": "quarantined", "reason": "rbac.no-grant", "writer": "unknown"})
    out = await mcp_substrate.call_tool("memory_write", {"text": FACT}, timeout=8)
    assert out["ok"] is False
    assert out["error"] == "memory_denied"
    assert out["reason"] == "rbac.no-grant"
    assert out["writer"] == "unknown"


async def test_call_tool_accepted_write_stays_ok(mcp_substrate):
    _Client.holder["result"] = _ToolResult({"outcome": "accepted", "id": "mem-3"})
    out = await mcp_substrate.call_tool("memory_write", {"text": FACT}, timeout=8)
    assert out["ok"] is True
    assert "error" not in out


async def test_hindsight_only_when_substrate_not_configured(caplog):
    hindsight = FakeHindsight()
    substrate = Substrate(Settings(substrate_url="", substrate_token=""))
    with caplog.at_level(logging.WARNING, logger="desk_gateway.tools.core"):
        reply = await memory_retain(_ctx(hindsight, substrate), {"content": FACT, "source": SOURCE})
    assert reply["ok"] is True
    assert reply["partial"] is True
    planes = _by_plane(reply)
    assert planes["hindsight"]["state"] == "stored"
    assert planes["substrate"]["state"] == "not_configured"
    assert reply["results"]["substrate"]["error"] == "not_configured"
    assert FACT not in caplog.text


async def test_both_planes_stored(caplog):
    hindsight = FakeHindsight()
    substrate = FakeSubstrate({"ok": True, "content": [{"id": "mem-4"}]})
    with caplog.at_level(logging.WARNING, logger="desk_gateway.tools.core"):
        reply = await memory_retain(_ctx(hindsight, substrate), {"content": FACT, "source": SOURCE})
    assert reply["ok"] is True
    assert reply["partial"] is False
    planes = _by_plane(reply)
    assert planes["hindsight"]["state"] == "stored"
    assert planes["substrate"]["state"] == "stored"
    assert reply["bank"] == "pd-systems"
    assert caplog.records == []


async def test_no_plane_stored_is_memory_unavailable():
    hindsight = FakeHindsight(configured=False)
    substrate = Substrate(Settings(substrate_url="", substrate_token=""))
    reply = await memory_retain(_ctx(hindsight, substrate), {"content": FACT, "source": SOURCE})
    assert reply["error"] == "memory_unavailable"
    assert reply["ok"] is False
    assert reply["partial"] is False
    planes = _by_plane(reply)
    assert planes["hindsight"]["state"] == "not_configured"
    assert planes["substrate"]["state"] == "not_configured"
    assert hindsight.calls == []


async def test_no_plane_when_both_error(caplog):
    hindsight = FakeHindsight(result={"error": "upstream_error", "reason": "hindsight returned HTTP 500"})
    substrate = FakeSubstrate({"error": "upstream_timeout", "reason": "substrate memory_write did not answer within 8s"})
    with caplog.at_level(logging.WARNING, logger="desk_gateway.tools.core"):
        reply = await memory_retain(_ctx(hindsight, substrate), {"content": FACT, "source": SOURCE})
    assert reply["error"] == "memory_unavailable"
    assert reply["ok"] is False
    planes = _by_plane(reply)
    assert planes["hindsight"]["state"] == "error"
    assert planes["substrate"]["state"] == "error"
    assert FACT not in caplog.text
    assert "hindsight returned HTTP 500" in caplog.text
