from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import INTAKE_TOKEN, PASS

VIEW_PASS = "view-pass-1234567890"
PAGE = "<!doctype html><title>Desk</title><div class=\"app\"></div><script type=\"module\">console.log('desk')</script>"


@pytest.fixture
def view_html(tmp_path, monkeypatch):
    import desk_gateway.server as server

    path = tmp_path / "desk3d.html"
    path.write_text(PAGE, encoding="utf-8")
    monkeypatch.setattr(server, "DESK_VIEW_HTML", path)
    return path


@pytest.fixture
def settings(settings, view_html):
    settings.view_passphrase = VIEW_PASS
    settings.view_secret = "test-view-secret-0123456789abcdef"  # pragma: allowlist secret (test fixture; signs cookies for this test run only)
    return settings


@pytest.fixture
def web_app(settings):
    from desk_gateway.server import build_app

    application, _ = build_app(settings)
    return application


def live_of(app):
    return app.state["services"].live


def events(app, type_=None):
    recent = list(live_of(app).recent)
    return [e for e in recent if type_ is None or e["type"] == type_]


async def test_snapshot_lists_every_seat_offline_before_any_bot_connects(app):
    snap = live_of(app).snapshot()
    assert snap["type"] == "desk.snapshot" and snap["v"] == 1
    bots = {b["id"]: b for b in snap["data"]["bots"]}
    assert set(bots) == set(PASS)
    assert all(b["status"] == "offline" for b in bots.values())
    assert snap["data"]["tasks"] == [] and snap["data"]["history"] == []


async def test_tool_calls_become_tool_and_gateway_events(app, rpc):
    await rpc.call("ios", "desk_memory_recall", {"query": "push notifications"})
    calls = events(app, "tool.call")
    results = events(app, "tool.result")
    assert calls[-1]["data"]["bot"] == "ios" and calls[-1]["data"]["tool"] == "desk_memory_recall"
    assert results[-1]["data"]["callId"] == calls[-1]["data"]["callId"]
    gateway = events(app, "gateway.request")
    assert gateway[-1]["data"] == {"bot": "ios", "resource": "hindsight", "ok": results[-1]["data"]["ok"], "ms": results[-1]["data"]["ms"]}
    status = events(app, "bot.status")
    assert status[0]["data"] == {"bot": "ios", "status": "working"}
    assert live_of(app).snapshot()["data"]["bots"][4]["toolCalls"] == 1


async def test_event_emit_drives_status_tasks_and_messages(app, rpc):
    await rpc.call("android", "desk_event_emit", {"kind": "status", "payload": {"status": "thinking", "detail": "Reading the spec"}})
    await rpc.call("lead", "desk_event_emit", {"kind": "task.assigned", "task_id": "T-7", "payload": {"to": "ANDROID", "title": "Build the opt-in dialog"}})
    await rpc.call("android", "desk_event_emit", {"kind": "task.progress", "task_id": "T-7", "payload": {"progress": 40}})
    snap = live_of(app).snapshot()
    assert snap["data"]["tasks"] == [{"taskId": "T-7", "bot": "android", "title": "Build the opt-in dialog", "progress": 0.4}]
    await rpc.call("android", "desk_event_emit", {"kind": "message", "payload": {"to": "bot-04-ios", "text": "Sharing the conflict rules"}})
    await rpc.call("android", "desk_event_emit", {"kind": "task.done", "task_id": "T-7", "payload": {"summary": "Dialog merged"}})
    await rpc.call("web", "desk_event_emit", {"kind": "deploy.preview", "payload": {"summary": "Preview is up"}})
    types = [e["type"] for e in events(app) if e["type"] != "bot.status"]
    assert types == ["task.assigned", "task.progress", "message", "task.completed", "note"]
    assert events(app, "task.assigned")[0]["data"] == {"taskId": "T-7", "from": "lead", "to": "android", "title": "Build the opt-in dialog"}
    assert events(app, "message")[0]["data"] == {"from": "android", "to": "ios", "text": "Sharing the conflict rules"}
    assert events(app, "task.completed")[0]["data"] == {"taskId": "T-7", "bot": "android", "ok": True, "summary": "Dialog merged"}
    assert events(app, "note")[0]["data"] == {"bot": "web", "text": "deploy.preview: Preview is up"}
    assert {"bot": "android", "status": "thinking", "detail": "Reading the spec"} in [e["data"] for e in events(app, "bot.status")]
    bots = {b["id"]: b for b in live_of(app).snapshot()["data"]["bots"]}
    assert bots["android"]["done"] == 1 and live_of(app).snapshot()["data"]["tasks"] == []
    assert not events(app, "tool.call")


