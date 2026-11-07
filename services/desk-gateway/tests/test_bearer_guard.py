from __future__ import annotations

import pytest

from desk_gateway.bearer_guard import BearerGuard, FailureTracker
from tests.conftest import PASS

CLIENT_A = "198.51.100.7"
CLIENT_B = "198.51.100.8"
JUNK = "not-a-real-bearer-token-0000000000"
LIVE_OAUTH = "live-oauth-access-token-0000000000"
GUESS = "p" * 24


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_seat_passphrase_floor(settings):
    settings.seat_passphrases["lead"] = "x" * 23
    assert settings.seat_for_passphrase("x" * 23) is None
    settings.seat_passphrases["lead"] = "y" * 24
    assert settings.seat_for_passphrase("y" * 24) == "lead"


def test_tracker_blocks_only_the_client_that_failed():
    tracker = FailureTracker(limit=3, window_sec=60, clock=FakeClock())
    for _ in range(3):
        tracker.record(CLIENT_A)
    assert tracker.blocked(CLIENT_A)
    assert not tracker.blocked(CLIENT_B)


def test_tracker_block_ages_out_with_the_window():
    clock = FakeClock()
    tracker = FailureTracker(limit=2, window_sec=60, clock=clock)
    tracker.record(CLIENT_A)
    tracker.record(CLIENT_A)
    assert tracker.blocked(CLIENT_A)
    clock.now += 61
    assert not tracker.blocked(CLIENT_A)


def test_tracker_forgets_the_longest_tracked_client_when_full():
    tracker = FailureTracker(limit=1, window_sec=60, max_clients=2, clock=FakeClock())
    tracker.record("a")
    tracker.record("b")
    tracker.record("c")
    assert not tracker.blocked("a")
    assert tracker.blocked("c")


async def _call(app, headers: dict[str, str]) -> list[dict]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": ("10.0.0.1", 1234),
    }
    await app(scope, receive, send)
    return sent


def _status(sent: list[dict]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _downstream(status: int, calls: list):
    async def app(scope, receive, send):
        calls.append(scope)
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return app


async def test_blocked_client_gets_one_refusal_for_any_bearer_token():
    calls: list = []
    guard = BearerGuard(
        _downstream(401, calls),
        tracker=FailureTracker(limit=2, window_sec=60, clock=FakeClock()),
        is_live_oauth_token=lambda token: token == LIVE_OAUTH,
    )
    junk = {"cf-connecting-ip": CLIENT_A, "authorization": f"Bearer {JUNK}"}
    assert _status(await _call(guard, junk)) == 401
    assert _status(await _call(guard, junk)) == 401

    reached = len(calls)
    # A wrong guess and a passphrase-shaped guess get the same refusal, and neither reaches the app.
    for token in (JUNK, GUESS):
        refused = await _call(guard, {"cf-connecting-ip": CLIENT_A, "authorization": f"Bearer {token}"})
        assert _status(refused) == 429
    assert len(calls) == reached

    # A live OAuth token from the same address still reaches the app.
    await _call(guard, {"cf-connecting-ip": CLIENT_A, "authorization": f"Bearer {LIVE_OAUTH}"})
    assert len(calls) == reached + 1

    # Another address is not affected.
    assert _status(await _call(guard, {"cf-connecting-ip": CLIENT_B, "authorization": f"Bearer {GUESS}"})) == 401
    assert len(calls) == reached + 2


def _route_headers(token: str, client: str) -> dict[str, str]:
    # JSON only: an open event stream would never end under ASGITransport.
    return {"Authorization": f"Bearer {token}", "cf-connecting-ip": client, "Accept": "application/json"}


@pytest.mark.parametrize("path", ["/v1/alerts/status", "/mcp/lead"])
async def test_bearer_guard_covers_v1_and_mcp_routes(client, path):
    for _ in range(10):
        resp = await client.get(path, headers=_route_headers(JUNK, CLIENT_A))
        assert resp.status_code == 401
    for token in (JUNK, PASS["lead"]):
        resp = await client.get(path, headers=_route_headers(token, CLIENT_A))
        assert resp.status_code == 429
    other = await client.get(path, headers=_route_headers(PASS["lead"], CLIENT_B))
    assert other.status_code not in (401, 429)
