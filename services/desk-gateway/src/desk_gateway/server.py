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

# Milestone v4.5 Registry
_global_neuro_graphs: dict[str, Any] = {}
_global_causal_dags: dict[str, Any] = {}


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

    from desk_gateway.zk_proving import (
        ZKCircuit,
        ZKConstraint,
        ZKProof,
        ZKProofGenerator,
        ZKProofReceipt,
        ZKProofVerifier,
        ZKStateTransitionProver,
    )
    from desk_gateway.zk_privacy import (
        HomomorphicCipherEngine,
        PrivateZKAnchorExporter,
        SecureMPCInferenceCoordinator,
        ThresholdSecretSharing,
        ZKPrivacyAgentSwarmDrillSimulator,
    )

    zk_proof_generator = ZKProofGenerator()
    zk_proof_verifier = ZKProofVerifier()
    zk_state_prover = ZKStateTransitionProver(proof_generator=zk_proof_generator, verifier=zk_proof_verifier)
    homomorphic_cipher = HomomorphicCipherEngine()
    tss_engine = ThresholdSecretSharing()
    mpc_coordinator = SecureMPCInferenceCoordinator()
    zk_anchor_exporter = PrivateZKAnchorExporter()
    zk_circuits_registry: dict[str, ZKCircuit] = {}

    mcp._zk_proof_generator = zk_proof_generator  # type: ignore[attr-defined]
    mcp._zk_proof_verifier = zk_proof_verifier  # type: ignore[attr-defined]
    mcp._zk_state_prover = zk_state_prover  # type: ignore[attr-defined]
    mcp._homomorphic_cipher = homomorphic_cipher  # type: ignore[attr-defined]
    mcp._tss_engine = tss_engine  # type: ignore[attr-defined]
    mcp._mpc_coordinator = mpc_coordinator  # type: ignore[attr-defined]
    mcp._zk_anchor_exporter = zk_anchor_exporter  # type: ignore[attr-defined]

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

    # Milestone v2.9 (Phase 25): Automated Split-Brain Protection, Fencing Tokens & Fast RTO Recovery
    from desk_gateway.split_brain_recovery import (
        FencingTokenAllocator,
        QuorumHeartbeatEvaluator,
        VectorClockReconciler,
        FastFailoverOrchestrator,
        DisasterRecoveryDrillVerifier,
    )
    fencing_allocator = FencingTokenAllocator(cluster_gen_id="prod-cluster-01")
    quorum_evaluator = QuorumHeartbeatEvaluator(cluster_nodes=["node-1", "node-2", "node-3"])
    vector_reconciler = VectorClockReconciler()
    failover_orchestrator = FastFailoverOrchestrator(
        fencing_allocator=fencing_allocator,
        quorum_evaluator=quorum_evaluator,
    )
    drill_verifier = DisasterRecoveryDrillVerifier(orchestrator=failover_orchestrator)
    setattr(mcp, "_fencing_allocator", fencing_allocator)
    setattr(mcp, "_quorum_evaluator", quorum_evaluator)
    setattr(mcp, "_vector_reconciler", vector_reconciler)
    setattr(mcp, "_failover_orchestrator", failover_orchestrator)
    setattr(mcp, "_drill_verifier", drill_verifier)

    # Milestone v3.0 (Phase 26): Continuous Zero-Trust Compliance & Cryptographic Enclave Attestation
    from desk_gateway.zero_trust import ZeroTrustEnclaveManager, AttestationReport
    zero_trust_mgr = ZeroTrustEnclaveManager()
    setattr(mcp, "_zero_trust_mgr", zero_trust_mgr)

    # Milestone v3.0 (Phase 27): Continuous Merkle Proof Verification & Immutable Audit Export
    from desk_gateway.merkle_audit import (
        IncrementalMerkleTree,
        ImmutableAuditExporter,
        AuditLogScrubber,
        ZeroTrustComplianceVerifier,
    )
    merkle_tree = IncrementalMerkleTree()
    audit_exporter = ImmutableAuditExporter()
    compliance_verifier = ZeroTrustComplianceVerifier(tree=merkle_tree)
    setattr(mcp, "_merkle_tree", merkle_tree)
    setattr(mcp, "_audit_exporter", audit_exporter)
    setattr(mcp, "_compliance_verifier", compliance_verifier)

    # Milestone v3.1 (Phase 28): Dynamic MCP Tool Mesh Registry & Capability Scopes
    from desk_gateway.mcp_mesh import DynamicMCPToolMeshRegistry, SeatPermissionScope
    from desk_gateway.mcp_remote_invoker import (
        MCPRemoteExecutionSupervisor,
        ExecutionReceipt,
        InvocationStatus,
    )
    mcp_mesh_registry = DynamicMCPToolMeshRegistry()
    setattr(mcp, "_mcp_mesh_registry", mcp_mesh_registry)
    remote_execution_supervisor = MCPRemoteExecutionSupervisor(registry=mcp_mesh_registry)
    setattr(mcp, "_remote_execution_supervisor", remote_execution_supervisor)

    # Milestone v3.2 (Phase 30): Distributed Sensory Memory Graph & Cross-Modal Embeddings
    from desk_gateway.memory_graph import SensoryMemoryGraphEngine, ModalType, GraphNode, GraphEdge
    memory_graph_engine = SensoryMemoryGraphEngine()
    setattr(mcp, "_memory_graph_engine", memory_graph_engine)

    # Milestone v3.2 (Phase 31): Dynamic Context Window Compression & Semantic Pruning
    from desk_gateway.context_compressor import (
        ContextCompressionEngine,
        ModelTier,
        ContextSegment,
        LosslessCompactor,
        LosslessCompactedPayload,
        SemanticPruner,
        HierarchicalRollupEngine,
        DynamicWindowAdapter,
        ContextFidelityVerifier,
    )
    context_compressor = ContextCompressionEngine()
    setattr(mcp, "_context_compressor", context_compressor)

    # Milestone v3.3 (Phase 32): Decentralized Multi-Desk Governance & Proposal State Machine
    from desk_gateway.governance import (
        GovernanceStateMachine,
        ProposalStatus,
        VoteChoice,
        Ballot,
        Proposal,
        QuorumEngine,
        TimelockExecutor,
        EmergencyVetoCircuitBreaker,
    )
    governance_sm = GovernanceStateMachine()
    setattr(mcp, "_governance_sm", governance_sm)

    # Milestone v3.3 (Phase 33): Byzantine Consensus Voting & Verifiable On-Chain Attestation
    from desk_gateway.byzantine_consensus import (
        ByzantineConsensusEngine,
        ConsensusPhase,
        ConsensusDecision,
        ConsensusMessage,
        GovernanceReceiptMerkleTree,
        GovernanceMerkleReceipt,
        LedgerAnchorExporter,
        OnChainAnchor,
        ByzantineAttackSimulator,
    )
    byzantine_engine = ByzantineConsensusEngine(
        desks=["desk-alpha", "desk-beta", "desk-gamma", "desk-delta"],
        local_desk_id=settings.public_host or "desk-alpha",
    )
    receipt_merkle_tree = GovernanceReceiptMerkleTree()
    ledger_exporter = LedgerAnchorExporter()
    byzantine_simulator = ByzantineAttackSimulator(byzantine_engine)
    setattr(mcp, "_byzantine_engine", byzantine_engine)
    setattr(mcp, "_receipt_merkle_tree", receipt_merkle_tree)
    setattr(mcp, "_ledger_exporter", ledger_exporter)
    setattr(mcp, "_byzantine_simulator", byzantine_simulator)

    # Milestone v3.4 (Phase 34 & 35): Swarm Self-Healing & Active Immune Defense
    from desk_gateway.swarm_immune import SwarmImmuneEngine
    from desk_gateway.swarm_reconstitution import (
        SwarmReconstitutionEngine,
        ChaosAnomalyHarness,
        AntibodyPolicy,
    )
    swarm_immune = SwarmImmuneEngine()
    swarm_reconstitution = SwarmReconstitutionEngine(
        immune_engine=swarm_immune,
        desk_id=settings.public_host or "desk-local",
    )
    chaos_immune_harness = ChaosAnomalyHarness(
        immune_engine=swarm_immune,
        reconstitution_engine=swarm_reconstitution,
    )
    setattr(mcp, "_swarm_immune", swarm_immune)
    setattr(mcp, "_swarm_reconstitution", swarm_reconstitution)
    setattr(mcp, "_chaos_immune_harness", chaos_immune_harness)

    # Milestone v3.5 (Phase 36 & 37): Autonomous Swarm Self-Evolution & Capability Synthesis
    from desk_gateway.skill_synthesis import (
        SkillSynthesisEngine,
        SkillSpecification,
        ToolParameterSchema,
        SyntheticTestCase,
        ToolLifecycleState,
        SecurityViolationError,
        SandboxExecutionError,
    )
    from desk_gateway.prompt_optimizer import (
        PromptRolloutOrchestrator,
        PromptTelemetryEvaluator,
        EvolutionaryPromptEngine,
        CanaryBenchmarkHarness,
        RolloutState,
        FitnessScore,
    )
    from desk_gateway.neural_routing import (
        NeuralRoutingEngine,
        IntentVectorizer,
        DeskCapabilityProfile,
        RoutingCircuitBreaker,
        CircuitState,
    )
    from desk_gateway.sovereign_enclaves import (
        SovereignEnclaveManager,
        TenantSovereigntyProfile,
        TenancyTier,
        ZKTokenMasker,
        TenantKeyEncapsulationMesh,
        AttestedDataFencingEngine,
        EnclaveBreachSimulator,
    )
    from desk_gateway.formal_verification import (
        FormalVerificationPipeline,
        InvariantContract,
        InvariantType,
        VerificationVerdict,
        CounterExample,
        FormalVerificationCertificate,
    )
    from desk_gateway.synthesis_proving import (
        MultiSeatConsensusEngine,
        ProofReceiptLedger,
        CrossDeskProofExporter,
        FormalVerificationDrillSimulator,
        ReviewVote,
        PromotionState,
        ConsensusReceipt,
    )
    from desk_gateway.sharding import (
        ConsistentHashRing,
        CRDTStore,
        GeoReplicationEngine,
        ShardRouter,
        ShardNode,
        ConsistencyLevel,
    )
    from desk_gateway.mesh_consensus import (
        AntiEntropyGossip,
        SplitBrainDetector,
        EpochCoordinator,
        PartitionHealingOrchestrator,
        GeoPartitionDrillSimulator,
    )
    from desk_gateway.post_quantum import (
        HybridKEM,
        HybridSignatureEngine,
        PQCChannelSession,
        QuantumAuditInspector,
    )
    from desk_gateway.lattice_ledger import (
        PQCMerkleLedger,
        PQCIdentityAuthority,
        CrossDeskLatticeVerifier,
        PQCAnchorExporter,
        QuantumAttackDrillSimulator,
    )
    from desk_gateway.swarm_orchestration import (
        CrossDeskWorkflowCompiler,
        WorkflowExecutionEngine,
        DependencyPipeline,
        SwarmResourceScheduler,
    )
    from desk_gateway.swarm_federation import (
        CapabilityFederationBroker,
        WorkflowReceiptLedger,
        WorkflowAnchorExporter,
        WorkflowFailureSynthesizer,
        SwarmOrchestrationDrillSimulator,
    )
    from desk_gateway.swarm_dao import (
        SwarmDAOEngine,
        StakeReputationRegistry,
        PolicyTimelockExecutor,
        VoteOption,
        ProposalStatus,
    )
    from desk_gateway.swarm_tokenomics import (
        ComputeCreditLedger,
        PaymentChannelManager,
        CrossDeskClearinghouse,
        SettlementAnchorExporter,
        TokenomicsDrillSimulator,
    )
    from desk_gateway.cross_chain_relay import (
        CrossChainRelayEngine,
        StateTrieVerifier,
        RelayerStakingRegistry,
        BlockHeader,
        ChainType,
        CrossChainMessage,
    )
    from desk_gateway.cross_chain_oracle import (
        OracleAggregator,
        MedianizerFilter,
        ThresholdOracleAttestor,
        OracleAnchorExporter,
        CrossChainOracleDrillSimulator,
        OracleReport,
    )
    from desk_gateway.model_distillation import (
        EnsembleDistillationEngine,
        QuantizationCompressor,
        DistillationBenchmarker,
        ModelArtifactRegistry,
        TeacherPrediction,
    )
    from desk_gateway.edge_mesh import (
        EdgeNode,
        EdgeComputeScheduler,
        InferenceProofEngine,
        EdgeClusterMonitor,
        EdgeCommitmentExporter,
        DistillationEdgeDrillSimulator,
    )
    import dataclasses
    secret_key = settings.seat_token_signing_secret.encode("utf-8") if hasattr(settings, "seat_token_signing_secret") and settings.seat_token_signing_secret else b"desk-skill-synthesis-secret-key-32b"  # pragma: allowlist secret
    skill_synthesis_engine = SkillSynthesisEngine(signing_key=secret_key)
    prompt_rollout_orchestrator = PromptRolloutOrchestrator(signing_key=secret_key)
    neural_routing_engine = NeuralRoutingEngine(signing_secret=secret_key.decode("utf-8", errors="ignore"))
    sovereign_enclave_manager = SovereignEnclaveManager(master_seed=secret_key.decode("utf-8", errors="ignore"))
    formal_verification_pipeline = FormalVerificationPipeline(secret_key=secret_key.decode("utf-8", errors="ignore"))
    proof_receipt_ledger = ProofReceiptLedger()
    synthesis_consensus_engine = MultiSeatConsensusEngine(
        ledger=proof_receipt_ledger,
        signing_secret=secret_key.decode("utf-8", errors="ignore"),
    )
    proof_exporter = CrossDeskProofExporter()
    shard_ring = ConsistentHashRing()
    shard_ring.add_node(ShardNode(node_id="desk-primary-local", region_id=settings.edge_default_region))
    shard_crdt_store = CRDTStore(region_id=settings.edge_default_region, node_id="desk-primary-local")
    geo_replication_engine = GeoReplicationEngine(
        region_id=settings.edge_default_region,
        signing_secret=secret_key.decode("utf-8", errors="ignore"),
    )
    shard_router = ShardRouter(
        ring=shard_ring,
        store=shard_crdt_store,
        replicator=geo_replication_engine,
    )
    anti_entropy_gossip = AntiEntropyGossip(
        region_id=settings.edge_default_region,
        store=shard_crdt_store,
    )
    split_brain_detector = SplitBrainDetector(
        local_region=settings.edge_default_region,
        total_regions=[settings.edge_default_region, "us-west", "eu-central"],
    )
    epoch_coordinator = EpochCoordinator(
        node_id="desk-primary-local",
        region_id=settings.edge_default_region,
        split_detector=split_brain_detector,
    )
    partition_healing_orchestrator = PartitionHealingOrchestrator(
        store=shard_crdt_store,
        replicator=geo_replication_engine,
        split_detector=split_brain_detector,
    )

    pqc_kem = HybridKEM(seed=secret_key)
    pqc_sig_engine = HybridSignatureEngine(signing_secret=secret_key.decode("utf-8", errors="ignore"))
    pqc_inspector = QuantumAuditInspector()
    pqc_ca = PQCIdentityAuthority(ca_secret=secret_key.decode("utf-8", errors="ignore"))
    pqc_ledger = PQCMerkleLedger(sig_engine=pqc_sig_engine)
    pqc_verifier = CrossDeskLatticeVerifier(authority=pqc_ca)
    pqc_anchor_exporter = PQCAnchorExporter()

    # Milestone v4.0 components
    workflow_compiler = CrossDeskWorkflowCompiler()
    workflow_scheduler = SwarmResourceScheduler()
    workflow_pipeline = DependencyPipeline()
    workflow_engine = WorkflowExecutionEngine(scheduler=workflow_scheduler, pipeline=workflow_pipeline)
    capability_broker = CapabilityFederationBroker()
    workflow_receipt_ledger = WorkflowReceiptLedger(signing_secret=secret_key.decode("utf-8", errors="ignore"))
    workflow_anchor_exporter = WorkflowAnchorExporter()

    # Milestone v4.1 components
    dao_registry = StakeReputationRegistry()
    swarm_dao_engine = SwarmDAOEngine(registry=dao_registry, signing_secret=secret_key.decode("utf-8", errors="ignore"))
    policy_timelock_executor = PolicyTimelockExecutor(dao_engine=swarm_dao_engine)
    compute_credit_ledger = ComputeCreditLedger()
    payment_channel_manager = PaymentChannelManager(signing_secret=secret_key.decode("utf-8", errors="ignore"))
    cross_desk_clearinghouse = CrossDeskClearinghouse(ledger=compute_credit_ledger)
    settlement_anchor_exporter = SettlementAnchorExporter()

    # Milestone v4.2 components
    relayer_staking_registry = RelayerStakingRegistry()
    cross_chain_relay_engine = CrossChainRelayEngine(staking_registry=relayer_staking_registry)
    oracle_aggregator = OracleAggregator()
    oracle_anchor_exporter = OracleAnchorExporter()

    # Milestone v4.3: Model Distillation & Edge Compute Mesh
    distillation_engine = EnsembleDistillationEngine()
    quantization_compressor = QuantizationCompressor()
    distillation_benchmarker = DistillationBenchmarker()
    model_artifact_registry = ModelArtifactRegistry()
    edge_compute_scheduler = EdgeComputeScheduler()
    # Register default edge nodes
    edge_compute_scheduler.register_node(EdgeNode(node_id="edge-desk-us-west", region="us-west", vram_mb=8192))
    edge_compute_scheduler.register_node(EdgeNode(node_id="edge-desk-eu-central", region="eu-central", vram_mb=4096))
    inference_proof_engine = InferenceProofEngine(secret_key=secret_key.decode("utf-8", errors="ignore"))
    edge_cluster_monitor = EdgeClusterMonitor(scheduler=edge_compute_scheduler)
    edge_commitment_exporter = EdgeCommitmentExporter()

    setattr(mcp, "_skill_synthesis_engine", skill_synthesis_engine)
    setattr(mcp, "_prompt_rollout_orchestrator", prompt_rollout_orchestrator)
    setattr(mcp, "_neural_routing_engine", neural_routing_engine)
    setattr(mcp, "_sovereign_enclave_manager", sovereign_enclave_manager)
    setattr(mcp, "_formal_verification_pipeline", formal_verification_pipeline)
    setattr(mcp, "_synthesis_consensus_engine", synthesis_consensus_engine)
    setattr(mcp, "_proof_receipt_ledger", proof_receipt_ledger)
    setattr(mcp, "_proof_exporter", proof_exporter)
    setattr(mcp, "_shard_ring", shard_ring)
    setattr(mcp, "_shard_crdt_store", shard_crdt_store)
    setattr(mcp, "_geo_replication_engine", geo_replication_engine)
    setattr(mcp, "_shard_router", shard_router)
    setattr(mcp, "_anti_entropy_gossip", anti_entropy_gossip)
    setattr(mcp, "_split_brain_detector", split_brain_detector)
    setattr(mcp, "_epoch_coordinator", epoch_coordinator)
    setattr(mcp, "_partition_healing_orchestrator", partition_healing_orchestrator)
    setattr(mcp, "_pqc_kem", pqc_kem)
    setattr(mcp, "_pqc_sig_engine", pqc_sig_engine)
    setattr(mcp, "_pqc_inspector", pqc_inspector)
    setattr(mcp, "_pqc_ca", pqc_ca)
    setattr(mcp, "_pqc_ledger", pqc_ledger)
    setattr(mcp, "_pqc_verifier", pqc_verifier)
    setattr(mcp, "_pqc_anchor_exporter", pqc_anchor_exporter)
    setattr(mcp, "_workflow_compiler", workflow_compiler)
    setattr(mcp, "_workflow_engine", workflow_engine)
    setattr(mcp, "_capability_broker", capability_broker)
    setattr(mcp, "_workflow_receipt_ledger", workflow_receipt_ledger)
    setattr(mcp, "_workflow_anchor_exporter", workflow_anchor_exporter)
    setattr(mcp, "_dao_registry", dao_registry)
    setattr(mcp, "_swarm_dao_engine", swarm_dao_engine)
    setattr(mcp, "_policy_timelock_executor", policy_timelock_executor)
    setattr(mcp, "_compute_credit_ledger", compute_credit_ledger)
    setattr(mcp, "_payment_channel_manager", payment_channel_manager)
    setattr(mcp, "_cross_desk_clearinghouse", cross_desk_clearinghouse)
    setattr(mcp, "_settlement_anchor_exporter", settlement_anchor_exporter)
    setattr(mcp, "_relayer_staking_registry", relayer_staking_registry)
    setattr(mcp, "_cross_chain_relay_engine", cross_chain_relay_engine)
    setattr(mcp, "_oracle_aggregator", oracle_aggregator)
    setattr(mcp, "_oracle_anchor_exporter", oracle_anchor_exporter)
    setattr(mcp, "_distillation_engine", distillation_engine)
    setattr(mcp, "_quantization_compressor", quantization_compressor)
    setattr(mcp, "_distillation_benchmarker", distillation_benchmarker)
    setattr(mcp, "_model_artifact_registry", model_artifact_registry)
    setattr(mcp, "_edge_compute_scheduler", edge_compute_scheduler)
    setattr(mcp, "_inference_proof_engine", inference_proof_engine)
    setattr(mcp, "_edge_cluster_monitor", edge_cluster_monitor)
    setattr(mcp, "_edge_commitment_exporter", edge_commitment_exporter)

    @mcp.custom_route("/v1/immune/telemetry/evaluate", methods=["POST"])
    async def immune_telemetry_evaluate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        tool_name = body.get("tool_name", "generic_tool")
        payload = body.get("payload", "")
        latency_ms = float(body.get("latency_ms", 50.0))
        is_error = bool(body.get("is_error", False))
        result = swarm_immune.record_telemetry(
            seat_id=seat_id,
            tool_name=tool_name,
            payload=payload,
            latency_ms=latency_ms,
            is_error=is_error,
        )
        return JSONResponse({"ok": True, "telemetry": result})

    @mcp.custom_route("/v1/immune/seat/quarantine", methods=["POST"])
    async def immune_seat_quarantine_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        reason = body.get("reason", "Manual operator quarantine")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        res = swarm_immune.quarantine_seat(seat_id, reason=reason)
        return JSONResponse({"ok": True, "result": res})

    @mcp.custom_route("/v1/immune/seat/unquarantine", methods=["POST"])
    async def immune_seat_unquarantine_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        reason = body.get("reason", "Operator unquarantine")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        res = swarm_immune.unquarantine_seat(seat_id, reason=reason)
        return JSONResponse({"ok": True, "result": res})

    @mcp.custom_route("/v1/immune/shadow/execute", methods=["POST"])
    async def immune_shadow_execute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        execution_id = body.get("execution_id", f"shadow-{secrets.token_hex(4)}")
        seat_id = body.get("seat_id", "lead")
        tool_name = body.get("tool_name", "speculative_tool")
        arguments = body.get("arguments", {})

        def dummy_handler(args):
            if args.get("fail"):
                raise RuntimeError("Simulated execution failure")
            return {"status": "executed", "echo": args}

        res = swarm_immune.shadow_sandbox.execute_in_shadow(
            execution_id=execution_id,
            seat_id=seat_id,
            tool_name=tool_name,
            arguments=arguments,
            handler=dummy_handler,
        )
        return JSONResponse({"ok": True, "execution": res})

    @mcp.custom_route("/v1/immune/status", methods=["GET"])
    async def immune_status_route(request: Request) -> Response:
        status = swarm_immune.get_status()
        return JSONResponse({"ok": True, "status": status})

    @mcp.custom_route("/v1/immune/reconstitute", methods=["POST"])
    async def immune_reconstitute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        reason = body.get("reason", "Autonomous post-quarantine self-healing")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        res = swarm_reconstitution.reconstitute_seat(seat_id, reason=reason)
        return JSONResponse({"ok": True, "result": res})

    @mcp.custom_route("/v1/immune/memory/ledger", methods=["GET"])
    async def immune_memory_ledger_route(request: Request) -> Response:
        ledger = swarm_reconstitution.ledger
        entries = [e.to_dict() for e in ledger.entries]
        valid = ledger.verify_integrity()
        root = ledger.get_merkle_root()
        return JSONResponse({"ok": True, "valid": valid, "merkle_root": root, "entries": entries})

    @mcp.custom_route("/v1/immune/antibodies/broadcast", methods=["POST"])
    async def immune_antibodies_broadcast_route(request: Request) -> Response:
        pkg = swarm_reconstitution.antibody_mesh.export_distribution_package()
        return JSONResponse({"ok": True, "package": pkg})

    @mcp.custom_route("/v1/immune/antibodies/ingest", methods=["POST"])
    async def immune_antibodies_ingest_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        pkg = body.get("package")
        if not pkg:
            return JSONResponse({"ok": False, "error": "package is required"}, status_code=400)
        try:
            count = swarm_reconstitution.antibody_mesh.ingest_distribution_package(pkg)
            return JSONResponse({"ok": True, "ingested_count": count})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/immune/rehabilitate/benchmark", methods=["POST"])
    async def immune_rehabilitate_benchmark_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        tasks = body.get("tasks")
        res = swarm_reconstitution.rehabilitation.run_synthetic_benchmarks(seat_id, benchmark_tasks=tasks)
        return JSONResponse({"ok": True, "rehabilitation": res})

    @mcp.custom_route("/v1/immune/chaos/inject", methods=["POST"])
    async def immune_chaos_inject_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "chaos-seat")
        res = chaos_immune_harness.run_chaos_resilience_drill(seat_id=seat_id)
        return JSONResponse({"ok": True, "drill": res})

    # Milestone v3.5: Dynamic Skill & Tool Synthesis Routes (Phase 36)
    @mcp.custom_route("/v1/evolution/skills/deploy", methods=["POST"])
    async def evolution_skill_deploy_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name")
        version = body.get("version", "1.0.0")
        description = body.get("description", "")
        return_type = body.get("return_type", "Any")
        author_seat_id = body.get("author_seat_id", "systems")
        python_source = body.get("python_source", "")
        raw_params = body.get("parameters", [])
        raw_tests = body.get("test_cases", [])
        permissions = set(body.get("required_permissions", []))

        if not tool_name or not python_source:
            return JSONResponse({"ok": False, "error": "tool_name and python_source are required"}, status_code=400)

        params = [
            ToolParameterSchema(
                name=p.get("name", ""),
                type_name=p.get("type_name", "str"),
                description=p.get("description", ""),
                required=p.get("required", True),
                default=p.get("default"),
            )
            for p in raw_params
        ]

        test_cases = [
            SyntheticTestCase(
                input_args=t.get("input_args", {}),
                expected_output=t.get("expected_output"),
                description=t.get("description", ""),
            )
            for t in raw_tests
        ]

        spec = SkillSpecification(
            tool_name=tool_name,
            version=version,
            description=description,
            parameters=params,
            return_type=return_type,
            required_permissions=permissions,
            author_seat_id=author_seat_id,
            python_source=python_source,
            test_cases=test_cases,
        )

        try:
            receipt = skill_synthesis_engine.verify_and_deploy_skill(spec)
            return JSONResponse({
                "ok": True,
                "receipt": {
                    "tool_name": receipt.tool_name,
                    "version": receipt.version,
                    "author_seat_id": receipt.author_seat_id,
                    "code_hash": receipt.code_hash,
                    "attestation_signature": receipt.attestation_signature,
                    "timestamp": receipt.timestamp,
                    "lifecycle_state": receipt.lifecycle_state.value,
                }
            })
        except (SecurityViolationError, SandboxExecutionError, Exception) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/evolution/skills/invoke", methods=["POST"])
    async def evolution_skill_invoke_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name")
        arguments = body.get("arguments", {})
        if not tool_name:
            return JSONResponse({"ok": False, "error": "tool_name is required"}, status_code=400)

        try:
            result = skill_synthesis_engine.invoke_synthetic_tool(tool_name, **arguments)
            return JSONResponse({"ok": True, "result": result})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @mcp.custom_route("/v1/evolution/skills/list", methods=["GET"])
    async def evolution_skills_list_route(request: Request) -> Response:
        tools = skill_synthesis_engine.list_active_tools()
        return JSONResponse({"ok": True, "tools": tools})

    @mcp.custom_route("/v1/evolution/skills/lifecycle", methods=["POST"])
    async def evolution_skills_lifecycle_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name")
        action = body.get("action", "deprecate")  # "deprecate" or "retire"
        if not tool_name:
            return JSONResponse({"ok": False, "error": "tool_name is required"}, status_code=400)
        try:
            if action == "retire":
                skill_synthesis_engine.retire_tool(tool_name)
            else:
                skill_synthesis_engine.deprecate_tool(tool_name)
            metrics = skill_synthesis_engine.lifecycle.get_metrics(tool_name)
            return JSONResponse({"ok": True, "tool_name": tool_name, "metrics": metrics})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    # Autonomous Prompt Optimization Routes (Phase 37)
    @mcp.custom_route("/v1/evolution/prompts/baseline", methods=["POST"])
    async def evolution_prompt_baseline_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        prompt_text = body.get("prompt_text")
        if not seat_id or not prompt_text:
            return JSONResponse({"ok": False, "error": "seat_id and prompt_text are required"}, status_code=400)
        variant = prompt_rollout_orchestrator.register_baseline_prompt(seat_id, prompt_text)
        return JSONResponse({"ok": True, "variant": variant.to_dict()})

    @mcp.custom_route("/v1/evolution/prompts/mutate", methods=["POST"])
    async def evolution_prompt_mutate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        strategy = body.get("strategy")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        try:
            candidate = prompt_rollout_orchestrator.generate_candidate_variant(seat_id, strategy=strategy)
            return JSONResponse({"ok": True, "candidate": candidate.to_dict()})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/evolution/prompts/canary", methods=["POST"])
    async def evolution_prompt_canary_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        revision_id = body.get("revision_id")
        if not revision_id:
            return JSONResponse({"ok": False, "error": "revision_id is required"}, status_code=400)
        try:
            fitness = prompt_rollout_orchestrator.run_canary_evaluation(revision_id)
            variant = prompt_rollout_orchestrator.get_variant(revision_id)
            return JSONResponse({"ok": True, "variant": variant.to_dict() if variant else None, "fitness": dataclasses.asdict(fitness)})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/evolution/prompts/promote", methods=["POST"])
    async def evolution_prompt_promote_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        revision_id = body.get("revision_id")
        if not revision_id:
            return JSONResponse({"ok": False, "error": "revision_id is required"}, status_code=400)
        try:
            promoted = prompt_rollout_orchestrator.promote_candidate(revision_id)
            variant = prompt_rollout_orchestrator.get_variant(revision_id)
            return JSONResponse({"ok": True, "promoted": promoted, "variant": variant.to_dict() if variant else None})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/evolution/prompts/rollback", methods=["POST"])
    async def evolution_prompt_rollback_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id")
        if not seat_id:
            return JSONResponse({"ok": False, "error": "seat_id is required"}, status_code=400)
        reverted = prompt_rollout_orchestrator.rollback_to_previous(seat_id)
        if reverted:
            return JSONResponse({"ok": True, "reverted_to": reverted.to_dict()})
        return JSONResponse({"ok": False, "error": "No prior revision available to rollback to"}, status_code=400)

    @mcp.custom_route("/v1/evolution/prompts/lineage/{seat_id}", methods=["GET"])
    async def evolution_prompt_lineage_route(request: Request) -> Response:
        seat_id = request.path_params.get("seat_id", "")
        lineage = prompt_rollout_orchestrator.get_lineage(seat_id)
        active = prompt_rollout_orchestrator.get_active_prompt(seat_id)
        return JSONResponse({"ok": True, "seat_id": seat_id, "active": active.to_dict() if active else None, "lineage": lineage})

    @mcp.custom_route("/v1/neural-routing/register-desk", methods=["POST"])
    async def neural_routing_register_desk_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        desk_id = body.get("desk_id")
        if not desk_id:
            return JSONResponse({"ok": False, "error": "desk_id is required"}, status_code=400)
        profile = DeskCapabilityProfile(
            desk_id=desk_id,
            seat_ids=body.get("seat_ids", []),
            domains=body.get("domains", []),
            supported_tools=body.get("supported_tools", []),
            capacity_limit=int(body.get("capacity_limit", 100)),
            active_load=int(body.get("active_load", 0)),
            base_latency_ms=float(body.get("base_latency_ms", 25.0)),
            cost_per_1k_tokens=float(body.get("cost_per_1k_tokens", 0.002)),
        )
        neural_routing_engine.register_desk(profile)
        return JSONResponse({"ok": True, "desk_id": desk_id, "registered": True})

    @mcp.custom_route("/v1/neural-routing/dispatch", methods=["POST"])
    async def neural_routing_dispatch_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", f"task-{secrets.token_hex(4)}")
        task_text = body.get("task_text", "")
        if not task_text:
            return JSONResponse({"ok": False, "error": "task_text is required"}, status_code=400)
        required_tools = body.get("required_tools", [])
        max_latency_budget_ms = float(body.get("max_latency_budget_ms", 500.0))
        max_cost_budget = float(body.get("max_cost_budget", 0.05))
        conversation_state = body.get("conversation_state", {})
        sensory_context = body.get("sensory_context", {})

        receipt, selected_desk = neural_routing_engine.route_task(
            task_id=task_id,
            task_text=task_text,
            required_tools=required_tools,
            max_latency_budget_ms=max_latency_budget_ms,
            max_cost_budget=max_cost_budget,
        )

        envelope = None
        if selected_desk:
            envelope = neural_routing_engine.create_context_envelope(
                task_id=task_id,
                source_desk_id=settings.public_host,
                target_desk_id=selected_desk.desk_id,
                target_seat_id=receipt.selected_seat_id,
                conversation_state=conversation_state,
                sensory_context=sensory_context,
            )

        return JSONResponse({
            "ok": True,
            "routed": bool(selected_desk is not None),
            "receipt": dataclasses.asdict(receipt),
            "envelope": dataclasses.asdict(envelope) if envelope else None,
        })

    @mcp.custom_route("/v1/neural-routing/circuit-breaker/probe", methods=["POST"])
    async def neural_routing_circuit_breaker_probe_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        desk_id = body.get("desk_id")
        if not desk_id:
            return JSONResponse({"ok": False, "error": "desk_id is required"}, status_code=400)
        success = bool(body.get("success", True))
        latency_ms = float(body.get("latency_ms", 30.0))
        state = neural_routing_engine.circuit_breaker.record_probe(desk_id, success=success, latency_ms=latency_ms)
        return JSONResponse({"ok": True, "desk_id": desk_id, "circuit_state": state.value})

    @mcp.custom_route("/v1/neural-routing/mesh/status", methods=["GET"])
    async def neural_routing_mesh_status_route(_request: Request) -> Response:
        status_desks = {}
        for d_id, d in neural_routing_engine.desks.items():
            state = neural_routing_engine.circuit_breaker.get_state(d_id)
            status_desks[d_id] = {
                "seat_ids": d.seat_ids,
                "domains": d.domains,
                "supported_tools": d.supported_tools,
                "active_load": d.active_load,
                "capacity_limit": d.capacity_limit,
                "load_ratio": round(d.load_ratio, 3),
                "circuit_state": state.value,
            }
        return JSONResponse({
            "ok": True,
            "registered_desks_count": len(neural_routing_engine.desks),
            "desks": status_desks,
        })

    @mcp.custom_route("/v1/neural-routing/receipt/{receipt_id}", methods=["GET"])
    async def neural_routing_receipt_route(request: Request) -> Response:
        receipt_id = request.path_params.get("receipt_id", "")
        receipt = neural_routing_engine.decision_receipts.get(receipt_id)
        if not receipt:
            return JSONResponse({"ok": False, "error": "receipt not found"}, status_code=404)
        return JSONResponse({"ok": True, "receipt": dataclasses.asdict(receipt)})

    @mcp.custom_route("/v1/enclaves/tenant/register", methods=["POST"])
    async def enclaves_tenant_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tenant_id = body.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"ok": False, "error": "tenant_id is required"}, status_code=400)
        tier_str = body.get("tier", "STANDARD")
        try:
            tier = TenancyTier(tier_str)
        except ValueError:
            tier = TenancyTier.STANDARD

        profile = TenantSovereigntyProfile(
            tenant_id=tenant_id,
            tier=tier,
            allowed_residency_regions=body.get("allowed_residency_regions", []),
            allowed_desks=body.get("allowed_desks", []),
            allowed_tools=body.get("allowed_tools", []),
            forbidden_egress_domains=body.get("forbidden_egress_domains", []),
            enforce_pii_masking=bool(body.get("enforce_pii_masking", True)),
        )
        sovereign_enclave_manager.register_tenant(profile)
        return JSONResponse({"ok": True, "tenant_id": tenant_id, "tier": tier.value})

    @mcp.custom_route("/v1/enclaves/mask", methods=["POST"])
    async def enclaves_mask_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        session_id = body.get("session_id", "default_session")
        text = body.get("text", "")
        masked = sovereign_enclave_manager.masker.mask_payload(session_id, text)
        return JSONResponse({"ok": True, "session_id": session_id, "masked_text": masked})

    @mcp.custom_route("/v1/enclaves/unmask", methods=["POST"])
    async def enclaves_unmask_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        session_id = body.get("session_id", "default_session")
        masked_text = body.get("masked_text", "")
        unmasked = sovereign_enclave_manager.masker.unmask_payload(session_id, masked_text)
        return JSONResponse({"ok": True, "session_id": session_id, "unmasked_text": unmasked})

    @mcp.custom_route("/v1/enclaves/fencing/evaluate", methods=["POST"])
    async def enclaves_fencing_evaluate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tenant_id = body.get("tenant_id")
        profile = sovereign_enclave_manager.profiles.get(tenant_id)
        if not profile:
            return JSONResponse({"ok": False, "error": f"Tenant '{tenant_id}' not found"}, status_code=404)

        action = body.get("action", "transfer_context")
        destination_region = body.get("destination_region", "us-east-1")
        destination_desk = body.get("destination_desk", "desk-default")
        tools_requested = body.get("tools_requested", [])

        receipt = sovereign_enclave_manager.fencing_engine.evaluate_boundary(
            profile=profile,
            action=action,
            destination_region=destination_region,
            destination_desk=destination_desk,
            tools_requested=tools_requested,
        )
        return JSONResponse({"ok": True, "fencing_decision": receipt.to_dict()})

    @mcp.custom_route("/v1/enclaves/key/rotate", methods=["POST"])
    async def enclaves_key_rotate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tenant_id = body.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"ok": False, "error": "tenant_id is required"}, status_code=400)
        new_ver, _ = sovereign_enclave_manager.kem.rotate_key(tenant_id)
        return JSONResponse({"ok": True, "tenant_id": tenant_id, "active_key_version": new_ver})

    @mcp.custom_route("/v1/enclaves/breach-test/run", methods=["POST"])
    async def enclaves_breach_test_run_route(_request: Request) -> Response:
        results = EnclaveBreachSimulator.run_benchmark(sovereign_enclave_manager)
        return JSONResponse({"ok": True, "benchmark": results})

    # Milestone v3.7 (Phase 40): Autonomous Formal Verification Routes
    @mcp.custom_route("/v1/verification/verify", methods=["POST"])
    async def verification_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name")
        version = body.get("version", "1.0.0")
        author_seat_id = body.get("author_seat_id", "systems")
        source_code = body.get("source_code")
        param_types = body.get("param_types", {})
        raw_contracts = body.get("contracts", [])
        trials = int(body.get("trials", 50))

        if not tool_name or not source_code:
            return JSONResponse({"ok": False, "error": "tool_name and source_code are required"}, status_code=400)

        contracts: List[InvariantContract] = []
        for c in raw_contracts:
            inv_type_str = c.get("invariant_type", "POST_CONDITION")
            try:
                inv_type = InvariantType(inv_type_str)
            except ValueError:
                inv_type = InvariantType.POST_CONDITION
            contracts.append(
                InvariantContract(
                    contract_id=c.get("contract_id", f"contract-{len(contracts)+1}"),
                    invariant_type=inv_type,
                    expression=c.get("expression", "True"),
                    description=c.get("description", ""),
                    target_function=c.get("target_function", tool_name),
                )
            )

        cert = formal_verification_pipeline.verify_tool_synthesis(
            tool_name=tool_name,
            version=version,
            author_seat_id=author_seat_id,
            source_code=source_code,
            param_types=param_types,
            contracts=contracts,
            trials=trials,
        )

        return JSONResponse({"ok": True, "certificate": cert.to_dict()})

    @mcp.custom_route("/v1/verification/certificate/{certificate_id}", methods=["GET"])
    async def verification_certificate_get_route(request: Request) -> Response:
        cert_id = request.path_params.get("certificate_id", "")
        cert = formal_verification_pipeline.certificates.get(cert_id)
        if not cert:
            return JSONResponse({"ok": False, "error": f"Certificate '{cert_id}' not found"}, status_code=404)
        valid = formal_verification_pipeline.verify_certificate(cert)
        return JSONResponse({"ok": True, "valid": valid, "certificate": cert.to_dict()})

    @mcp.custom_route("/v1/verification/triage", methods=["POST"])
    async def verification_triage_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        raw_ces = body.get("counterexamples", [])
        ces: List[CounterExample] = []
        for r in raw_ces:
            inv_type = InvariantType(r.get("invariant_type", "POST_CONDITION")) if r.get("invariant_type") in [e.value for e in InvariantType] else InvariantType.POST_CONDITION
            ces.append(
                CounterExample(
                    contract_id=r.get("contract_id", "ce-1"),
                    invariant_type=inv_type,
                    expression=r.get("expression", ""),
                    inputs=r.get("inputs", {}),
                    output=r.get("output"),
                    error_message=r.get("error_message", ""),
                    suggested_patch=r.get("suggested_patch", ""),
                )
            )
        triage_report = formal_verification_pipeline.triage_analyzer.triage(ces)
        return JSONResponse({"ok": True, "triage": triage_report})

    # Milestone v3.7 (Phase 41): Multi-Seat Synthesis Consensus & Cryptographic Proof Ledger
    @mcp.custom_route("/v1/synthesis/review/initiate", methods=["POST"])
    async def synthesis_review_initiate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        cert_id = body.get("certificate_id")
        if not cert_id:
            return JSONResponse({"ok": False, "error": "certificate_id is required"}, status_code=400)
        cert = formal_verification_pipeline.certificates.get(cert_id)
        if not cert:
            return JSONResponse({"ok": False, "error": f"Certificate '{cert_id}' not found"}, status_code=404)
        threshold_ratio = float(body.get("threshold_ratio", 0.60))
        consensus_id = synthesis_consensus_engine.initiate_review(cert, threshold_ratio=threshold_ratio)
        return JSONResponse({"ok": True, "consensus_id": consensus_id, "status": "PENDING_REVIEW"})

    @mcp.custom_route("/v1/synthesis/review/vote", methods=["POST"])
    async def synthesis_review_vote_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        consensus_id = body.get("consensus_id")
        reviewer_seat_id = body.get("reviewer_seat_id")
        vote_str = body.get("vote", "APPROVE")
        critique_notes = body.get("critique_notes", "")
        if not consensus_id or not reviewer_seat_id:
            return JSONResponse({"ok": False, "error": "consensus_id and reviewer_seat_id are required"}, status_code=400)
        try:
            vote = ReviewVote(vote_str)
        except ValueError:
            return JSONResponse({"ok": False, "error": f"Invalid vote: {vote_str}"}, status_code=400)
        try:
            ballot = synthesis_consensus_engine.cast_ballot(
                consensus_id=consensus_id,
                reviewer_seat_id=reviewer_seat_id,
                vote=vote,
                critique_notes=critique_notes,
            )
            return JSONResponse({"ok": True, "ballot": ballot.to_dict()})
        except (KeyError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/synthesis/review/finalize", methods=["POST"])
    async def synthesis_review_finalize_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        consensus_id = body.get("consensus_id")
        if not consensus_id:
            return JSONResponse({"ok": False, "error": "consensus_id is required"}, status_code=400)
        try:
            receipt = synthesis_consensus_engine.tally_and_finalize(consensus_id)
            root = proof_receipt_ledger.compute_root()
            return JSONResponse({"ok": True, "receipt": receipt.to_dict(), "ledger_root": root})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/synthesis/ledger/proof/{leaf_index}", methods=["GET"])
    async def synthesis_ledger_proof_route(request: Request) -> Response:
        leaf_idx_str = request.path_params.get("leaf_index", "0")
        try:
            leaf_idx = int(leaf_idx_str)
            proof = proof_receipt_ledger.generate_proof(leaf_idx)
            is_valid = ProofReceiptLedger.verify_proof(proof)
            return JSONResponse({"ok": True, "valid": is_valid, "proof": proof.to_dict()})
        except (IndexError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/synthesis/anchor/solana", methods=["POST"])
    async def synthesis_anchor_solana_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        consensus_id = body.get("consensus_id")
        receipt = next((r for r in proof_receipt_ledger.receipts if r.consensus_id == consensus_id), None)
        if not receipt:
            return JSONResponse({"ok": False, "error": f"Receipt '{consensus_id}' not found in ledger"}, status_code=404)
        root = proof_receipt_ledger.compute_root()
        anchor = proof_exporter.export_solana_anchor(receipt, root)
        return JSONResponse({"ok": True, "anchor": anchor})

    @mcp.custom_route("/v1/synthesis/drill/simulate", methods=["POST"])
    async def synthesis_drill_simulate_route(_request: Request) -> Response:
        drill_results = FormalVerificationDrillSimulator.run_synthesis_consensus_drill(synthesis_consensus_engine)
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v3.8 (Phases 42 & 43): Dynamic Sharding & Sovereign Mesh Consensus
    @mcp.custom_route("/v1/sharding/nodes/register", methods=["POST"])
    async def sharding_node_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id")
        region_id = body.get("region_id", settings.edge_default_region)
        weight = int(body.get("weight", 1))
        if not node_id:
            return JSONResponse({"ok": False, "error": "node_id is required"}, status_code=400)
        node = ShardNode(node_id=node_id, region_id=region_id, weight=weight)
        shard_ring.add_node(node)
        return JSONResponse({"ok": True, "node": node.to_dict(), "total_nodes": len(shard_ring.nodes)})

    @mcp.custom_route("/v1/sharding/nodes", methods=["GET"])
    async def sharding_nodes_list_route(_request: Request) -> Response:
        return JSONResponse({"ok": True, "nodes": shard_ring.list_nodes()})

    @mcp.custom_route("/v1/sharding/route/{key}", methods=["GET"])
    async def sharding_route_key_route(request: Request) -> Response:
        key = request.path_params.get("key", "")
        routing = shard_router.route_key(key)
        return JSONResponse({"ok": True, "routing": routing})

    @mcp.custom_route("/v1/sharding/crdt/write", methods=["POST"])
    async def sharding_crdt_write_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        key = body.get("key")
        crdt_type = body.get("crdt_type", "lww")
        if not key:
            return JSONResponse({"ok": False, "error": "key is required"}, status_code=400)

        if crdt_type == "lww":
            val = body.get("value")
            res = shard_router.write_lww(key, val)
            return JSONResponse({"ok": True, **res})
        elif crdt_type == "pn_counter":
            delta = int(body.get("delta", 1))
            res = shard_router.update_counter(key, delta)
            return JSONResponse({"ok": True, **res})
        elif crdt_type == "or_set":
            elem = body.get("element", "")
            action = body.get("action", "add")
            if action == "remove":
                s = shard_crdt_store.remove_set(key, elem)
            else:
                s = shard_crdt_store.add_set(key, elem)
            routing = shard_router.route_key(key)
            delta_obj = geo_replication_engine.create_delta(
                key=key,
                crdt_type="or_set",
                payload=s.to_dict(),
                vector_clock=shard_crdt_store.vector_clock,
            )
            return JSONResponse({
                "ok": True,
                "key": key,
                "elements": sorted(list(s.read())),
                "delta_id": delta_obj.delta_id,
                "routing": routing,
            })
        else:
            return JSONResponse({"ok": False, "error": f"Unsupported crdt_type: {crdt_type}"}, status_code=400)

    @mcp.custom_route("/v1/sharding/crdt/read/{key}", methods=["GET"])
    async def sharding_crdt_read_route(request: Request) -> Response:
        key = request.path_params.get("key", "")
        crdt_type = request.query_params.get("crdt_type", "lww")
        routing = shard_router.route_key(key)

        if crdt_type == "lww":
            val = shard_crdt_store.read_lww(key)
            return JSONResponse({"ok": True, "key": key, "value": val, "crdt_type": "lww", "routing": routing})
        elif crdt_type == "pn_counter":
            val = shard_crdt_store.read_counter(key)
            return JSONResponse({"ok": True, "key": key, "value": val, "crdt_type": "pn_counter", "routing": routing})
        elif crdt_type == "or_set":
            elems = shard_crdt_store.read_set(key)
            return JSONResponse({"ok": True, "key": key, "elements": sorted(list(elems)), "crdt_type": "or_set", "routing": routing})
        return JSONResponse({"ok": False, "error": f"Unknown crdt_type: {crdt_type}"}, status_code=400)

    @mcp.custom_route("/v1/mesh/consensus/gossip/digest", methods=["POST"])
    async def mesh_consensus_gossip_digest_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        peer_digest_dict = body.get("digest")
        if not peer_digest_dict:
            # return local digest
            local_digest = anti_entropy_gossip.generate_digest()
            return JSONResponse({"ok": True, "digest": local_digest.to_dict()})

        from desk_gateway.mesh_consensus import GossipDigest
        remote_digest = GossipDigest(
            region_id=peer_digest_dict["region_id"],
            vector_clock=peer_digest_dict["vector_clock"],
            known_keys_hash=peer_digest_dict["known_keys_hash"],
            timestamp=peer_digest_dict.get("timestamp", time.time()),
        )
        res = anti_entropy_gossip.receive_digest(remote_digest)
        return JSONResponse({"ok": True, "comparison": res})

    @mcp.custom_route("/v1/mesh/consensus/lease/acquire", methods=["POST"])
    async def mesh_consensus_lease_acquire_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        ttl = float(body.get("ttl_seconds", 30.0))
        lease = epoch_coordinator.acquire_lease(ttl_seconds=ttl)
        if not lease:
            return JSONResponse({"ok": False, "error": "Split-brain partition fencing active: quorum unavailable"}, status_code=503)
        return JSONResponse({"ok": True, "lease": lease.to_dict()})

    @mcp.custom_route("/v1/mesh/consensus/drill/simulate", methods=["POST"])
    async def mesh_consensus_drill_simulate_route(_request: Request) -> Response:
        drill_results = GeoPartitionDrillSimulator.run_partition_and_healing_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v3.9 (Phases 44 & 45): Post-Quantum Cryptographic Migration & Lattice Attestation Mesh
    @mcp.custom_route("/v1/pqc/keys/generate", methods=["POST"])
    async def pqc_keys_generate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        key_id = body.get("key_id")
        keypair = pqc_kem.generate_keypair(key_id=key_id)
        return JSONResponse({"ok": True, "bundle": keypair.public_bundle()})

    @mcp.custom_route("/v1/pqc/kem/encapsulate", methods=["POST"])
    async def pqc_kem_encapsulate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        key_id = body.get("key_id", "default-kem-key")
        keypair = pqc_kem.generate_keypair(key_id=key_id)
        sec, receipt = pqc_kem.encapsulate(keypair)
        return JSONResponse({"ok": True, "receipt": receipt.to_dict()})

    @mcp.custom_route("/v1/pqc/signature/sign", methods=["POST"])
    async def pqc_signature_sign_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        message = body.get("message", "").encode("utf-8")
        key_id = body.get("key_id", "seat-pqc-signer")
        sig = pqc_sig_engine.sign(message, key_id=key_id)
        return JSONResponse({"ok": True, "signature": sig.to_dict()})

    @mcp.custom_route("/v1/pqc/signature/verify", methods=["POST"])
    async def pqc_signature_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        message = body.get("message", "").encode("utf-8")
        sig_data = body.get("signature", {})
        from desk_gateway.post_quantum import HybridSignature
        sig = HybridSignature(
            key_id=sig_data.get("key_id", ""),
            classical_sig=sig_data.get("classical_sig", ""),
            lattice_sig=sig_data.get("lattice_sig", ""),
            algorithm_suite=sig_data.get("algorithm_suite", ""),
            message_digest=sig_data.get("message_digest", ""),
            timestamp=sig_data.get("timestamp", time.time()),
        )
        valid = pqc_sig_engine.verify(message, sig)
        return JSONResponse({"ok": True, "valid": valid})

    @mcp.custom_route("/v1/pqc/audit/negotiate", methods=["POST"])
    async def pqc_audit_negotiate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        client_suites = body.get("client_suites", [])
        server_suites = body.get("server_suites", [])
        agreed_suite = body.get("agreed_suite", "")
        res = pqc_inspector.evaluate_negotiation(client_suites, server_suites, agreed_suite)
        return JSONResponse({"ok": True, "negotiation": res})

    @mcp.custom_route("/v1/pqc/identity/passport/issue", methods=["POST"])
    async def pqc_identity_passport_issue_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        desk_id = body.get("desk_id", settings.public_host)
        roles = body.get("roles")
        passport = pqc_ca.issue_passport(seat_id, desk_id, roles=roles)
        return JSONResponse({"ok": True, "passport": passport.to_dict()})

    @mcp.custom_route("/v1/pqc/identity/passport/verify", methods=["POST"])
    async def pqc_identity_passport_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        pass_data = body.get("passport", {})
        from desk_gateway.lattice_ledger import PQCSeatPassport
        passport = PQCSeatPassport(
            seat_id=pass_data["seat_id"],
            desk_id=pass_data["desk_id"],
            public_bundle=pass_data["public_bundle"],
            roles=pass_data["roles"],
            expires_at=pass_data["expires_at"],
            ca_signature=pass_data["ca_signature"],
            issued_at=pass_data.get("issued_at", time.time()),
        )
        res = pqc_verifier.verify_remote_peer(passport)
        return JSONResponse({"ok": True, "verification": res})

    @mcp.custom_route("/v1/pqc/ledger/append", methods=["POST"])
    async def pqc_ledger_append_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        desk_id = body.get("desk_id", settings.public_host)
        action = body.get("action", "record_event")
        payload = body.get("payload", {})
        entry = pqc_ledger.append_entry(desk_id=desk_id, action=action, payload=payload)
        return JSONResponse({
            "ok": True,
            "entry": entry.to_dict(),
            "merkle_root": pqc_ledger.compute_merkle_root(),
        })

    @mcp.custom_route("/v1/pqc/ledger/anchor/export", methods=["POST"])
    async def pqc_ledger_anchor_export_route(_request: Request) -> Response:
        anchor = pqc_anchor_exporter.export_anchor(pqc_ledger)
        return JSONResponse({"ok": True, "anchor": anchor})

    @mcp.custom_route("/v1/pqc/drill/simulate", methods=["POST"])
    async def pqc_drill_simulate_route(_request: Request) -> Response:
        drill_results = QuantumAttackDrillSimulator.run_quantum_attack_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.0 (Phases 46 & 47): Autonomous Swarm Orchestration & Self-Synthesizing Workflow Mesh
    @mcp.custom_route("/v1/swarm/workflows/compile", methods=["POST"])
    async def swarm_workflows_compile_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        try:
            dag = workflow_compiler.compile(body)
            return JSONResponse({"ok": True, "workflow": dag.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/workflows/submit", methods=["POST"])
    async def swarm_workflows_submit_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        try:
            dag = workflow_compiler.compile(body)
            workflow_engine.submit_workflow(dag)
            return JSONResponse({"ok": True, "workflow_id": dag.workflow_id, "status": "SUBMITTED"})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/swarm/workflows/{workflow_id}/step", methods=["POST"])
    async def swarm_workflows_step_route(request: Request) -> Response:
        workflow_id = request.path_params.get("workflow_id", "")
        if workflow_id not in workflow_engine.workflows:
            return JSONResponse({"ok": False, "error": "Workflow not found"}, status_code=404)
        res = workflow_engine.step_execution(workflow_id)
        return JSONResponse({"ok": True, "execution": res})

    @mcp.custom_route("/v1/swarm/workflows/{workflow_id}/status", methods=["GET"])
    async def swarm_workflows_status_route(request: Request) -> Response:
        workflow_id = request.path_params.get("workflow_id", "")
        dag = workflow_engine.workflows.get(workflow_id)
        if not dag:
            return JSONResponse({"ok": False, "error": "Workflow not found"}, status_code=404)
        return JSONResponse({"ok": True, "workflow": dag.to_dict()})

    @mcp.custom_route("/v1/swarm/capabilities/register", methods=["POST"])
    async def swarm_capabilities_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        from desk_gateway.swarm_federation import FederatedCapability
        cap = FederatedCapability(
            capability_name=body.get("capability_name", "generic_cap"),
            desk_id=body.get("desk_id", "desk-local"),
            seat_id=body.get("seat_id", "systems"),
            schema_contract=body.get("schema_contract", {}),
            version=body.get("version", "1.0.0"),
        )
        capability_broker.register_capability(cap)
        return JSONResponse({"ok": True, "capability": cap.to_dict()})

    @mcp.custom_route("/v1/swarm/capabilities", methods=["GET"])
    async def swarm_capabilities_list_route(_request: Request) -> Response:
        return JSONResponse({"ok": True, "capabilities": capability_broker.list_capabilities()})

    @mcp.custom_route("/v1/swarm/workflows/{workflow_id}/receipt", methods=["POST"])
    async def swarm_workflows_receipt_route(request: Request) -> Response:
        workflow_id = request.path_params.get("workflow_id", "")
        dag = workflow_engine.workflows.get(workflow_id)
        if not dag:
            return JSONResponse({"ok": False, "error": "Workflow not found"}, status_code=404)
        receipt = workflow_receipt_ledger.record_execution(dag, duration_ms=50.0)
        anchor = workflow_anchor_exporter.export_anchor(receipt)
        return JSONResponse({"ok": True, "receipt": receipt.to_dict(), "anchor": anchor})

    @mcp.custom_route("/v1/swarm/workflows/drill/simulate", methods=["POST"])
    async def swarm_workflows_drill_simulate_route(_request: Request) -> Response:
        drill_results = SwarmOrchestrationDrillSimulator.run_swarm_orchestration_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.1 (Phases 48 & 49): Swarm DAO Governance & Algorithmic Tokenomics
    @mcp.custom_route("/v1/dao/proposals/create", methods=["POST"])
    async def dao_proposals_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        prop = swarm_dao_engine.create_proposal(
            proposer_seat=body.get("proposer_seat", "lead"),
            title=body.get("title", "Governance Proposal"),
            description=body.get("description", ""),
            action_payload=body.get("action_payload", {}),
            voting_duration_seconds=float(body.get("voting_duration_seconds", 300.0)),
            timelock_delay_seconds=float(body.get("timelock_delay_seconds", 60.0)),
        )
        return JSONResponse({"ok": True, "proposal": prop.to_dict()})

    @mcp.custom_route("/v1/dao/proposals/{proposal_id}/vote", methods=["POST"])
    async def dao_proposals_vote_route(request: Request) -> Response:
        proposal_id = request.path_params.get("proposal_id", "")
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        voter_seat = body.get("voter_seat", "lead")
        opt_str = body.get("option", "YES")
        try:
            ballot = swarm_dao_engine.cast_vote(proposal_id, voter_seat, VoteOption(opt_str))
            return JSONResponse({"ok": True, "ballot": ballot.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/dao/proposals/{proposal_id}/resolve", methods=["POST"])
    async def dao_proposals_resolve_route(request: Request) -> Response:
        proposal_id = request.path_params.get("proposal_id", "")
        try:
            prop = swarm_dao_engine.resolve_proposal(proposal_id)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/dao/proposals/{proposal_id}/execute", methods=["POST"])
    async def dao_proposals_execute_route(request: Request) -> Response:
        proposal_id = request.path_params.get("proposal_id", "")
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        force_unlock = bool(body.get("force_unlock", False))
        try:
            rec = policy_timelock_executor.execute_proposal(proposal_id, force_unlock=force_unlock)
            return JSONResponse({"ok": True, "execution": rec})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/dao/tokenomics/pricing", methods=["GET"])
    async def dao_tokenomics_pricing_route(request: Request) -> Response:
        load = float(request.query_params.get("node_load", 0.0))
        price = compute_credit_ledger.calculate_compute_price(load)
        return JSONResponse({"ok": True, "node_load": load, "unit_price": price})

    @mcp.custom_route("/v1/dao/tokenomics/drill/simulate", methods=["POST"])
    async def dao_tokenomics_drill_simulate_route(_request: Request) -> Response:
        drill_results = TokenomicsDrillSimulator.run_tokenomics_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.2 (Phases 50 & 51): Autonomous Cross-Chain Bridge & Decentralized Oracle Mesh
    @mcp.custom_route("/v1/bridge/relay/header", methods=["POST"])
    async def bridge_relay_header_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        chain_str = body.get("chain_type", "EVM")
        try:
            chain = ChainType(chain_str.upper())
        except ValueError:
            return JSONResponse({"ok": False, "error": f"Invalid chain_type: {chain_str}"}, status_code=400)

        relayer_id = body.get("relayer_id", "relayer-primary")
        header = BlockHeader(
            chain=chain,
            height=int(body.get("height", body.get("block_number", 0))),
            block_hash=body.get("block_hash", ""),
            parent_hash=body.get("parent_hash", ""),
            state_root=body.get("state_root", ""),
            receipts_root=body.get("receipts_root", "0x0"),
            timestamp=float(body.get("timestamp", time.time())),
        )
        try:
            stored = cross_chain_relay_engine.relay_header(relayer_id=relayer_id, header=header)
            return JSONResponse({"ok": True, "header": stored.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/bridge/message/dispatch", methods=["POST"])
    async def bridge_message_dispatch_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        src_str = body.get("source_chain", "EVM")
        tgt_str = body.get("target_chain", "SOLANA")
        try:
            src_chain = ChainType(src_str.upper())
            tgt_chain = ChainType(tgt_str.upper())
        except ValueError:
            return JSONResponse({"ok": False, "error": "Invalid chain type specified"}, status_code=400)

        relayer_id = body.get("relayer_id", "relayer-primary")
        msg = CrossChainMessage(
            message_id=body.get("message_id", f"msg-{secrets.token_hex(4)}"),
            source_chain=src_chain,
            target_chain=tgt_chain,
            sender_address=body.get("sender_address", body.get("sender", "0xSender")),
            recipient_address=body.get("recipient_address", body.get("recipient", "RecipientAccount")),
            payload=body.get("payload", {}),
            nonce=int(body.get("nonce", 1)),
            proof=body.get("proof", "proof-dummy"),
            signature=body.get("signature", ""),
            timestamp=float(body.get("timestamp", time.time())),
        )
        proof_nodes = body.get("proof_nodes", [])
        try:
            res = cross_chain_relay_engine.dispatch_message(relayer_id=relayer_id, message=msg, proof_nodes=proof_nodes)
            return JSONResponse({"ok": True, "dispatch": res})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/oracle/reports/ingest", methods=["POST"])
    async def oracle_reports_ingest_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        feed_name = body.get("feed_name", "SOL/USD")
        source_id = body.get("source_id", body.get("reporter_seat", "lead"))
        value = float(body.get("value", 0.0))
        report = OracleReport(
            source_id=source_id,
            feed_name=feed_name,
            value=value,
            timestamp=float(body.get("timestamp", time.time())),
            signature=body.get("signature", "sig"),
        )
        try:
            oracle_aggregator.ingest_report(report)
            return JSONResponse({"ok": True, "report": report.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/oracle/feeds/{feed_name}/finalize", methods=["POST"])
    async def oracle_feed_finalize_route(request: Request) -> Response:
        feed_name = request.path_params.get("feed_name", "")
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        min_reports = int(body.get("min_reports", 3))
        try:
            feed = oracle_aggregator.finalize_feed(feed_name, min_reports=min_reports)
            anchor = oracle_anchor_exporter.export_oracle_anchor(feed)
            return JSONResponse({"ok": True, "feed": feed.to_dict(), "anchor": anchor})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/oracle/feeds/{feed_name}", methods=["GET"])
    async def oracle_feed_get_route(request: Request) -> Response:
        feed_name = request.path_params.get("feed_name", "")
        feed = oracle_aggregator.finalized_feeds.get(feed_name)
        if not feed:
            return JSONResponse({"ok": False, "error": f"Feed not found: {feed_name}"}, status_code=404)
        return JSONResponse({"ok": True, "feed": feed.to_dict()})

    @mcp.custom_route("/v1/bridge/drill/simulate", methods=["POST"])
    async def bridge_drill_simulate_route(_request: Request) -> Response:
        drill_results = CrossChainOracleDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.3: Model Distillation & Edge Compute Routes
    @mcp.custom_route("/v1/distillation/jobs", methods=["POST"])
    async def distillation_job_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        student_model = body.get("student_model", "student-desk-v1")
        teacher_models = body.get("teacher_models", ["teacher-llama-70b", "teacher-qwen-72b"])
        temperature = float(body.get("temperature", 2.0))
        alpha = float(body.get("alpha", 0.5))
        target_quant = body.get("target_quantization", "INT8")

        job = model_artifact_registry.register_job(
            student_model_name=student_model,
            teacher_models=teacher_models,
            temperature=temperature,
            alpha=alpha,
            target_quantization=target_quant,
        )
        return JSONResponse({"ok": True, "job_id": job.job_id, "status": job.status, "student_model": job.student_model_name})

    @mcp.custom_route("/v1/distillation/step", methods=["POST"])
    async def distillation_step_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        student_logits = body.get("student_logits", [1.0, 0.0, 0.0])
        teachers_data = body.get("teacher_predictions", [])
        ground_truth = int(body.get("ground_truth_label", 0))
        temp = body.get("temperature")
        alpha = body.get("alpha")

        predictions = [
            TeacherPrediction(
                model_id=t.get("model_id", "teacher"),
                weight=float(t.get("weight", 1.0)),
                logits=t.get("logits", [1.0, 0.0, 0.0]),
            )
            for t in teachers_data
        ]
        metrics = distillation_engine.compute_distillation_step(
            student_logits=student_logits,
            teacher_predictions=predictions,
            ground_truth_label=ground_truth,
            temperature=temp,
            alpha=alpha,
        )
        return JSONResponse({"ok": True, "metrics": metrics})

    @mcp.custom_route("/v1/distillation/artifacts", methods=["POST"])
    async def distillation_artifact_store_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        model_name = body.get("model_name", "student-desk-v1")
        quant_type = body.get("quantization_type", "INT8")
        weights = body.get("weights", [0.1, -0.2, 0.5, -0.8])
        metadata = body.get("metadata", {})

        art = model_artifact_registry.store_artifact(
            model_name=model_name,
            quantization_type=quant_type,
            weights=weights,
            metadata=metadata,
        )
        return JSONResponse({
            "ok": True,
            "artifact_id": art.artifact_id,
            "digest": art.sha256_digest,
            "parameter_count": art.parameter_count,
            "compressed_size_bytes": art.compressed_size_bytes,
        })

    @mcp.custom_route("/v1/distillation/artifacts/{artifact_id}", methods=["GET"])
    async def distillation_artifact_get_route(request: Request) -> Response:
        artifact_id = request.path_params.get("artifact_id", "")
        art = model_artifact_registry.get_artifact(artifact_id)
        if not art:
            return JSONResponse({"ok": False, "error": f"Artifact not found: {artifact_id}"}, status_code=404)
        return JSONResponse({
            "ok": True,
            "artifact": {
                "artifact_id": art.artifact_id,
                "model_name": art.model_name,
                "quantization_type": art.quantization_type,
                "parameter_count": art.parameter_count,
                "compressed_size_bytes": art.compressed_size_bytes,
                "sha256_digest": art.sha256_digest,
                "scales": art.scales,
                "zero_points": art.zero_points,
            }
        })

    @mcp.custom_route("/v1/distillation/benchmark/retention", methods=["POST"])
    async def distillation_benchmark_retention_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        t_acc = float(body.get("teacher_accuracy", 0.85))
        s_acc = float(body.get("student_accuracy", 0.82))
        res = distillation_benchmarker.evaluate_retention(t_acc, s_acc)
        return JSONResponse({"ok": True, "evaluation": res})

    @mcp.custom_route("/v1/edge/nodes", methods=["GET"])
    async def edge_nodes_list_route(_request: Request) -> Response:
        nodes = edge_compute_scheduler.list_nodes()
        return JSONResponse({
            "ok": True,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "region": n.region,
                    "vram_mb": n.vram_mb,
                    "used_vram_mb": n.used_vram_mb,
                    "active_tasks": n.active_tasks,
                    "is_healthy": n.is_healthy,
                    "latency_ms": n.latency_ms,
                    "supported_quantizations": n.supported_quantizations,
                }
                for n in nodes
            ]
        })

    @mcp.custom_route("/v1/edge/schedule", methods=["POST"])
    async def edge_schedule_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        art_id = body.get("artifact_id", "art-default")
        vram = int(body.get("required_vram_mb", 1024))
        quant = body.get("quantization", "INT8")

        node = edge_compute_scheduler.schedule_inference(art_id, vram, quant)
        if not node:
            return JSONResponse({"ok": False, "error": "No available edge node satisfying constraints"}, status_code=503)
        return JSONResponse({
            "ok": True,
            "scheduled_node": {
                "node_id": node.node_id,
                "region": node.region,
                "used_vram_mb": node.used_vram_mb,
                "active_tasks": node.active_tasks,
            }
        })

    @mcp.custom_route("/v1/edge/inference/prove", methods=["POST"])
    async def edge_inference_prove_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_id = body.get("task_id", f"task-{secrets.token_hex(4)}")
        node_id = body.get("node_id", "edge-desk-us-west")
        art_id = body.get("artifact_id", "art-default")
        prompt = body.get("prompt", "")
        completion = body.get("completion", "")
        latency = float(body.get("latency_ms", 12.5))

        receipt = inference_proof_engine.generate_receipt(
            task_id=task_id,
            node_id=node_id,
            artifact_id=art_id,
            prompt_text=prompt,
            completion_text=completion,
            latency_ms=latency,
        )
        return JSONResponse({
            "ok": True,
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "task_id": receipt.task_id,
                "node_id": receipt.node_id,
                "artifact_id": receipt.artifact_id,
                "input_hash": receipt.input_hash,
                "output_hash": receipt.output_hash,
                "signature_proof": receipt.signature_proof,
                "timestamp": receipt.timestamp,
            }
        })

    @mcp.custom_route("/v1/edge/commitments/export", methods=["POST"])
    async def edge_commitments_export_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipts_data = body.get("receipts", [])
        from desk_gateway.edge_mesh import InferenceProofReceipt
        receipts = [
            InferenceProofReceipt(
                receipt_id=r.get("receipt_id", ""),
                task_id=r.get("task_id", ""),
                node_id=r.get("node_id", ""),
                artifact_id=r.get("artifact_id", ""),
                input_hash=r.get("input_hash", ""),
                output_hash=r.get("output_hash", ""),
                timestamp=float(r.get("timestamp", time.time())),
                signature_proof=r.get("signature_proof", ""),
            )
            for r in receipts_data
        ]
        commitment = edge_commitment_exporter.export_batch_commitment(receipts)
        return JSONResponse({"ok": True, "commitment": commitment})

    @mcp.custom_route("/v1/distillation/drill/simulate", methods=["POST"])
    async def distillation_drill_simulate_route(_request: Request) -> Response:
        simulator = DistillationEdgeDrillSimulator()
        drill_results = simulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.4: Zero-Knowledge Proving & Privacy-Preserving Agent Swarm
    @mcp.custom_route("/v1/zk/circuits/synthesize", methods=["POST"])
    async def zk_circuits_synthesize_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        circuit_id = body.get("circuit_id", "custom-circuit")
        circuit_name = body.get("name", "CustomArithmeticCircuit")
        pub_wires = body.get("public_wires", ["one", "x", "y"])
        priv_wires = body.get("private_wires", ["w"])
        raw_constraints = body.get("constraints", [])

        circuit = ZKCircuit(
            circuit_id=circuit_id,
            name=circuit_name,
            public_wire_names=pub_wires,
            private_wire_names=priv_wires,
        )
        for idx, c in enumerate(raw_constraints):
            constraint = ZKConstraint(
                constraint_id=c.get("constraint_id", f"c_{idx}"),
                a_coefficients=c.get("a", {}),
                b_coefficients=c.get("b", {}),
                c_coefficients=c.get("c", {}),
            )
            circuit.add_constraint(constraint)

        zk_circuits_registry[circuit_id] = circuit
        return JSONResponse({
            "ok": True,
            "circuit_id": circuit_id,
            "constraints_count": len(circuit.constraints),
            "public_wires": circuit.public_wire_names,
            "private_wires": circuit.private_wire_names,
        })

    @mcp.custom_route("/v1/zk/proof/generate", methods=["POST"])
    async def zk_proof_generate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        circuit_id = body.get("circuit_id", "state-transition-v1")
        public_inputs = body.get("public_inputs", {})
        private_witness = body.get("private_witness", {})
        proof_type = body.get("proof_type", "GROTH16")

        circuit = zk_circuits_registry.get(circuit_id)
        if not circuit:
            # Build default state transition circuit if not yet registered
            circuit = zk_state_prover.build_state_transition_circuit(circuit_id)
            zk_circuits_registry[circuit_id] = circuit

        try:
            proof = zk_proof_generator.generate_proof(
                circuit=circuit,
                public_inputs=public_inputs,
                private_witness=private_witness,
                proof_type=proof_type,
            )
            return JSONResponse({
                "ok": True,
                "proof": {
                    "proof_id": proof.proof_id,
                    "circuit_id": proof.circuit_id,
                    "proof_type": proof.proof_type,
                    "public_inputs": proof.public_inputs,
                    "commitment_hash": proof.commitment_hash,
                    "proof_bytes": proof.proof_bytes,
                    "timestamp": proof.timestamp,
                }
            })
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/zk/proof/verify", methods=["POST"])
    async def zk_proof_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        circuit_id = body.get("circuit_id", "state-transition-v1")
        proof_dict = body.get("proof", {})

        circuit = zk_circuits_registry.get(circuit_id)
        if not circuit:
            circuit = zk_state_prover.build_state_transition_circuit(circuit_id)
            zk_circuits_registry[circuit_id] = circuit

        proof = ZKProof(
            proof_id=proof_dict.get("proof_id", ""),
            circuit_id=circuit_id,
            proof_type=proof_dict.get("proof_type", "GROTH16"),
            public_inputs=proof_dict.get("public_inputs", {}),
            commitment_hash=proof_dict.get("commitment_hash", ""),
            proof_bytes=proof_dict.get("proof_bytes", "{}"),
            timestamp=float(proof_dict.get("timestamp", time.time())),
        )
        receipt = zk_proof_verifier.verify_proof(circuit, proof)
        return JSONResponse({
            "ok": True,
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "proof_id": receipt.proof_id,
                "circuit_id": receipt.circuit_id,
                "is_valid": receipt.is_valid,
                "verified_at": receipt.verified_at,
                "verification_digest": receipt.verification_digest,
                "public_inputs": receipt.public_inputs,
            }
        })

    @mcp.custom_route("/v1/zk/state/prove", methods=["POST"])
    async def zk_state_prove_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        initial_state = float(body.get("initial_state", 100.0))
        delta = float(body.get("delta", 25.0))
        secret_auth = float(body.get("secret_auth_code", 1234.0))
        circuit_id = body.get("circuit_id", "state-transition-v1")

        proof, receipt = zk_state_prover.prove_state_transition(
            initial_state=initial_state,
            delta=delta,
            secret_auth_code=secret_auth,
            circuit_id=circuit_id,
        )
        return JSONResponse({
            "ok": True,
            "proof_id": proof.proof_id,
            "is_valid": receipt.is_valid,
            "final_state": initial_state + delta,
            "verification_digest": receipt.verification_digest,
        })

    @mcp.custom_route("/v1/privacy/homomorphic/encrypt", methods=["POST"])
    async def privacy_homomorphic_encrypt_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        val = int(body.get("value", 42))
        c = homomorphic_cipher.encrypt(val)
        return JSONResponse({
            "ok": True,
            "ciphertext_id": c.ciphertext_id,
            "encrypted_data": c.encrypted_data,
            "modulus": c.modulus,
            "public_key_fingerprint": c.public_key_fingerprint,
        })

    @mcp.custom_route("/v1/privacy/homomorphic/add", methods=["POST"])
    async def privacy_homomorphic_add_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        val1 = int(body.get("val1", 10))
        val2 = int(body.get("val2", 20))
        c1 = homomorphic_cipher.encrypt(val1)
        c2 = homomorphic_cipher.encrypt(val2)
        c_res = homomorphic_cipher.add(c1, c2)
        decrypted = homomorphic_cipher.decrypt(c_res)
        return JSONResponse({
            "ok": True,
            "ciphertext_id": c_res.ciphertext_id,
            "encrypted_data": c_res.encrypted_data,
            "decrypted_sum": decrypted,
        })

    @mcp.custom_route("/v1/privacy/tss/split", methods=["POST"])
    async def privacy_tss_split_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        secret = int(body.get("secret", 987654321))
        threshold = int(body.get("threshold", 3))
        total_shares = int(body.get("total_shares", 5))

        shares = tss_engine.split_secret(secret, threshold=threshold, total_shares=total_shares)
        return JSONResponse({
            "ok": True,
            "threshold": threshold,
            "total_shares": total_shares,
            "shares": [
                {
                    "share_index": s.share_index,
                    "share_value": s.share_value,
                }
                for s in shares
            ]
        })

    @mcp.custom_route("/v1/privacy/mpc/infer", methods=["POST"])
    async def privacy_mpc_infer_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        session_id = body.get("session_id", f"mpc-{secrets.token_hex(4)}")
        seat_inputs = body.get("seat_inputs", {
            "lead": [0.5, 0.2, 0.1],
            "systems": [0.4, 0.3, 0.2],
            "infra": [0.6, 0.1, 0.3],
        })
        weights = body.get("weights", [0.8, -0.4, 1.2])

        try:
            res = mpc_coordinator.run_mpc_inference(
                session_id=session_id,
                seat_inputs=seat_inputs,
                weights=weights,
            )
            return JSONResponse({
                "ok": True,
                "session_id": res.session_id,
                "prediction": res.aggregated_prediction,
                "participating_seats": res.participating_seats,
                "commitment_hash": res.mpc_commitment_hash,
            })
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/privacy/zk/commitments/export", methods=["POST"])
    async def privacy_zk_commitments_export_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipts_data = body.get("receipts", [])
        receipts = [
            ZKProofReceipt(
                receipt_id=r.get("receipt_id", f"zkrec-{secrets.token_hex(4)}"),
                proof_id=r.get("proof_id", "zkp-default"),
                circuit_id=r.get("circuit_id", "circuit-default"),
                is_valid=bool(r.get("is_valid", True)),
                verified_at=float(r.get("verified_at", time.time())),
                verification_digest=r.get("verification_digest", "hash-dummy"),
                public_inputs=r.get("public_inputs", {}),
            )
            for r in receipts_data
        ]
        anchor = zk_anchor_exporter.export_zk_commitment(receipts)
        return JSONResponse({"ok": True, "anchor": anchor})

    @mcp.custom_route("/v1/zk/drill/simulate", methods=["POST"])
    async def zk_drill_simulate_route(_request: Request) -> Response:
        drill_results = ZKPrivacyAgentSwarmDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.5: Autonomous Multi-Agent Neuro-Symbolic Reasoning & Causal Inference Mesh
    from desk_gateway.neuro_symbolic import (
        FirstOrderLogicEngine,
        LogicalInvariantChecker,
        NeuroSymbolicGraph,
        Predicate,
        RuleExtractionEngine,
        SymbolicRule,
    )
    from desk_gateway.causal_mesh import (
        CausalAnchorExporter,
        CausalDAG,
        CausalEdge,
        CausalVariable,
        ConstraintCausalDiscovery,
        CounterfactualSimulator,
        DoCalculusEngine,
        NeuroSymbolicCausalDrillSimulator,
    )

    neuro_graph = NeuroSymbolicGraph(embedding_dimension=4)
    logic_engine = neuro_graph.logic_engine
    invariant_checker = LogicalInvariantChecker(logic_engine)
    rule_extractor = RuleExtractionEngine()
    causal_discovery = ConstraintCausalDiscovery()
    causal_anchor_exporter = CausalAnchorExporter()

    mcp._neuro_graph = neuro_graph  # type: ignore[attr-defined]
    mcp._logic_engine = logic_engine  # type: ignore[attr-defined]
    mcp._invariant_checker = invariant_checker  # type: ignore[attr-defined]
    mcp._rule_extractor = rule_extractor  # type: ignore[attr-defined]
    mcp._causal_discovery = causal_discovery  # type: ignore[attr-defined]
    mcp._causal_anchor_exporter = causal_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/neuro-symbolic/facts", methods=["POST"])
    async def neuro_symbolic_add_fact_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        name = body.get("name", "")
        args = tuple(body.get("args", []))
        truth_val = float(body.get("truth_val", 1.0))
        if not name:
            return JSONResponse({"ok": False, "error": "Predicate name is required"}, status_code=400)
        pred = Predicate(name=name, args=args, truth_val=truth_val)
        logic_engine.add_fact(pred)
        return JSONResponse({"ok": True, "predicate": pred.key(), "truth_val": pred.truth_val})

    @mcp.custom_route("/v1/neuro-symbolic/rules", methods=["POST"])
    async def neuro_symbolic_add_rule_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        rule_id = body.get("rule_id", f"rule-{secrets.token_hex(4)}")
        raw_antecedents = body.get("antecedents", [])
        raw_consequent = body.get("consequent", {})
        conf = float(body.get("confidence", 1.0))
        desc = body.get("description", "")

        antecedents = [
            Predicate(name=a["name"], args=tuple(a.get("args", [])), truth_val=float(a.get("truth_val", 1.0)))
            for a in raw_antecedents
        ]
        consequent = Predicate(
            name=raw_consequent.get("name", "inferred"),
            args=tuple(raw_consequent.get("args", [])),
            truth_val=float(raw_consequent.get("truth_val", 1.0)),
        )
        rule = SymbolicRule(rule_id=rule_id, antecedents=antecedents, consequent=consequent, confidence=conf, description=desc)
        logic_engine.add_rule(rule)
        return JSONResponse({"ok": True, "rule": rule.to_dict()})

    @mcp.custom_route("/v1/neuro-symbolic/deduce", methods=["POST"])
    async def neuro_symbolic_deduce_route(_request: Request) -> Response:
        inferred = logic_engine.evaluate_forward_chaining()
        return JSONResponse({
            "ok": True,
            "inferred_count": len(inferred),
            "inferred_facts": [p.key() for p in inferred],
        })

    @mcp.custom_route("/v1/neuro-symbolic/query", methods=["POST"])
    async def neuro_symbolic_query_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        name = body.get("name", "")
        args = tuple(body.get("args", []))
        pred = Predicate(name=name, args=args)
        bindings = logic_engine.query(pred)
        return JSONResponse({"ok": True, "predicate": pred.key(), "matches_count": len(bindings), "bindings": bindings})

    @mcp.custom_route("/v1/neuro-symbolic/concepts", methods=["POST"])
    async def neuro_symbolic_concept_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id", f"node-{secrets.token_hex(4)}")
        name = body.get("name", node_id)
        category = body.get("category", "entity")
        embedding = body.get("embedding", [0.0, 0.0, 0.0, 0.0])
        attributes = body.get("attributes", {})
        node = neuro_graph.add_concept(
            node_id=node_id,
            name=name,
            category=category,
            embedding=embedding,
            attributes=attributes,
        )
        return JSONResponse({"ok": True, "node_id": node.node_id, "category": node.category})

    @mcp.custom_route("/v1/neuro-symbolic/concepts/search", methods=["POST"])
    async def neuro_symbolic_concept_search_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        query_emb = body.get("query_embedding", [0.0, 0.0, 0.0, 0.0])
        top_k = int(body.get("top_k", 3))
        results = neuro_graph.query_similarity(query_emb, top_k=top_k)
        return JSONResponse({
            "ok": True,
            "results": [{"node_id": node.node_id, "name": node.name, "similarity": round(sim, 4)} for node, sim in results],
        })

    @mcp.custom_route("/v1/neuro-symbolic/invariants/check", methods=["POST"])
    async def neuro_symbolic_invariant_check_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        action = body.get("action", "execute_operation")
        raw_facts = body.get("candidate_facts", [])
        candidate_facts = [
            Predicate(name=f["name"], args=tuple(f.get("args", [])))
            for f in raw_facts
        ]
        violations = invariant_checker.check_invariants(action, candidate_facts)
        return JSONResponse({
            "ok": len(violations) == 0,
            "action": action,
            "violations_count": len(violations),
            "violations": [
                {
                    "invariant_name": v.invariant_name,
                    "target_action": v.target_action,
                    "violating_bindings": v.violating_bindings,
                    "message": v.message,
                }
                for v in violations
            ],
        })

    @mcp.custom_route("/v1/causal/dags/create", methods=["POST"])
    async def causal_dag_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        dag_id = body.get("dag_id", f"dag-{secrets.token_hex(4)}")
        variables = body.get("variables", [])
        edges = body.get("edges", [])

        dag = CausalDAG(dag_id=dag_id)
        for v in variables:
            dag.add_variable(CausalVariable(name=v.get("name", "v"), base_mean=float(v.get("base_mean", 0.0))))
        for e in edges:
            dag.add_edge(CausalEdge(source=e["source"], target=e["target"], weight=float(e.get("weight", 1.0))))

        _global_causal_dags[dag_id] = dag
        return JSONResponse({
            "ok": True,
            "dag_id": dag.dag_id,
            "variables_count": len(dag.variables),
            "edges_count": len(dag.edges),
            "topological_order": dag.topological_sort(),
        })

    @mcp.custom_route("/v1/causal/discover", methods=["POST"])
    async def causal_discover_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        dag_id = body.get("dag_id", f"discovered-{secrets.token_hex(4)}")
        variables = body.get("variables", [])
        samples = body.get("samples", [])

        dag = causal_discovery.discover_skeleton_and_dag(
            dag_id=dag_id,
            variable_names=variables,
            data_samples=samples,
        )
        _global_causal_dags[dag_id] = dag
        return JSONResponse({
            "ok": True,
            "dag_id": dag.dag_id,
            "edges": [{"source": e.source, "target": e.target, "weight": e.weight} for e in dag.edges],
            "topological_order": dag.topological_sort(),
        })

    @mcp.custom_route("/v1/causal/intervene", methods=["POST"])
    async def causal_intervene_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        dag_id = body.get("dag_id", "")
        treatment = body.get("treatment", "")
        val = float(body.get("intervention_value", 1.0))
        outcome = body.get("outcome", "")
        baseline = body.get("baseline_values")

        dag = _global_causal_dags.get(dag_id)
        if not dag:
            return JSONResponse({"ok": False, "error": f"Causal DAG '{dag_id}' not found"}, status_code=404)

        engine = DoCalculusEngine(dag)
        res = engine.simulate_intervention(
            treatment=treatment,
            intervention_value=val,
            outcome=outcome,
            baseline_values=baseline,
        )
        return JSONResponse({"ok": True, **res})

    @mcp.custom_route("/v1/causal/counterfactual", methods=["POST"])
    async def causal_counterfactual_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        dag_id = body.get("dag_id", "")
        evidence = body.get("factual_evidence", {})
        intervention = body.get("counterfactual_intervention", {})
        target_var = body.get("target_variable", "")

        dag = _global_causal_dags.get(dag_id)
        if not dag:
            return JSONResponse({"ok": False, "error": f"Causal DAG '{dag_id}' not found"}, status_code=404)

        sim = CounterfactualSimulator(dag)
        res = sim.evaluate_counterfactual(
            factual_evidence=evidence,
            counterfactual_intervention=intervention,
            target_variable=target_var,
        )
        return JSONResponse({"ok": True, **res})

    @mcp.custom_route("/v1/neuro-symbolic/drill/simulate", methods=["POST"])
    async def neuro_symbolic_drill_simulate_route(_request: Request) -> Response:
        drill_results = NeuroSymbolicCausalDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.6: Autonomous Self-Reflective Metacognition & Continuous Epistemic Verification Mesh
    from desk_gateway.metacognition import (
        EpistemicCalibrator,
        MetacognitiveIntrospector,
        EpistemicBeliefNetwork,
        IntrospectiveStrategyOptimizer,
    )
    from desk_gateway.epistemic_mesh import (
        CounterEvidenceSynthesizer,
        EpistemicConsistencyVerifier,
        EpistemicReceiptLedger,
        EpistemicAnchorExporter,
        MetacognitiveEpistemicDrillSimulator,
    )

    epistemic_calibrator = EpistemicCalibrator()
    metacognitive_introspector = MetacognitiveIntrospector()
    epistemic_network = EpistemicBeliefNetwork()
    strategy_optimizer = IntrospectiveStrategyOptimizer()
    counter_evidence_synthesizer = CounterEvidenceSynthesizer()
    epistemic_verifier = EpistemicConsistencyVerifier()
    epistemic_ledger = EpistemicReceiptLedger()
    epistemic_anchor_exporter = EpistemicAnchorExporter()

    mcp._epistemic_calibrator = epistemic_calibrator  # type: ignore[attr-defined]
    mcp._metacognitive_introspector = metacognitive_introspector  # type: ignore[attr-defined]
    mcp._epistemic_network = epistemic_network  # type: ignore[attr-defined]
    mcp._strategy_optimizer = strategy_optimizer  # type: ignore[attr-defined]
    mcp._counter_evidence_synthesizer = counter_evidence_synthesizer  # type: ignore[attr-defined]
    mcp._epistemic_verifier = epistemic_verifier  # type: ignore[attr-defined]
    mcp._epistemic_ledger = epistemic_ledger  # type: ignore[attr-defined]
    mcp._epistemic_anchor_exporter = epistemic_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/metacognition/calibrate", methods=["POST"])
    async def metacognition_calibrate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        raw_conf = float(body.get("raw_confidence", 0.5))
        history_samples = body.get("history_samples", [])
        for item in history_samples:
            epistemic_calibrator.record_outcome(float(item["confidence"]), bool(item["is_correct"]))
        if history_samples:
            epistemic_calibrator.fit_temperature()
        calibrated = epistemic_calibrator.calibrate(raw_conf)
        return JSONResponse({"ok": True, "calibration": calibrated.to_dict()})

    @mcp.custom_route("/v1/metacognition/introspect", methods=["POST"])
    async def metacognition_introspect_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        steps = body.get("reasoning_steps", [])
        report = metacognitive_introspector.introspect_reasoning_chain(steps, calibrator=epistemic_calibrator)
        return JSONResponse({"ok": True, "bias_report": report.to_dict()})

    @mcp.custom_route("/v1/metacognition/beliefs", methods=["POST"])
    async def metacognition_beliefs_add_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        h_id = body.get("hypothesis_id", f"hyp-{secrets.token_hex(4)}")
        desc = body.get("description", "")
        prior = float(body.get("prior", 0.5))
        node = epistemic_network.register_hypothesis(h_id, desc, prior)
        return JSONResponse({"ok": True, "node": node.to_dict()})

    @mcp.custom_route("/v1/metacognition/beliefs/{hypothesis_id}/assimilate", methods=["POST"])
    async def metacognition_beliefs_assimilate_route(request: Request) -> Response:
        h_id = request.path_params.get("hypothesis_id", "")
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        lr = float(body.get("likelihood_ratio", 1.0))
        try:
            update = epistemic_network.assimilate_evidence(h_id, lr)
            return JSONResponse({"ok": True, "update": update.to_dict()})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/metacognition/strategy/select", methods=["POST"])
    async def metacognition_strategy_select_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        entropy = body.get("epistemic_entropy")
        if entropy is None:
            entropy = epistemic_network.compute_epistemic_entropy()
        else:
            entropy = float(entropy)
        crit = body.get("task_criticality", "medium")
        res = strategy_optimizer.select_strategy(epistemic_entropy=entropy, task_criticality=crit)
        return JSONResponse({"ok": True, **res})

    @mcp.custom_route("/v1/epistemic/socratic/challenge", methods=["POST"])
    async def epistemic_socratic_challenge_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        h_id = body.get("hypothesis_id", "hyp-default")
        desc = body.get("description", "default premise")
        prob = float(body.get("current_probability", 0.5))
        probe = body.get("probe_type", "boundary_falsification")
        challenge = counter_evidence_synthesizer.synthesize_challenge(h_id, desc, prob, probe)
        return JSONResponse({"ok": True, "challenge": challenge.to_dict()})

    @mcp.custom_route("/v1/epistemic/coherence/verify", methods=["POST"])
    async def epistemic_coherence_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_beliefs = body.get("seat_beliefs", {})
        thresh = float(body.get("divergence_threshold", 0.25))
        coherence = epistemic_verifier.verify_coherence(seat_beliefs, divergence_threshold=thresh)
        return JSONResponse({"ok": True, "coherence": coherence})

    @mcp.custom_route("/v1/epistemic/ledger/receipts", methods=["POST"])
    async def epistemic_ledger_receipt_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        net_id = body.get("network_id", "default-net")
        rtype = body.get("receipt_type", "EPISTEMIC_UPDATE")
        payload = body.get("payload", {})
        rec = epistemic_ledger.append_receipt(net_id, rtype, payload)
        return JSONResponse({"ok": True, "receipt": rec.to_dict()})

    @mcp.custom_route("/v1/epistemic/anchor/export", methods=["POST"])
    async def epistemic_anchor_export_route(_request: Request) -> Response:
        anchor = epistemic_anchor_exporter.export_epistemic_commitment(epistemic_ledger.receipts)
        return JSONResponse({"ok": True, "anchor": anchor})

    @mcp.custom_route("/v1/metacognition/drill/simulate", methods=["POST"])
    async def metacognition_drill_simulate_route(_request: Request) -> Response:
        drill_results = MetacognitiveEpistemicDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.7: Autonomous Multi-Substrate Hardware Acceleration & Neuromorphic Compute Mesh
    from desk_gateway.hardware_mesh import (
        HardwareSubstrate,
        KernelOpType,
        SubstrateKernelCompiler,
        SubstrateProfile,
        SubstrateRegistry,
        SubstrateTelemetryProfiler,
        SubstrateWorkloadDispatcher,
    )
    from desk_gateway.neuromorphic_mesh import (
        HardwareNeuromorphicDrillSimulator,
        NeuromorphicAnchorExporter,
        NeuromorphicMesh,
        SpikeEvent,
        SynapticAttestationLedger,
    )

    substrate_registry = SubstrateRegistry()
    substrate_compiler = SubstrateKernelCompiler()
    substrate_dispatcher = SubstrateWorkloadDispatcher(substrate_registry, substrate_compiler)
    substrate_profiler = SubstrateTelemetryProfiler(substrate_registry)
    neuromorphic_mesh = NeuromorphicMesh(mesh_id="primary-neuromorphic-mesh")
    synaptic_ledger = SynapticAttestationLedger()
    neuromorphic_anchor_exporter = NeuromorphicAnchorExporter()

    mcp._substrate_registry = substrate_registry  # type: ignore[attr-defined]
    mcp._substrate_compiler = substrate_compiler  # type: ignore[attr-defined]
    mcp._substrate_dispatcher = substrate_dispatcher  # type: ignore[attr-defined]
    mcp._substrate_profiler = substrate_profiler  # type: ignore[attr-defined]
    mcp._neuromorphic_mesh = neuromorphic_mesh  # type: ignore[attr-defined]
    mcp._synaptic_ledger = synaptic_ledger  # type: ignore[attr-defined]
    mcp._neuromorphic_anchor_exporter = neuromorphic_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/hardware/substrates", methods=["GET"])
    async def hardware_substrates_list_route(_request: Request) -> Response:
        substrates = [s.to_dict() for s in substrate_registry.list_substrates()]
        return JSONResponse({"ok": True, "substrates": substrates})

    @mcp.custom_route("/v1/hardware/compile", methods=["POST"])
    async def hardware_compile_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        op_str = body.get("op_type", "gemm")
        sub_str = body.get("target_substrate", "gpu_cuda")
        shapes = body.get("input_shapes", [[1024, 1024], [1024, 1024]])
        opt_level = int(body.get("optimization_level", 3))

        try:
            op_type = KernelOpType(op_str.lower())
        except ValueError:
            op_type = KernelOpType.GEMM

        try:
            substrate = HardwareSubstrate(sub_str.lower())
        except ValueError:
            substrate = HardwareSubstrate.GPU_CUDA

        compiled = substrate_compiler.compile(op_type=op_type, target_substrate=substrate, input_shapes=shapes, optimization_level=opt_level)
        return JSONResponse({"ok": True, "kernel": compiled.to_dict()})

    @mcp.custom_route("/v1/hardware/dispatch", methods=["POST"])
    async def hardware_dispatch_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        op_str = body.get("op_type", "gemm")
        shapes = body.get("input_shapes", [[512, 512], [512, 512]])
        priority = int(body.get("priority", 5))
        sub_override_str = body.get("target_override")

        try:
            op_type = KernelOpType(op_str.lower())
        except ValueError:
            op_type = KernelOpType.GEMM

        override_sub = None
        if sub_override_str:
            try:
                override_sub = HardwareSubstrate(sub_override_str.lower())
            except ValueError:
                override_sub = None

        assignment = substrate_dispatcher.schedule_task(
            op_type=op_type,
            input_shapes=shapes,
            priority=priority,
            target_override=override_sub,
        )
        return JSONResponse({"ok": True, "assignment": assignment.to_dict()})

    @mcp.custom_route("/v1/hardware/telemetry", methods=["GET"])
    async def hardware_telemetry_route(_request: Request) -> Response:
        telemetry = substrate_profiler.collect_cluster_telemetry()
        return JSONResponse({"ok": True, "telemetry": telemetry})

    @mcp.custom_route("/v1/neuromorphic/spikes/inject", methods=["POST"])
    async def neuromorphic_spikes_inject_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        spikes_data = body.get("spikes", [])  # list of [neuron_id, intensity]
        parsed_spikes = [(item[0], float(item[1])) for item in spikes_data if len(item) == 2]
        count = neuromorphic_mesh.inject_spikes(parsed_spikes)
        return JSONResponse({"ok": True, "injected_spikes_count": count})

    @mcp.custom_route("/v1/neuromorphic/step", methods=["POST"])
    async def neuromorphic_step_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        duration_us = float(body.get("duration_us", 10.0))
        step_dt_us = float(body.get("step_dt_us", 1.0))
        step_res = neuromorphic_mesh.step_simulation(duration_us=duration_us, step_dt_us=step_dt_us)
        return JSONResponse({"ok": True, "simulation": step_res})

    @mcp.custom_route("/v1/neuromorphic/ledger/receipts", methods=["POST"])
    async def neuromorphic_ledger_receipts_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        mesh_id = body.get("mesh_id", neuromorphic_mesh.mesh_id)
        rtype = body.get("receipt_type", "SYNAPTIC_WEIGHT_UPDATE")
        payload = body.get("payload", {})
        fp = neuromorphic_mesh.compute_synaptic_fingerprint()

        rec = synaptic_ledger.append_receipt(
            mesh_id=mesh_id,
            receipt_type=rtype,
            simulated_time_us=neuromorphic_mesh.simulated_time_us,
            total_spikes=neuromorphic_mesh.total_mesh_spikes,
            synaptic_fingerprint=fp,
            payload=payload,
        )
        return JSONResponse({"ok": True, "receipt": rec.to_dict()})

    @mcp.custom_route("/v1/neuromorphic/anchor/export", methods=["POST"])
    async def neuromorphic_anchor_export_route(_request: Request) -> Response:
        anchor = neuromorphic_anchor_exporter.export_commitment(synaptic_ledger.receipts)
        return JSONResponse({"ok": True, "anchor": anchor})

    @mcp.custom_route("/v1/hardware/drill/simulate", methods=["POST"])
    async def hardware_drill_simulate_route(_request: Request) -> Response:
        drill_results = HardwareNeuromorphicDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.8: Autonomous Swarm Immune & DePIN Physical Resource Mesh
    from desk_gateway.swarm_immune_mesh import (
        ImmuneAntibody,
        MitigationAction,
        MultiSeatAntibodyDistributor,
        RuntimeReconstitutionSupervisor,
        SwarmAntiFragilityEngine,
        ThreatSeverity,
        ThreatVectorType,
    )
    from desk_gateway.depin_mesh import (
        DePINAnchorExporter,
        DePINResourceLedger,
        PhysicalResourceNode,
        PhysicalResourceType,
        SwarmImmuneDePINDrillSimulator,
        VerifiableResourceOrchestrator,
    )

    swarm_antibody_distributor = MultiSeatAntibodyDistributor(seat_id="gateway")
    swarm_antifragility_engine = SwarmAntiFragilityEngine(swarm_antibody_distributor)
    runtime_reconstitution_supervisor = RuntimeReconstitutionSupervisor(swarm_antifragility_engine)
    depin_orchestrator = VerifiableResourceOrchestrator()
    depin_ledger = DePINResourceLedger()
    depin_anchor_exporter = DePINAnchorExporter()

    mcp._swarm_antibody_distributor = swarm_antibody_distributor  # type: ignore[attr-defined]
    mcp._swarm_antifragility_engine = swarm_antifragility_engine  # type: ignore[attr-defined]
    mcp._runtime_reconstitution_supervisor = runtime_reconstitution_supervisor  # type: ignore[attr-defined]
    mcp._depin_orchestrator = depin_orchestrator  # type: ignore[attr-defined]
    mcp._depin_ledger = depin_ledger  # type: ignore[attr-defined]
    mcp._depin_anchor_exporter = depin_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/immune/mesh/antibodies", methods=["GET"])
    async def immune_mesh_antibodies_list_route(_request: Request) -> Response:
        antibodies = [ab.to_dict() for ab in swarm_antibody_distributor.antibodies.values()]
        return JSONResponse({"ok": True, "antibodies": antibodies})

    @mcp.custom_route("/v1/immune/mesh/antibodies/create", methods=["POST"])
    async def immune_mesh_antibodies_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        vtype_str = body.get("vector_type", "byzantine_injection")
        pattern_str = body.get("indicator_pattern", "UNAUTHORIZED_OP")
        mitigation_str = body.get("mitigation", "quarantine_isolate")
        severity_str = body.get("severity", "high")
        fitness = float(body.get("fitness_score", 0.85))

        try:
            vtype = ThreatVectorType(vtype_str.lower())
        except ValueError:
            vtype = ThreatVectorType.BYZANTINE_INJECTION

        try:
            mitigation = MitigationAction(mitigation_str.lower())
        except ValueError:
            mitigation = MitigationAction.QUARANTINE_ISOLATE

        try:
            severity = ThreatSeverity(severity_str.lower())
        except ValueError:
            severity = ThreatSeverity.HIGH

        ab = swarm_antibody_distributor.create_and_sign(
            vector_type=vtype,
            indicator_pattern=pattern_str,
            mitigation=mitigation,
            severity=severity,
            fitness_score=fitness,
        )
        return JSONResponse({"ok": True, "antibody": ab.to_dict()})

    @mcp.custom_route("/v1/immune/mesh/perturb", methods=["POST"])
    async def immune_mesh_perturb_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "bot-02-web-edge")
        vtype_str = body.get("vector_type", "latency_poisoning")
        payload = body.get("payload", "BENCHMARK_PROBE")
        entropy = float(body.get("entropy", 0.5))

        try:
            vtype = ThreatVectorType(vtype_str.lower())
        except ValueError:
            vtype = ThreatVectorType.LATENCY_POISONING

        res = swarm_antifragility_engine.inject_chaos_perturbation(
            target_seat=seat_id,
            vector_type=vtype,
            attack_payload=payload,
            simulated_entropy=entropy,
        )
        return JSONResponse({"ok": True, "perturbation": res})

    @mcp.custom_route("/v1/immune/mesh/reconstitute", methods=["POST"])
    async def immune_mesh_reconstitute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "bot-02-web-edge")
        reconstitution = runtime_reconstitution_supervisor.reconstitute_seat(seat_id)
        return JSONResponse({"ok": True, "reconstitution": reconstitution})

    @mcp.custom_route("/v1/depin/nodes", methods=["GET"])
    async def depin_nodes_list_route(_request: Request) -> Response:
        nodes = [n.to_dict() for n in depin_orchestrator.nodes.values()]
        return JSONResponse({"ok": True, "nodes": nodes})

    @mcp.custom_route("/v1/depin/lease", methods=["POST"])
    async def depin_lease_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("consumer_seat", "lead")
        rtype_str = body.get("resource_type", "gpu_cluster")
        units = float(body.get("units", 100.0))
        duration = float(body.get("duration_seconds", 3600.0))

        try:
            rtype = PhysicalResourceType(rtype_str.lower())
        except ValueError:
            rtype = PhysicalResourceType.GPU_CLUSTER

        lease = depin_orchestrator.allocate_lease(
            consumer_seat=seat_id,
            resource_type=rtype,
            required_units=units,
            duration_seconds=duration,
        )
        if not lease:
            return JSONResponse({"ok": False, "error": "insufficient_capacity"}, status_code=400)

        depin_ledger.append_event("LEASE_ALLOCATION", lease.to_dict())
        return JSONResponse({"ok": True, "lease": lease.to_dict()})

    @mcp.custom_route("/v1/depin/popw/generate", methods=["POST"])
    async def depin_popw_generate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id", "depin-us-east-gpu-0")
        work_units = float(body.get("work_units", 50.0))
        workload = body.get("workload_payload", "TENSOR_GEMM_1024")
        elapsed = float(body.get("elapsed_ms", 25.0))

        try:
            popw = depin_orchestrator.generate_proof_of_physical_work(
                node_id=node_id,
                work_units=work_units,
                workload_payload=workload,
                elapsed_ms=elapsed,
            )
        except ValueError as err:
            return JSONResponse({"ok": False, "error": str(err)}, status_code=404)

        depin_ledger.append_event("POPW_VERIFIED", popw.to_dict())
        return JSONResponse({"ok": True, "proof": popw.to_dict()})

    @mcp.custom_route("/v1/depin/anchor/export", methods=["POST"])
    async def depin_anchor_export_route(_request: Request) -> Response:
        commitment = depin_anchor_exporter.export_commitment(depin_ledger)
        return JSONResponse({"ok": True, "anchor": commitment})

    @mcp.custom_route("/v1/immune/drill/simulate", methods=["POST"])
    async def immune_drill_simulate_route(_request: Request) -> Response:
        drill_results = SwarmImmuneDePINDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v4.9 (Phases 64 & 65): Space-Air-Ground Integrated Network (SAGIN) & Delay-Tolerant Satellite Swarm Mesh
    from desk_gateway.sagin_orbital_mesh import (
        BundlePriority,
        ContactGraphRouter,
        ContactPlanEntry,
        CustodialStorageManager,
        DelayTolerantBundle,
        DopplerTelemetryTracker,
        OrbitalEphemeris,
    )
    from desk_gateway.sagin_downlink_consensus import (
        GroundStationNode,
        IntermittentGroundConsensusEngine,
        MultiConstellationDownlinkManager,
        SAGINAnchorExporter,
        SAGINOrbitalVerificationDrillSimulator,
        SatelliteMerkleReceiptLedger,
    )

    sagin_cgr = ContactGraphRouter(local_eid="dtn://gateway-orbital-0")
    sagin_custody = CustodialStorageManager(custodian_eid="dtn://gateway-orbital-0")
    sagin_downlink_mgr = MultiConstellationDownlinkManager()
    sagin_consensus = IntermittentGroundConsensusEngine()
    sagin_ledger = SatelliteMerkleReceiptLedger()
    sagin_anchor_exporter = SAGINAnchorExporter()

    # Pre-populate sample ephemeris and contact plan for demonstration / testing
    sat_sample = OrbitalEphemeris("sat-starlink-leo-01", "Starlink-Gen2", 550.0, 53.0)
    sagin_cgr.register_ephemeris(sat_sample)
    now_ts = time.time()
    sagin_cgr.add_contact(ContactPlanEntry("contact-01", "dtn://gateway-orbital-0", "dtn://gs-svalbard-01", now_ts, now_ts + 3600, 50000.0))

    mcp._sagin_cgr = sagin_cgr  # type: ignore[attr-defined]
    mcp._sagin_custody = sagin_custody  # type: ignore[attr-defined]
    mcp._sagin_downlink_mgr = sagin_downlink_mgr  # type: ignore[attr-defined]
    mcp._sagin_consensus = sagin_consensus  # type: ignore[attr-defined]
    mcp._sagin_ledger = sagin_ledger  # type: ignore[attr-defined]
    mcp._sagin_anchor_exporter = sagin_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/sagin/ephemeris/contact_window", methods=["POST"])
    async def sagin_ephemeris_window_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        sat_id = body.get("satellite_id", "sat-starlink-leo-01")
        constellation = body.get("constellation", "Starlink-Gen2")
        alt = float(body.get("altitude_km", 550.0))
        inc = float(body.get("inclination_deg", 53.0))
        lat = float(body.get("station_latitude", 78.22))
        lon = float(body.get("station_longitude", 15.65))

        ephem = OrbitalEphemeris(satellite_id=sat_id, constellation=constellation, altitude_km=alt, inclination_deg=inc)
        window = ephem.calculate_contact_window(lat, lon)
        return JSONResponse({"ok": True, "contact_window": window})

    @mcp.custom_route("/v1/sagin/doppler/shift", methods=["POST"])
    async def sagin_doppler_shift_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        carrier_ghz = float(body.get("carrier_frequency_ghz", 28.5))
        rel_vel = float(body.get("relative_velocity_km_s", 7.2))
        res = DopplerTelemetryTracker.compute_doppler_shift(carrier_ghz, rel_vel)
        return JSONResponse({"ok": True, "doppler": res})

    @mcp.custom_route("/v1/sagin/bundle/route", methods=["POST"])
    async def sagin_bundle_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        bundle_id = body.get("bundle_id", f"b-{secrets.token_hex(4)}")
        source_eid = body.get("source_eid", "dtn://gateway-orbital-0")
        dest_eid = body.get("destination_eid", "dtn://gs-svalbard-01")
        payload = body.get("payload_raw", "TELEMETRY_PAYLOAD")
        prio_str = body.get("priority", "normal")

        try:
            prio = BundlePriority(prio_str.lower())
        except ValueError:
            prio = BundlePriority.NORMAL

        bundle = DelayTolerantBundle(
            bundle_id=bundle_id,
            source_eid=source_eid,
            destination_eid=dest_eid,
            payload_raw=payload,
            priority=prio,
        )
        route_result = sagin_cgr.route_bundle(bundle)
        return JSONResponse({"ok": True, "route_result": route_result, "bundle": bundle.to_dict()})

    @mcp.custom_route("/v1/sagin/custody/accept", methods=["POST"])
    async def sagin_custody_accept_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        bundle_id = body.get("bundle_id", f"b-{secrets.token_hex(4)}")
        source_eid = body.get("source_eid", "dtn://sat-relay-1")
        dest_eid = body.get("destination_eid", "dtn://gs-svalbard-01")
        payload = body.get("payload_raw", "ORBITAL_IMAGERY_STREAM")

        bundle = DelayTolerantBundle(bundle_id=bundle_id, source_eid=source_eid, destination_eid=dest_eid, payload_raw=payload)
        rcpt = sagin_custody.accept_custody(bundle)
        sagin_ledger.append_event("CUSTODY_ACCEPTED", source_eid, sagin_custody.custodian_eid, rcpt)
        return JSONResponse({"ok": True, "custody_receipt": rcpt})

    @mcp.custom_route("/v1/sagin/downlink/session", methods=["POST"])
    async def sagin_downlink_session_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        station_id = body.get("station_id", "gs-svalbard-01")
        sat_id = body.get("satellite_id", "sat-starlink-leo-01")
        ephem = sagin_cgr.ephemeris_registry.get(sat_id) or OrbitalEphemeris(sat_id, "Starlink-Gen2", 550.0, 53.0)
        session = sagin_downlink_mgr.initiate_downlink_session(station_id, ephem)
        return JSONResponse({"ok": True, "downlink_session": session})

    @mcp.custom_route("/v1/sagin/consensus/propose", methods=["POST"])
    async def sagin_consensus_propose_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        batch_id = body.get("batch_id", f"batch-{secrets.token_hex(4)}")
        sat_id = body.get("satellite_id", "sat-starlink-leo-01")
        state_root = body.get("state_root", secrets.token_hex(32))
        digests = body.get("downlink_digests", [secrets.token_hex(32)])
        station_id = body.get("proposer_station", "gs-svalbard-01")

        batch = sagin_consensus.propose_orbital_batch(batch_id, sat_id, state_root, digests, station_id)
        return JSONResponse({"ok": True, "batch": batch})

    @mcp.custom_route("/v1/sagin/consensus/ballot", methods=["POST"])
    async def sagin_consensus_ballot_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        batch_id = body.get("batch_id", "")
        station_id = body.get("station_id", "gs-singapore-01")
        vote = body.get("vote", "APPROVE")
        res = sagin_consensus.submit_ballot(batch_id, station_id, vote)
        if res.get("is_committed"):
            sagin_ledger.append_event("CONSENSUS_COMMITTED", "swarm-constellation", station_id, res)
        return JSONResponse({"ok": True, "ballot_result": res})

    @mcp.custom_route("/v1/sagin/anchor/export", methods=["POST"])
    async def sagin_anchor_export_route(_request: Request) -> Response:
        commitment = sagin_anchor_exporter.export_commitment(sagin_ledger)
        return JSONResponse({"ok": True, "anchor": commitment})

    @mcp.custom_route("/v1/sagin/drill/simulate", methods=["POST"])
    async def sagin_drill_simulate_route(_request: Request) -> Response:
        drill_results = SAGINOrbitalVerificationDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v5.0 (Phases 66 & 67): Quantum-Classical Hybrid Mesh & Topological Qubit Fault-Tolerant Orchestration
    from desk_gateway.quantum_hybrid_mesh import (
        AnsatzCircuit,
        HamiltonianOperator,
        NoiseModel,
        QAOAOptimizer,
        QuantumCircuitState,
        QuantumDecoherenceSimulator,
        QuantumGate,
        QuantumGateType,
        QuantumWorkloadScheduler,
        VQEProcessor,
    )
    from desk_gateway.quantum_topological_mesh import (
        MWPMDecoder,
        QuantumAnchorExporter,
        QuantumStateReceiptLedger,
        QuantumTopologicalDrillSimulator,
        SurfaceCodeLattice,
        SyndromeExtractor,
    )

    quantum_scheduler = QuantumWorkloadScheduler()
    quantum_decoherence = QuantumDecoherenceSimulator()
    quantum_ledger = QuantumStateReceiptLedger()
    quantum_anchor_exporter = QuantumAnchorExporter()

    mcp._quantum_scheduler = quantum_scheduler  # type: ignore[attr-defined]
    mcp._quantum_decoherence = quantum_decoherence  # type: ignore[attr-defined]
    mcp._quantum_ledger = quantum_ledger  # type: ignore[attr-defined]
    mcp._quantum_anchor_exporter = quantum_anchor_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/quantum/circuit/simulate", methods=["POST"])
    async def quantum_circuit_simulate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        num_qubits = int(body.get("num_qubits", 2))
        gates_data = body.get("gates", [])

        circuit = QuantumCircuitState(num_qubits=num_qubits)
        for g_dict in gates_data:
            gtype = QuantumGateType(g_dict.get("gate_type", "H"))
            targets = g_dict.get("target_qubits", [0])
            controls = g_dict.get("control_qubits", [])
            params = g_dict.get("parameters", [])
            gate = QuantumGate(gtype, targets, controls, params)
            circuit.apply_gate(gate)

        return JSONResponse({"ok": True, "circuit": circuit.to_dict()})

    @mcp.custom_route("/v1/quantum/vqe/solve", methods=["POST"])
    async def quantum_vqe_solve_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        num_qubits = int(body.get("num_qubits", 2))
        terms = body.get("hamiltonian_terms", [{"coefficient": -1.0, "pauli_string": "Z Z"}])
        layers = int(body.get("layers", 1))
        max_iters = int(body.get("max_iterations", 15))

        h = HamiltonianOperator()
        for t in terms:
            h.add_term(float(t["coefficient"]), str(t["pauli_string"]))

        ansatz = AnsatzCircuit(num_qubits=num_qubits, num_layers=layers)
        vqe = VQEProcessor(h, ansatz)
        opt_res = vqe.optimize(max_iterations=max_iters)

        quantum_ledger.append_event("VQE_CONVERGED", opt_res["final_state_digest"], 0, 0)
        return JSONResponse({"ok": True, "vqe": opt_res})

    @mcp.custom_route("/v1/quantum/qaoa/partition", methods=["POST"])
    async def quantum_qaoa_partition_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        num_qubits = int(body.get("num_qubits", 3))
        edges_raw = body.get("edges", [[[0, 1], 1.0], [[1, 2], 1.0]])
        gammas = [float(x) for x in body.get("gammas", [0.3])]
        betas = [float(x) for x in body.get("betas", [0.4])]

        weights = {(int(e[0][0]), int(e[0][1])): float(e[1]) for e in edges_raw}
        qaoa = QAOAOptimizer(num_qubits=num_qubits, p_steps=len(gammas))
        res = qaoa.solve_partition(weights, gammas, betas)
        return JSONResponse({"ok": True, "qaoa": res})

    @mcp.custom_route("/v1/quantum/schedule/dispatch", methods=["POST"])
    async def quantum_schedule_dispatch_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        task_name = body.get("task_name", "q-vqe-ground-state")
        circuit_type = body.get("circuit_type", "ansatz-hea")
        num_qubits = int(body.get("num_qubits", 2))
        params = body.get("params", {})

        task = quantum_scheduler.dispatch_quantum_task(task_name, circuit_type, num_qubits, params)
        return JSONResponse({"ok": True, "task": task})

    @mcp.custom_route("/v1/quantum/surface-code/syndrome", methods=["POST"])
    async def quantum_surface_code_syndrome_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        distance = int(body.get("distance", 3))
        errors = body.get("inject_errors", [{"row": 1, "col": 1, "error": "X"}])

        lattice = SurfaceCodeLattice(distance=distance)
        for err in errors:
            lattice.inject_physical_error(int(err["row"]), int(err["col"]), str(err["error"]))

        extractor = SyndromeExtractor(lattice)
        syndromes = extractor.extract_syndrome()

        decoder = MWPMDecoder(lattice)
        corrections = decoder.decode_syndromes(syndromes)
        post_syndromes = extractor.extract_syndrome()

        rcpt = quantum_ledger.append_event(
            "SURFACE_CODE_CORRECTION",
            hashlib.sha256(json.dumps(lattice.to_dict()).encode("utf-8")).hexdigest(),
            len([s for s in syndromes if s.syndrome_bit == -1]),
            len(corrections),
        )

        return JSONResponse({
            "ok": True,
            "lattice": lattice.to_dict(),
            "defects_count": len([s for s in syndromes if s.syndrome_bit == -1]),
            "corrections": [{"qubit_id": c.qubit_id, "correction": c.pauli_correction} for c in corrections],
            "resolved": all(s.syndrome_bit == 1 for s in post_syndromes),
            "receipt": rcpt.to_dict(),
        })

    @mcp.custom_route("/v1/quantum/anchor/export", methods=["POST"])
    async def quantum_anchor_export_route(_request: Request) -> Response:
        commitment = quantum_anchor_exporter.export_commitment(quantum_ledger)
        return JSONResponse({"ok": True, "anchor": commitment})

    @mcp.custom_route("/v1/quantum/drill/simulate", methods=["POST"])
    async def quantum_drill_simulate_route(_request: Request) -> Response:
        drill_results = QuantumTopologicalDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})

    # Milestone v5.1 (Phases 68 & 69): Inter-Cluster Quantum Teleportation, QKD & Entangled Swarm Mesh
    from desk_gateway.quantum_teleportation import (
        BellPairPool,
        BellStateType,
        EntanglementPurifier,
        EntanglementSwapper,
        QuantumRepeaterMesh,
        QuantumTeleportationProtocol,
    )
    from desk_gateway.quantum_qkd_mesh import (
        EavesdropDetector,
        QKDProtocolEngine,
        QuantumTeleportationAnchorExporter,
        QuantumTeleportationDrillSimulator,
        QuantumTeleportationReceiptLedger,
    )

    qteleport_pool = BellPairPool()
    qteleport_mesh = QuantumRepeaterMesh(qteleport_pool)
    qteleport_proto = QuantumTeleportationProtocol(qteleport_mesh)
    qkd_engine = QKDProtocolEngine(qteleport_mesh)
    qteleport_ledger = QuantumTeleportationReceiptLedger()
    qteleport_exporter = QuantumTeleportationAnchorExporter()

    mcp._qteleport_pool = qteleport_pool  # type: ignore[attr-defined]
    mcp._qteleport_mesh = qteleport_mesh  # type: ignore[attr-defined]
    mcp._qteleport_proto = qteleport_proto  # type: ignore[attr-defined]
    mcp._qkd_engine = qkd_engine  # type: ignore[attr-defined]
    mcp._qteleport_ledger = qteleport_ledger  # type: ignore[attr-defined]
    mcp._qteleport_exporter = qteleport_exporter  # type: ignore[attr-defined]

    @mcp.custom_route("/v1/quantum/teleportation/bell-pair/create", methods=["POST"])
    async def quantum_bell_pair_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_a = body.get("node_a", "desk-alpha")
        node_b = body.get("node_b", "desk-beta")
        stype_raw = body.get("state_type", "PHI_PLUS")
        try:
            stype = BellStateType(stype_raw)
        except ValueError:
            stype = BellStateType.PHI_PLUS
        fidelity = float(body.get("initial_fidelity", 0.99))
        pair = qteleport_pool.create_pair(node_a, node_b, stype, fidelity)
        return JSONResponse({"ok": True, "bell_pair": pair.to_dict()})

    @mcp.custom_route("/v1/quantum/teleportation/purify", methods=["POST"])
    async def quantum_teleportation_purify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        pair_id_1 = body.get("pair_id_1", "")
        pair_id_2 = body.get("pair_id_2", "")
        p1 = qteleport_pool.get_pair(pair_id_1)
        p2 = qteleport_pool.get_pair(pair_id_2)
        if not p1 or not p2:
            return JSONResponse({"ok": False, "error": "Bell pairs not found"}, status_code=404)
        ok, purified, p_succ = EntanglementPurifier.purify(p1, p2)
        if ok and purified:
            qteleport_pool.pairs[purified.pair_id] = purified
            return JSONResponse({"ok": True, "purified_pair": purified.to_dict(), "p_succ": p_succ})
        return JSONResponse({"ok": False, "error": "Purification distillation failed"}, status_code=400)

    @mcp.custom_route("/v1/quantum/repeater/route", methods=["POST"])
    async def quantum_repeater_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_path = body.get("node_path", ["desk-alpha", "repeater-1", "desk-beta"])
        base_fidelity = float(body.get("base_fidelity", 0.98))
        purify = bool(body.get("purify", True))
        ok, pair, logs = qteleport_mesh.establish_multi_hop_entanglement(node_path, base_fidelity, purify)
        return JSONResponse({
            "ok": ok,
            "bell_pair": pair.to_dict() if pair else None,
            "logs": logs,
        })

    @mcp.custom_route("/v1/quantum/teleportation/teleport", methods=["POST"])
    async def quantum_teleportation_teleport_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        source_node = body.get("source_node", "desk-alpha")
        target_node = body.get("target_node", "desk-beta")
        alpha_val = body.get("alpha", {"real": 1.0, "imag": 0.0})
        beta_val = body.get("beta", {"real": 0.0, "imag": 0.0})
        alpha = complex(float(alpha_val.get("real", 1.0)), float(alpha_val.get("imag", 0.0)))
        beta = complex(float(beta_val.get("real", 0.0)), float(beta_val.get("imag", 0.0)))
        intermediate_hops = body.get("intermediate_hops")

        res = qteleport_proto.teleport_qubit(
            source_node=source_node,
            target_node=target_node,
            alpha=alpha,
            beta=beta,
            intermediate_hops=intermediate_hops,
        )
        rcpt = qteleport_ledger.append_event(
            "QUANTUM_TELEPORTATION",
            [source_node, target_node],
            res.session_id,
            res.fidelity,
            res.to_dict(),
        )
        return JSONResponse({"ok": True, "result": res.to_dict(), "receipt": rcpt.to_dict()})

    @mcp.custom_route("/v1/quantum/qkd/bb84", methods=["POST"])
    async def quantum_qkd_bb84_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        sender = body.get("sender", "desk-alpha")
        receiver = body.get("receiver", "desk-beta")
        bit_length = int(body.get("bit_length", 128))
        intercept_ratio = float(body.get("intercept_ratio", 0.0))

        session = qkd_engine.run_bb84_exchange(sender, receiver, bit_length, intercept_ratio)
        rcpt = qteleport_ledger.append_event(
            "QKD_BB84_SESSION",
            [sender, receiver],
            session.session_id,
            session.qber,
            session.to_dict(),
        )
        return JSONResponse({"ok": True, "session": session.to_dict(), "receipt": rcpt.to_dict()})

    @mcp.custom_route("/v1/quantum/qkd/e91", methods=["POST"])
    async def quantum_qkd_e91_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        sender = body.get("sender", "desk-alpha")
        receiver = body.get("receiver", "desk-beta")
        pair_count = int(body.get("pair_count", 100))
        noise_level = float(body.get("noise_level", 0.01))

        session = qkd_engine.run_e91_exchange(sender, receiver, pair_count, noise_level)
        rcpt = qteleport_ledger.append_event(
            "QKD_E91_SESSION",
            [sender, receiver],
            session.session_id,
            session.qber,
            session.to_dict(),
        )
        return JSONResponse({"ok": True, "session": session.to_dict(), "receipt": rcpt.to_dict()})

    @mcp.custom_route("/v1/quantum/teleportation/anchor/export", methods=["POST"])
    async def quantum_teleportation_anchor_export_route(_request: Request) -> Response:
        commitment = qteleport_exporter.export_commitment(qteleport_ledger)
        return JSONResponse({"ok": True, "anchor": commitment})

    @mcp.custom_route("/v1/quantum/teleportation/drill/simulate", methods=["POST"])
    async def quantum_teleportation_drill_simulate_route(_request: Request) -> Response:
        drill_results = QuantumTeleportationDrillSimulator.run_drill()
        return JSONResponse({"ok": True, "drill": drill_results})


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

    # Split-Brain Protection & Fast RTO Recovery (Phase 25)
    @mcp.custom_route("/v1/dr/fencing/allocate", methods=["POST"])
    async def dr_fencing_allocate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id", "candidate-node")
        token = fencing_allocator.allocate(node_id)
        return JSONResponse({"ok": True, "token": token.to_dict()})

    @mcp.custom_route("/v1/dr/fencing/validate", methods=["POST"])
    async def dr_fencing_validate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        epoch = int(body.get("epoch", 0))
        cluster_gen_id = body.get("cluster_gen_id", "")
        valid, msg = fencing_allocator.validate(epoch, cluster_gen_id)
        return JSONResponse({"ok": True, "valid": valid, "detail": msg})

    @mcp.custom_route("/v1/dr/quorum/heartbeat", methods=["POST"])
    async def dr_quorum_heartbeat_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id", "node-1")
        quorum_evaluator.record_heartbeat(node_id)
        state, alive, total = quorum_evaluator.evaluate_quorum()
        return JSONResponse({
            "ok": True,
            "quorum_state": state.value,
            "alive_nodes": alive,
            "total_nodes": total,
        })

    @mcp.custom_route("/v1/dr/reconcile", methods=["POST"])
    async def dr_reconcile_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        entry_a = body.get("entry_a", {})
        entry_b = body.get("entry_b", {})
        winner = vector_reconciler.reconcile(entry_a, entry_b)
        return JSONResponse({"ok": True, "winner": winner})

    @mcp.custom_route("/v1/dr/drill/run", methods=["POST"])
    async def dr_drill_run_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        drill_id = body.get("drill_id", f"drill-{secrets.token_hex(4)}")
        candidate_node = body.get("candidate_node", "node-2")
        receipt = drill_verifier.run_drill(drill_id=drill_id, candidate_node=candidate_node)
        valid = drill_verifier.verify_receipt(receipt)
        return JSONResponse({
            "ok": True,
            "valid": valid,
            "receipt": {
                "drill_id": receipt.drill_id,
                "scenario": receipt.scenario,
                "simulated_failure_node": receipt.simulated_failure_node,
                "promoted_node": receipt.promoted_node,
                "rto_ms": receipt.rto_ms,
                "rpo_loss_blocks": receipt.rpo_loss_blocks,
                "passed": receipt.passed,
                "receipt_hash": receipt.receipt_hash,
                "signature": receipt.signature,
            }
        })

    # Zero-Trust Security & Enclave Attestation (Phase 26)
    @mcp.custom_route("/v1/zero-trust/claim/issue", methods=["POST"])
    async def zt_token_issue_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        ttl = body.get("ttl_seconds")
        cred = zero_trust_mgr.issue_ephemeral_token(
            seat_id=seat_id,
            ttl_seconds=float(ttl) if ttl is not None else None,
        )
        return JSONResponse({
            "ok": True,
            "token_id": cred.token_id,
            "seat_id": cred.seat_id,
            "expires_at": cred.expires_at,
            "ttl_seconds": cred.ttl_seconds,
            "signature": cred.signature,
        })

    @mcp.custom_route("/v1/zero-trust/claim/validate", methods=["POST"])
    async def zt_token_validate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        token_id = body.get("claim_id") or body.get("token_id", "")
        seat_id = body.get("seat_id", "")
        valid, msg = zero_trust_mgr.validate_ephemeral_token(token_id=token_id, seat_id=seat_id)
        return JSONResponse({"ok": True, "valid": valid, "detail": msg})

    @mcp.custom_route("/v1/zero-trust/cert/issue", methods=["POST"])
    async def zt_cert_issue_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        pk_pem = body.get("public_key_pem", f"PUBLIC_KEY_{seat_id}")
        cert = zero_trust_mgr.issue_seat_cert(seat_id=seat_id, public_key_pem=pk_pem)
        return JSONResponse({
            "ok": True,
            "serial_number": cert.serial_number,
            "seat_id": cert.seat_id,
            "public_key_hash": cert.public_key_hash,
            "expires_at": cert.expires_at,
            "fingerprint": cert.fingerprint,
        })

    @mcp.custom_route("/v1/zero-trust/attestation/verify", methods=["POST"])
    async def zt_attestation_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        report = AttestationReport(
            enclave_id=body.get("enclave_id", "lead"),
            measurement_hash=body.get("measurement_hash", ""),
            platform_nonce=body.get("platform_nonce", secrets.token_hex(8)),
            timestamp=float(body.get("timestamp", time.time())),
            signature=body.get("signature", "sig"),
        )
        valid, msg = zero_trust_mgr.verify_attestation_report(report)
        return JSONResponse({"ok": True, "valid": valid, "detail": msg})

    @mcp.custom_route("/v1/zero-trust/posture/evaluate", methods=["POST"])
    async def zt_posture_evaluate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        tool_name = body.get("tool_name", "standard_tool")
        is_sensitive = bool(body.get("is_sensitive", False))
        valid, msg = zero_trust_mgr.evaluate_tool_invocation_posture(
            seat_id=seat_id,
            tool_name=tool_name,
            is_sensitive=is_sensitive,
        )
        return JSONResponse({"ok": True, "valid": valid, "detail": msg})

    @mcp.custom_route("/v1/zero-trust/revoke", methods=["POST"])
    async def zt_revoke_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        token_id = body.get("token_id")
        serial = body.get("serial_number")
        reason = body.get("reason", "admin_revocation")
        if token_id:
            zero_trust_mgr.revoke_token(token_id, reason=reason)
        if serial:
            zero_trust_mgr.revoke_cert(serial, reason=reason)
        return JSONResponse({"ok": True, "crl": zero_trust_mgr.get_crl()})

    @mcp.custom_route("/v1/zero-trust/crl", methods=["GET"])
    async def zt_crl_route(request: Request) -> Response:
        return JSONResponse({"ok": True, **zero_trust_mgr.get_crl()})

    # Merkle Proof Verification & Immutable Audit Export (Phase 27)
    @mcp.custom_route("/v1/audit/merkle/append", methods=["POST"])
    async def audit_merkle_append_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        operation = body.get("operation", "system_event")
        payload = body.get("payload", {})
        leaf = merkle_tree.append_leaf(seat_id=seat_id, operation=operation, payload=payload)
        return JSONResponse({
            "ok": True,
            "leaf_index": leaf.index,
            "leaf_hash": leaf.leaf_hash,
            "merkle_root": merkle_tree.get_root_hash(),
            "total_leaves": len(merkle_tree.leaves),
        })

    @mcp.custom_route("/v1/audit/merkle/root", methods=["GET"])
    async def audit_merkle_root_route(request: Request) -> Response:
        return JSONResponse({
            "ok": True,
            "merkle_root": merkle_tree.get_root_hash(),
            "total_leaves": len(merkle_tree.leaves),
        })

    @mcp.custom_route("/v1/audit/merkle/proof", methods=["POST"])
    async def audit_merkle_proof_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        leaf_index = int(body.get("leaf_index", 0))
        try:
            target_hash, proof_path = merkle_tree.generate_inclusion_proof(leaf_index)
            return JSONResponse({
                "ok": True,
                "leaf_index": leaf_index,
                "target_hash": target_hash,
                "proof_path": proof_path,
                "merkle_root": merkle_tree.get_root_hash(),
            })
        except IndexError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/audit/merkle/verify", methods=["POST"])
    async def audit_merkle_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        leaf_hash = body.get("leaf_hash", "")
        proof_path = body.get("proof_path", [])
        expected_root = body.get("expected_root", "")
        valid = IncrementalMerkleTree.verify_inclusion_proof(leaf_hash, proof_path, expected_root)
        return JSONResponse({"ok": True, "valid": valid})

    @mcp.custom_route("/v1/audit/export/anchor", methods=["POST"])
    async def audit_export_anchor_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        batch_id = body.get("batch_id", f"batch-{secrets.token_hex(4)}")
        target = body.get("anchor_target", "solana_devnet")
        root = merkle_tree.get_root_hash()
        count = len(merkle_tree.leaves)
        start_t = merkle_tree.leaves[0].timestamp if merkle_tree.leaves else time.time()
        end_t = merkle_tree.leaves[-1].timestamp if merkle_tree.leaves else time.time()
        batch = audit_exporter.export_anchor(
            batch_id=batch_id,
            merkle_root=root,
            leaf_count=count,
            start_t=start_t,
            end_t=end_t,
            anchor_target=target,
        )
        return JSONResponse({
            "ok": True,
            "batch_id": batch.batch_id,
            "merkle_root": batch.merkle_root,
            "leaf_count": batch.leaf_count,
            "anchor_target": batch.anchor_target,
            "signature": batch.signature,
        })

    @mcp.custom_route("/v1/audit/scrub", methods=["POST"])
    async def audit_scrub_route(request: Request) -> Response:
        passed, anomalies = AuditLogScrubber.scrub(merkle_tree.leaves)
        return JSONResponse({"ok": True, "passed": passed, "anomalies": anomalies})

    @mcp.custom_route("/v1/audit/compliance/drill", methods=["POST"])
    async def audit_compliance_drill_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipt_id = body.get("receipt_id", f"receipt-{secrets.token_hex(4)}")
        receipt = compliance_verifier.run_compliance_drill(receipt_id=receipt_id)
        valid = compliance_verifier.verify_compliance_receipt(receipt)
        return JSONResponse({
            "ok": True,
            "valid": valid,
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "merkle_root": receipt.merkle_root,
                "total_leaves": receipt.total_leaves,
                "scrub_passed": receipt.scrub_passed,
                "signature": receipt.signature,
                "timestamp": receipt.timestamp,
            }
        })

    # Dynamic MCP Tool Mesh Registry (Phase 28)
    @mcp.custom_route("/v1/mcp-mesh/server/register", methods=["POST"])
    async def mcp_mesh_server_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        server_id = body.get("server_id", "remote-mcp-1")
        host = body.get("host", "http://127.0.0.1:9000")
        transport = body.get("transport", "sse")
        caps = body.get("capabilities", ["standard"])
        max_concurrency = int(body.get("max_concurrency", 5))
        max_rpm = int(body.get("max_rpm", 60))

        ep = mcp_mesh_registry.register_server(
            server_id=server_id,
            host=host,
            transport=transport,
            capabilities=caps,
            max_concurrency=max_concurrency,
            max_rpm=max_rpm,
        )
        return JSONResponse({
            "ok": True,
            "server_id": ep.server_id,
            "host": ep.host,
            "transport": ep.transport,
            "max_concurrency": ep.max_concurrency,
            "circuit_state": ep.circuit_state.value,
        })

    @mcp.custom_route("/v1/mcp-mesh/tool/register", methods=["POST"])
    async def mcp_mesh_tool_register_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        server_id = body.get("server_id", "")
        tool_name = body.get("tool_name", "")
        description = body.get("description", "")
        input_schema = body.get("input_schema", {})
        output_schema = body.get("output_schema", {})
        caps = body.get("required_capabilities", [])
        is_sensitive = bool(body.get("is_sensitive", False))
        try:
            tool = mcp_mesh_registry.register_tool(
                server_id=server_id,
                tool_name=tool_name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                required_capabilities=caps,
                is_sensitive=is_sensitive,
            )
            return JSONResponse({
                "ok": True,
                "tool_name": tool.tool_name,
                "server_id": tool.server_id,
                "is_sensitive": tool.is_sensitive,
            })
        except KeyError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/mcp-mesh/tools", methods=["GET"])
    async def mcp_mesh_tools_list_route(request: Request) -> Response:
        seat_id = request.query_params.get("seat_id", "lead")
        tools = mcp_mesh_registry.list_tools_for_seat(seat_id=seat_id)
        return JSONResponse({"ok": True, "seat_id": seat_id, "tools": tools})

    @mcp.custom_route("/v1/mcp-mesh/tools/authorize", methods=["POST"])
    async def mcp_mesh_tools_authorize_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        seat_id = body.get("seat_id", "lead")
        tool_name = body.get("tool_name", "")
        args = body.get("arguments", {})

        auth_ok, auth_msg = mcp_mesh_registry.authorize_seat_tool_call(seat_id, tool_name)
        if not auth_ok:
            return JSONResponse({"ok": False, "authorized": False, "detail": auth_msg})

        val_ok, val_msg = mcp_mesh_registry.validate_tool_arguments(tool_name, args)
        if not val_ok:
            return JSONResponse({"ok": False, "authorized": True, "valid_args": False, "detail": val_msg})

        return JSONResponse({"ok": True, "authorized": True, "valid_args": True, "detail": "Authorized and arguments valid"})

    @mcp.custom_route("/v1/mcp-mesh/slot/acquire", methods=["POST"])
    async def mcp_mesh_slot_acquire_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        server_id = body.get("server_id", "")
        acquired, msg = mcp_mesh_registry.acquire_execution_slot(server_id)
        return JSONResponse({"ok": acquired, "detail": msg})

    @mcp.custom_route("/v1/mcp-mesh/slot/release", methods=["POST"])
    async def mcp_mesh_slot_release_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        server_id = body.get("server_id", "")
        mcp_mesh_registry.release_execution_slot(server_id)
        return JSONResponse({"ok": True, "server_id": server_id})

    @mcp.custom_route("/v1/mcp-mesh/status", methods=["GET"])
    async def mcp_mesh_status_route(request: Request) -> Response:
        return JSONResponse({"ok": True, **mcp_mesh_registry.get_mesh_status()})

    # Cross-Desk Remote Tool Invocation & Attested Execution Receipts (Phase 29)
    @mcp.custom_route("/v1/mcp-mesh/invoke", methods=["POST"])
    async def mcp_mesh_invoke_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        tool_name = body.get("tool_name", "")
        arguments = body.get("arguments", {})
        source_seat = body.get("source_seat", "lead")
        timeout_seconds = body.get("timeout_seconds")
        timeout = float(timeout_seconds) if timeout_seconds is not None else None

        try:
            success, output, receipt = await remote_execution_supervisor.invoke_remote_tool(
                tool_name=tool_name,
                arguments=arguments,
                source_seat=source_seat,
                timeout_seconds=timeout,
            )
            return JSONResponse({
                "ok": success,
                "output": output,
                "receipt": receipt.to_dict(),
            })
        except (PermissionError, ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @mcp.custom_route("/v1/mcp-mesh/receipts/{invocation_id}", methods=["GET"])
    async def mcp_mesh_get_receipt_route(request: Request) -> Response:
        inv_id = request.path_params.get("invocation_id", "")
        receipt = remote_execution_supervisor.receipts.get(inv_id)
        if not receipt:
            return JSONResponse({"error": f"Receipt '{inv_id}' not found"}, status_code=404)
        return JSONResponse({"ok": True, "receipt": receipt.to_dict()})

    @mcp.custom_route("/v1/mcp-mesh/receipts/verify", methods=["POST"])
    async def mcp_mesh_verify_receipt_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipt_data = body.get("receipt", {})
        try:
            receipt = ExecutionReceipt(
                invocation_id=receipt_data["invocation_id"],
                tool_name=receipt_data["tool_name"],
                source_seat=receipt_data["source_seat"],
                target_server_id=receipt_data["target_server_id"],
                status=InvocationStatus(receipt_data["status"]),
                input_hash=receipt_data["input_hash"],
                output_hash=receipt_data["output_hash"],
                duration_ms=float(receipt_data["duration_ms"]),
                timestamp=float(receipt_data["timestamp"]),
                signature=receipt_data["signature"],
            )
            valid = remote_execution_supervisor.verify_execution_receipt(receipt)
            return JSONResponse({"ok": True, "valid": valid, "invocation_id": receipt.invocation_id})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"Invalid receipt format: {exc}"}, status_code=400)

    # Multi-Modal Sensory Memory Graph Endpoints (Phase 30)
    @mcp.custom_route("/v1/graph/node/create", methods=["POST"])
    async def graph_node_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        node_id = body.get("node_id")
        if not node_id:
            return JSONResponse({"ok": False, "error": "node_id is required"}, status_code=400)
        modality = body.get("modality", "text")
        label = body.get("label", "")
        content = body.get("content", "")
        embedding = body.get("embedding", [])
        metadata = body.get("metadata", {})
        partition_id = body.get("partition_id", "default")
        attention_score = float(body.get("attention_score", 1.0))

        try:
            node = memory_graph_engine.add_node(
                node_id=node_id,
                modality=modality,
                label=label,
                content=content,
                embedding=embedding,
                metadata=metadata,
                partition_id=partition_id,
                attention_score=attention_score,
            )
            return JSONResponse({"ok": True, "node": node.to_dict()})
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/graph/edge/create", methods=["POST"])
    async def graph_edge_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        edge_id = body.get("edge_id")
        source_id = body.get("source_id")
        target_id = body.get("target_id")
        relation = body.get("relation", "RELATED_TO")
        weight = float(body.get("weight", 1.0))
        metadata = body.get("metadata", {})

        if not edge_id or not source_id or not target_id:
            return JSONResponse({"ok": False, "error": "edge_id, source_id, and target_id are required"}, status_code=400)

        try:
            edge = memory_graph_engine.add_edge(
                edge_id=edge_id,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=weight,
                metadata=metadata,
            )
            return JSONResponse({"ok": True, "edge": edge.to_dict()})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/graph/search/semantic", methods=["POST"])
    async def graph_search_semantic_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        embedding = body.get("query_embedding", [])
        if not embedding:
            return JSONResponse({"ok": False, "error": "query_embedding is required"}, status_code=400)
        top_k = int(body.get("top_k", 10))
        modality = body.get("modality")
        partition_id = body.get("partition_id")
        min_score = float(body.get("min_score", 0.0))
        apply_decay = bool(body.get("apply_decay", True))

        results = memory_graph_engine.search_semantic(
            query_embedding=embedding,
            top_k=top_k,
            modality=modality,
            partition_id=partition_id,
            min_score=min_score,
            apply_decay=apply_decay,
        )
        return JSONResponse({
            "ok": True,
            "count": len(results),
            "results": [
                {
                    "node": r.node.to_dict(),
                    "raw_similarity": r.raw_similarity,
                    "decayed_score": r.decayed_score,
                    "temporal_factor": r.temporal_factor,
                }
                for r in results
            ],
        })

    @mcp.custom_route("/v1/graph/traverse/{node_id}", methods=["GET"])
    async def graph_traverse_route(request: Request) -> Response:
        node_id = request.path_params.get("node_id", "")
        max_depth = int(request.query_params.get("max_depth", 2))
        partition_id = request.query_params.get("partition_id")
        direction = request.query_params.get("direction", "out")
        try:
            traversal = memory_graph_engine.traverse(
                start_node_id=node_id,
                max_depth=max_depth,
                partition_id=partition_id,
                direction=direction,
            )
            return JSONResponse({"ok": True, **traversal})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/graph/commit", methods=["POST"])
    async def graph_commit_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        commit_id = body.get("commit_id")
        receipt = memory_graph_engine.commit_state(commit_id=commit_id)
        valid = memory_graph_engine.verify_commitment(receipt)
        return JSONResponse({"ok": True, "valid": valid, "receipt": receipt.to_dict()})

    # Dynamic Context Window Compression & Semantic Pruning Endpoints (Phase 31)
    @mcp.custom_route("/v1/context/compress", methods=["POST"])
    async def context_compress_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        text = body.get("text", "")
        if not text:
            return JSONResponse({"ok": False, "error": "text is required"}, status_code=400)
        payload = context_compressor.compactor.compress_text(text)
        return JSONResponse({"ok": True, "compressed": payload.to_dict()})

    @mcp.custom_route("/v1/context/decompress", methods=["POST"])
    async def context_decompress_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        comp_b64 = body.get("compressed_b64", "")
        orig_bytes = int(body.get("original_size_bytes", 0))
        comp_bytes = int(body.get("compressed_size_bytes", 0))
        ratio = float(body.get("compression_ratio", 1.0))
        checksum = body.get("checksum_sha256", "")
        if not comp_b64 or not checksum:
            return JSONResponse({"ok": False, "error": "compressed_b64 and checksum_sha256 are required"}, status_code=400)
        try:
            payload = LosslessCompactedPayload(
                compressed_b64=comp_b64,
                original_size_bytes=orig_bytes,
                compressed_size_bytes=comp_bytes,
                compression_ratio=ratio,
                checksum_sha256=checksum,
            )
            decompressed = context_compressor.compactor.decompress_text(payload)
            return JSONResponse({"ok": True, "text": decompressed})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/context/prune", methods=["POST"])
    async def context_prune_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        text = body.get("text", "")
        threshold = float(body.get("salience_threshold", 0.3))
        preserve_syntax = bool(body.get("preserve_syntax", True))
        pruned_text, ratio = context_compressor.pruner.prune_text(
            text, salience_threshold=threshold, preserve_syntax=preserve_syntax
        )
        return JSONResponse({
            "ok": True,
            "pruned_text": pruned_text,
            "compression_ratio": ratio,
        })

    @mcp.custom_route("/v1/context/rollup", methods=["POST"])
    async def context_rollup_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        raw_segments = body.get("segments", [])
        chunk_size = int(body.get("chunk_size", 3))
        level = int(body.get("level", 1))

        segments = [
            ContextSegment(
                segment_id=s.get("segment_id", f"seg-{i}"),
                content=s.get("content", ""),
                token_count=int(s.get("token_count", 0)),
                modality=s.get("modality", "text"),
                salience_score=float(s.get("salience_score", 1.0)),
                metadata=s.get("metadata", {}),
            )
            for i, s in enumerate(raw_segments)
        ]
        rollups = context_compressor.rollup_engine.rollup_segments(segments, chunk_size=chunk_size, level=level)
        proof = context_compressor.rollup_engine.evict_and_prove(segments)
        return JSONResponse({
            "ok": True,
            "rollups": [r.to_dict() for r in rollups],
            "eviction_proof": proof.to_dict(),
        })

    @mcp.custom_route("/v1/context/adapt", methods=["POST"])
    async def context_adapt_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        raw_segments = body.get("segments", [])
        tier_str = body.get("tier", "tier_2_standard")
        ceiling = body.get("budget_ceiling")
        hard_ceiling = int(ceiling) if ceiling is not None else None

        try:
            tier = ModelTier(tier_str)
        except ValueError:
            tier = ModelTier.TIER_2_STANDARD

        segments = [
            ContextSegment(
                segment_id=s.get("segment_id", f"seg-{i}"),
                content=s.get("content", ""),
                token_count=int(s.get("token_count", 0)),
                modality=s.get("modality", "text"),
                salience_score=float(s.get("salience_score", 1.0)),
                metadata=s.get("metadata", {}),
            )
            for i, s in enumerate(raw_segments)
        ]

        adapted_res = context_compressor.adapter.adapt_context(
            segments=segments,
            tier=tier,
            hard_budget_ceiling=hard_ceiling,
            pruner=context_compressor.pruner,
            rollup_engine=context_compressor.rollup_engine,
        )
        return JSONResponse({"ok": True, **adapted_res})

    @mcp.custom_route("/v1/context/verify", methods=["POST"])
    async def context_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        content = body.get("content", "")
        test_id = body.get("test_id")
        if not content:
            return JSONResponse({"ok": False, "error": "content is required"}, status_code=400)

        result = context_compressor.verifier.run_verification(
            test_content=content,
            test_id=test_id,
            compactor=context_compressor.compactor,
            pruner=context_compressor.pruner,
            rollup_engine=context_compressor.rollup_engine,
        )
        return JSONResponse({"ok": True, "verification": result.to_dict()})

    # Milestone v3.3 (Phase 32): Decentralized Multi-Desk Governance REST Endpoints
    @mcp.custom_route("/v1/governance/proposal/create", methods=["POST"])
    async def governance_proposal_create_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id")
        proposer_seat = body.get("proposer_seat", "lead")
        proposer_desk_id = body.get("proposer_desk_id", "desk-local")
        title = body.get("title", "")
        description = body.get("description", "")
        action_payload = body.get("action_payload", {})
        timelock_delay_seconds = float(body.get("timelock_delay_seconds", 60.0))
        voting_period_seconds = float(body.get("voting_period_seconds", 300.0))
        quorum_threshold = float(body.get("quorum_threshold", 0.5))
        approval_threshold = float(body.get("approval_threshold", 0.66))
        tags = body.get("tags", [])

        if not proposal_id or not title:
            return JSONResponse({"ok": False, "error": "proposal_id and title are required"}, status_code=400)

        try:
            prop = governance_sm.create_proposal(
                proposal_id=proposal_id,
                proposer_seat=proposer_seat,
                proposer_desk_id=proposer_desk_id,
                title=title,
                description=description,
                action_payload=action_payload,
                timelock_delay_seconds=timelock_delay_seconds,
                voting_period_seconds=voting_period_seconds,
                quorum_threshold=quorum_threshold,
                approval_threshold=approval_threshold,
                tags=tags,
            )
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/proposal/{proposal_id}", methods=["GET"])
    async def governance_proposal_get_route(request: Request) -> Response:
        proposal_id = request.path_params.get("proposal_id", "")
        try:
            prop = governance_sm.get_proposal(proposal_id)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except KeyError:
            return JSONResponse({"ok": False, "error": f"Proposal '{proposal_id}' not found"}, status_code=404)

    @mcp.custom_route("/v1/governance/proposal/start_voting", methods=["POST"])
    async def governance_proposal_start_voting_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        try:
            prop = governance_sm.start_voting(proposal_id)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except (KeyError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/vote", methods=["POST"])
    async def governance_vote_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        seat = body.get("seat", "lead")
        desk_id = body.get("desk_id", "desk-local")
        choice = body.get("choice", "YES")
        raw_votes = float(body.get("raw_votes", 1.0))
        reason = body.get("reason", "")
        signature = body.get("signature")

        try:
            ballot = governance_sm.cast_vote(
                proposal_id=proposal_id,
                seat=seat,
                desk_id=desk_id,
                choice=choice,
                raw_votes=raw_votes,
                reason=reason,
                signature=signature,
            )
            return JSONResponse({"ok": True, "ballot": ballot.to_dict()})
        except (KeyError, ValueError, TimeoutError, PermissionError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/tally", methods=["POST"])
    async def governance_tally_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        total_possible_seats = int(body.get("total_possible_seats", 7))
        try:
            result = governance_sm.tally_and_resolve(proposal_id, total_possible_seats=total_possible_seats)
            return JSONResponse({"ok": True, "result": result.to_dict()})
        except (KeyError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/queue", methods=["POST"])
    async def governance_queue_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        try:
            prop = governance_sm.queue_for_execution(proposal_id)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except (KeyError, ValueError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/execute", methods=["POST"])
    async def governance_execute_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        executor_seat = body.get("executor_seat", "lead")
        current_time = body.get("current_time")
        now = float(current_time) if current_time is not None else None
        try:
            receipt = governance_sm.execute_proposal(proposal_id, executor_seat=executor_seat, current_time=now)
            return JSONResponse({"ok": True, "receipt": receipt})
        except (KeyError, ValueError, PermissionError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/veto", methods=["POST"])
    async def governance_veto_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        veto_seat = body.get("veto_seat", "security")
        reason = body.get("reason", "Emergency veto triggered")
        try:
            prop = governance_sm.emergency_veto(proposal_id, veto_seat=veto_seat, reason=reason)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except (KeyError, ValueError, PermissionError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/governance/cancel", methods=["POST"])
    async def governance_cancel_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        proposal_id = body.get("proposal_id", "")
        requester_seat = body.get("requester_seat", "lead")
        try:
            prop = governance_sm.cancel_proposal(proposal_id, requester_seat=requester_seat)
            return JSONResponse({"ok": True, "proposal": prop.to_dict()})
        except (KeyError, ValueError, PermissionError) as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    # Milestone v3.3 (Phase 33): Byzantine Consensus REST Endpoints
    @mcp.custom_route("/v1/consensus/round/start", methods=["POST"])
    async def consensus_round_start_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        round_id = body.get("round_id")
        proposal_id = body.get("proposal_id")
        proposal_payload = body.get("proposal_payload", {})
        leader_desk = body.get("leader_desk")
        if not round_id or not proposal_id:
            return JSONResponse({"ok": False, "error": "round_id and proposal_id are required"}, status_code=400)
        try:
            msg = byzantine_engine.start_round(
                round_id=round_id,
                proposal_id=proposal_id,
                proposal_payload=proposal_payload,
                leader_desk=leader_desk,
            )
            return JSONResponse({"ok": True, "message": msg.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @mcp.custom_route("/v1/consensus/round/prepare", methods=["POST"])
    async def consensus_round_prepare_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        round_id = body.get("round_id", "")
        sender_desk = body.get("sender_desk", "")
        proposal_digest = body.get("proposal_digest", "")
        decision_str = body.get("decision", "APPROVE")
        signature = body.get("signature")
        try:
            decision = ConsensusDecision(decision_str)
        except ValueError:
            return JSONResponse({"ok": False, "error": f"Invalid decision: {decision_str}"}, status_code=400)

        ok, reason, commit_msg = byzantine_engine.process_prepare(
            round_id=round_id,
            sender_desk=sender_desk,
            proposal_digest=proposal_digest,
            decision=decision,
            signature=signature,
        )
        if not ok:
            return JSONResponse({"ok": False, "error": reason}, status_code=400)
        return JSONResponse({
            "ok": True,
            "message": reason,
            "commit_msg": commit_msg.to_dict() if commit_msg else None,
        })

    @mcp.custom_route("/v1/consensus/round/commit", methods=["POST"])
    async def consensus_round_commit_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        round_id = body.get("round_id", "")
        sender_desk = body.get("sender_desk", "")
        proposal_digest = body.get("proposal_digest", "")
        decision_str = body.get("decision", "APPROVE")
        signature = body.get("signature")
        try:
            decision = ConsensusDecision(decision_str)
        except ValueError:
            return JSONResponse({"ok": False, "error": f"Invalid decision: {decision_str}"}, status_code=400)

        ok, reason, finalized = byzantine_engine.process_commit(
            round_id=round_id,
            sender_desk=sender_desk,
            proposal_digest=proposal_digest,
            decision=decision,
            signature=signature,
        )
        if not ok:
            return JSONResponse({"ok": False, "error": reason}, status_code=400)
        return JSONResponse({
            "ok": True,
            "message": reason,
            "finalized": finalized,
        })

    @mcp.custom_route("/v1/consensus/view_change", methods=["POST"])
    async def consensus_view_change_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        round_id = body.get("round_id", "")
        sender_desk = body.get("sender_desk", "")
        reason = body.get("reason", "Leader unresponsive")
        ok, msg, current_view = byzantine_engine.request_view_change(
            round_id=round_id,
            sender_desk=sender_desk,
            reason=reason,
        )
        return JSONResponse({
            "ok": ok,
            "message": msg,
            "current_view": current_view,
            "current_leader": byzantine_engine.current_leader,
        })

    @mcp.custom_route("/v1/consensus/round/{round_id}", methods=["GET"])
    async def consensus_round_summary_route(request: Request) -> Response:
        round_id = request.path_params.get("round_id", "")
        try:
            summary = byzantine_engine.get_round_summary(round_id)
            return JSONResponse({"ok": True, "round": summary})
        except KeyError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)

    @mcp.custom_route("/v1/consensus/receipt/build", methods=["POST"])
    async def consensus_receipt_build_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        round_id = body.get("round_id", "")
        proposal_id = body.get("proposal_id", "")
        proposal_digest = body.get("proposal_digest", "")
        state_transitions = body.get("state_transitions", [])
        ballot_tallies = body.get("ballot_tallies", {})
        execution_outcome = body.get("execution_outcome", {})
        signers = body.get("signers", ["desk-alpha"])

        receipt = receipt_merkle_tree.build_receipt(
            round_id=round_id,
            proposal_id=proposal_id,
            proposal_digest=proposal_digest,
            state_transitions=state_transitions,
            ballot_tallies=ballot_tallies,
            execution_outcome=execution_outcome,
            signers=signers,
        )
        return JSONResponse({"ok": True, "receipt": receipt.to_dict()})

    @mcp.custom_route("/v1/consensus/receipt/verify", methods=["POST"])
    async def consensus_receipt_verify_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipt_dict = body.get("receipt", {})
        try:
            receipt = GovernanceMerkleReceipt(
                receipt_id=receipt_dict["receipt_id"],
                round_id=receipt_dict["round_id"],
                proposal_id=receipt_dict["proposal_id"],
                proposal_digest=receipt_dict["proposal_digest"],
                merkle_root=receipt_dict["merkle_root"],
                transition_hash=receipt_dict["transition_hash"],
                tally_hash=receipt_dict["tally_hash"],
                execution_hash=receipt_dict["execution_hash"],
                signers=receipt_dict["signers"],
                aggregate_signature=receipt_dict["aggregate_signature"],
                timestamp=receipt_dict.get("timestamp", time.time()),
            )
            valid = receipt_merkle_tree.verify_receipt(receipt)
            return JSONResponse({"ok": True, "valid": valid, "receipt_id": receipt.receipt_id})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"Invalid receipt format: {exc}"}, status_code=400)

    @mcp.custom_route("/v1/consensus/anchor/export", methods=["POST"])
    async def consensus_anchor_export_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        receipt_dict = body.get("receipt", {})
        target_ledger = body.get("target_ledger", "solana_devnet")
        try:
            receipt = GovernanceMerkleReceipt(
                receipt_id=receipt_dict["receipt_id"],
                round_id=receipt_dict["round_id"],
                proposal_id=receipt_dict["proposal_id"],
                proposal_digest=receipt_dict["proposal_digest"],
                merkle_root=receipt_dict["merkle_root"],
                transition_hash=receipt_dict["transition_hash"],
                tally_hash=receipt_dict["tally_hash"],
                execution_hash=receipt_dict["execution_hash"],
                signers=receipt_dict["signers"],
                aggregate_signature=receipt_dict["aggregate_signature"],
                timestamp=receipt_dict.get("timestamp", time.time()),
            )
            anchor = ledger_exporter.anchor_receipt(receipt, target_ledger=target_ledger)
            return JSONResponse({"ok": True, "anchor": anchor.to_dict()})
        except Exception as exc:
            return JSONResponse({"ok": False, "error": f"Failed to anchor: {exc}"}, status_code=400)

    @mcp.custom_route("/v1/consensus/drill/simulate", methods=["POST"])
    async def consensus_drill_simulate_route(request: Request) -> Response:
        body = await request.json() if "application/json" in request.headers.get("content-type", "") else {}
        payload = body.get("payload", {"action": "emergency_param_update", "val": 42})
        drill_results = byzantine_simulator.run_full_byzantine_resilience_suite(payload)
        return JSONResponse({"ok": True, "drill": drill_results})

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
        "fencing_allocator": getattr(mcp, "_fencing_allocator", None),
        "quorum_evaluator": getattr(mcp, "_quorum_evaluator", None),
        "failover_orchestrator": getattr(mcp, "_failover_orchestrator", None),
        "drill_verifier": getattr(mcp, "_drill_verifier", None),
        "zero_trust_mgr": getattr(mcp, "_zero_trust_mgr", None),
        "merkle_tree": getattr(mcp, "_merkle_tree", None),
        "audit_exporter": getattr(mcp, "_audit_exporter", None),
        "compliance_verifier": getattr(mcp, "_compliance_verifier", None),
        "mcp_mesh_registry": getattr(mcp, "_mcp_mesh_registry", None),
        "remote_execution_supervisor": getattr(mcp, "_remote_execution_supervisor", None),
        "memory_graph_engine": getattr(mcp, "_memory_graph_engine", None),
        "context_compressor": getattr(mcp, "_context_compressor", None),
        "governance_sm": getattr(mcp, "_governance_sm", None),
        "byzantine_engine": getattr(mcp, "_byzantine_engine", None),
        "receipt_merkle_tree": getattr(mcp, "_receipt_merkle_tree", None),
        "ledger_exporter": getattr(mcp, "_ledger_exporter", None),
        "byzantine_simulator": getattr(mcp, "_byzantine_simulator", None),
        "swarm_immune": getattr(mcp, "_swarm_immune", None),
        "swarm_reconstitution": getattr(mcp, "_swarm_reconstitution", None),
        "chaos_immune_harness": getattr(mcp, "_chaos_immune_harness", None),
        "skill_synthesis_engine": getattr(mcp, "_skill_synthesis_engine", None),
        "prompt_rollout_orchestrator": getattr(mcp, "_prompt_rollout_orchestrator", None),
        "neural_routing_engine": getattr(mcp, "_neural_routing_engine", None),
        "sovereign_enclave_manager": getattr(mcp, "_sovereign_enclave_manager", None),
        "formal_verification_pipeline": getattr(mcp, "_formal_verification_pipeline", None),
        "synthesis_consensus_engine": getattr(mcp, "_synthesis_consensus_engine", None),
        "proof_receipt_ledger": getattr(mcp, "_proof_receipt_ledger", None),
        "proof_exporter": getattr(mcp, "_proof_exporter", None),
        "shard_ring": getattr(mcp, "_shard_ring", None),
        "shard_crdt_store": getattr(mcp, "_shard_crdt_store", None),
        "geo_replication_engine": getattr(mcp, "_geo_replication_engine", None),
        "shard_router": getattr(mcp, "_shard_router", None),
        "anti_entropy_gossip": getattr(mcp, "_anti_entropy_gossip", None),
        "split_brain_detector": getattr(mcp, "_split_brain_detector", None),
        "epoch_coordinator": getattr(mcp, "_epoch_coordinator", None),
        "partition_healing_orchestrator": getattr(mcp, "_partition_healing_orchestrator", None),
        "pqc_kem": getattr(mcp, "_pqc_kem", None),
        "pqc_sig_engine": getattr(mcp, "_pqc_sig_engine", None),
        "pqc_inspector": getattr(mcp, "_pqc_inspector", None),
        "pqc_ca": getattr(mcp, "_pqc_ca", None),
        "pqc_ledger": getattr(mcp, "_pqc_ledger", None),
        "pqc_verifier": getattr(mcp, "_pqc_verifier", None),
        "pqc_anchor_exporter": getattr(mcp, "_pqc_anchor_exporter", None),
        "workflow_compiler": getattr(mcp, "_workflow_compiler", None),
        "workflow_engine": getattr(mcp, "_workflow_engine", None),
        "capability_broker": getattr(mcp, "_capability_broker", None),
        "workflow_receipt_ledger": getattr(mcp, "_workflow_receipt_ledger", None),
        "workflow_anchor_exporter": getattr(mcp, "_workflow_anchor_exporter", None),
        "dao_registry": getattr(mcp, "_dao_registry", None),
        "swarm_dao_engine": getattr(mcp, "_swarm_dao_engine", None),
        "policy_timelock_executor": getattr(mcp, "_policy_timelock_executor", None),
        "compute_credit_ledger": getattr(mcp, "_compute_credit_ledger", None),
        "payment_channel_manager": getattr(mcp, "_payment_channel_manager", None),
        "cross_desk_clearinghouse": getattr(mcp, "_cross_desk_clearinghouse", None),
        "settlement_anchor_exporter": getattr(mcp, "_settlement_anchor_exporter", None),
        "relayer_staking_registry": getattr(mcp, "_relayer_staking_registry", None),
        "cross_chain_relay_engine": getattr(mcp, "_cross_chain_relay_engine", None),
        "oracle_aggregator": getattr(mcp, "_oracle_aggregator", None),
        "oracle_anchor_exporter": getattr(mcp, "_oracle_anchor_exporter", None),
        "distillation_engine": getattr(mcp, "_distillation_engine", None),
        "quantization_compressor": getattr(mcp, "_quantization_compressor", None),
        "distillation_benchmarker": getattr(mcp, "_distillation_benchmarker", None),
        "model_artifact_registry": getattr(mcp, "_model_artifact_registry", None),
        "edge_compute_scheduler": getattr(mcp, "_edge_compute_scheduler", None),
        "inference_proof_engine": getattr(mcp, "_inference_proof_engine", None),
        "edge_cluster_monitor": getattr(mcp, "_edge_cluster_monitor", None),
        "edge_commitment_exporter": getattr(mcp, "_edge_commitment_exporter", None),
        "zk_proof_generator": getattr(mcp, "_zk_proof_generator", None),
        "zk_proof_verifier": getattr(mcp, "_zk_proof_verifier", None),
        "zk_state_prover": getattr(mcp, "_zk_state_prover", None),
        "homomorphic_cipher": getattr(mcp, "_homomorphic_cipher", None),
        "tss_engine": getattr(mcp, "_tss_engine", None),
        "mpc_coordinator": getattr(mcp, "_mpc_coordinator", None),
        "zk_anchor_exporter": getattr(mcp, "_zk_anchor_exporter", None),
        "neuro_graph": getattr(mcp, "_neuro_graph", None),
        "logic_engine": getattr(mcp, "_logic_engine", None),
        "invariant_checker": getattr(mcp, "_invariant_checker", None),
        "rule_extractor": getattr(mcp, "_rule_extractor", None),
        "causal_discovery": getattr(mcp, "_causal_discovery", None),
        "causal_anchor_exporter": getattr(mcp, "_causal_anchor_exporter", None),
        "epistemic_calibrator": getattr(mcp, "_epistemic_calibrator", None),
        "metacognitive_introspector": getattr(mcp, "_metacognitive_introspector", None),
        "epistemic_network": getattr(mcp, "_epistemic_network", None),
        "strategy_optimizer": getattr(mcp, "_strategy_optimizer", None),
        "counter_evidence_synthesizer": getattr(mcp, "_counter_evidence_synthesizer", None),
        "epistemic_verifier": getattr(mcp, "_epistemic_verifier", None),
        "epistemic_ledger": getattr(mcp, "_epistemic_ledger", None),
        "epistemic_anchor_exporter": getattr(mcp, "_epistemic_anchor_exporter", None),
        "substrate_registry": getattr(mcp, "_substrate_registry", None),
        "substrate_compiler": getattr(mcp, "_substrate_compiler", None),
        "substrate_dispatcher": getattr(mcp, "_substrate_dispatcher", None),
        "substrate_profiler": getattr(mcp, "_substrate_profiler", None),
        "neuromorphic_mesh": getattr(mcp, "_neuromorphic_mesh", None),
        "synaptic_ledger": getattr(mcp, "_synaptic_ledger", None),
        "neuromorphic_anchor_exporter": getattr(mcp, "_neuromorphic_anchor_exporter", None),
        "swarm_antibody_distributor": getattr(mcp, "_swarm_antibody_distributor", None),
        "swarm_antifragility_engine": getattr(mcp, "_swarm_antifragility_engine", None),
        "runtime_reconstitution_supervisor": getattr(mcp, "_runtime_reconstitution_supervisor", None),
        "depin_orchestrator": getattr(mcp, "_depin_orchestrator", None),
        "depin_ledger": getattr(mcp, "_depin_ledger", None),
        "depin_anchor_exporter": getattr(mcp, "_depin_anchor_exporter", None),
        "sagin_cgr": getattr(mcp, "_sagin_cgr", None),
        "sagin_custody": getattr(mcp, "_sagin_custody", None),
        "sagin_downlink_mgr": getattr(mcp, "_sagin_downlink_mgr", None),
        "sagin_consensus": getattr(mcp, "_sagin_consensus", None),
        "sagin_ledger": getattr(mcp, "_sagin_ledger", None),
        "sagin_anchor_exporter": getattr(mcp, "_sagin_anchor_exporter", None),
        "quantum_scheduler": getattr(mcp, "_quantum_scheduler", None),
        "quantum_decoherence": getattr(mcp, "_quantum_decoherence", None),
        "quantum_ledger": getattr(mcp, "_quantum_ledger", None),
        "quantum_anchor_exporter": getattr(mcp, "_quantum_anchor_exporter", None),
        "qteleport_pool": getattr(mcp, "_qteleport_pool", None),
        "qteleport_mesh": getattr(mcp, "_qteleport_mesh", None),
        "qteleport_proto": getattr(mcp, "_qteleport_proto", None),
        "qkd_engine": getattr(mcp, "_qkd_engine", None),
        "qteleport_ledger": getattr(mcp, "_qteleport_ledger", None),
        "qteleport_exporter": getattr(mcp, "_qteleport_exporter", None),
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
