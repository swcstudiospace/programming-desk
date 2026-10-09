"""Live desk view: the gateway's own traffic, re-published as Desk Event v1 for the 3D view."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections import deque
from pathlib import Path
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from desk_gateway.config import SEAT_BY_BOT, SEAT_LABEL, SEATS, Settings
from desk_gateway.redact import redact_text
from desk_gateway.store import Store
from desk_gateway.telemetry import get_current_trace_context

logger = logging.getLogger("desk_gateway.live")

EVENT_VERSION = 1
HISTORY_EVENTS = 60
REPLAY_EVENTS = 200
QUEUE_LIMIT = 500
AUTO_IDLE_SEC = 120
REPORTED_IDLE_SEC = 1800
ONLINE_WINDOW_SEC = 3600
SWEEP_SEC = 15
STATUSES = ("idle", "thinking", "working", "blocked", "error", "offline")
OUTSIDE = "outside"

UPSTREAM_RESOURCE = {
    "hindsight": "hindsight",
    "ragflow": "ragflow",
    "greptime": "greptimedb",
    "timescale": "timescaledb",
    "dragonfly": "dragonflydb",
}
BACKEND_UPSTREAMS: dict[str, tuple[str, ...]] = {
    "core.brief": ("hindsight",),
    "core.docs_search": ("ragflow",),
    "core.memory_retain": ("hindsight",),
    "core.memory_recall": ("hindsight",),
    "core.doctor": ("hindsight",),
    "systems.index_query": ("timescale",),
    "systems.events_query": ("greptime",),
    "systems.cache": ("dragonfly",),
    "infra.db_health": ("greptime", "timescale", "dragonfly", "hindsight", "ragflow"),
}
QUIET_BACKENDS = frozenset({"core.event_emit"})

STATUS_KINDS = frozenset({"status", "desk.status", "bot.status"})
ASSIGN_KINDS = frozenset({"task.assigned", "task.assign", "delegate"})
PROGRESS_KINDS = frozenset({"task.progress"})
DONE_KINDS = frozenset({"task.completed", "task.done", "task.failed"})
MESSAGE_KINDS = frozenset({"message", "handoff"})

SESSION_COOKIE = "desk_view"
SESSION_TTL_SEC = 30 * 86400
LOGIN_WINDOW_SEC = 600
LOGIN_MAX_FAILURES = 8
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_SLOW = 4408
INLINE_SCRIPT = re.compile(r"<script(?: type=\"module\")?>(.*?)</script>", re.S)


def seat_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    if key in SEATS:
        return key
    if key in SEAT_BY_BOT:
        return SEAT_BY_BOT[key]
    for short, label in SEAT_LABEL.items():
        if key == label.lower():
            return short
    if key in {OUTSIDE, "requester", "origin"}:
        return OUTSIDE
    return None


def _clip(value: Any, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return redact_text(" ".join(value.split()))[:limit]


class LiveDesk:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.viewers: dict[asyncio.Queue[dict[str, Any] | None], float] = {}
        self.recent: deque[dict[str, Any]] = deque(maxlen=REPLAY_EVENTS)
        self.state: dict[str, dict[str, Any]] = {s: {"status": None, "source": None, "at": 0.0, "detail": ""} for s in SEATS}
        self.activity: dict[str, float] = dict.fromkeys(SEATS, 0.0)
        self.counters: dict[str, dict[str, int]] = {s: {"done": 0, "failed": 0, "toolCalls": 0} for s in SEATS}
        self.tasks: dict[str, dict[str, Any]] = {}
        self._seq = 0
        self._sweeper: asyncio.Task[None] | None = None

    def emit(self, type_: str, data: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        event = {"v": EVENT_VERSION, "type": type_, "ts": round(time.time(), 3), "seq": self._seq, "data": data}
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            event["trace"] = trace_ctx
        self.recent.append(event)
        for queue in list(self.viewers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._evict(queue)
        self._ensure_sweeper()
        return event

    def _evict(self, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
        self.viewers.pop(queue, None)
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)

    def _ensure_sweeper(self) -> None:
        if self._sweeper and not self._sweeper.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._sweeper = loop.create_task(self._sweep_forever())

    async def _sweep_forever(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_SEC)
            try:
                self.sweep()
            except Exception:
                logger.exception("live sweep failed")

    def sweep(self, now: float | None = None) -> None:
        now = now or time.time()
        for seat in SEATS:
            entry = self.state[seat]
            quiet = now - max(entry["at"], self.activity[seat])
            if entry["source"] == "auto" and entry["status"] in {"working", "thinking"} and now - self.activity[seat] > AUTO_IDLE_SEC:
                self.set_status(seat, "idle", source="auto")
            elif entry["source"] == "reported" and entry["status"] not in {None, "idle", "offline"} and quiet > REPORTED_IDLE_SEC:
                self.set_status(seat, "idle", source="auto")
            elif entry["status"] == "idle" and not self.online(seat, now):
                self.set_status(seat, "offline", source="auto")

    def online(self, seat: str, now: float | None = None) -> bool:
        now = now or time.time()
        seen = ((self.store.roster().get("seats") or {}).get(seat) or {}).get("last_seen")
        last = max(self.activity[seat], float(seen) if isinstance(seen, (int, float)) else 0.0)
        return now - last < ONLINE_WINDOW_SEC

    def status_of(self, seat: str) -> str:
        entry = self.state[seat]
        if entry["status"]:
            return entry["status"]
        return "idle" if self.online(seat) else "offline"

    def set_status(self, seat: str, status: str, *, detail: str = "", source: str = "reported") -> None:
        entry = self.state[seat]
        now = time.time()
        changed = entry["status"] != status or entry["detail"] != detail
        entry.update(status=status, detail=detail, source=source, at=now)
        if changed:
            data: dict[str, Any] = {"bot": seat, "status": status}
            if detail:
                data["detail"] = detail
            self.emit("bot.status", data)

    def _touch(self, seat: str) -> None:
        self.activity[seat] = time.time()
        entry = self.state[seat]
        current = self.status_of(seat)
        if current in {"idle", "offline"} or (entry["source"] == "auto" and current == "thinking"):
            self.set_status(seat, "working", source="auto")

    def snapshot(self) -> dict[str, Any]:
        bots = []
        for seat in SEATS:
            entry: dict[str, Any] = {"id": seat, "status": self.status_of(seat), **self.counters[seat]}
            if self.state[seat]["detail"]:
                entry["detail"] = self.state[seat]["detail"]
            bots.append(entry)
        history = [e for e in self.recent if e["type"] != "bot.status"][-HISTORY_EVENTS:]
        return {
            "v": EVENT_VERSION,
            "type": "desk.snapshot",
            "ts": round(time.time(), 3),
            "seq": self._seq,
            "data": {"bots": bots, "tasks": list(self.tasks.values()), "history": history},
        }

    def tool_started(self, seat: str, tool: str, call_id: str, backend: str) -> None:
        if backend in QUIET_BACKENDS:
            return
        self._touch(seat)
        self.counters[seat]["toolCalls"] += 1
        self.emit("tool.call", {"bot": seat, "tool": tool, "callId": call_id})

    def tool_finished(
        self,
        seat: str,
        tool: str,
        call_id: str,
        backend: str,
        *,
        ok: bool,
        ms: float,
        args: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        if backend in QUIET_BACKENDS:
            return
        self.activity[seat] = time.time()
        self.emit("tool.result", {"bot": seat, "callId": call_id, "tool": tool, "ok": ok, "ms": round(ms)})
        for upstream in BACKEND_UPSTREAMS.get(backend, ()):
            self.emit("gateway.request", {"bot": seat, "resource": UPSTREAM_RESOURCE[upstream], "ok": ok, "ms": round(ms)})
        if backend == "lead.intake_next" and ok and isinstance(payload.get("work_order"), dict):
            order = payload["work_order"]
            self.set_status(seat, "thinking", detail=_clip(f"Reading {order.get('title') or 'a work order'}", 120), source="auto")
        if backend == "lead.intake_ack" and ok:
            note = _clip(args.get("message"), 160)
            self.emit("message", {"from": seat, "to": OUTSIDE, "text": f"{args.get('status', 'update')}{f': {note}' if note else ''}"})

    def request_received(self, intake_id: str, title: str) -> None:
        self.emit("request.received", {"requestId": intake_id, "title": _clip(title, 160) or intake_id})

    def reported(self, seat: str, kind: str, task_id: str | None, payload: dict[str, Any]) -> None:
        self.activity[seat] = time.time()
        if kind in STATUS_KINDS:
            status = str(payload.get("status") or "").strip().lower()
            if status in STATUSES:
                self.set_status(seat, status, detail=_clip(payload.get("detail"), 120), source="reported")
                return
        elif kind in ASSIGN_KINDS:
            target = seat_ref(payload.get("to"))
            title = _clip(payload.get("title")) or _clip(payload.get("summary"))
            if target and target != OUTSIDE and title:
                task = task_id or f"t-{secrets.token_hex(4)}"
                self.tasks[task] = {"taskId": task, "bot": target, "title": title, "progress": 0}
                self.emit("task.assigned", {"taskId": task, "from": seat, "to": target, "title": title})
                return
        elif kind in PROGRESS_KINDS:
            progress = payload.get("progress")
            if task_id and isinstance(progress, (int, float)) and not isinstance(progress, bool) and 0 <= progress <= 100:
                value = progress / 100 if progress > 1 else float(progress)
                if task_id in self.tasks:
                    self.tasks[task_id]["progress"] = value
                self.emit("task.progress", {"taskId": task_id, "bot": seat, "progress": value})
                return
        elif kind in DONE_KINDS:
            if task_id:
                ok = kind != "task.failed" and payload.get("ok") is not False
                self.tasks.pop(task_id, None)
                self.counters[seat]["done" if ok else "failed"] += 1
                data: dict[str, Any] = {"taskId": task_id, "bot": seat, "ok": ok}
                summary = _clip(payload.get("summary"))
                if summary:
                    data["summary"] = summary
                self.emit("task.completed", data)
                return
        elif kind in MESSAGE_KINDS:
            target = seat_ref(payload.get("to"))
            if target:
                data = {"from": seat, "to": target}
                text = _clip(payload.get("text")) or _clip(payload.get("summary"))
                if text:
                    data["text"] = text
                self.emit("message", data)
                return
        text = _clip(payload.get("summary")) or _clip(payload.get("text")) or _clip(payload.get("detail"))
        self.emit("note", {"bot": seat, "text": f"{kind}: {text}" if text else kind})

    async def serve(self, websocket: WebSocket) -> None:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self.viewers[queue] = time.time()
        self._ensure_sweeper()

        async def pump() -> None:
            await websocket.send_text(json.dumps(self.snapshot(), separators=(",", ":")))
            while True:
                event = await queue.get()
                if event is None:
                    await websocket.close(code=CLOSE_SLOW)
                    return
                await websocket.send_text(json.dumps(event, separators=(",", ":")))

        async def drain() -> None:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        tasks = [asyncio.create_task(pump()), asyncio.create_task(drain())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                error = task.exception()
                if error and not isinstance(error, (WebSocketDisconnect, RuntimeError)):
                    logger.warning("desk view socket closed: %s", error)
        finally:
            for task in tasks:
                task.cancel()
            self.viewers.pop(queue, None)


class ViewerAuth:
    def __init__(self, settings: Settings) -> None:
        self.passphrase = settings.view_passphrase
        key = settings.view_secret or secrets.token_urlsafe(32)
        if not settings.view_secret:
            logger.warning("DESK_VIEW_SECRET is not set; viewer sessions end when the gateway restarts")
        fingerprint = hashlib.sha256(self.passphrase.encode()).hexdigest()
        self.key = f"{key}:{fingerprint}".encode()
        self.failures: dict[str, deque[float]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.passphrase)

    def check(self, candidate: str) -> bool:
        return self.enabled and secrets.compare_digest(candidate.encode(), self.passphrase.encode())

    def _sign(self, body: str) -> str:
        digest = hmac.new(self.key, body.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def issue(self) -> str:
        body = f"{int(time.time()) + SESSION_TTL_SEC}.{secrets.token_urlsafe(9)}"
        return f"{body}.{self._sign(body)}"

    def valid(self, token: str | None) -> bool:
        if not self.enabled or not token:
            return False
        parts = token.split(".")
        if len(parts) != 3 or not parts[0].isdigit():
            return False
        body = f"{parts[0]}.{parts[1]}"
        return secrets.compare_digest(parts[2], self._sign(body)) and int(parts[0]) > time.time()

    def throttled(self, client: str) -> bool:
        window = self.failures.get(client)
        if not window:
            return False
        cutoff = time.time() - LOGIN_WINDOW_SEC
        while window and window[0] < cutoff:
            window.popleft()
        return len(window) >= LOGIN_MAX_FAILURES

    def failed(self, client: str) -> None:
        self.failures.setdefault(client, deque()).append(time.time())


class DeskView:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.html: str | None = None
        self.script_hashes: list[str] = []
        if path.is_file():
            self.html = path.read_text(encoding="utf-8")
            for body in INLINE_SCRIPT.findall(self.html):
                digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                self.script_hashes.append(f"'sha256-{digest}'")

    def headers(self, public_host: str) -> dict[str, str]:
        scripts = " ".join(self.script_hashes) or "'none'"
        csp = (
            "default-src 'none'; "
            f"script-src {scripts}; "
            "style-src 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            f"connect-src 'self' wss://{public_host}; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return {
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": csp,
        }


def client_key(headers: Any, fallback: str | None) -> str:
    return headers.get("cf-connecting-ip") or fallback or "unknown"


def origin_allowed(origin: str | None, public_host: str) -> bool:
    if not origin:
        return True
    if origin == f"https://{public_host}":
        return True
    return bool(re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$", origin))
