"""Per-client limit on rejected bearer requests, applied to every route.

A seat passphrase is accepted as a bearer token (Authorization header or x-connector-key) on the
MCP routes and on the /v1 routes. This middleware counts the 401 responses to requests that present
a bearer or connector key, per client address. nginx restores that address from Cloudflare's
CF-Connecting-IP before it reaches the gateway.

A client that reaches FAILURE_LIMIT rejections inside FAILURE_WINDOW_SEC is refused every bearer
request that is not a live OAuth access token. The refusal is the same 429 for any token, so the
response does not reveal whether a guess was a passphrase. Refused requests never reach the app,
and no passphrase is evaluated for them. A live OAuth token from the same address still passes.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from desk_gateway.live import client_key

FAILURE_LIMIT = 10
FAILURE_WINDOW_SEC = 600.0
MAX_TRACKED_CLIENTS = 10_000


class FailureTracker:
    """Sliding-window count of rejected bearer requests per client key."""

    def __init__(
        self,
        *,
        limit: int = FAILURE_LIMIT,
        window_sec: float = FAILURE_WINDOW_SEC,
        max_clients: int = MAX_TRACKED_CLIENTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self.max_clients = max_clients
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def _trim(self, events: deque[float]) -> None:
        cutoff = self._clock() - self.window_sec
        while events and events[0] <= cutoff:
            events.popleft()

    def blocked(self, key: str) -> bool:
        events = self._events.get(key)
        if events is None:
            return False
        self._trim(events)
        if not events:
            del self._events[key]
            return False
        return len(events) >= self.limit

    def record(self, key: str) -> None:
        if key not in self._events and len(self._events) >= self.max_clients:
            # Bounded memory: forget the client that has been tracked the longest.
            del self._events[next(iter(self._events))]
        events = self._events.setdefault(key, deque())
        self._trim(events)
        if len(events) < self.limit:
            events.append(self._clock())


class BearerGuard:
    """ASGI middleware. Wrap the whole app so every route is covered."""

    def __init__(
        self,
        app: Any,
        *,
        tracker: FailureTracker,
        is_live_oauth_token: Callable[[str], bool],
    ) -> None:
        self.app = app
        self.tracker = tracker
        self.is_live_oauth_token = is_live_oauth_token
        self.state: dict[str, Any] = {}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _header_map(scope)
        token = _presented_token(headers)
        if token is None:
            await self.app(scope, receive, send)
            return
        key = client_key(headers, _peer_host(scope))
        if self.tracker.blocked(key) and not self.is_live_oauth_token(token):
            await _throttled(send, self.tracker.window_sec)
            return
        status = 0

        async def watch(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        await self.app(scope, receive, watch)
        if status == 401:
            self.tracker.record(key)


def _header_map(scope: dict[str, Any]) -> dict[str, str]:
    return {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers") or []}


def _presented_token(headers: dict[str, str]) -> str | None:
    # Same precedence as server._bearer: Authorization first, then x-connector-key.
    auth = headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return headers.get("x-connector-key", "").strip() or None


def _peer_host(scope: dict[str, Any]) -> str | None:
    client = scope.get("client")
    return client[0] if client else None


async def _throttled(send: Any, window_sec: float) -> None:
    body = json.dumps(
        {
            "type": "about:blank",
            "title": "Too Many Invalid Bearer Tokens",
            "status": 429,
            "detail": (
                "Too many rejected bearer tokens from this client. Bearer requests are paused for "
                "this client until its recent rejections age out."
            ),
            "error_code": "bearer_throttled",
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/problem+json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(int(window_sec)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
