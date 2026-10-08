"""Programming Desk gateway: one MCP endpoint per seat, contract-defined rosters, LEAD-only intake."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as MCPTool
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from desk_gateway import __version__
from desk_gateway.config import MAX_LIVE_TOOLS, SEATS, TOOL_DEADLINE_SEC, Settings
from desk_gateway.live import (
    CLOSE_FORBIDDEN_ORIGIN,
    CLOSE_UNAUTHORIZED,
    SESSION_COOKIE,
    SESSION_TTL_SEC,
    DeskView,
    ViewerAuth,
    client_key,
    origin_allowed,
)
from desk_gateway.oauth import ConsentError, SeatOAuthProvider, seat_of
from desk_gateway.pages import consent_page, landing_page, message_page, view_login_page
from desk_gateway.problems import problem_details, problem_response
from desk_gateway.redact import contains_secret, redact_value
from desk_gateway.rosters import RosterError, Rosters, ToolSpec
from desk_gateway.schema import SchemaError, validate
from desk_gateway.store import Store
from desk_gateway.tools import Services, ToolContext, resolve

logger = logging.getLogger("desk_gateway")

PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
}
SEAT_PATH = re.compile(r"^/mcp/(?P<seat>[a-z]+)(?:/packs/(?P<pack>[a-z][a-z0-9-]{1,40}))?/?$")
RESOURCE_META_PATH = re.compile(r"^/\.well-known/oauth-protected-resource/mcp(?:/[a-z]+(?:/packs/[a-z0-9-]+)?)?/?$")
INTAKE_PRIORITIES = ("low", "normal", "high", "urgent")
INTAKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "ask"],
    "properties": {
        "origin": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,40}$"},
        "title": {"type": "string", "minLength": 3, "maxLength": 200},
        "ask": {"type": "string", "minLength": 10, "maxLength": 20000},
        "links": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 500, "pattern": "^https://"}},
        "priority": {"type": "string", "enum": list(INTAKE_PRIORITIES), "default": "normal"},
        "requested_by": {"type": "string", "maxLength": 120},
        "idempotency_key": {"type": "string", "maxLength": 200},
    },
}

current_seat: contextvars.ContextVar[str | None] = contextvars.ContextVar("desk_seat", default=None)
current_pack: contextvars.ContextVar[str | None] = contextvars.ContextVar("desk_pack", default=None)

INSTRUCTIONS = """\
Programming Desk gateway. You are connected as one seat; tools/list is your contract
(contracts/tool-rosters/<seat>.yaml). A tool that is not listed does not exist. Call desk_brief at
the start of a turn and desk_ownership_resolve before the first edit. Read tools fail open with a
`reason`; write tools fail closed. Tools tagged g5 need rollback_plan and approval_id, g6 need
approval_id (PD-5). A 403 means you are on another seat's endpoint: stop and tell LEAD.
"""


class SeatServer(MCPServer):
    def __init__(self, services: Services, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.services = services

    def _surface(self) -> tuple[str, dict[str, ToolSpec]]:
        seat = current_seat.get() or seat_of(get_access_token())
        if seat is None or seat not in SEATS:
            raise PermissionError("no seat")
        pack = current_pack.get()
        if pack:
            return seat, self.services.rosters.pack_surface(seat, pack)
        return seat, self.services.rosters.surface(seat, self.services.store.packs_for(seat))

    async def list_tools(self) -> list[MCPTool]:
        try:
            _, tools = self._surface()
        except (PermissionError, RosterError) as exc:
            logger.warning("tools/list refused: %s", exc)
            return []
        return [
            MCPTool(
                name=spec.name,
                title=spec.name.replace("_", " "),
                description=spec.description + (f" Gates: {' '.join(spec.gates)}." if spec.gates else ""),
                input_schema=spec.input_schema,
                annotations={"readOnlyHint": spec.read_only, "destructiveHint": "g6" in spec.gates},
            )
            for spec in tools.values()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any], context: Any = None) -> CallToolResult:
        started = time.monotonic()
        try:
            seat, tools = self._surface()
        except (PermissionError, RosterError) as exc:
            return _result({"error": "forbidden", "reason": str(exc)}, is_error=True)
        spec = tools.get(name)
        if spec is None:
            return _result({"error": "unknown_tool", "reason": f"{name} is not on the {seat} roster; a tool the gateway did not list does not exist"}, is_error=True)
        try:
            args = validate(spec.input_schema, arguments or {})
        except SchemaError as exc:
            return _result({"error": "invalid_args", "reason": str(exc)}, is_error=True)
        if contains_secret(json.dumps(args)):
            return _result({"error": "secret_refused", "reason": "tool arguments contain a credential shape; never paste secrets into tool calls (PD-4)"}, is_error=True)
        ctx = ToolContext(services=self.services, seat=self.services.rosters.seats[seat], spec=spec)
        call_id = secrets.token_hex(4)
        _live(self.services.live.tool_started, seat, name, call_id, spec.backend)
        error: str | None = None
        try:
            fn = resolve(spec.backend)
            async with asyncio.timeout(TOOL_DEADLINE_SEC):
                payload = await fn(ctx, args)
        except TimeoutError:
            error = "deadline"
            payload = {"error": "deadline", "reason": f"{name} did not finish within {TOOL_DEADLINE_SEC:.0f}s"}
        except LookupError:
            error = "backend_missing"
            payload = {"error": "backend_missing", "reason": f"{spec.backend} is not implemented on this gateway"}
        except Exception as exc:
            logger.exception("tool %s failed", name)
            error = "internal"
            payload = {"error": "internal", "reason": f"{type(exc).__name__} while running {name}"}
        if payload.get("error"):
            error = str(payload["error"])
        if error and spec.read_only and "results" not in payload and "rows" not in payload:
            payload.setdefault("reason", error)
        ms = (time.monotonic() - started) * 1000
        _live(
            self.services.live.tool_finished,
            seat,
            name,
            call_id,
            spec.backend,
            ok=error is None,
            ms=ms,
            args=args,
            payload=payload,
        )
        event = self.services.audit.tool_event(seat=seat, tool=name, arguments=args, ok=error is None, ms=ms, error=error, gates=spec.gates)
        self.services.audit.fire_and_forget(event)
        return _result(redact_value(payload), is_error=bool(error) and not spec.read_only)


DESK_VIEW_HTML = Path(__file__).parent / "web" / "desk3d.html"


def _live(fn: Any, *args: Any, **kwargs: Any) -> None:
    """Run a live-desk update, swallowing any failure.

    The 3D view is an observer. A broken live update must never fail the tool call or request
    that triggered it, so every call into LiveDesk goes through here.
    """
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.exception("live desk update failed")


def _result(payload: dict[str, Any], *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, default=str))], structured_content=payload, is_error=is_error)


class SeatRouter:
    """Maps /mcp/<seat>[/packs/<app>] onto the single MCP route, refusing a token that belongs to
    another seat with a real HTTP 403 before the request reaches the MCP handler."""

    def __init__(self, app: Any, provider: SeatOAuthProvider, rosters: Rosters) -> None:
        self.app = app
        self.provider = provider
        self.rosters = rosters

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if RESOURCE_META_PATH.match(path):
            scope = dict(scope)
            scope["path"] = "/.well-known/oauth-protected-resource/mcp"
            scope["raw_path"] = scope["path"].encode()
            await self.app(scope, receive, send)
            return
        match = SEAT_PATH.match(path)
        if not match:
            await self.app(scope, receive, send)
            return
        seat, pack = match.group("seat"), match.group("pack")
        if seat not in SEATS:
            await _json(send, 404, {"error": "unknown_seat", "seats": sorted(SEATS)})
            return
        token = _bearer(scope)
        if token:
            access = await self.provider.load_access_token(token)
            token_seat = seat_of(access)
            if access is None:
                # Corrupted, unissued, or expired token
                prob = problem_details(
                    status=401,
                    title="Invalid or Expired Token",
                    detail="The provided bearer token is invalid, expired, or corrupted.",
                    error_code="invalid_token",
                    instance=path,
                )
                headers = [
                    (b"www-authenticate", b'Bearer error="invalid_token", error_description="The token is invalid or expired"'),
                ]
                await _json(send, 401, prob, headers=headers)
                return
            elif token_seat != seat:
                prob = problem_details(
                    status=403,
                    title="Wrong Seat",
                    detail=f"this token belongs to {token_seat or 'no seat'}; connect to /mcp/{token_seat} or re-authorise with the {seat} passphrase",
                    error_code="wrong_seat",
                    instance=path,
                    token_seat=token_seat,
                    expected_seat=seat,
                )
                await _json(send, 403, prob)
                return
        if pack and not self.rosters.pack_surface(seat, pack):
            await _json(send, 404, {"error": "unknown_pack", "reason": f"no pack {pack} for seat {seat}"})
            return
        scope = dict(scope)
        scope["path"] = "/mcp"
        scope["raw_path"] = b"/mcp"
        seat_token = current_seat.set(seat)
        pack_token = current_pack.set(pack)
        try:
            await self.app(scope, receive, send)
        finally:
            current_seat.reset(seat_token)
            current_pack.reset(pack_token)


def _bearer(scope: dict[str, Any]) -> str | None:
    headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
    auth = headers.get(b"authorization")
    if auth and auth.lower().startswith(b"bearer "):
        return auth[7:].decode(errors="ignore").strip()
    key = headers.get(b"x-connector-key")
    return key.decode(errors="ignore").strip() if key else None


async def _json(send: Any, status: int, body: dict[str, Any], headers: list[tuple[bytes, bytes]] | None = None) -> None:
    raw = json.dumps(body).encode()
    content_type = b"application/problem+json" if "title" in body and "status" in body else b"application/json"
    resp_headers = [
        (b"content-type", content_type),
        (b"content-length", str(len(raw)).encode()),
        (b"cache-control", b"no-store"),
    ]
    if headers:
        resp_headers.extend(headers)
    await send({"type": "http.response.start", "status": status, "headers": resp_headers})
    await send({"type": "http.response.body", "body": raw})


class ConnectorKeyHeader:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = list(scope.get("headers") or [])
            has_auth = any(key == b"authorization" for key, _ in headers)
            connector_key = next((val for key, val in headers if key == b"x-connector-key"), None)
            if connector_key and not has_auth:
                scope = dict(scope)
                scope["headers"] = [*headers, (b"authorization", b"Bearer " + connector_key)]
        await self.app(scope, receive, send)


def create_mcp(
    settings: Settings,
    services: Services,
    oauth: SeatOAuthProvider,
    viewer: ViewerAuth,
    view: DeskView,
) -> SeatServer:
    mcp = SeatServer(
        services,
        name="desk-gateway",
        title="Programming Desk gateway",
        description="One MCP endpoint per Programming Desk seat, with contract-defined tool rosters.",
        version=__version__,
        instructions=INSTRUCTIONS,
        log_level=settings.log_level if settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO",
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(settings.issuer_url),
            resource_server_url=AnyHttpUrl(settings.resource_url),
            validate_token_resource=False,
            required_scopes=["mcp"],
            client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["mcp", *(f"seat:{s}" for s in SEATS)], default_scopes=["mcp"]),
        ),
        auth_server_provider=oauth,
    )
    store = services.store

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        roster = store.roster()
        return JSONResponse(
            {
                "status": "ok",
                "service": "desk-gateway",
                "version": __version__,
                "seats": {s: f"/mcp/{s}" for s in SEATS},
                "packs": sorted(services.rosters.packs),
                "registered_seats": sorted(k for k, v in (roster.get("seats") or {}).items() if v.get("agent_uuid")),
                "channel_registered": bool(roster.get("channel_id")),
                "intake": store.intake_counts(),
                "oauth": {
                    "issuer": settings.issuer_url,
                    "authorization_endpoint": f"{settings.issuer_url}/authorize",
                    "token_endpoint": f"{settings.issuer_url}/token",
                    "registration_endpoint": f"{settings.issuer_url}/register",
                },
            }
        )

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(_request: Request) -> Response:
        return JSONResponse(
            {
                "status": "ok",
                "service": "desk-gateway",
                "version": __version__,
                "timestamp": time.time(),
            }
        )

    @mcp.custom_route("/readyz", methods=["GET"])
    async def readyz(_request: Request) -> Response:
        # Verify store readiness (ability to read roster/intake) and roster integrity
        is_ready = True
        details: dict[str, Any] = {}
        try:
            roster = store.roster()
            details["store"] = "ok"
        except Exception as exc:
            is_ready = False
            details["store"] = f"error: {exc}"

        try:
            roster_count = len(services.rosters.seats)
            if roster_count == 0:
                is_ready = False
                details["rosters"] = "empty"
            else:
                details["rosters"] = f"{roster_count} seats loaded"
        except Exception as exc:
            is_ready = False
            details["rosters"] = f"error: {exc}"

        status_code = 200 if is_ready else 503
        return JSONResponse(
            {
                "status": "ready" if is_ready else "not_ready",
                "service": "desk-gateway",
                "ready": is_ready,
                "checks": details,
            },
            status_code=status_code,
        )

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics(_request: Request) -> Response:
        intake_counts = store.intake_counts()
        total_intake = sum(intake_counts.values())
        seat_tool_counts = {
            s: len(services.rosters.seats[s].tools) if s in services.rosters.seats else 0
            for s in SEATS
        }
        lines = [
            "# HELP desk_gateway_up Whether the desk-gateway service is up",
            "# TYPE desk_gateway_up gauge",
            "desk_gateway_up 1",
            "# HELP desk_gateway_active_viewers Current active websocket viewers connected to live desk",
            "# TYPE desk_gateway_active_viewers gauge",
            f"desk_gateway_active_viewers {len(services.live.viewers)}",
            "# HELP desk_gateway_intake_queue_total Current items in the intake queue by state",
            "# TYPE desk_gateway_intake_queue_total gauge",
        ]
        for state, count in sorted(intake_counts.items()):
            lines.append(f'desk_gateway_intake_queue_total{{state="{state}"}} {count}')
        if not intake_counts:
            lines.append('desk_gateway_intake_queue_total{state="queued"} 0')
        lines.extend([
            "# HELP desk_gateway_registered_seats_total Number of registered seats with active agent uuids",
            "# TYPE desk_gateway_registered_seats_total gauge",
        ])
        roster = store.roster()
        reg_seats = len([k for k, v in (roster.get("seats") or {}).items() if v.get("agent_uuid")])
        lines.append(f"desk_gateway_registered_seats_total {reg_seats}")
        lines.extend([
            "# HELP desk_gateway_seat_tools_total Configured tool count per seat roster",
            "# TYPE desk_gateway_seat_tools_total gauge",
        ])
        for s, count in sorted(seat_tool_counts.items()):
            lines.append(f'desk_gateway_seat_tools_total{{seat="{s}"}} {count}')
        lines.append("")
        return Response(content="\n".join(lines), media_type="text/plain; version=0.0.4")

    @mcp.custom_route("/", methods=["GET"])
    async def root(request: Request) -> Response:
        # With the desk view off (or its bundle absent) `/` stays the connect landing page.
        if not viewer.enabled or view.html is None:
            return HTMLResponse(landing_page(settings), headers=PAGE_HEADERS)
        if not viewer.valid(request.cookies.get(SESSION_COOKIE)):
            return HTMLResponse(view_login_page(), headers=PAGE_HEADERS)
        return HTMLResponse(view.html, headers=view.headers(settings.public_host))

    @mcp.custom_route("/connect", methods=["GET"])
    async def connect(_request: Request) -> Response:
        # The seat-connection instructions, kept at a stable URL now that `/` serves the view.
        return HTMLResponse(landing_page(settings), headers=PAGE_HEADERS)

    @mcp.custom_route("/view/login", methods=["POST"])
    async def view_login(request: Request) -> Response:
        if not viewer.enabled:
            return HTMLResponse(
                message_page("Desk view is off", "Set DESK_VIEW_PASSPHRASE on the gateway to turn it on."),
                status_code=404,
                headers=PAGE_HEADERS,
            )
        client = client_key(request.headers, request.client.host if request.client else None)
        if viewer.throttled(client):
            return HTMLResponse(view_login_page("throttled"), status_code=429, headers=PAGE_HEADERS)
        form = await request.form()
        if not viewer.check(str(form.get("passphrase") or "")):
            viewer.failed(client)
            return HTMLResponse(view_login_page("bad_passphrase"), status_code=401, headers=PAGE_HEADERS)
        response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
        response.set_cookie(
            SESSION_COOKIE,
            viewer.issue(),
            max_age=SESSION_TTL_SEC,
            httponly=True,
            secure=True,
            samesite="strict",
        )
        return response

    @mcp.custom_route("/view/logout", methods=["POST"])
    async def view_logout(_request: Request) -> Response:
        response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
        response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="strict")
        return response

    @mcp.custom_route("/oauth/consent", methods=["GET"])
    async def consent_get(request: Request) -> Response:
        pending = oauth.pending(request.query_params.get("request", ""))
        if pending is None:
            return HTMLResponse(message_page("Request expired", "Start the connection again from Grok Bot."), status_code=410, headers=PAGE_HEADERS)
        return HTMLResponse(consent_page(request_id=pending.request_id, client_name=pending.client_name, client_id=pending.client_id, redirect_host=pending.redirect_host), headers=PAGE_HEADERS)

    @mcp.custom_route("/oauth/consent", methods=["POST"])
    async def consent_post(request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("request") or "")
        if str(form.get("action") or "") == "deny":
            target = oauth.deny(request_id)
            if target is None:
                return HTMLResponse(message_page("Request expired", "Start the connection again from Grok Bot."), status_code=410, headers=PAGE_HEADERS)
            return RedirectResponse(target, status_code=303, headers={"Cache-Control": "no-store"})
        try:
            target = oauth.approve(request_id, str(form.get("passphrase") or ""))
        except ConsentError as exc:
            if exc.code == "bad_passphrase":
                pending = oauth.pending(request_id)
                if pending is not None:
                    return HTMLResponse(consent_page(request_id=pending.request_id, client_name=pending.client_name, client_id=pending.client_id, redirect_host=pending.redirect_host, error="bad_passphrase"), status_code=401, headers=PAGE_HEADERS)
            logger.warning("oauth consent rejected: %s", exc.code)
            return HTMLResponse(message_page("Request closed", "Start the connection again from Grok Bot."), status_code=403, headers=PAGE_HEADERS)
        return RedirectResponse(target, status_code=303, headers={"Cache-Control": "no-store"})

    @mcp.custom_route("/v1/intake", methods=["POST"])
    async def intake(request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        origin = settings.origin_for_intake_token(token)
        if origin is None:
            if token and settings.seat_for_passphrase(token):
                return problem_response(
                    status=403,
                    title="Seat Token Forbidden For Intake",
                    detail="seat tokens cannot submit intake; only origin tokens can",
                    error_code="forbidden",
                    instance="/v1/intake",
                )
            return problem_response(
                status=401,
                title="Unauthorized Origin Token",
                detail="missing or unknown origin token",
                error_code="unauthorized",
                instance="/v1/intake",
                headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="missing or unknown origin token"'},
            )
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid_body"}, status_code=400)
        body.setdefault("origin", origin)
        try:
            item = validate(INTAKE_SCHEMA, body)
        except SchemaError as exc:
            return JSONResponse({"error": "invalid_args", "reason": str(exc)}, status_code=400)
        if item["origin"] != origin:
            return JSONResponse({"error": "forbidden", "reason": f"token belongs to origin {origin}"}, status_code=403)
        if contains_secret(item["ask"]) or contains_secret(item["title"]):
            return JSONResponse({"error": "secret_refused", "reason": "the ask contains a credential shape; remove it and resend"}, status_code=422)
        record = store.intake_create(item)
        _live(services.live.request_received, record["intake_id"], item["title"])
        event = {"kind": "handoff", "summary": f"intake from {origin}: {item['title'][:80]}", "payload": {"intake_id": record["intake_id"], "origin": origin, "priority": item.get("priority")}, "actor": "human" if origin in {"github", "slack", "shortcut"} else "agent"}
        store.audit_append({**event, "ts_gateway": time.time()})
        services.audit.fire_and_forget(event)
        return JSONResponse({"ok": True, "intake_id": record["intake_id"], "state": record["state"], "queue": store.intake_counts()}, status_code=202)

    return mcp


def build_app(settings: Settings | None = None) -> tuple[Any, Settings]:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir = settings.repo_dir / "contracts"
    rosters = Rosters.load(contracts_dir)
    store = Store(settings.data_dir)
    services = Services.build(settings, store, rosters)
    oauth = SeatOAuthProvider(settings, store_dir=settings.data_dir / "oauth")
    # One ViewerAuth for the whole app: it holds the signing key, so a second instance would
    # reject the sessions the first one issued whenever DESK_VIEW_SECRET is unset.
    viewer = ViewerAuth(settings)
    mcp = create_mcp(settings, services, oauth, viewer=viewer, view=DeskView(DESK_VIEW_HTML))
    origins = [
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://localhost",
        "http://localhost:*",
        f"https://{settings.public_host}",
        f"https://{settings.public_host}:*",
        "https://grok.com",
        "https://grok.x.ai",
        "https://x.ai",
        "https://cursor.com",
        *settings.extra_allowed_origins,
    ]
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]", "[::1]:*", settings.public_host, f"{settings.public_host}:*", "testserver"],
        allowed_origins=origins,
    )
    starlette_app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True, stateless_http=True, transport_security=transport_security, host=settings.public_host)

    async def desk_events(websocket: WebSocket) -> None:
        await websocket.accept()
        if not origin_allowed(websocket.headers.get("origin"), settings.public_host):
            await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
            return
        if not viewer.valid(websocket.cookies.get(SESSION_COOKIE)):
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        await services.live.serve(websocket)

    starlette_app.routes.append(WebSocketRoute("/desk/events", desk_events))
    app = ConnectorKeyHeader(SeatRouter(starlette_app, oauth, rosters))
    app.state = {"store": store, "services": services, "oauth": oauth, "rosters": rosters, "mcp": mcp, "viewer": viewer}
    return app, settings


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    _load_env_file(Path(os.environ.get("GATEWAY_ENV_FILE", "/etc/desk-gateway/gateway.env")))
    app, settings = build_app()
    missing = [s for s in SEATS if s not in settings.seat_passphrases]
    if missing:
        logger.warning("no passphrase for seats %s; those endpoints cannot be authorised", ",".join(missing))
    logger.info("starting desk-gateway v%s on %s:%s (data=%s, repo=%s, live-tool ceiling %s)", __version__, settings.host, settings.port, settings.data_dir, settings.repo_dir, MAX_LIVE_TOOLS)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower(), proxy_headers=True, forwarded_allow_ips="127.0.0.1")


def generate_passphrases() -> dict[str, str]:
    return {s: secrets.token_urlsafe(24) for s in SEATS}
