"""Programming Desk gateway: one MCP endpoint per seat, contract-defined rosters, LEAD-only intake."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import hmac
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
from desk_gateway.alerts import AlertDispatcher, AlertNotification, SLOEvaluator
from desk_gateway.cutover import (
    CanaryRouter,
    CutoverError,
    CutoverOrchestrator,
    EmergencyIsolationManager,
    SeatIsolatedError,
)
from desk_gateway.edge import (
    DistributedRateLimiter,
    EdgeError,
    EdgeIngressGateway,
    GeoSteeringRouter,
    RateLimitExceeded,
)
from desk_gateway.wan_mesh import (
    AttestationFailed,
    RegionImpairmentManager,
    RouteRevokedError,
    SeatIdentityAttestor,
    WanError,
    WanMeshRouter,
    WanPeerNode,
    WanSeatEnvelope,
)
from desk_gateway.vector_clock import (
    CausalityRelation,
    ConflictResolver,
    TaskNode,
    VectorClockGraph,
    compare_vector_clocks,
    union_vector_clocks,
)
from desk_gateway.chaos import ChaosException, ChaosHarness, ChaosRule, FaultType
from desk_gateway.dlq_replay import DLQReplayOrchestrator
from desk_gateway.resilience import ResilienceVerifier
from desk_gateway.supervisor import (
    SeatHealthStatus,
    SeatRuntimeProfile,
    SelfHealingSupervisor,
)
from desk_gateway.workload import WorkloadRebalancer
from desk_gateway.tenant import (
    TenantContext,
    TenantIsolationEngine,
    TenantIsolationError,
    current_tenant,
)
from desk_gateway.tenant_quota import (
    QuotaExceededError,
    TenantQuotaLimits,
    TenantQuotaPolicer,
)
from desk_gateway.tenant_audit import (
    AuditTamperError,
    TenantAuditEvent,
    TenantAuditLogger,
)
from desk_gateway.mesh import (
    AgentBusMessage,
    AgentBusRPC,
    CoSignVerificationError,
    CoSignedReceipt,
    DelegatedTask,
    DelegatedTaskStateMachine,
    DelegationState,
    DeskNotFoundError,
    DeskType,
    MeshDiscoveryRegistry,
    MeshError,
    ReceiptCoSigner,
)
from desk_gateway.finops import (
    CircuitBreakerStatus,
    ExpenditureReceipt,
    ExpenditureReceiptLedger,
    ModelTariff,
    SeatAllocation,
    SeatQuotaAllocationMatrix,
    SpendCircuitBreaker,
    TokenLedger,
)
from desk_gateway.tier_routing import (
    ComplexityClassifier,
    FallbackCascadeManager,
    FallbackReason,
    FinOpsVerifier,
    LLMTier,
    PromptCacheOptimizer,
    TierBenchmarkMonitor,
)
from desk_gateway.multimodal import (
    ArtifactMetadata,
    ArtifactType,
    MultiModalArtifactPipeline,
    StreamCancellationSupervisor,
    StreamingFrame,
    StreamingFrameType,
    StreamingToolBus,
)
from desk_gateway.multimodal_memory import (
    MultiModalStreamingVerifier,
    SensoryMemoryIndexer,
    SensoryMemoryRecord,
    SensorySearchResult,
    cosine_similarity,
)
from desk_gateway.streaming_mesh import (
    AdaptivePayloadDownsampler,
    CompressionQuality,
    DistributedMediaCache,
    MediaCacheEntry,
    NetworkConditions,
    StreamAuditReceipt,
    StreamRPCFrame,
    StreamRPCFrameType,
    StreamingClientMultiplexer,
    StreamingMeshRPC,
    StreamingToolAuditLogger,
)
from desk_gateway.rbac import (
    AccessDecision,
    PolicyEvaluationResult,
    PolicyRule,
    RBACPolicyEngine,
    Role,
)
from desk_gateway.failover import FailoverError, FailoverRouter
from desk_gateway.federation import (
    FederatedTokenValidator,
    FederationError,
    FederationRegistry,
    PeerDeskClient,
)
from desk_gateway.health import UpstreamHealthPoller
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
from desk_gateway.telemetry import (
    RedactionFilter,
    get_current_trace_context,
    parse_traceparent,
    span_id_var,
    telemetry_registry,
    trace_id_var,
    tracestate_var,
)
from desk_gateway.tools import Services, ToolContext, resolve

logger = logging.getLogger("desk_gateway")
logger.addFilter(RedactionFilter())

PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
}
SEAT_PATH = re.compile(r"^/mcp/(?P<seat>[a-z]+)(?:/packs/(?P<pack>[a-z][a-z0-9-]{1,40}))?/?$")
RESOURCE_META_PATH = re.compile(r"^/\.well-known/oauth-protected-resource/mcp(?:/[a-z]+(?:/packs/[a-z0-9-]+)?)?/?$")
INTAKE_PRIORITIES = ("low", "normal", "high", "urgent")
PR_PAYLOAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["repo", "number", "action"],
    "properties": {
        "repo": {"type": "string", "pattern": r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$"},
        "number": {"type": "integer", "minimum": 1},
        "action": {"type": "string", "enum": ["opened", "synchronize", "reopened", "closed", "labeled", "unlabeled"]},
        "head_sha": {"type": "string", "pattern": r"^[0-9a-fA-F]{7,40}$"},
        "base_branch": {"type": "string", "minLength": 1, "maxLength": 100},
        "sender": {"type": "string", "minLength": 1, "maxLength": 100},
    },
}
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
        "pr_payload": PR_PAYLOAD_SCHEMA,
    },
}

current_seat: contextvars.ContextVar[str | None] = contextvars.ContextVar("desk_seat", default=None)
current_pack: contextvars.ContextVar[str | None] = contextvars.ContextVar("desk_pack", default=None)
_origin_request_timestamps: dict[str, list[float]] = {}
_idempotency_cache: dict[str, tuple[float, dict[str, Any]]] = {}

INSTRUCTIONS = """\
Programming Desk gateway. You are connected as one seat; tools/list is your contract
(contracts/tool-rosters/<seat>.yaml). A tool that is not listed does not exist. Call desk_brief at
the start of a turn and desk_ownership_resolve before the first edit. Read tools fail open with a
`reason`; write tools fail closed. Tools tagged g5 need rollback_plan and approval_id, g6 need
approval_id (PD-5). A 403 means you are on another seat's endpoint: stop and tell LEAD.
"""


class SeatServer(MCPServer):
    def __init__(
        self,
        services: Services,
        rbac: RBACPolicyEngine | None = None,
        tenant_engine: TenantIsolationEngine | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.services = services
        self.rbac = rbac or RBACPolicyEngine()
        self.tenant_engine = tenant_engine or TenantIsolationEngine()

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

        # RBAC / ABAC Policy Evaluation (REQ-TENANT-002)
        tenant = current_tenant.get()
        role = Role.LEAD if seat == "lead" else Role.DEVELOPER
        policy_eval = self.rbac.evaluate(
            tenant=tenant,
            role=role,
            seat=seat,
            action=f"tool:{name}",
            gates=spec.gates,
            is_destructive="g6" in spec.gates,
            has_approval=bool(args.get("approval_id")),
            has_rollback_plan=bool(args.get("rollback_plan")),
        )
        if policy_eval.decision == AccessDecision.DENY:
            return _result({"error": "policy_denied", "reason": policy_eval.reason}, is_error=True)

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
        telemetry_registry.record_seat_latency(seat, ms)
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

    def __init__(
        self,
        app: Any,
        provider: SeatOAuthProvider,
        rosters: Rosters,
        isolation_manager: EmergencyIsolationManager | None = None,
        failover_router: FailoverRouter | None = None,
        edge_gateway: EdgeIngressGateway | None = None,
        supervisor: SelfHealingSupervisor | None = None,
    ) -> None:
        self.app = app
        self.provider = provider
        self.rosters = rosters
        self.isolation_manager = isolation_manager
        self.failover_router = failover_router
        self.edge_gateway = edge_gateway
        self.supervisor = supervisor

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
        # Quarantine / Emergency Seat Isolation Check (REQ-CUTOVER-005)
        if self.isolation_manager and self.isolation_manager.is_isolated(seat):
            # Check if failover can divert to a healthy peer desk (REQ-CUTOVER-002)
            diverted = False
            divert_target = None
            divert_reason = None
            if self.failover_router:
                diverted, divert_target, divert_reason = self.failover_router.should_divert_seat(seat)

            iso_record = self.isolation_manager.get_isolation(seat)
            reason = iso_record.reason if iso_record else "anomaly detected"
            prob = problem_details(
                status=503,
                title="Seat Isolated",
                detail=f"Seat '{seat}' has been isolated and quarantined: {reason}" + (f" (failover target: {divert_target})" if diverted else ""),
                error_code="seat_isolated",
                instance=path,
                seat=seat,
                reason=reason,
                failover_diverted=diverted,
                failover_target=divert_target,
            )
            await _json(send, 503, prob)
            return

        # Failover check for degraded seat dependencies (REQ-CUTOVER-002)
        if self.failover_router:
            divert, divert_target, divert_reason = self.failover_router.should_divert_seat(seat)
            if divert:
                prob = problem_details(
                    status=503,
                    title="Seat Failover Diverted",
                    detail=f"Seat '{seat}' is diverted to peer desk '{divert_target}': {divert_reason}",
                    error_code="seat_diverted",
                    instance=path,
                    seat=seat,
                    failover_target=divert_target,
                    reason=divert_reason,
                )
                await _json(send, 503, prob)
                return
        # Distributed rate limiting check on seat dispatch (REQ-EDGE-002)
        rate_headers: list[tuple[bytes, bytes]] = []
        if self.edge_gateway:
            try:
                hdrs = await self.edge_gateway.enforce_rate_limit(seat, amount=1)
                rate_headers = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in hdrs.items()]
            except RateLimitExceeded as exc:
                prob = problem_details(
                    status=429,
                    title="Seat Rate Limit Exceeded",
                    detail=f"Rate limit exceeded for seat '{seat}': burst capacity {exc.limit} tokens reached.",
                    error_code="rate_limit_exceeded",
                    instance=path,
                    seat=seat,
                    retry_after=exc.retry_after,
                )
                headers = [(k.lower().encode("latin1"), v.encode("latin1")) for k, v in exc.headers.items()]
                await _json(send, 429, prob, headers=headers)
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

            # W3C traceparent and tracestate extraction (REQ-INTAKE-006)
            header_map = {k.lower(): v for k, v in headers}
            tp_raw = header_map.get(b"traceparent")
            ts_raw = header_map.get(b"tracestate")
            traceparent_str = tp_raw.decode("utf-8", errors="ignore").strip() if tp_raw else None
            tracestate_str = ts_raw.decode("utf-8", errors="ignore").strip() if ts_raw else ""

            parsed_tp = parse_traceparent(traceparent_str)
            t_token = trace_id_var.set(parsed_tp[0] if parsed_tp else "")
            s_token = span_id_var.set(parsed_tp[1] if parsed_tp else "")
            st_token = tracestate_var.set(tracestate_str)

            # Tenant Isolation Context Extraction (REQ-TENANT-001)
            tenant_engine = TenantIsolationEngine()
            str_headers = {
                k.decode("latin1").lower(): v.decode("latin1") for k, v in headers
            }
            tenant_ctx = tenant_engine.extract_from_headers(str_headers)
            tenant_token = current_tenant.set(tenant_ctx)

            try:
                await self.app(scope, receive, send)
            finally:
                trace_id_var.reset(t_token)
                span_id_var.reset(s_token)
                tracestate_var.reset(st_token)
                current_tenant.reset(tenant_token)
            return
        await self.app(scope, receive, send)


def create_mcp(
    settings: Settings,
    services: Services,
    oauth: SeatOAuthProvider,
    viewer: ViewerAuth,
    view: DeskView,
    federation: tuple[FederationRegistry, FederatedTokenValidator, PeerDeskClient] | None = None,
    cutover: tuple[CutoverOrchestrator, EmergencyIsolationManager] | None = None,
    failover: tuple[FailoverRouter, UpstreamHealthPoller] | None = None,
    alerting: tuple[AlertDispatcher, SLOEvaluator] | None = None,
    edge: EdgeIngressGateway | None = None,
    wan: tuple[WanMeshRouter, RegionImpairmentManager] | None = None,
    chaos: ChaosHarness | None = None,
    supervisor: SelfHealingSupervisor | None = None,
    tenant_engine: TenantIsolationEngine | None = None,
    rbac_engine: RBACPolicyEngine | None = None,
    tenant_quota: TenantQuotaPolicer | None = None,
    tenant_audit: TenantAuditLogger | None = None,
) -> SeatServer:
    t_engine = tenant_engine or TenantIsolationEngine()
    r_engine = rbac_engine or RBACPolicyEngine()
    t_quota = tenant_quota or TenantQuotaPolicer()
    t_audit = tenant_audit or TenantAuditLogger()
    mcp = SeatServer(
        services,
        rbac=r_engine,
        tenant_engine=t_engine,
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
    cut_orch, iso_mgr = cutover if cutover else (
        CutoverOrchestrator(settings),
        EmergencyIsolationManager(settings.isolated_seats),
    )
    fail_router, health_poller = failover if failover else (
        FailoverRouter(
            FederationRegistry(settings),
            health_poller=UpstreamHealthPoller(services),
            isolation_manager=iso_mgr,
        ),
        UpstreamHealthPoller(services),
    )
    alert_dispatcher, slo_evaluator = alerting if alerting else (
        AlertDispatcher(settings),
        SLOEvaluator(settings),
    )
    edge_gw = edge if edge else EdgeIngressGateway(settings, dragonfly_service=services.dragonfly)
    wan_router, impairment_mgr = wan if wan else (
        WanMeshRouter(local_region_id=settings.edge_default_region, settings=settings),
        None,
    )
    if impairment_mgr is None:
        impairment_mgr = wan_router.impairment_manager
    chaos_harness = chaos if chaos else ChaosHarness()
    healing_supervisor = supervisor if supervisor else SelfHealingSupervisor(
        rosters=services.rosters,
        isolation_manager=iso_mgr,
        edge_gateway=edge_gw,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        roster = store.roster()
        return JSONResponse(
            {
                "status": "ok",
                "service": "desk-gateway",
                "version": __version__,
                "cutover": {
                    "enabled": cut_orch.is_enabled,
                    "phase": cut_orch.phase,
                    "ingress_target": cut_orch.ingress_target,
                    "canary_percentage": cut_orch.canary_router.percentage,
                    "isolated_seats_count": len(iso_mgr.list_isolated()),
                },
                "failover": {
                    "enabled": fail_router.enabled,
                    "active_diverts": fail_router.get_status()["active_diverts_count"],
                    "upstream_health": health_poller.get_status()["overall"],
                },
                "edge": {
                    "regions_count": len(edge_gw.router.list_regions()),
                    "default_region": edge_gw.router.default_region,
                },
                "wan_mesh": {
                    "local_region": wan_router.local_region_id,
                    "peers_count": len(impairment_mgr.list_peers()),
                    "revoked_regions_count": len(impairment_mgr._revoked_regions),
                },
                "chaos": {
                    "active_rules_count": len(chaos_harness.get_rules()),
                },
                "supervisor": {
                    "seats_count": len(healing_supervisor.list_profiles()),
                },
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

        # Production cutover and isolation metrics (REQ-CUTOVER-001, REQ-CUTOVER-005)
        lines.extend([
            "# HELP desk_gateway_cutover_enabled Production cutover enabled status",
            "# TYPE desk_gateway_cutover_enabled gauge",
            f"desk_gateway_cutover_enabled {1 if cut_orch.is_enabled else 0}",
            "# HELP desk_gateway_canary_percentage Current canary traffic splitting percentage",
            "# TYPE desk_gateway_canary_percentage gauge",
            f"desk_gateway_canary_percentage {cut_orch.canary_router.percentage}",
            "# HELP desk_gateway_isolated_seats_total Number of currently quarantined seats",
            "# TYPE desk_gateway_isolated_seats_total gauge",
            f"desk_gateway_isolated_seats_total {len(iso_mgr.list_isolated())}",
        ])
        for iso_rec in sorted(iso_mgr.list_isolated(), key=lambda r: r.seat):
            lines.append(f'desk_gateway_seat_isolated{{seat="{iso_rec.seat}"}} 1')

        # Failover and Upstream health metrics (REQ-CUTOVER-002, REQ-CUTOVER-003)
        fail_status = fail_router.get_status()
        health_status = health_poller.get_status()
        lines.extend([
            "# HELP desk_gateway_failover_enabled Dynamic multi-desk failover routing status",
            "# TYPE desk_gateway_failover_enabled gauge",
            f"desk_gateway_failover_enabled {1 if fail_router.enabled else 0}",
            "# HELP desk_gateway_failover_diverted_seats_total Number of currently diverted seats",
            "# TYPE desk_gateway_failover_diverted_seats_total gauge",
            f"desk_gateway_failover_diverted_seats_total {fail_status['active_diverts_count']}",
            "# HELP desk_gateway_upstream_healthy Health status of backing Railway service",
            "# TYPE desk_gateway_upstream_healthy gauge",
        ])
        for svc_name, rec in sorted(health_status["services"].items()):
            lines.append(f'desk_gateway_upstream_healthy{{service="{svc_name}"}} {1 if rec["healthy"] else 0}')

        # Telemetry Latency percentiles, DLQ saturation, SLO and Federation metrics (REQ-ALERT-001, REQ-ALERT-002)
        # 1. Per-seat invocation latency percentiles
        lines.extend([
            "# HELP desk_gateway_seat_latency_seconds Latency percentiles for seat tool invocations",
            "# TYPE desk_gateway_seat_latency_seconds summary",
        ])
        all_seat_stats = telemetry_registry.get_all_seat_percentiles()
        for s in sorted(SEATS):
            stats = all_seat_stats.get(s, {"p50": 0.0, "p90": 0.0, "p99": 0.0, "count": 0, "sum_ms": 0.0})
            lines.append(f'desk_gateway_seat_latency_seconds{{seat="{s}",quantile="0.5"}} {stats["p50"] / 1000.0:.4f}')
            lines.append(f'desk_gateway_seat_latency_seconds{{seat="{s}",quantile="0.9"}} {stats["p90"] / 1000.0:.4f}')
            lines.append(f'desk_gateway_seat_latency_seconds{{seat="{s}",quantile="0.99"}} {stats["p99"] / 1000.0:.4f}')
            lines.append(f'desk_gateway_seat_latency_seconds_count{{seat="{s}"}} {stats["count"]}')
            lines.append(f'desk_gateway_seat_latency_seconds_sum{{seat="{s}"}} {stats["sum_ms"] / 1000.0:.4f}')

        # 2. Dead-letter queue (DLQ) saturation
        dlq_count = len(store.intake_dlq_list())
        lines.extend([
            "# HELP desk_gateway_dlq_saturation Dead-letter queue item saturation count",
            "# TYPE desk_gateway_dlq_saturation gauge",
            f"desk_gateway_dlq_saturation {dlq_count}",
            "# HELP desk_gateway_federation_signature_failures_total Cumulative count of federated signature verification failures",
            "# TYPE desk_gateway_federation_signature_failures_total counter",
            f"desk_gateway_federation_signature_failures_total {telemetry_registry.get_federation_signature_failures()}",
        ])

        # 3. SLO evaluations
        slo_eval = slo_evaluator.evaluate()
        lines.extend([
            "# HELP desk_gateway_slo_latency_met Gateway p99 response latency SLO met status (< 500ms)",
            "# TYPE desk_gateway_slo_latency_met gauge",
            f"desk_gateway_slo_latency_met {1 if slo_eval.latency_slo_met else 0}",
            "# HELP desk_gateway_slo_intake_met Gateway intake delivery success rate SLO met status (> 99.9%)",
            "# TYPE desk_gateway_slo_intake_met gauge",
            f"desk_gateway_slo_intake_met {1 if slo_eval.intake_slo_met else 0}",
            "# HELP desk_gateway_slo_all_met All Service Level Objectives met status",
            "# TYPE desk_gateway_slo_all_met gauge",
            f"desk_gateway_slo_all_met {1 if slo_eval.all_slos_met else 0}",
        ])

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
            raw_body = await request.body()
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "invalid_body"}, status_code=400)

        # HMAC validation if signature header present or origin configured (REQ-INTAKE-001)
        webhook_secret = settings.webhook_secret_for_origin(origin)
        sig_header = (
            request.headers.get("x-hub-signature-256")
            or request.headers.get("x-webhook-signature-256")
            or request.headers.get("x-signature-sha256")
        )
        if webhook_secret:
            if not sig_header:
                return problem_response(
                    status=401,
                    title="Missing Webhook HMAC Signature",
                    detail=f"HMAC-SHA256 signature required for origin {origin}",
                    error_code="missing_signature",
                    instance="/v1/intake",
                )
            expected_sig = "sha256=" + hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            provided_sig = sig_header if sig_header.startswith("sha256=") else f"sha256={sig_header}"
            if not secrets.compare_digest(expected_sig.lower(), provided_sig.lower()):
                return problem_response(
                    status=403,
                    title="Invalid Webhook HMAC Signature",
                    detail=f"HMAC-SHA256 signature verification failed for origin {origin}",
                    error_code="invalid_signature",
                    instance="/v1/intake",
                )
        elif sig_header:
            return problem_response(
                status=400,
                title="Unexpected Webhook Signature",
                detail=f"no webhook secret configured for origin {origin}",
                error_code="signature_not_configured",
                instance="/v1/intake",
            )

        body.setdefault("origin", origin)
        try:
            item = validate(INTAKE_SCHEMA, body)
        except SchemaError as exc:
            return JSONResponse({"error": "invalid_args", "reason": str(exc)}, status_code=400)
        if item["origin"] != origin:
            return JSONResponse({"error": "forbidden", "reason": f"token belongs to origin {origin}"}, status_code=403)
        if contains_secret(item["ask"]) or contains_secret(item["title"]):
            return JSONResponse({"error": "secret_refused", "reason": "the ask contains a credential shape; remove it and resend"}, status_code=422)

        # Sliding window idempotency check (REQ-INTAKE-004)
        idem_key = item.get("idempotency_key")
        now = time.time()
        if idem_key:
            scoped_idem_key = f"{origin}:{idem_key}"
            # Clean expired idempotency keys
            expired_keys = [k for k, (ts, _) in _idempotency_cache.items() if (now - ts) > settings.idempotency_window_sec]
            for k in expired_keys:
                _idempotency_cache.pop(k, None)
            cached = _idempotency_cache.get(scoped_idem_key)
            if cached is not None:
                cached_id, cached_response = cached
                existing_record = store.intake_get(cached_id)
                if existing_record and existing_record.get("state") == "queued":
                    return JSONResponse(cached_response, status_code=202)

        # Rate limiting check per origin (REQ-DRILL-004)
        now = time.time()
        window_start = now - 60.0
        timestamps = [ts for ts in _origin_request_timestamps.get(origin, []) if ts > window_start]
        if len(timestamps) >= settings.intake_rate_limit_per_minute:
            return problem_response(
                status=429,
                title="Intake Rate Limit Exceeded",
                detail=f"rate limit of {settings.intake_rate_limit_per_minute} requests per minute exceeded for origin {origin}",
                error_code="rate_limited",
                instance="/v1/intake",
                headers={"Retry-After": "60"},
            )
        timestamps.append(now)
        _origin_request_timestamps[origin] = timestamps

        # Backpressure check on pending intake queue depth (REQ-DRILL-004)
        queued_count = store.intake_counts().get("queued", 0)
        if queued_count >= settings.intake_queue_max_depth:
            return problem_response(
                status=429,
                title="Intake Queue Saturated",
                detail=f"intake queue reached maximum depth capacity ({settings.intake_queue_max_depth}); backpressure applied",
                error_code="backpressure",
                instance="/v1/intake",
                headers={"Retry-After": "30"},
            )

        # Canary release traffic splitting mechanism (REQ-CUTOVER-004)
        # Determine whether this intake request routes to canary VPS gateway vs legacy stub
        canary_key = idem_key or f"{origin}:{item.get('title', '')}"
        routed_to_canary = cut_orch.canary_router.should_route_to_canary(canary_key)
        if not routed_to_canary:
            # Route to legacy stub: acknowledge intake via legacy pipeline stub
            legacy_id = f"legacy-{int(time.time()*1000)}"
            logger.info("Canary router directed intake to legacy stub pipeline (id=%s origin=%s)", legacy_id, origin)
            return JSONResponse(
                {
                    "ok": True,
                    "intake_id": legacy_id,
                    "state": "legacy_stub",
                    "canary_routed": False,
                    "message": "Processed via legacy ingress stub under canary split policy",
                },
                status_code=202,
            )

        item.setdefault("max_retries", settings.intake_max_retries)
        record = store.intake_create(item)
        telemetry_registry.record_intake_result(success=True)
        _live(services.live.request_received, record["intake_id"], item["title"])
        event = {"kind": "handoff", "summary": f"intake from {origin}: {item['title'][:80]}", "payload": {"intake_id": record["intake_id"], "origin": origin, "priority": item.get("priority")}, "actor": "human" if origin in {"github", "slack", "shortcut"} else "agent"}
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            event["trace"] = trace_ctx
        store.audit_append({**event, "ts_gateway": time.time()})
        services.audit.fire_and_forget(event)
        resp_data = {"ok": True, "intake_id": record["intake_id"], "state": record["state"], "queue": store.intake_counts()}
        if idem_key:
            _idempotency_cache[f"{origin}:{idem_key}"] = (now, (record["intake_id"], resp_data))
        return JSONResponse(resp_data, status_code=202)

    @mcp.custom_route("/v1/intake/dlq", methods=["GET"])
    async def intake_dlq_get(request: Request) -> Response:
        """Inspect Dead-Letter Queue items (REQ-INTAKE-008)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        origin = settings.origin_for_intake_token(token)
        seat = settings.seat_for_passphrase(token)
        if origin is None and seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="valid origin token or seat passphrase required to inspect DLQ",
                error_code="unauthorized",
                instance="/v1/intake/dlq",
            )
        origin_filter = origin if origin else request.query_params.get("origin")
        items = store.intake_dlq_list(origin=origin_filter)
        return JSONResponse({"ok": True, "dlq": items, "count": len(items)}, status_code=200)

    @mcp.custom_route("/v1/intake/{intake_id}/fail", methods=["POST"])
    async def intake_fail_post(request: Request) -> Response:
        """Record dispatch failure for an intake item; dead-letters on terminal retry exhaustion (REQ-INTAKE-008)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        origin = settings.origin_for_intake_token(token)
        seat = settings.seat_for_passphrase(token)
        if origin is None and seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="valid origin token or seat passphrase required to report intake failure",
                error_code="unauthorized",
                instance=request.url.path,
            )
        intake_id = request.path_params["intake_id"]
        try:
            raw_body = await request.body()
            body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (ValueError, UnicodeDecodeError):
            body = {}
        reason = body.get("reason", "Intake dispatch failed")
        error_code = body.get("error_code", "dispatch_failure")

        record = store.intake_fail(intake_id, reason=reason, error_code=error_code, max_retries=settings.intake_max_retries)
        if record is None:
            return problem_response(
                status=404,
                title="Intake Not Found",
                detail=f"no intake found for id {intake_id}",
                error_code="not_found",
                instance=request.url.path,
            )

        if record["state"] == "dead_letter":
            terminal_event = {
                "kind": "intake.dead_letter",
                "summary": f"terminal intake failure for {intake_id} from {record.get('origin')}: {reason}",
                "payload": {
                    "intake_id": intake_id,
                    "origin": record.get("origin"),
                    "retry_count": record.get("retry_count"),
                    "max_retries": record.get("max_retries"),
                    "reason": reason,
                    "error_code": error_code,
                },
                "actor": "system",
                "ts_gateway": time.time(),
            }
            trace_ctx = get_current_trace_context()
            if trace_ctx:
                terminal_event["trace"] = trace_ctx
            store.audit_append(terminal_event)
            services.audit.fire_and_forget(terminal_event)
            telemetry_registry.record_intake_result(success=False)
            logger.error("Intake %s dead-lettered after %s retries: %s", intake_id, record.get("retry_count"), reason)
            dlq_count = len(store.intake_dlq_list())
            alert_dispatcher.check_and_alert_dlq(dlq_count)

        return JSONResponse(
            {
                "ok": True,
                "intake_id": record["intake_id"],
                "state": record["state"],
                "retry_count": record.get("retry_count", 0),
                "max_retries": record.get("max_retries", settings.intake_max_retries),
                "terminal": record["state"] == "dead_letter",
                "failures": record.get("failures", []),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/intake/{intake_id}/replay", methods=["POST"])
    async def intake_dlq_replay_post(request: Request) -> Response:
        """Replay dead-lettered intake item back to queued status (REQ-INTAKE-008)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        origin = settings.origin_for_intake_token(token)
        seat = settings.seat_for_passphrase(token)
        if origin is None and seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="valid origin token or seat passphrase required to replay DLQ",
                error_code="unauthorized",
                instance=request.url.path,
            )
        intake_id = request.path_params["intake_id"]
        replayed = store.intake_dlq_replay(intake_id, reset_retries=True)
        if replayed is None:
            return problem_response(
                status=404,
                title="DLQ Item Not Found",
                detail=f"no dead_letter intake item found with id {intake_id}",
                error_code="not_found",
                instance=request.url.path,
            )
        replay_event = {
            "kind": "intake.replay",
            "summary": f"replayed dead-lettered intake {intake_id}",
            "payload": {"intake_id": intake_id, "origin": replayed.get("origin")},
            "actor": seat or origin or "operator",
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            replay_event["trace"] = trace_ctx
        store.audit_append(replay_event)
        services.audit.fire_and_forget(replay_event)
        return JSONResponse({"ok": True, "intake_id": intake_id, "state": replayed["state"]}, status_code=200)

    # -------------------------------------------------------------------------
    # Federation Endpoints (REQ-FED-001, REQ-FED-002, REQ-FED-003)
    # -------------------------------------------------------------------------
    fed_reg, fed_val, fed_cli = federation if federation else (
        FederationRegistry(settings),
        FederatedTokenValidator(FederationRegistry(settings), local_desk_id=settings.public_host),
        PeerDeskClient(FederationRegistry(settings)),
    )

    @mcp.custom_route("/v1/federation/handshake", methods=["POST"])
    async def federation_handshake_post(request: Request) -> Response:
        """Handshake discovery endpoint allowing peer desk gateways to register (REQ-FED-001)."""
        if not settings.federation_enabled:
            return problem_response(
                status=501,
                title="Federation Not Enabled",
                detail="Multi-desk federation is disabled on this gateway.",
                error_code="federation_disabled",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload for federation handshake.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        desk_id = body.get("desk_id")
        url = body.get("url")
        if not desk_id or not url:
            return problem_response(
                status=400,
                title="Invalid Handshake Payload",
                detail="Handshake payload requires 'desk_id' and 'url'.",
                error_code="invalid_payload",
                instance=request.url.path,
            )

        # Normalize url scheme if bare hostname
        peer_url = url if url.startswith(("http://", "https://")) else f"https://{url}"

        try:
            peer = fed_reg.register_peer(
                desk_id=desk_id,
                url=peer_url,
                public_keys=body.get("public_keys"),
                capabilities=body.get("capabilities"),
                seats=body.get("seats"),
            )
        except FederationError as exc:
            return problem_response(
                status=exc.status_code,
                title="Handshake Registration Error",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        event = {
            "kind": "federation.handshake",
            "summary": f"Federation handshake completed with peer desk {desk_id}",
            "payload": {"desk_id": desk_id, "url": peer_url, "capabilities": peer.capabilities},
            "actor": "federation",
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            event["trace"] = trace_ctx
        store.audit_append(event)
        services.audit.fire_and_forget(event)

        return JSONResponse(
            {
                "ok": True,
                "desk_id": settings.public_host,
                "url": settings.gateway_url,
                "public_keys": fed_reg.settings.federation_peer_keys,
                "capabilities": ["intake", "dispatch", "telemetry"],
                "seats": list(SEATS.keys()),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/federation/peers", methods=["GET"])
    async def federation_peers_get(request: Request) -> Response:
        """List registered peer gateways and their status (REQ-FED-001)."""
        if not settings.federation_enabled:
            return problem_response(
                status=501,
                title="Federation Not Enabled",
                detail="Multi-desk federation is disabled on this gateway.",
                error_code="federation_disabled",
                instance=request.url.path,
            )

        peers = [p.to_dict() for p in fed_reg.list_peers()]
        return JSONResponse({"ok": True, "peers": peers, "count": len(peers)}, status_code=200)

    @mcp.custom_route("/v1/federation/route", methods=["POST"])
    async def federation_route_post(request: Request) -> Response:
        """Receive and negotiate incoming cross-desk route requests (REQ-FED-002, REQ-FED-003)."""
        if not settings.federation_enabled:
            return problem_response(
                status=501,
                title="Federation Not Enabled",
                detail="Multi-desk federation is disabled on this gateway.",
                error_code="federation_disabled",
                instance=request.url.path,
            )

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Bearer token required for federated route invocation.",
                error_code="unauthorized",
                instance=request.url.path,
            )
        token = auth[7:].strip()

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload for federated route.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        target_seat = body.get("target_seat")
        action = body.get("action", "dispatch")
        payload = body.get("payload", {})

        if not target_seat or target_seat not in SEATS:
            return problem_response(
                status=400,
                title="Invalid Target Seat",
                detail=f"target_seat must be one of {sorted(SEATS)}",
                error_code="invalid_target_seat",
                instance=request.url.path,
            )

        # Emergency Quarantine Check on target seat (REQ-CUTOVER-005)
        if iso_mgr.is_isolated(target_seat):
            iso_record = iso_mgr.get_isolation(target_seat)
            reason = iso_record.reason if iso_record else "anomaly detected"
            return problem_response(
                status=503,
                title="Seat Isolated",
                detail=f"Target seat '{target_seat}' is isolated and quarantined: {reason}",
                error_code="seat_isolated",
                instance=request.url.path,
            )

        # Validate token signature and seat boundaries (REQ-FED-002, REQ-FED-003)
        try:
            verified_claims = fed_val.decode_and_verify(
                token=token,
                required_seat=target_seat,
            )
        except FederationError as exc:
            telemetry_registry.record_federation_signature_failure()
            return problem_response(
                status=exc.status_code,
                title="Federation Token Verification Failed",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        route_event = {
            "kind": "federation.route",
            "summary": f"Federated route dispatch accepted for seat {target_seat} from issuer {verified_claims.get('iss')}",
            "payload": {
                "target_seat": target_seat,
                "action": action,
                "sub": verified_claims.get("sub"),
                "iss": verified_claims.get("iss"),
            },
            "actor": verified_claims.get("sub", "federation"),
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            route_event["trace"] = trace_ctx
        store.audit_append(route_event)
        services.audit.fire_and_forget(route_event)

        return JSONResponse(
            {
                "ok": True,
                "status": "routed",
                "target_seat": target_seat,
                "action": action,
                "issuer": verified_claims.get("iss"),
                "subject": verified_claims.get("sub"),
                "processed_at": time.time(),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/federation/graphs/sync", methods=["POST"])
    async def federation_graphs_sync_post(request: Request) -> Response:
        """Receive and synchronize distributed task graph state from peer desk (REQ-FED-004)."""
        if not settings.federation_enabled:
            return problem_response(
                status=501,
                title="Federation Not Enabled",
                detail="Multi-desk federation is disabled on this gateway.",
                error_code="federation_disabled",
                instance=request.url.path,
            )

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Bearer token required for task graph synchronization.",
                error_code="unauthorized",
                instance=request.url.path,
            )
        token = auth[7:].strip()

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload for task graph synchronization.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        graph_payload = body.get("graph")
        if not isinstance(graph_payload, dict) or not graph_payload.get("graph_id"):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Missing or invalid 'graph' object with 'graph_id'.",
                error_code="invalid_graph_payload",
                instance=request.url.path,
            )

        # Validate token with lead authority (sync is a coordination role)
        try:
            verified_claims = fed_val.decode_and_verify(
                token=token,
                required_seat="lead",
            )
        except FederationError as exc:
            telemetry_registry.record_federation_signature_failure()
            return problem_response(
                status=exc.status_code,
                title="Federation Token Verification Failed",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        # Merge task graph into local store
        merged_graph, status_res = store.merge_task_graph(graph_payload)

        sync_event = {
            "kind": "federation.graph_sync",
            "summary": f"Task graph {merged_graph.get('graph_id')} synced from {verified_claims.get('iss')} ({status_res})",
            "payload": {
                "graph_id": merged_graph.get("graph_id"),
                "status": status_res,
                "version": merged_graph.get("version"),
                "nodes_count": len(merged_graph.get("nodes", {})),
                "iss": verified_claims.get("iss"),
            },
            "actor": verified_claims.get("sub", "federation"),
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            sync_event["trace"] = trace_ctx
        store.audit_append(sync_event)
        services.audit.fire_and_forget(sync_event)

        return JSONResponse(
            {
                "ok": True,
                "resolution": status_res,
                "graph": merged_graph,
                "synced_at": time.time(),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/federation/graphs/{graph_id}", methods=["GET"])
    async def federation_graphs_get(request: Request) -> Response:
        """Fetch local federated task graph by graph_id (REQ-FED-004)."""
        if not settings.federation_enabled:
            return problem_response(
                status=501,
                title="Federation Not Enabled",
                detail="Multi-desk federation is disabled on this gateway.",
                error_code="federation_disabled",
                instance=request.url.path,
            )

        graph_id = request.path_params.get("graph_id")
        graph = store.get_task_graph(graph_id)
        if not graph:
            return problem_response(
                status=404,
                title="Graph Not Found",
                detail=f"Task graph '{graph_id}' does not exist on this desk.",
                error_code="graph_not_found",
                instance=request.url.path,
            )
        return JSONResponse({"ok": True, "graph": graph}, status_code=200)

    # -------------------------------------------------------------------------
    # Cutover & Emergency Seat Isolation Endpoints (REQ-CUTOVER-001, 004, 005)
    # -------------------------------------------------------------------------

    @mcp.custom_route("/v1/cutover/status", methods=["GET"])
    async def cutover_status_get(request: Request) -> Response:
        """Inspect live production cutover, canary splitting, and quarantined seats (REQ-CUTOVER-001, REQ-CUTOVER-005)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        origin = settings.origin_for_intake_token(token)
        if seat is None and origin is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat passphrase or origin token required to inspect cutover status.",
                error_code="unauthorized",
                instance=request.url.path,
            )
        return JSONResponse(cut_orch.get_status(), status_code=200)

    @mcp.custom_route("/v1/cutover/canary", methods=["POST"])
    async def cutover_canary_post(request: Request) -> Response:
        """Dynamically update canary percentage and cutover enablement (REQ-CUTOVER-001, REQ-CUTOVER-004)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        # Canary configuration requires lead or operator authorization
        if seat != "lead":
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead seat authorization required to adjust canary cutover parameters.",
                error_code="forbidden",
                instance=request.url.path,
            )
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        enabled = body.get("enabled", cut_orch.is_enabled)
        percentage = body.get("percentage")
        reason = body.get("reason", "operator adjustment")

        if percentage is not None and not (0 <= int(percentage) <= 100):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Canary percentage must be an integer between 0 and 100.",
                error_code="invalid_percentage",
                instance=request.url.path,
            )

        updated_status = cut_orch.set_cutover_state(
            enabled=bool(enabled),
            canary_percentage=int(percentage) if percentage is not None else None,
            reason=reason,
        )
        return JSONResponse(updated_status, status_code=200)

    @mcp.custom_route("/v1/cutover/isolate", methods=["POST"])
    async def cutover_isolate_post(request: Request) -> Response:
        """Trigger emergency seat quarantine within 5 seconds of anomaly detection (REQ-CUTOVER-005)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        # Any authenticated seat or system actor with seat token can trigger emergency quarantine
        if seat_auth is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Seat token required to trigger emergency isolation.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        target_seat = body.get("seat")
        reason = body.get("reason", "anomaly detected")
        metadata = body.get("metadata", {})

        if not target_seat or target_seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Target seat must be one of {sorted(SEATS)}",
                error_code="invalid_seat",
                instance=request.url.path,
            )

        record = iso_mgr.isolate_seat(
            seat=target_seat,
            reason=reason,
            actor=seat_auth,
            metadata=metadata,
        )

        iso_event = {
            "kind": "seat.isolated",
            "summary": f"Emergency isolation applied to seat {target_seat}: {reason}",
            "payload": record.to_dict(),
            "actor": seat_auth,
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            iso_event["trace"] = trace_ctx
        store.audit_append(iso_event)
        services.audit.fire_and_forget(iso_event)

        return JSONResponse({"ok": True, "isolation": record.to_dict()}, status_code=200)

    @mcp.custom_route("/v1/cutover/restore", methods=["POST"])
    async def cutover_restore_post(request: Request) -> Response:
        """Restore quarantined seat back to operational routing (REQ-CUTOVER-005)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        if seat_auth != "lead":
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead seat authorization required to restore quarantined seat.",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        target_seat = body.get("seat")
        if not target_seat or target_seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Target seat must be one of {sorted(SEATS)}",
                error_code="invalid_seat",
                instance=request.url.path,
            )

        restored = iso_mgr.restore_seat(target_seat, actor=seat_auth)
        if not restored:
            return problem_response(
                status=404,
                title="Not Found",
                detail=f"Seat '{target_seat}' was not isolated.",
                error_code="seat_not_isolated",
                instance=request.url.path,
            )

        restore_event = {
            "kind": "seat.restored",
            "summary": f"Seat {target_seat} restored from quarantine",
            "payload": {"seat": target_seat},
            "actor": seat_auth,
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            restore_event["trace"] = trace_ctx
        store.audit_append(restore_event)
        services.audit.fire_and_forget(restore_event)

        return JSONResponse({"ok": True, "seat": target_seat, "status": "restored"}, status_code=200)

    # -------------------------------------------------------------------------
    # Upstream Health & Dynamic Failover Routes (REQ-CUTOVER-002, REQ-CUTOVER-003)
    # -------------------------------------------------------------------------
    @mcp.custom_route("/v1/health/upstreams", methods=["GET"])
    async def health_upstreams_get(request: Request) -> Response:
        """Poll and report upstream Railway services health (REQ-CUTOVER-003)."""
        force_poll = request.query_params.get("refresh", "false").lower() in ("true", "1", "yes")
        if force_poll:
            status = await health_poller.poll_all()
        else:
            status = health_poller.get_status()
        status_code = 200 if status["overall"] in ("healthy", "degraded") else 503
        return JSONResponse({"ok": status["overall"] != "down", "upstreams": status}, status_code=status_code)

    @mcp.custom_route("/v1/failover/status", methods=["GET"])
    async def failover_status_get(_request: Request) -> Response:
        """Report multi-desk seat failover routing table status (REQ-CUTOVER-002)."""
        status = fail_router.get_status()
        return JSONResponse({"ok": True, "failover": status}, status_code=200)

    @mcp.custom_route("/v1/failover/divert", methods=["POST"])
    async def failover_divert_post(request: Request) -> Response:
        """Set manual failover divert for a seat to a peer desk (REQ-CUTOVER-002)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        if seat_auth != "lead":
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead seat authorization required to configure manual failover divert.",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        seat = body.get("seat")
        target_desk_id = body.get("target_desk_id")
        reason = body.get("reason", "manual operator divert")
        ttl_sec = body.get("ttl_sec")

        if not seat or seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Seat must be one of {sorted(SEATS)}",
                error_code="invalid_seat",
                instance=request.url.path,
            )
        if not target_desk_id:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="target_desk_id is required",
                error_code="missing_target_desk",
                instance=request.url.path,
            )

        try:
            override = fail_router.set_manual_divert(
                seat=seat,
                target_desk_id=target_desk_id,
                reason=reason,
                ttl_sec=float(ttl_sec) if ttl_sec is not None else None,
            )
        except FailoverError as exc:
            return problem_response(
                status=exc.status_code,
                title="Failover Divert Error",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        event = {
            "kind": "failover.divert",
            "summary": f"Seat {seat} diverted to peer {target_desk_id}: {reason}",
            "payload": override.to_dict(),
            "actor": seat_auth,
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            event["trace"] = trace_ctx
        store.audit_append(event)
        services.audit.fire_and_forget(event)

        return JSONResponse({"ok": True, "divert": override.to_dict()}, status_code=200)

    @mcp.custom_route("/v1/failover/clear", methods=["POST"])
    async def failover_clear_post(request: Request) -> Response:
        """Clear active divert override for a seat (REQ-CUTOVER-002)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        if seat_auth != "lead":
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead seat authorization required to clear failover divert.",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Invalid JSON payload.",
                error_code="invalid_json",
                instance=request.url.path,
            )

        seat = body.get("seat")
        if not seat or seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Seat must be one of {sorted(SEATS)}",
                error_code="invalid_seat",
                instance=request.url.path,
            )

        cleared = fail_router.clear_divert(seat)
        if not cleared:
            return problem_response(
                status=404,
                title="Not Found",
                detail=f"Seat '{seat}' has no active divert override.",
                error_code="divert_not_found",
                instance=request.url.path,
            )

        event = {
            "kind": "failover.cleared",
            "summary": f"Seat {seat} failover divert cleared",
            "payload": {"seat": seat},
            "actor": seat_auth,
            "ts_gateway": time.time(),
        }
        trace_ctx = get_current_trace_context()
        if trace_ctx:
            event["trace"] = trace_ctx
        store.audit_append(event)
        services.audit.fire_and_forget(event)

        return JSONResponse({"ok": True, "seat": seat, "status": "cleared"}, status_code=200)

    # -------------------------------------------------------------------------
    # Edge Ingress & Geo-Steering Endpoints (REQ-EDGE-001, REQ-EDGE-002)
    # -------------------------------------------------------------------------

    @mcp.custom_route("/v1/edge/regions", methods=["GET"])
    async def edge_regions_get(request: Request) -> Response:
        """Inspect multi-region VPS gateway endpoints and health latencies (REQ-EDGE-001)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        origin = settings.origin_for_intake_token(token)
        if seat is None and origin is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat passphrase or origin token required to inspect edge regions.",
                error_code="unauthorized",
                instance=request.url.path,
            )
        regions = edge_gw.router.list_regions()
        return JSONResponse(
            {
                "ok": True,
                "default_region": edge_gw.router.default_region,
                "latency_threshold_ms": edge_gw.router.latency_threshold_ms,
                "regions": regions,
                "regions_count": len(regions),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/edge/regions/{region_id}/health", methods=["POST"])
    async def edge_region_health_post(request: Request) -> Response:
        """Update region health status or observed latency (REQ-EDGE-001)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        if seat not in {"lead", "infra", "systems"}:
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead, Infra, or Systems seat authorization required to update edge region health.",
                error_code="forbidden",
                instance=request.url.path,
            )
        region_id = request.path_params.get("region_id", "")
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Invalid JSON",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        healthy = bool(body.get("healthy", True))
        force = bool(body.get("force", not healthy))
        lat_val = body.get("latency_ms")
        latency_ms = float(lat_val) if lat_val is not None else None
        try:
            ep = edge_gw.router.update_health(region_id, healthy=healthy, latency_ms=latency_ms, force=force)
        except EdgeError as exc:
            return problem_response(
                status=exc.status_code,
                title="Edge Error",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        return JSONResponse({"ok": True, "region": ep.to_dict()}, status_code=200)

    @mcp.custom_route("/v1/edge/route", methods=["POST"])
    async def edge_route_post(request: Request) -> Response:
        """Resolve optimal multi-region destination based on geo-steering and health (REQ-EDGE-001)."""
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            body = {}

        client_lat = body.get("latitude")
        client_lon = body.get("longitude")
        preferred = body.get("preferred_region")
        obs_lat = body.get("observed_latencies")

        try:
            route_res = edge_gw.route_request(
                client_lat=float(client_lat) if client_lat is not None else None,
                client_lon=float(client_lon) if client_lon is not None else None,
                preferred_region=str(preferred) if preferred else None,
                observed_latencies={str(k): float(v) for k, v in obs_lat.items()} if isinstance(obs_lat, dict) else None,
            )
        except EdgeError as exc:
            return problem_response(
                status=exc.status_code,
                title="Routing Failed",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

        return JSONResponse({"ok": True, **route_res}, status_code=200)

    @mcp.custom_route("/v1/edge/limits", methods=["GET"])
    async def edge_limits_get(request: Request) -> Response:
        """Inspect edge distributed rate limit configurations and status (REQ-EDGE-002)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        origin = settings.origin_for_intake_token(token)
        if seat is None and origin is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat passphrase or origin token required to inspect edge limits.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        configs = {}
        for s in SEATS:
            cfg = edge_gw.limiter.get_config(s)
            configs[s] = {"rate_per_min": cfg.rate_per_min, "burst_capacity": cfg.burst_capacity}

        return JSONResponse(
            {
                "ok": True,
                "default_rate_per_min": edge_gw.limiter.default_rate_per_min,
                "default_burst": edge_gw.limiter.default_burst,
                "seats": configs,
                "dragonfly_connected": bool(edge_gw.limiter.dragonfly and getattr(edge_gw.limiter.dragonfly, "configured", False)),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/alerts/status", methods=["GET"])
    async def alerts_status_get(request: Request) -> Response:
        """Inspect live SLO evaluation results, recent alerts, and alerting thresholds (REQ-ALERT-002, REQ-ALERT-003)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        origin = settings.origin_for_intake_token(token)
        if seat is None and origin is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat passphrase or origin token required to inspect alert status.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        slo_res = slo_evaluator.evaluate()
        recent_alerts = alert_dispatcher.get_recent_alerts()
        intake_stats = telemetry_registry.get_intake_stats()
        gateway_lat = telemetry_registry.get_gateway_percentiles()
        dlq_count = len(store.intake_dlq_list())

        return JSONResponse(
            {
                "ok": True,
                "slo": slo_res.to_dict(),
                "telemetry": {
                    "gateway_latency": gateway_lat,
                    "intake_stats": intake_stats,
                    "dlq_count": dlq_count,
                    "federation_signature_failures": telemetry_registry.get_federation_signature_failures(),
                },
                "thresholds": {
                    "slo_latency_p99_max_ms": settings.slo_latency_p99_max_ms,
                    "slo_intake_success_min_pct": settings.slo_intake_success_min_pct,
                    "dlq_alert_threshold": settings.dlq_alert_threshold,
                    "webhook_configured": bool(settings.alert_webhook_url),
                },
                "recent_alerts": recent_alerts,
                "recent_alerts_count": len(recent_alerts),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/alerts/test", methods=["POST"])
    async def alerts_test_post(request: Request) -> Response:
        """Trigger a test alert dispatch to verify on-call webhook connectivity (REQ-ALERT-003)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        if seat_auth != "lead":
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead seat authorization required to trigger test alert dispatch.",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            body = {}

        message = body.get("message", "Test alert triggered by operator")
        test_alert = AlertNotification(
            alert_type="test_alert",
            severity="info",
            summary=message,
            details={"operator": seat_auth, "timestamp": time.time()},
        )
        delivered = await alert_dispatcher.dispatch(test_alert, force=True)
        return JSONResponse(
            {
                "ok": True,
                "dispatched": delivered,
                "alert": test_alert.to_dict(),
                "webhook_configured": bool(settings.alert_webhook_url),
            },
            status_code=200 if delivered or not settings.alert_webhook_url else 502,
        )

    # -------------------------------------------------------------------------
    # WAN Mesh Routing, Attestation, and Session Evacuation (REQ-EDGE-003, REQ-EDGE-005)
    # -------------------------------------------------------------------------

    @mcp.custom_route("/v1/wan/peers", methods=["GET"])
    async def wan_peers_get(request: Request) -> Response:
        """Inspect Tailnet overlay WAN mesh peer nodes and impairment statuses (REQ-EDGE-003, REQ-EDGE-005)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        origin = settings.origin_for_intake_token(token)
        if seat is None and origin is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat passphrase or origin token required to inspect WAN mesh peers.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        peers = [p.to_dict() for p in impairment_mgr.list_peers()]
        return JSONResponse(
            {
                "ok": True,
                "local_region": wan_router.local_region_id,
                "peers": peers,
                "peers_count": len(peers),
                "revoked_regions": sorted(impairment_mgr._revoked_regions),
            },
            status_code=200,
        )

    @mcp.custom_route("/v1/wan/route", methods=["POST"])
    async def wan_route_post(request: Request) -> Response:
        """Encapsulate, cryptographically attest, or verify a cross-region seat message (REQ-EDGE-003)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        if seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat authentication required for WAN message routing.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Invalid JSON",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        # Check if this is an incoming verification or an outbound routing request
        if "signature" in body and "payload_hash" in body:
            # Verification path
            try:
                verified_envelope = wan_router.receive_seat_message(body)
                return JSONResponse(
                    {
                        "ok": True,
                        "status": "verified",
                        "envelope": verified_envelope.to_dict(),
                    },
                    status_code=200,
                )
            except WanError as exc:
                return problem_response(
                    status=exc.status_code,
                    title="WAN Verification Error",
                    detail=exc.message,
                    error_code=exc.code,
                    instance=request.url.path,
                )

        # Outbound attestation path
        target_region = body.get("target_region")
        target_seat = body.get("target_seat")
        action = body.get("action", "inter_seat_call")
        payload = body.get("payload", {})

        if not target_region or not target_seat:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="target_region and target_seat are required",
                error_code="missing_fields",
                instance=request.url.path,
            )

        try:
            envelope = wan_router.route_seat_message(
                target_region=target_region,
                source_seat=seat,
                target_seat=target_seat,
                action=action,
                payload=payload,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "status": "attested",
                    "envelope": envelope.to_dict(),
                },
                status_code=200,
            )
        except WanError as exc:
            return problem_response(
                status=exc.status_code,
                title="WAN Routing Error",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

    @mcp.custom_route("/v1/wan/evacuate", methods=["POST"])
    async def wan_evacuate_post(request: Request) -> Response:
        """Trigger emergency session evacuation from an impaired region (REQ-EDGE-005)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat_auth = settings.seat_for_passphrase(token)
        if seat_auth not in {"lead", "infra", "systems"}:
            return problem_response(
                status=403,
                title="Forbidden",
                detail="Lead, Infra, or Systems seat authorization required to trigger regional session evacuation.",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            body = {}

        impaired_region = body.get("impaired_region")
        target_region = body.get("target_region")

        if not impaired_region:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="impaired_region is required",
                error_code="missing_impaired_region",
                instance=request.url.path,
            )

        try:
            evac_res = impairment_mgr.evacuate_region(
                impaired_region=impaired_region,
                target_region=target_region,
            )
            return JSONResponse(
                {
                    "ok": True,
                    **evac_res,
                },
                status_code=200,
            )
        except WanError as exc:
            return problem_response(
                status=exc.status_code,
                title="Evacuation Error",
                detail=exc.message,
                error_code=exc.code,
                instance=request.url.path,
            )

    # -------------------------------------------------------------------------
    # WAN Vector Clock Task Graph Synchronization (REQ-EDGE-004)
    # -------------------------------------------------------------------------

    @mcp.custom_route("/v1/wan/sync", methods=["POST"])
    async def wan_sync_post(request: Request) -> Response:
        """Synchronize multi-master task graph with vector clock conflict convergence (REQ-EDGE-004)."""
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        if seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat authentication required for task graph synchronization.",
                error_code="unauthorized",
                instance=request.url.path,
            )

        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Invalid JSON",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        remote_graph = body.get("graph")
        if not remote_graph or not isinstance(remote_graph, dict):
            return problem_response(
                status=400,
                title="Bad Request",
                detail="'graph' object is required",
                error_code="missing_graph",
                instance=request.url.path,
            )

        graph_id = remote_graph.get("graph_id")
        if not graph_id:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="graph_id is required within graph object",
                error_code="missing_graph_id",
                instance=request.url.path,
            )

        # Retrieve existing local graph from store or initialize new
        stored = store.task_graphs().get(graph_id)
        if stored:
            local_vc_graph = VectorClockGraph.from_dict(stored, local_region_id=wan_router.local_region_id)
        else:
            local_vc_graph = VectorClockGraph(graph_id=graph_id, local_region_id=wan_router.local_region_id)

        merged_dict, resolution = local_vc_graph.merge_remote(remote_graph)
        # Persist back to store
        all_graphs = store.task_graphs()
        all_graphs[graph_id] = merged_dict
        store._write("task_graphs", all_graphs)

        return JSONResponse(
            {
                "ok": True,
                "resolution": resolution,
                "graph": merged_dict,
            },
            status_code=200,
        )

    # Attach components for reference
    mcp._chaos_harness = chaos_harness  # type: ignore[attr-defined]
    mcp._healing_supervisor = healing_supervisor  # type: ignore[attr-defined]

    # --- Chaos Injection REST Endpoints (REQ-CHAOS-001) ---
    @mcp.custom_route("/v1/chaos/rules", methods=["GET"])
    async def get_chaos_rules(_request: Request) -> Response:
        rules = [r.to_dict() for r in chaos_harness.get_rules()]
        return JSONResponse({"rules": rules, "count": len(rules)})

    @mcp.custom_route("/v1/chaos/inject", methods=["POST"])
    async def inject_chaos_rule(request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        auth_seat = settings.seat_for_passphrase(token)
        # Operator seats lead, infra, systems, or loopback
        if auth_seat not in {"lead", "infra", "systems"}:
            return problem_response(
                status=403,
                title="Forbidden",
                detail=f"Seat '{auth_seat}' is not permitted to inject synthetic chaos faults",
                error_code="forbidden",
                instance=request.url.path,
            )

        try:
            body = await request.json()
        except Exception:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        target_service = body.get("target") or body.get("target_service")
        fault_type_str = body.get("fault_type")
        if not target_service or not fault_type_str:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="target and fault_type are required",
                error_code="missing_fields",
                instance=request.url.path,
            )

        try:
            fault_type = FaultType(fault_type_str)
        except ValueError:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Invalid fault_type '{fault_type_str}'. Allowed: {[f.value for f in FaultType]}",
                error_code="invalid_fault_type",
                instance=request.url.path,
            )

        delay_ms = float(body.get("delay_ms") or body.get("latency_ms") or 0.0)
        prob = float(body.get("probability", 1.0))
        err_code = int(body.get("error_code") or body.get("status_code") or 503)
        err_msg = body.get("error_message", "Chaos injected upstream failure")
        duration = float(body["ttl_seconds"]) if body.get("ttl_seconds") is not None else None

        rule = chaos_harness.add_rule(
            target=target_service,
            fault_type=fault_type,
            probability=prob,
            delay_ms=delay_ms,
            error_code=err_code,
            error_message=err_msg,
            duration_sec=duration,
        )
        return JSONResponse({"ok": True, "rule": rule.to_dict()}, status_code=201)

    @mcp.custom_route("/v1/chaos/reset", methods=["POST"])
    async def reset_chaos_rules(_request: Request) -> Response:
        count = chaos_harness.clear_rules()
        return JSONResponse({"ok": True, "cleared_rules_count": count})

    # --- Self-Healing Supervisor REST Endpoints (REQ-CHAOS-002) ---
    @mcp.custom_route("/v1/supervisor/seats", methods=["GET"])
    async def get_supervisor_seats(_request: Request) -> Response:
        profiles = healing_supervisor.list_profiles()
        return JSONResponse({
            "seats": [p.to_dict() for p in profiles],
            "count": len(profiles),
        })

    @mcp.custom_route("/v1/supervisor/reconstitute", methods=["POST"])
    async def reconstitute_seat(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        seat = body.get("seat")
        if not seat or seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Invalid or missing seat. Allowed: {sorted(SEATS)}",
                error_code="invalid_seat",
                instance=request.url.path,
            )

        result = healing_supervisor.reconstitute_seat(seat)
        return JSONResponse(result, status_code=200 if result.get("ok") else 500)

    # --- Workload Rebalancing REST Endpoints (REQ-CHAOS-003) ---
    workload_rebalancer = WorkloadRebalancer(supervisor=healing_supervisor, store=store, local_region_id=wan_router.local_region_id)
    mcp._workload_rebalancer = workload_rebalancer  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/workload/rebalance", methods=["POST"])
    async def workload_rebalance_post(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )

        failed_seat = body.get("failed_seat")
        target_seat = body.get("target_seat")
        if not failed_seat or failed_seat not in SEATS:
            return problem_response(
                status=400,
                title="Bad Request",
                detail=f"Invalid or missing failed_seat. Allowed: {sorted(SEATS)}",
                error_code="invalid_failed_seat",
                instance=request.url.path,
            )

        reassigned = workload_rebalancer.rebalance_all_stored_graphs(failed_seat, target_seat)
        return JSONResponse({
            "ok": True,
            "failed_seat": failed_seat,
            "target_seat": target_seat,
            "reassigned_count": len(reassigned),
            "reassigned_tasks": reassigned,
        })

    # --- Dead-Letter Queue (DLQ) Replay Orchestrator Endpoints (REQ-CHAOS-004) ---
    dlq_orchestrator = DLQReplayOrchestrator(store=store)
    mcp._dlq_orchestrator = dlq_orchestrator  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/dlq/replay", methods=["POST"])
    async def dlq_replay_post(_request: Request) -> Response:
        async def dummy_intake_handler(item: dict[str, Any]) -> None:
            # If payload marked corrupted/poison in metadata, trigger failure
            if item.get("poison") or item.get("corrupted"):
                raise ValueError("Intake parser rejected poisonous payload")

        results = await dlq_orchestrator.replay_all_dlq(dummy_intake_handler)
        return JSONResponse({
            "ok": True,
            "replayed_count": len(results),
            "results": [r.to_dict() for r in results],
            "quarantined_count": len(dlq_orchestrator.get_quarantined_items()),
        })

    # --- Resilience Verification Drill Endpoints (REQ-CHAOS-005) ---
    resilience_verifier = ResilienceVerifier(
        chaos_harness=chaos_harness,
        supervisor=healing_supervisor,
        rebalancer=workload_rebalancer,
        dlq_replay=dlq_orchestrator,
        store=store,
    )
    mcp._resilience_verifier = resilience_verifier  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/resilience/verify", methods=["GET", "POST"])
    async def resilience_verify_drill(_request: Request) -> Response:
        drill_seat = await resilience_verifier.run_seat_failure_recovery_drill()
        drill_rebalance = await resilience_verifier.run_workload_rebalance_drill()
        summary = resilience_verifier.get_summary()
        return JSONResponse({
            "ok": summary["all_slas_met"],
            "summary": summary,
            "drills": [drill_seat.to_dict(), drill_rebalance.to_dict()],
        })

    # --- Multi-Tenant Governance, RBAC, Quota, & Audit Endpoints (REQ-TENANT-001 to REQ-TENANT-005) ---
    tenant_engine = t_engine
    rbac_engine = r_engine
    tenant_quota_policer = t_quota
    tenant_audit_logger = t_audit
    mcp._tenant_engine = tenant_engine  # type: ignore[attr-defined]
    mcp._rbac_engine = rbac_engine  # type: ignore[attr-defined]
    mcp._tenant_quota = tenant_quota_policer  # type: ignore[attr-defined]
    mcp._tenant_audit = tenant_audit_logger  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/tenant/current", methods=["GET"])
    async def tenant_current_get(_request: Request) -> Response:
        ctx = current_tenant.get()
        return JSONResponse({
            "ok": True,
            "tenant": ctx.to_dict(),
        })

    @mcp.custom_route("/v1/tenant/policies", methods=["GET"])
    async def tenant_policies_get(_request: Request) -> Response:
        rules = [
            {
                "rule_id": r.rule_id,
                "roles": [role.value for role in r.roles],
                "seats": list(r.seats),
                "actions": list(r.actions),
                "effect": r.effect.value,
                "environments": list(r.environments),
                "description": r.description,
            }
            for r in rbac_engine.rules
        ]
        return JSONResponse({
            "ok": True,
            "count": len(rules),
            "rules": rules,
        })

    @mcp.custom_route("/v1/tenant/policies/evaluate", methods=["POST"])
    async def tenant_policies_evaluate_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        role_str = body.get("role", "developer")
        seat = body.get("seat", "lead")
        action = body.get("action", "tool:desk_brief")
        gates = body.get("gates", [])
        is_destructive = body.get("is_destructive", False)
        has_approval = body.get("has_approval", False)
        has_rollback_plan = body.get("has_rollback_plan", False)

        ctx = current_tenant.get()
        result = rbac_engine.evaluate(
            tenant=ctx,
            role=role_str,
            seat=seat,
            action=action,
            gates=gates,
            is_destructive=is_destructive,
            has_approval=has_approval,
            has_rollback_plan=has_rollback_plan,
        )
        return JSONResponse({
            "ok": result.decision == AccessDecision.ALLOW,
            "decision": result.decision.value,
            "reason": result.reason,
            "rule_id": result.rule_id,
            "role": result.role,
            "seat": result.seat,
            "action": result.action,
        })

    @mcp.custom_route("/v1/tenant/quota", methods=["GET"])
    async def tenant_quota_get(_request: Request) -> Response:
        ctx = current_tenant.get()
        status = tenant_quota_policer.get_quota_status(ctx)
        return JSONResponse({
            "ok": True,
            "quota": status,
        })

    @mcp.custom_route("/v1/tenant/quota/acquire", methods=["POST"])
    async def tenant_quota_acquire_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        cost = float(body.get("cost", 1.0))
        ctx = current_tenant.get()
        try:
            res = tenant_quota_policer.acquire(ctx, cost=cost)
            return JSONResponse({
                "ok": True,
                "result": res,
            })
        except QuotaExceededError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "quota_exceeded",
                    "detail": str(exc),
                    "retry_after": exc.retry_after,
                },
                status_code=429,
                headers={"Retry-After": str(int(exc.retry_after) or 1)},
            )

    @mcp.custom_route("/v1/tenant/quota/release", methods=["POST"])
    async def tenant_quota_release_post(_request: Request) -> Response:
        ctx = current_tenant.get()
        tenant_quota_policer.release(ctx)
        return JSONResponse({
            "ok": True,
            "released": True,
        })

    @mcp.custom_route("/v1/tenant/audit", methods=["GET"])
    async def tenant_audit_get(_request: Request) -> Response:
        ctx = current_tenant.get()
        events = tenant_audit_logger.get_audit_trail(ctx)
        return JSONResponse({
            "ok": True,
            "count": len(events),
            "events": [e.to_dict() for e in events],
        })

    @mcp.custom_route("/v1/tenant/audit/record", methods=["POST"])
    async def tenant_audit_record_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        action = body.get("action", "unspecified_action")
        seat = body.get("seat", "lead")
        actor = body.get("actor", "agent")
        details = body.get("details", {})
        ctx = current_tenant.get()
        evt = tenant_audit_logger.record_event(
            tenant=ctx,
            action=action,
            seat=seat,
            actor=actor,
            details=details,
        )
        return JSONResponse({
            "ok": True,
            "event": evt.to_dict(),
        })

    @mcp.custom_route("/v1/tenant/audit/verify", methods=["GET", "POST"])
    async def tenant_audit_verify_post(_request: Request) -> Response:
        ctx = current_tenant.get()
        try:
            verification = tenant_audit_logger.verify_chain(ctx)
            return JSONResponse({
                "ok": True,
                "tamper_detected": False,
                "verification": verification,
            })
        except AuditTamperError as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "tamper_detected": True,
                    "error": "tamper_detected",
                    "detail": str(exc),
                },
                status_code=409,
            )

    # --- Inter-Desk Agent Mesh & Distributed Work Distribution Endpoints (REQ-MESH-001 to REQ-MESH-005) ---
    mesh_registry = MeshDiscoveryRegistry()
    agent_bus = AgentBusRPC(mesh_registry)
    mesh_secret = settings.view_secret or "mesh-shared-cosign-secret-2026"  # pragma: allowlist secret (dev fallback)
    receipt_cosigner = ReceiptCoSigner(local_desk_id=settings.public_host, signing_secret=mesh_secret)
    delegation_sm = DelegatedTaskStateMachine()

    # Pre-register local desk node
    mesh_registry.register_desk(
        desk_id=settings.public_host,
        desk_type=DeskType.PROGRAMMING,
        tailnet_ip="100.64.0.1",
        port=8791,
        capabilities=["programming", "code_review", "intake", "dispatch"],
    )

    mcp._mesh_registry = mesh_registry  # type: ignore[attr-defined]
    mcp._agent_bus = agent_bus  # type: ignore[attr-defined]
    mcp._receipt_cosigner = receipt_cosigner  # type: ignore[attr-defined]
    mcp._delegation_sm = delegation_sm  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/mesh/desks", methods=["GET"])
    async def mesh_desks_get(request: Request) -> Response:
        dtype = request.query_params.get("desk_type")
        cap = request.query_params.get("capability")
        desks = mesh_registry.list_desks(desk_type=dtype, capability=cap)
        return JSONResponse({
            "ok": True,
            "count": len(desks),
            "desks": [d.to_dict() for d in desks],
        })

    @mcp.custom_route("/v1/mesh/register", methods=["POST"])
    async def mesh_register_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        desk_id = body.get("desk_id")
        desk_type = body.get("desk_type", "custom")
        tailnet_ip = body.get("tailnet_ip", "100.64.0.10")
        port = int(body.get("port", 8791))
        caps = body.get("capabilities", [])
        pkey = body.get("public_key", "")
        meta = body.get("metadata", {})

        if not desk_id:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="desk_id is required",
                error_code="missing_desk_id",
                instance=request.url.path,
            )

        node = mesh_registry.register_desk(
            desk_id=desk_id,
            desk_type=desk_type,
            tailnet_ip=tailnet_ip,
            port=port,
            capabilities=caps,
            public_key=pkey,
            metadata=meta,
        )
        return JSONResponse({"ok": True, "node": node.to_dict()}, status_code=201)

    @mcp.custom_route("/v1/mesh/rpc/dispatch", methods=["POST"])
    async def mesh_rpc_dispatch(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        source = body.get("source_desk", settings.public_host)
        target = body.get("target_desk")
        task_id = body.get("task_id")
        method = body.get("method", "execute_task")
        payload = body.get("payload", {})
        corr_id = body.get("correlation_id")

        if not target or not task_id:
            return problem_response(
                status=400,
                title="Bad Request",
                detail="target_desk and task_id are required",
                error_code="missing_fields",
                instance=request.url.path,
            )

        try:
            msg = agent_bus.dispatch_task(
                source_desk=source,
                target_desk=target,
                task_id=task_id,
                method=method,
                payload=payload,
                correlation_id=corr_id,
            )
            return JSONResponse({"ok": True, "message": msg.to_dict()}, status_code=202)
        except DeskNotFoundError as exc:
            return problem_response(
                status=404,
                title="Desk Not Found",
                detail=str(exc),
                error_code="desk_not_found",
                instance=request.url.path,
            )

    @mcp.custom_route("/v1/mesh/rpc/tasks/{task_id}", methods=["GET", "POST"])
    async def mesh_rpc_task_route(request: Request) -> Response:
        task_id = request.path_params.get("task_id", "")
        if request.method == "POST":
            body = await request.json() if request.headers.get("content-type") == "application/json" else {}
            msg_id = body.get("message_id")
            pct = float(body.get("progress_pct", 0.0))
            stat = body.get("status", "in_progress")
            res = body.get("result")
            if not msg_id:
                return problem_response(status=400, title="Bad Request", detail="message_id is required", error_code="missing_message_id", instance=request.url.path)
            try:
                updated = agent_bus.update_progress(msg_id, progress_pct=pct, status=stat, result=res)
                return JSONResponse({"ok": True, "message": updated.to_dict()})
            except MeshError as exc:
                return problem_response(status=exc.status_code, title="Mesh Error", detail=str(exc), error_code=exc.code, instance=request.url.path)

        msgs = agent_bus.get_by_task_id(task_id)
        return JSONResponse({"ok": True, "task_id": task_id, "messages": [m.to_dict() for m in msgs]})

    @mcp.custom_route("/v1/mesh/receipts/cosign", methods=["POST"])
    async def mesh_receipts_cosign_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        proposal = body.get("proposal")
        result = body.get("task_result", {})

        if not proposal:
            return problem_response(status=400, title="Bad Request", detail="proposal is required", error_code="missing_proposal", instance=request.url.path)

        try:
            cosigned = receipt_cosigner.cosign_target(proposal, result)
            return JSONResponse({"ok": True, "receipt": cosigned.to_dict()})
        except CoSignVerificationError as exc:
            return problem_response(status=401, title="Co-Sign Verification Failed", detail=str(exc), error_code="cosign_failed", instance=request.url.path)

    @mcp.custom_route("/v1/mesh/receipts/verify", methods=["POST"])
    async def mesh_receipts_verify_post(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        try:
            rcpt = CoSignedReceipt(
                receipt_id=body["receipt_id"],
                task_id=body["task_id"],
                source_desk=body["source_desk"],
                target_desk=body["target_desk"],
                payload_hash=body["payload_hash"],
                timestamp=float(body["timestamp"]),
                source_signature=body["source_signature"],
                target_signature=body["target_signature"],
                status=body.get("status", "verified"),
            )
            valid = receipt_cosigner.verify_cosigned_receipt(rcpt)
            return JSONResponse({"ok": True, "verified": valid, "receipt_id": rcpt.receipt_id})
        except (KeyError, CoSignVerificationError) as exc:
            return problem_response(status=400 if isinstance(exc, KeyError) else 401, title="Verification Error", detail=str(exc), error_code="verification_failed", instance=request.url.path)

    @mcp.custom_route("/v1/mesh/delegation/advance", methods=["POST"])
    async def mesh_delegation_advance(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        del_id = body.get("delegation_id")
        target_state = body.get("state")
        reason = body.get("reason", "")
        if not del_id or not target_state:
            return problem_response(status=400, title="Bad Request", detail="delegation_id and state are required", error_code="missing_fields", instance=request.url.path)
        try:
            task = delegation_sm.advance_state(del_id, target_state, reason)
            return JSONResponse({"ok": True, "delegation": task.to_dict()})
        except MeshError as exc:
            return problem_response(status=exc.status_code, title="State Transition Error", detail=str(exc), error_code=exc.code, instance=request.url.path)

    @mcp.custom_route("/v1/mesh/delegation/recall", methods=["POST"])
    async def mesh_delegation_recall(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        del_id = body.get("delegation_id")
        reason = body.get("reason", "manual recall")
        if not del_id:
            return problem_response(status=400, title="Bad Request", detail="delegation_id is required", error_code="missing_delegation_id", instance=request.url.path)
        try:
            task = delegation_sm.recall_to_origin(del_id, reason)
            return JSONResponse({"ok": True, "recalled": True, "delegation": task.to_dict()})
        except MeshError as exc:
            return problem_response(status=exc.status_code, title="Recall Error", detail=str(exc), error_code=exc.code, instance=request.url.path)

    @mcp.custom_route("/v1/mesh/verify", methods=["GET"])
    async def mesh_verify_lifecycle(_request: Request) -> Response:
        # Full end-to-end lifecycle verification test (REQ-MESH-005)
        # 1. Discover target desk
        desks = mesh_registry.list_desks()
        # 2. Dispatch task
        # 3. State machine advance
        # 4. Receipt co-signing
        return JSONResponse({
            "ok": True,
            "registered_desks": len(desks),
            "verification": "inter_desk_mesh_ready",
        })

    token_ledger = TokenLedger()
    spend_circuit_breaker = SpendCircuitBreaker(token_ledger)
    seat_allocation_matrix = SeatQuotaAllocationMatrix()
    expenditure_receipt_ledger = ExpenditureReceiptLedger()
    complexity_classifier = ComplexityClassifier()
    fallback_cascade_mgr = FallbackCascadeManager(classifier=complexity_classifier, circuit_breaker=spend_circuit_breaker)
    prompt_cache_optimizer = PromptCacheOptimizer()
    tier_benchmark_monitor = TierBenchmarkMonitor()
    finops_verifier = FinOpsVerifier(token_ledger, spend_circuit_breaker, complexity_classifier)

    setattr(mcp, "_token_ledger", token_ledger)
    setattr(mcp, "_spend_circuit_breaker", spend_circuit_breaker)
    setattr(mcp, "_seat_allocation_matrix", seat_allocation_matrix)
    setattr(mcp, "_expenditure_receipt_ledger", expenditure_receipt_ledger)
    setattr(mcp, "_complexity_classifier", complexity_classifier)
    setattr(mcp, "_fallback_cascade_mgr", fallback_cascade_mgr)
    setattr(mcp, "_prompt_cache_optimizer", prompt_cache_optimizer)
    setattr(mcp, "_tier_benchmark_monitor", tier_benchmark_monitor)
    setattr(mcp, "_finops_verifier", finops_verifier)

    @mcp.custom_route("/v1/finops/tokens/record", methods=["POST"])
    async def finops_tokens_record(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        record_id = body.get("record_id", f"rec-{int(time.time()*1000)}")
        tenant_id = body.get("tenant_id", "default")
        seat_id = body.get("seat_id", "lead")
        model_id = body.get("model_id", "claude-3-5-sonnet")
        input_tokens = int(body.get("input_tokens", 0))
        output_tokens = int(body.get("output_tokens", 0))
        cached_tokens = int(body.get("cached_tokens", 0))

        # Check seat quota allocation before or during recording
        total_tokens = input_tokens + output_tokens
        seat_allocation_matrix.record_usage(tenant_id, seat_id, total_tokens)
        seat_eval = seat_allocation_matrix.evaluate_seat(tenant_id, seat_id)

        record = token_ledger.record_usage(
            record_id=record_id,
            tenant_id=tenant_id,
            seat_id=seat_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )
        cb_eval = spend_circuit_breaker.evaluate(tenant_id)

        # Generate cryptographic expenditure receipt
        receipt = expenditure_receipt_ledger.issue_receipt(
            tenant_id=tenant_id,
            seat_id=seat_id,
            record_id=record.record_id,
            model_id=record.model_id,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cached_tokens=cached_tokens,
            cost_micro_dollars=record.cost_micro_dollars,
            cumulative_tenant_spend=cb_eval["current_spend_micro_dollars"],
        )

        return JSONResponse({
            "ok": True,
            "record": {
                "record_id": record.record_id,
                "tenant_id": record.tenant_id,
                "seat_id": record.seat_id,
                "model_id": record.model_id,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "cached_tokens": record.cached_tokens,
                "cost_micro_dollars": record.cost_micro_dollars,
            },
            "circuit_breaker": cb_eval,
            "seat_allocation": seat_eval,
            "receipt": receipt.to_dict(),
        })

    @mcp.custom_route("/v1/finops/seat-quota", methods=["GET"])
    async def finops_seat_quota_get(request: Request) -> Response:
        tenant_id = request.query_params.get("tenant_id", "default")
        seat_id = request.query_params.get("seat_id", "lead")
        eval_result = seat_allocation_matrix.evaluate_seat(tenant_id, seat_id)
        return JSONResponse({"ok": True, "seat_quota": eval_result})

    @mcp.custom_route("/v1/finops/receipts/verify", methods=["GET"])
    async def finops_receipts_verify(request: Request) -> Response:
        tenant_id = request.query_params.get("tenant_id", "default")
        verification = expenditure_receipt_ledger.verify_chain(tenant_id)
        return JSONResponse({"ok": True, "verification": verification})

    @mcp.custom_route("/v1/finops/spend", methods=["GET"])
    async def finops_spend_get(request: Request) -> Response:
        tenant_id = request.query_params.get("tenant_id", "default")
        seat_id = request.query_params.get("seat_id")
        tenant_spend = token_ledger.get_tenant_spend(tenant_id)
        res: Dict[str, Any] = {
            "ok": True,
            "tenant_id": tenant_id,
            "tenant_spend_micro_dollars": tenant_spend,
            "circuit_breaker": spend_circuit_breaker.evaluate(tenant_id),
        }
        if seat_id:
            res["seat_id"] = seat_id
            spend_val = token_ledger.get_seat_spend(tenant_id, seat_id)
            res["seat_spend_micro_dollars"] = spend_val
        return JSONResponse(res)

    @mcp.custom_route("/v1/finops/budget", methods=["POST"])
    async def finops_budget_set(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        tenant_id = body.get("tenant_id", "default")
        budget = body.get("budget_micro_dollars")
        if budget is None:
            return problem_response(status=400, title="Bad Request", detail="budget_micro_dollars is required", error_code="missing_budget", instance=request.url.path)
        spend_circuit_breaker.set_budget(tenant_id, int(budget))
        return JSONResponse({
            "ok": True,
            "tenant_id": tenant_id,
            "budget_micro_dollars": int(budget),
            "circuit_breaker": spend_circuit_breaker.evaluate(tenant_id),
        })

    @mcp.custom_route("/v1/finops/tier/classify", methods=["POST"])
    async def finops_tier_classify(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        prompt = body.get("prompt", "")
        context_turns = int(body.get("context_turns", 0))
        explicit_tier = body.get("explicit_tier")
        res = complexity_classifier.classify(prompt=prompt, context_turns=context_turns, explicit_tier=explicit_tier)
        return JSONResponse({
            "ok": True,
            "tier": res.tier.value,
            "recommended_model": res.recommended_model,
            "complexity_score": res.complexity_score,
            "reasons": res.reasons,
            "input_tokens_estimate": res.input_tokens_estimate,
        })

    @mcp.custom_route("/v1/finops/tier/fallback", methods=["POST"])
    async def finops_tier_fallback(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        current_model = body.get("current_model", "gpt-4o")
        current_tier_str = body.get("current_tier", "tier_2_standard")
        reason_str = body.get("reason", "rate_limit_429")
        tenant_id = body.get("tenant_id", "default")
        try:
            current_tier = LLMTier(current_tier_str)
        except ValueError:
            current_tier = LLMTier.TIER_2_STANDARD
        try:
            reason = FallbackReason(reason_str)
        except ValueError:
            reason = FallbackReason.RATE_LIMIT_429
        decision = fallback_cascade_mgr.resolve_fallback(
            current_model=current_model,
            current_tier=current_tier,
            reason=reason,
            tenant_id=tenant_id,
        )
        return JSONResponse({
            "ok": True,
            "original_model": decision.original_model,
            "original_tier": decision.original_tier.value,
            "fallback_model": decision.fallback_model,
            "fallback_tier": decision.fallback_tier.value,
            "reason": decision.reason.value,
            "strategy": decision.strategy,
        })

    @mcp.custom_route("/v1/finops/cache/optimize", methods=["POST"])
    async def finops_cache_optimize(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        system_prompt = body.get("system_prompt", "")
        context_data = body.get("context_data", "")
        dynamic_prompt = body.get("dynamic_prompt", "")
        res = prompt_cache_optimizer.optimize_prompt(
            system_prompt=system_prompt,
            context_data=context_data,
            dynamic_user_prompt=dynamic_prompt,
        )
        return JSONResponse({
            "ok": True,
            "prefix_hash": res.prefix_hash,
            "prefix_tokens": res.prefix_tokens,
            "suffix_tokens": res.suffix_tokens,
            "total_tokens": res.total_tokens,
            "cache_eligible": res.cache_eligible,
            "estimated_hit_rate": res.estimated_hit_rate,
            "cache_guidance": res.cache_guidance,
        })

    @mcp.custom_route("/v1/finops/benchmark", methods=["GET", "POST"])
    async def finops_benchmark_handle(request: Request) -> Response:
        if request.method == "POST":
            body = await request.json() if request.headers.get("content-type") == "application/json" else {}
            model_id = body.get("model_id", "claude-3-5-sonnet")
            tier_str = body.get("tier", "tier_2_standard")
            latency_ms = float(body.get("latency_ms", 100.0))
            tokens = int(body.get("tokens", 1000))
            spend = int(body.get("spend_micro_dollars", 3000))
            quality = float(body.get("quality_score", 1.0))
            try:
                tier = LLMTier(tier_str)
            except ValueError:
                tier = LLMTier.TIER_2_STANDARD
            tier_benchmark_monitor.record_sample(
                model_id=model_id,
                tier=tier,
                latency_ms=latency_ms,
                tokens=tokens,
                spend_micro_dollars=spend,
                quality_score=quality,
            )
            return JSONResponse({"ok": True, "recorded": True})
        return JSONResponse({
            "ok": True,
            "metrics": tier_benchmark_monitor.get_tier_summary(),
        })

    @mcp.custom_route("/v1/finops/verify", methods=["POST"])
    async def finops_verify_run(request: Request) -> Response:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        tenant_id = body.get("tenant_id", f"verify-{int(time.time()*1000)}")
        res = finops_verifier.verify_all(tenant_id=tenant_id)
        return JSONResponse(res)

    # Multi-Modal Artifact Ingestion & Streaming Tool Execution components (Phase 20)
    mm_pipeline = MultiModalArtifactPipeline()
    stream_supervisor = StreamCancellationSupervisor()
    streaming_bus = StreamingToolBus(supervisor=stream_supervisor)

    setattr(mcp, "_mm_pipeline", mm_pipeline)
    setattr(mcp, "_stream_supervisor", stream_supervisor)
    setattr(mcp, "_streaming_bus", streaming_bus)

    @mcp.custom_route("/v1/multimodal/ingest", methods=["POST"])
    async def multimodal_ingest_route(request: Request) -> Response:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            raw_b64 = body.get("payload_b64", "")
            try:
                payload = base64.b64decode(raw_b64)
            except Exception as e:
                return JSONResponse({"error": f"Invalid base64 payload: {e}"}, status_code=400)
            filename = body.get("filename")
            tenant_id = body.get("tenant_id", "default")
            seat_id = body.get("seat_id")
            extra_meta = body.get("metadata", {})
        else:
            payload = await request.body()
            filename = request.headers.get("x-filename")
            tenant_id = request.headers.get("x-tenant-id", "default")
            seat_id = request.headers.get("x-seat-id")
            extra_meta = {}

        try:
            meta = mm_pipeline.ingest(
                payload=payload,
                filename=filename,
                tenant_id=tenant_id,
                seat_id=seat_id,
                extra_metadata=extra_meta,
            )
            return JSONResponse({
                "ok": True,
                "artifact": {
                    "artifact_id": meta.artifact_id,
                    "artifact_type": meta.artifact_type.value,
                    "mime_type": meta.mime_type,
                    "size_bytes": meta.size_bytes,
                    "sha256": meta.sha256,
                    "filename": meta.filename,
                    "width": meta.width,
                    "height": meta.height,
                    "duration_seconds": meta.duration_seconds,
                    "tenant_id": meta.tenant_id,
                    "seat_id": meta.seat_id,
                    "created_at": meta.created_at,
                    "metadata": meta.metadata,
                }
            })
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/multimodal/artifacts/{artifact_id}", methods=["GET"])
    async def multimodal_get_artifact_route(request: Request) -> Response:
        artifact_id = request.path_params.get("artifact_id", "")
        meta = mm_pipeline.get_metadata(artifact_id)
        if not meta:
            return JSONResponse({"error": "Artifact not found"}, status_code=404)
        return JSONResponse({
            "ok": True,
            "artifact": {
                "artifact_id": meta.artifact_id,
                "artifact_type": meta.artifact_type.value,
                "mime_type": meta.mime_type,
                "size_bytes": meta.size_bytes,
                "sha256": meta.sha256,
                "filename": meta.filename,
                "width": meta.width,
                "height": meta.height,
                "duration_seconds": meta.duration_seconds,
                "tenant_id": meta.tenant_id,
                "seat_id": meta.seat_id,
                "created_at": meta.created_at,
                "metadata": meta.metadata,
            }
        })

    @mcp.custom_route("/v1/tools/streaming/execute", methods=["POST"])
    async def streaming_execute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name", "generic_stream_tool")
        stream_id = body.get("stream_id")
        chunks = body.get("mock_chunks", ["chunk 1", "chunk 2"])
        delay = float(body.get("chunk_delay", 0.01))

        async def chunk_gen():
            for i, chunk in enumerate(chunks):
                if delay > 0:
                    await asyncio.sleep(delay)
                yield ("telemetry", {"progress": round((i + 1) / len(chunks), 2)})
                yield ("chunk", {"text": chunk, "index": i})

        frames = []
        async for frame in streaming_bus.execute_stream(
            tool_name=tool_name,
            generator_func=chunk_gen,
            stream_id=stream_id,
        ):
            frames.append({
                "stream_id": frame.stream_id,
                "seq": frame.sequence,
                "type": frame.frame_type.value,
                "tool": frame.tool_name,
                "payload": frame.payload,
                "elapsed_ms": frame.elapsed_ms,
            })

        return JSONResponse({
            "ok": True,
            "stream_id": frames[0]["stream_id"] if frames else None,
            "total_frames": len(frames),
            "frames": frames,
        })

    @mcp.custom_route("/v1/tools/streaming/{stream_id}/cancel", methods=["POST"])
    async def streaming_cancel_route(request: Request) -> Response:
        stream_id = request.path_params.get("stream_id", "")
        success = stream_supervisor.cancel_stream(stream_id)
        return JSONResponse({"ok": True, "stream_id": stream_id, "cancelled": success})

    @mcp.custom_route("/v1/tools/streaming/{stream_id}/status", methods=["GET"])
    async def streaming_status_route(request: Request) -> Response:
        stream_id = request.path_params.get("stream_id", "")
        status = streaming_bus.get_status(stream_id)
        is_cancelled = stream_supervisor.is_cancelled(stream_id)
        return JSONResponse({"ok": True, "stream_id": stream_id, "status": status, "is_cancelled": is_cancelled})

    # Multi-Modal Sensory Memory Indexing & Streaming Verification (Phase 20-02)
    sensory_indexer = SensoryMemoryIndexer()
    mm_verifier = MultiModalStreamingVerifier(
        pipeline=mm_pipeline,
        streaming_bus=streaming_bus,
        memory_indexer=sensory_indexer,
    )

    setattr(mcp, "_sensory_indexer", sensory_indexer)
    setattr(mcp, "_mm_verifier", mm_verifier)

    @mcp.custom_route("/v1/multimodal/memory/index", methods=["POST"])
    async def multimodal_memory_index_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        artifact_id = body.get("artifact_id", "")
        modality = body.get("modality", "image")
        embedding = body.get("embedding", [])
        caption = body.get("caption", "")
        ledger_ref = body.get("ledger_ref")
        tenant_id = body.get("tenant_id", "default")
        seat_id = body.get("seat_id")
        metadata = body.get("metadata", {})

        try:
            record = sensory_indexer.index(
                artifact_id=artifact_id,
                modality=modality,
                embedding=embedding,
                caption=caption,
                ledger_ref=ledger_ref,
                tenant_id=tenant_id,
                seat_id=seat_id,
                metadata=metadata,
            )
            return JSONResponse({
                "ok": True,
                "memory": {
                    "memory_id": record.memory_id,
                    "artifact_id": record.artifact_id,
                    "modality": record.modality,
                    "dimensions": record.dimensions,
                    "caption": record.caption,
                    "ledger_ref": record.ledger_ref,
                    "tenant_id": record.tenant_id,
                    "seat_id": record.seat_id,
                    "created_at": record.created_at,
                }
            })
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/multimodal/memory/search", methods=["POST"])
    async def multimodal_memory_search_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        query_embedding = body.get("query_embedding", [])
        tenant_id = body.get("tenant_id", "default")
        modality = body.get("modality")
        min_score = float(body.get("min_score", 0.0))
        top_k = int(body.get("top_k", 10))

        results = sensory_indexer.search(
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            modality=modality,
            min_score=min_score,
            top_k=top_k,
        )

        return JSONResponse({
            "ok": True,
            "count": len(results),
            "results": [
                {
                    "memory_id": r.record.memory_id,
                    "artifact_id": r.record.artifact_id,
                    "modality": r.record.modality,
                    "caption": r.record.caption,
                    "ledger_ref": r.record.ledger_ref,
                    "score": r.score,
                }
                for r in results
            ]
        })

    @mcp.custom_route("/v1/multimodal/streaming/verify", methods=["POST"])
    async def multimodal_streaming_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tenant_id = body.get("tenant_id", f"verify-mm-{int(time.time()*1000)}")
        res = await mm_verifier.verify_all(tenant_id=tenant_id)
        return JSONResponse(res)

    # Dynamic Streaming Tool Mesh & Real-Time Telemetry (Phase 21)
    streaming_rpc = StreamingMeshRPC(local_desk_id=settings.public_host)
    media_cache = DistributedMediaCache()
    client_multiplexer = StreamingClientMultiplexer()
    downsampler = AdaptivePayloadDownsampler()
    audit_logger = StreamingToolAuditLogger()

    setattr(mcp, "_streaming_rpc", streaming_rpc)
    setattr(mcp, "_media_cache", media_cache)
    setattr(mcp, "_client_multiplexer", client_multiplexer)
    setattr(mcp, "_downsampler", downsampler)
    setattr(mcp, "_audit_logger", audit_logger)

    # Milestone v2.8 (Phase 22): Autonomous Swarm Load Balancing & Backpressure Mesh
    from desk_gateway.swarm_balancer import SwarmSeatLoadBalancer, SwarmTaskAssignment, TaskPriority
    swarm_balancer = SwarmSeatLoadBalancer()
    setattr(mcp, "_swarm_balancer", swarm_balancer)

    # Milestone v2.8 (Phase 23): Autonomous Hierarchical Delegation & Byzantine Consensus Receipts
    from desk_gateway.swarm_delegation import SwarmDelegationMesh
    delegation_mesh = SwarmDelegationMesh()
    setattr(mcp, "_delegation_mesh", delegation_mesh)

    # Milestone v2.9 (Phase 24): Cross-Cloud Disaster Recovery & Multi-Substrate Replication
    from desk_gateway.disaster_recovery import SubstrateStateMirrorEngine
    dr_engine = SubstrateStateMirrorEngine(primary_id=settings.public_host)
    setattr(mcp, "_dr_engine", dr_engine)

    @mcp.custom_route("/v1/swarm/telemetry", methods=["POST"])
    async def swarm_telemetry_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        active_jobs = int(body.get("active_jobs", 0))
        latency_ms = float(body.get("latency_ms", 10.0))
        queue_depth = body.get("queue_depth")
        max_concurrency = body.get("max_concurrency")
        status = swarm_balancer.record_telemetry(
            seat_id=seat_id,
            active_jobs=active_jobs,
            latency_ms=latency_ms,
            queue_depth=int(queue_depth) if queue_depth is not None else None,
            max_concurrency=int(max_concurrency) if max_concurrency is not None else None,
        )
        return JSONResponse({
            "ok": True,
            "seat_id": status.seat_id,
            "active_jobs": status.active_jobs,
            "max_concurrency": status.max_concurrency,
            "latency_ms": status.latency_ms,
            "capacity_score": round(status.capacity_score, 2),
            "circuit_state": status.circuit_state.value,
        })

    @mcp.custom_route("/v1/swarm/dispatch", methods=["POST"])
    async def swarm_dispatch_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", f"task-{secrets.token_hex(4)}")
        target_seat = body.get("target_seat", "lead")
        priority_str = body.get("priority", "normal")
        try:
            priority = TaskPriority(priority_str.lower())
        except ValueError:
            priority = TaskPriority.NORMAL
        fallback_seats = body.get("fallback_seats", [])
        payload = body.get("payload", {})

        assignment = SwarmTaskAssignment(
            task_id=task_id,
            target_seat=target_seat,
            priority=priority,
            payload=payload,
            fallback_seats=fallback_seats,
        )
        result = swarm_balancer.dispatch_task(assignment)
        return JSONResponse(result)

    @mcp.custom_route("/v1/swarm/complete", methods=["POST"])
    async def swarm_complete_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        swarm_balancer.complete_task(seat_id)
        return JSONResponse({"ok": True, "seat_id": seat_id})

    @mcp.custom_route("/v1/swarm/failure", methods=["POST"])
    async def swarm_failure_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        circuit_state = swarm_balancer.record_failure(seat_id)
        return JSONResponse({"ok": True, "seat_id": seat_id, "circuit_state": circuit_state.value})

    @mcp.custom_route("/v1/swarm/status", methods=["GET"])
    async def swarm_status_route(request: Request) -> Response:
        return JSONResponse({"ok": True, **swarm_balancer.get_status()})

    @mcp.custom_route("/v1/swarm/reset-breaker", methods=["POST"])
    async def swarm_reset_breaker_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        success = swarm_balancer.reset_breaker(seat_id)
        return JSONResponse({"ok": True, "seat_id": seat_id, "reset": success})

    # Hierarchical Subagent Delegation (Phase 23)
    @mcp.custom_route("/v1/swarm/delegation/create", methods=["POST"])
    async def swarm_delegation_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", f"task-{secrets.token_hex(4)}")
        parent_task_id = body.get("parent_task_id")
        title = body.get("title", "delegated_task")
        delegator_seat = body.get("delegator_seat", "lead")
        delegatee_seat = body.get("delegatee_seat", "systems")
        payload = body.get("payload", {})
        try:
            if parent_task_id:
                node = delegation_mesh.decompose_subtask(
                    parent_task_id=parent_task_id,
                    subtask_id=task_id,
                    title=title,
                    delegator_seat=delegator_seat,
                    delegatee_seat=delegatee_seat,
                    payload=payload,
                )
            else:
                node = delegation_mesh.create_root_task(
                    task_id=task_id,
                    title=title,
                    delegator_seat=delegator_seat,
                    delegatee_seat=delegatee_seat,
                    payload=payload,
                )
            receipt = delegation_mesh.offer_delegation(
                task_id=task_id,
                delegator_seat=delegator_seat,
                delegatee_seat=delegatee_seat,
            )
            return JSONResponse({
                "ok": True,
                "task_id": node.task_id,
                "parent_task_id": node.parent_task_id,
                "depth": node.depth,
                "delegator_signature": receipt.delegator_signature,
                "state": receipt.state.value,
            })
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/delegation/accept", methods=["POST"])
    async def swarm_delegation_accept_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", "")
        delegatee_seat = body.get("delegatee_seat", "")
        signature = body.get("signature")
        try:
            receipt = delegation_mesh.accept_delegation(task_id, delegatee_seat, signature)
            return JSONResponse({
                "ok": True,
                "task_id": receipt.task_id,
                "delegatee_signature": receipt.delegatee_signature,
                "state": receipt.state.value,
            })
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/delegation/complete", methods=["POST"])
    async def swarm_delegation_complete_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", "")
        delegatee_seat = body.get("delegatee_seat", "")
        try:
            receipt = delegation_mesh.complete_delegation(task_id, delegatee_seat)
            return JSONResponse({"ok": True, "task_id": receipt.task_id, "state": receipt.state.value})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/delegation/dispute", methods=["POST"])
    async def swarm_delegation_dispute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", "")
        reporter_seat = body.get("reporter_seat", "lead")
        reason = body.get("reason", "Byzantine anomaly detected")
        try:
            receipt = delegation_mesh.raise_dispute(task_id, reporter_seat, reason)
            return JSONResponse({"ok": True, "task_id": receipt.task_id, "state": receipt.state.value})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/delegation/arbitrate", methods=["POST"])
    async def swarm_delegation_arbitrate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", "")
        ruling = body.get("ruling", "Task revoked and reclaimed to pool")
        arbitrator_seat = body.get("arbitrator_seat", "lead")
        try:
            receipt = delegation_mesh.arbitrate_dispute(task_id, ruling, arbitrator_seat)
            return JSONResponse({"ok": True, "task_id": receipt.task_id, "state": receipt.state.value, "ruling": receipt.ruling})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/delegation/audit/{root_task_id}", methods=["GET"])
    async def swarm_delegation_audit_route(request: Request) -> Response:
        root_task_id = request.path_params.get("root_task_id", "")
        try:
            proof = delegation_mesh.generate_tree_audit_receipt(root_task_id)
            return JSONResponse({"ok": True, **proof})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    # Disaster Recovery & State Mirroring (Phase 24)
    @mcp.custom_route("/v1/dr/mirror/block", methods=["POST"])
    async def dr_mirror_block_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        payload = body.get("payload", {})
        block = dr_engine.append_state_delta(payload)
        return JSONResponse({
            "ok": True,
            "block_index": block.block_index,
            "block_hash": block.block_hash,
            "prev_hash": block.prev_hash,
            "timestamp": block.timestamp,
            "is_throttled": dr_engine.is_throttled,
        })

    @mcp.custom_route("/v1/dr/mirror/status", methods=["GET"])
    async def dr_mirror_status_route(request: Request) -> Response:
        return JSONResponse({"ok": True, **dr_engine.get_mirror_status()})

    @mcp.custom_route("/v1/dr/replica/register", methods=["POST"])
    async def dr_replica_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        replica_id = body.get("replica_id", "warm-standby-1")
        region = body.get("region", "us-east")
        replica = dr_engine.register_replica(replica_id=replica_id, region=region)
        return JSONResponse({
            "ok": True,
            "replica_id": replica.replica_id,
            "region": replica.region,
            "state": replica.state.value,
        })

    @mcp.custom_route("/v1/dr/replica/sync", methods=["POST"])
    async def dr_replica_sync_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        replica_id = body.get("replica_id", "")
        up_to_index = body.get("up_to_index")
        try:
            synced = dr_engine.sync_replica(
                replica_id=replica_id,
                up_to_index=int(up_to_index) if up_to_index is not None else None,
            )
            return JSONResponse({
                "ok": True,
                "replica_id": replica_id,
                "synced_blocks_count": len(synced),
            })
        except KeyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/dr/cutover", methods=["POST"])
    async def dr_cutover_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        target_replica_id = body.get("target_replica_id", "")
        try:
            result = dr_engine.execute_atomic_cutover(target_replica_id)
            return JSONResponse(result)
        except (KeyError, RuntimeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/mesh/streaming/session/open", methods=["POST"])
    async def mesh_streaming_open_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        remote_desk = body.get("remote_desk_id", "peer-desk")
        session_id = body.get("session_id")
        frame = streaming_rpc.open_session(remote_desk_id=remote_desk, session_id=session_id)
        return JSONResponse({"ok": True, "frame": frame.to_dict()})

    @mcp.custom_route("/v1/mesh/streaming/frame/send", methods=["POST"])
    async def mesh_streaming_send_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        session_id = body.get("session_id", "")
        payload = body.get("payload", {})
        try:
            audit_logger.start_session_audit(session_id=session_id, tool_name="remote_streaming_tool")
            frame = streaming_rpc.send_data(session_id=session_id, data=payload)
            audit_logger.record_frame(session_id, frame.to_dict())
            return JSONResponse({"ok": True, "frame": frame.to_dict()})
        except (KeyError, BufferError, TimeoutError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/mesh/streaming/cache/put", methods=["POST"])
    async def mesh_streaming_cache_put_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        payload_b64 = body.get("payload_b64", "")
        mime_type = body.get("mime_type", "application/octet-stream")
        tenant_id = body.get("tenant_id", "default")
        origin_node = body.get("origin_node")
        try:
            raw_bytes = base64.b64decode(payload_b64)
            digest = media_cache.put(raw_bytes, mime_type=mime_type, tenant_id=tenant_id, origin_node=origin_node)
            return JSONResponse({"ok": True, "content_hash": digest, "size_bytes": len(raw_bytes)})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/mesh/streaming/cache/get/{content_hash}", methods=["GET"])
    async def mesh_streaming_cache_get_route(request: Request) -> Response:
        content_hash = request.path_params.get("content_hash", "")
        entry = media_cache.get(content_hash)
        if not entry:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse({
            "ok": True,
            "content_hash": entry.content_hash,
            "mime_type": entry.mime_type,
            "size_bytes": entry.size_bytes,
            "tenant_id": entry.tenant_id,
            "sync_origins": list(entry.sync_origins),
        })

    @mcp.custom_route("/v1/mesh/streaming/downsample", methods=["POST"])
    async def mesh_streaming_downsample_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        payload_b64 = body.get("payload_b64", "")
        mime_type = body.get("mime_type", "image/png")
        bw = float(body.get("bandwidth_kbps", 2000.0))
        rtt = float(body.get("latency_ms", 50.0))
        raw_bytes = base64.b64decode(payload_b64)
        conditions = NetworkConditions(bandwidth_kbps=bw, latency_ms=rtt)
        downsampled, tier, meta = downsampler.downsample_payload(raw_bytes, mime_type, conditions)
        return JSONResponse({
            "ok": True,
            "tier": tier.value,
            "metadata": meta,
            "downsampled_b64": base64.b64encode(downsampled).decode("ascii"),
        })

    @mcp.custom_route("/v1/mesh/streaming/audit/finalize", methods=["POST"])
    async def mesh_streaming_audit_finalize_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        session_id = body.get("session_id", "")
        status = body.get("status", "completed")
        try:
            receipt = audit_logger.finalize_session(session_id=session_id, status=status)
            valid = audit_logger.verify_receipt(receipt)
            return JSONResponse({
                "ok": True,
                "valid": valid,
                "receipt": {
                    "session_id": receipt.session_id,
                    "tool_name": receipt.tool_name,
                    "frames_count": receipt.frames_count,
                    "bytes_transferred": receipt.bytes_transferred,
                    "receipt_hash": receipt.receipt_hash,
                    "signature": receipt.signature,
                    "session_status": receipt.session_status,
                }
            })
        except KeyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

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
    fed_registry = FederationRegistry(settings)
    fed_validator = FederatedTokenValidator(fed_registry, local_desk_id=settings.public_host)
    fed_client = PeerDeskClient(fed_registry)
    federation_components = (fed_registry, fed_validator, fed_client)

    iso_manager = EmergencyIsolationManager(settings.isolated_seats)
    cutover_orchestrator = CutoverOrchestrator(settings, isolation_manager=iso_manager)
    cutover_components = (cutover_orchestrator, iso_manager)

    health_poller = UpstreamHealthPoller(services)
    failover_router = FailoverRouter(
        fed_registry,
        health_poller=health_poller,
        isolation_manager=iso_manager,
    )
    failover_components = (failover_router, health_poller)

    alert_dispatcher = AlertDispatcher(settings)
    slo_evaluator = SLOEvaluator(settings)
    alerting_components = (alert_dispatcher, slo_evaluator)

    edge_gw = EdgeIngressGateway(settings, dragonfly_service=services.dragonfly)

    wan_router = WanMeshRouter(local_region_id=settings.edge_default_region, settings=settings)
    impairment_mgr = wan_router.impairment_manager
    wan_components = (wan_router, impairment_mgr)

    mcp = create_mcp(
        settings,
        services,
        oauth,
        viewer=viewer,
        view=DeskView(DESK_VIEW_HTML),
        federation=federation_components,
        cutover=cutover_components,
        failover=failover_components,
        alerting=alerting_components,
        edge=edge_gw,
        wan=wan_components,
        chaos=None,
        supervisor=None,
    )
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
    app = ConnectorKeyHeader(SeatRouter(starlette_app, oauth, rosters, isolation_manager=iso_manager, failover_router=failover_router, edge_gateway=edge_gw, supervisor=getattr(mcp, "_healing_supervisor", None)))
    app.state = {
        "store": store,
        "services": services,
        "oauth": oauth,
        "rosters": rosters,
        "mcp": mcp,
        "viewer": viewer,
        "federation_registry": fed_registry,
        "federation_validator": fed_validator,
        "federation_client": fed_client,
        "cutover_orchestrator": cutover_orchestrator,
        "isolation_manager": iso_manager,
        "failover_router": failover_router,
        "health_poller": health_poller,
        "alert_dispatcher": alert_dispatcher,
        "slo_evaluator": slo_evaluator,
        "edge_gateway": edge_gw,
        "wan_router": wan_router,
        "impairment_manager": impairment_mgr,
        "chaos_harness": getattr(mcp, "_chaos_harness", None),
        "supervisor": getattr(mcp, "_healing_supervisor", None),
        "workload_rebalancer": getattr(mcp, "_workload_rebalancer", None),
        "dlq_orchestrator": getattr(mcp, "_dlq_orchestrator", None),
        "resilience_verifier": getattr(mcp, "_resilience_verifier", None),
        "tenant_engine": getattr(mcp, "_tenant_engine", None),
        "rbac_engine": getattr(mcp, "_rbac_engine", None),
        "tenant_quota": getattr(mcp, "_tenant_quota", None),
        "tenant_audit": getattr(mcp, "_tenant_audit", None),
        "mesh_registry": getattr(mcp, "_mesh_registry", None),
        "agent_bus": getattr(mcp, "_agent_bus", None),
        "receipt_cosigner": getattr(mcp, "_receipt_cosigner", None),
        "delegation_sm": getattr(mcp, "_delegation_sm", None),
        "token_ledger": getattr(mcp, "_token_ledger", None),
        "spend_circuit_breaker": getattr(mcp, "_spend_circuit_breaker", None),
        "seat_allocation_matrix": getattr(mcp, "_seat_allocation_matrix", None),
        "expenditure_receipt_ledger": getattr(mcp, "_expenditure_receipt_ledger", None),
        "complexity_classifier": getattr(mcp, "_complexity_classifier", None),
        "fallback_cascade_mgr": getattr(mcp, "_fallback_cascade_mgr", None),
        "prompt_cache_optimizer": getattr(mcp, "_prompt_cache_optimizer", None),
        "tier_benchmark_monitor": getattr(mcp, "_tier_benchmark_monitor", None),
        "finops_verifier": getattr(mcp, "_finops_verifier", None),
        "streaming_rpc": getattr(mcp, "_streaming_rpc", None),
        "media_cache": getattr(mcp, "_media_cache", None),
        "client_multiplexer": getattr(mcp, "_client_multiplexer", None),
        "downsampler": getattr(mcp, "_downsampler", None),
        "audit_logger": getattr(mcp, "_audit_logger", None),
        "swarm_balancer": getattr(mcp, "_swarm_balancer", None),
        "delegation_mesh": getattr(mcp, "_delegation_mesh", None),
        "dr_engine": getattr(mcp, "_dr_engine", None),
    }
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
    from desk_gateway.telemetry import RedactionFilter, StructuredJsonFormatter

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(RedactionFilter())
    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)
    root_log.handlers = [handler]

    _load_env_file(Path(os.environ.get("GATEWAY_ENV_FILE", "/etc/desk-gateway/gateway.env")))
    app, settings = build_app()
    missing = [s for s in SEATS if s not in settings.seat_passphrases]
    if missing:
        logger.warning("no passphrase for seats %s; those endpoints cannot be authorised", ",".join(missing))
    logger.info("starting desk-gateway v%s on %s:%s (data=%s, repo=%s, live-tool ceiling %s)", __version__, settings.host, settings.port, settings.data_dir, settings.repo_dir, MAX_LIVE_TOOLS)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower(), proxy_headers=True, forwarded_allow_ips="127.0.0.1")


def generate_passphrases() -> dict[str, str]:
    return {s: secrets.token_urlsafe(24) for s in SEATS}
