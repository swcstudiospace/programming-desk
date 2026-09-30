from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "src"))

PASS = {
    "lead": "lead-pass-1234567890",
    "systems": "systems-pass-1234567890",
    "web": "web-pass-1234567890",
    "android": "android-pass-1234567890",
    "ios": "ios-pass-1234567890",
    "infra": "infra-pass-1234567890",
    "quality": "quality-pass-1234567890",
}
INTAKE_TOKEN = "test_origin_token_github_0001"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2025-06-18",
}


def _settings_env_names() -> set[str]:
    """Every variable config.py reads, taken from config.py itself.

    Read from the source rather than listed here so a new upstream cannot be added without
    the isolation below covering it. The assertion is the point: if the shape of config.py
    changes so this stops matching, the fixture fails loudly instead of quietly letting
    ambient credentials through again.
    """
    source = (ROOT / "src" / "desk_gateway" / "config.py").read_text()
    names = set(re.findall(r'_env\(\s*"([A-Z0-9_]+)"', source))
    assert len(names) > 20, (
        f"only {len(names)} env names found in config.py — the _env(...) pattern this test "
        "isolation depends on has changed, so upstream credentials would leak into tests"
    )
    return names


@pytest.fixture
def settings(tmp_path: Path):
    from desk_gateway.config import Settings

    env = {
        "PUBLIC_HOST": "desk.swcstudio.space",
        "DESK_REPO_DIR": str(REPO),
        "DESK_REPO_REMOTE": "",
        "DESK_REPO_BRANCH": "HEAD",
        "DATA_DIR": str(tmp_path / "data"),
        "INTAKE_TOKENS": f"github:{INTAKE_TOKEN}",
        **{f"SEAT_PASSPHRASE_{k.upper()}": v for k, v in PASS.items()},
    }
    old = dict(os.environ)
    # Clear every upstream variable this fixture does not set. Otherwise an ambient token
    # makes that upstream `configured`, and the suite issues live API calls with whatever
    # credentials the host happens to hold — GitHub, Railway, Vercel, Play Console, App
    # Store Connect. That is a real risk on the persistent self-hosted runner, and it also
    # made test_intake_flow_only_lead_can_drain pass or fail depending on the environment.
    for name in _settings_env_names() - set(env):
        os.environ.pop(name, None)
    os.environ.update(env)
    try:
        yield Settings.from_env()
    finally:
        os.environ.clear()
        os.environ.update(old)


@pytest.fixture
async def app(settings):
    from desk_gateway.server import build_app

    application, _ = build_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class Rpc:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.n = 0

    async def raw(self, seat: str, key: str | None, method: str, params: dict | None = None, path: str | None = None):
        self.n += 1
        headers = dict(MCP_HEADERS)
        if key:
            headers["x-connector-key"] = key
        body = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}
        return await self.client.post(path or f"/mcp/{seat}", headers=headers, json=body)

    async def tools(self, seat: str, key: str | None = None, path: str | None = None) -> list[str]:
        resp = await self.raw(seat, key or PASS[seat], "tools/list", path=path)
        assert resp.status_code == 200, resp.text
        return [t["name"] for t in resp.json()["result"]["tools"]]

    async def call(self, seat: str, name: str, args: dict, key: str | None = None) -> dict:
        resp = await self.raw(seat, key or PASS[seat], "tools/call", {"name": name, "arguments": args})
        assert resp.status_code == 200, resp.text
        result = resp.json()["result"]
        return {"is_error": result.get("isError", False), **(result.get("structuredContent") or {})}


@pytest.fixture
def rpc(client):
    return Rpc(client)