async def test_reported_text_is_redacted(app, rpc):
    await rpc.call("infra", "desk_event_emit", {"kind": "status", "payload": {"status": "blocked", "detail": "waiting on token rotation"}})
    live_of(app).reported("infra", "note", None, {"summary": "password=hunter2hunter2 leaked"})
    assert "hunter2" not in json.dumps(list(live_of(app).recent))


async def test_intake_becomes_request_received(client, app):
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json={"title": "Ship 2.4", "ask": "Ship release 2.4 to both stores this week."})
    assert resp.status_code == 202
    received = events(app, "request.received")
    assert received[-1]["data"] == {"requestId": resp.json()["intake_id"], "title": "Ship 2.4"}


def test_view_requires_sign_in_and_serves_the_page_with_a_hashed_script(web_app):
    app = web_app
    with TestClient(app, base_url="https://desk.swcstudio.space") as client:
        page = client.get("/")
        assert page.status_code == 200 and "Desk view passphrase" in page.text
        assert client.get("/connect").status_code == 200
        bad = client.post("/view/login", data={"passphrase": "nope"}, follow_redirects=False)
        assert bad.status_code == 401
        good = client.post("/view/login", data={"passphrase": VIEW_PASS}, follow_redirects=False)
        assert good.status_code == 303
        cookie = good.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=strict" in cookie.lower()
        view = client.get("/")
        assert view.status_code == 200 and "console.log('desk')" in view.text
        csp = view.headers["content-security-policy"]
        assert "script-src 'sha256-" in csp and "unsafe-eval" not in csp and "connect-src 'self' wss://desk.swcstudio.space" in csp


def test_login_is_throttled_after_repeated_failures(web_app):
    app = web_app
    with TestClient(app, base_url="https://desk.swcstudio.space") as client:
        for _ in range(8):
            client.post("/view/login", data={"passphrase": "wrong"}, headers={"cf-connecting-ip": "203.0.113.9"})
        blocked = client.post("/view/login", data={"passphrase": VIEW_PASS}, headers={"cf-connecting-ip": "203.0.113.9"}, follow_redirects=False)
        assert blocked.status_code == 429


def test_socket_refuses_viewers_without_a_session_or_from_other_origins(web_app):
    app = web_app
    with TestClient(app, base_url="https://desk.swcstudio.space") as client:
        with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect("/desk/events") as ws:
            ws.receive_text()
        assert closed.value.code == 4401
        token = app.state["viewer"].issue()
        headers = {"cookie": f"desk_view={token}", "origin": "https://evil.example"}
        with pytest.raises(WebSocketDisconnect) as closed, client.websocket_connect("/desk/events", headers=headers) as ws:
            ws.receive_text()
        assert closed.value.code == 4403


def test_socket_sends_a_snapshot_then_live_events(web_app):
    app = web_app
    with TestClient(app, base_url="https://desk.swcstudio.space") as client:
        token = app.state["viewer"].issue()
        headers = {"cookie": f"desk_view={token}", "origin": "https://desk.swcstudio.space"}
        with client.websocket_connect("/desk/events", headers=headers) as ws:
            first = json.loads(ws.receive_text())
            assert first["type"] == "desk.snapshot" and len(first["data"]["bots"]) == 7
            client.portal.call(_emit, live_of(app))
            second = json.loads(ws.receive_text())
            assert second["type"] == "request.received" and second["data"]["title"] == "Ship it"


async def _emit(live):
    live.request_received("in-1", "Ship it")


def test_forged_or_expired_sessions_are_rejected(app):
    viewer = app.state["viewer"]
    token = viewer.issue()
    exp, nonce, sig = token.split(".")
    assert viewer.valid(token)
    assert not viewer.valid(f"{int(exp) + 1}.{nonce}.{sig}")
    assert not viewer.valid(f"1.{nonce}.{sig}")
    assert not viewer.valid("garbage")


def test_sweep_returns_quiet_seats_to_idle(app):
    live = live_of(app)
    live.tool_started("web", "desk_preview_check", "c1", "web.preview_check")
    assert live.status_of("web") == "working"
    live.sweep(now=live.activity["web"] + 121)
    assert live.status_of("web") == "idle"
