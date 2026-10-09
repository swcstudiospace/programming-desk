"""Dynamic MCP Tool Mesh Registry & Capability Scopes (Milestone v3.1 - Phase 28).

Implements:
- REQ-MCP-001: Dynamic MCP server capability discovery and registration across federated desks.
- REQ-MCP-002: Fine-grained per-seat tool permission schemas and capability scoping.
- REQ-MCP-003: Dynamic schema translation and validation for foreign tool descriptors.
- REQ-MCP-004: Rate-limiting and concurrent tool execution quotas per MCP server connection.
- REQ-MCP-005: Health monitoring and automatic circuit breaker for degraded remote MCP endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("desk_gateway.mcp_mesh")


class CircuitState(str, Enum):
    CLOSED = "closed"
    DEGRADED = "degraded"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class MCPToolDescriptor:
    tool_name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_capabilities: List[str]
    server_id: str
    is_sensitive: bool = False


@dataclass
class MCPServerEndpoint:
    server_id: str
    host: str
    transport: str = "sse"  # sse, stdio, websocket
    capabilities: List[str] = field(default_factory=list)
    active_jobs: int = 0
    max_concurrency: int = 5
    max_requests_per_minute: int = 60
    request_timestamps: List[float] = field(default_factory=list)
    consecutive_failures: int = 0
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    last_failure_time: float = 0.0
    circuit_state: CircuitState = CircuitState.CLOSED
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class SeatPermissionScope:
    seat_id: str
    allowed_patterns: List[str] = field(default_factory=lambda: ["*"])
    denied_patterns: List[str] = field(default_factory=list)
    allowed_capabilities: List[str] = field(default_factory=list)
    allow_sensitive: bool = False


class DynamicMCPToolMeshRegistry:
    """Manages MCP server discovery, per-seat capability scopes,
    schema translation, concurrency rate-limiting, and circuit breakers.
    """

    def __init__(self, failure_threshold: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.servers: Dict[str, MCPServerEndpoint] = {}
        self.tools: Dict[str, MCPToolDescriptor] = {}
        self.seat_scopes: Dict[str, SeatPermissionScope] = {}
        self._init_default_scopes()

    def _init_default_scopes(self) -> None:
        # Lead has full access
        self.seat_scopes["lead"] = SeatPermissionScope(
            seat_id="lead",
            allowed_patterns=["*"],
            allow_sensitive=True,
            allowed_capabilities=["all", "read", "write", "admin"],
        )
        # Quality has read/verify access
        self.seat_scopes["quality"] = SeatPermissionScope(
            seat_id="quality",
            allowed_patterns=["*audit*", "*verify*", "*check*", "*test*", "*get*"],
            denied_patterns=["*destroy*", "*delete*"],
            allow_sensitive=False,
            allowed_capabilities=["read", "verify"],
        )

    def configure_seat_permission(self, seat_id: str, scope: SeatPermissionScope) -> None:
        self.seat_scopes[seat_id] = scope

    # -------------------------------------------------------------------------
    # REQ-MCP-001: Dynamic Server & Tool Discovery
    # -------------------------------------------------------------------------
    def register_server(
        self,
        server_id: str,
        host: str,
        transport: str = "sse",
        capabilities: Optional[List[str]] = None,
        max_concurrency: int = 5,
        max_rpm: int = 60,
        circuit_failure_threshold: Optional[int] = None,
        circuit_recovery_timeout: float = 30.0,
    ) -> MCPServerEndpoint:
        ep = MCPServerEndpoint(
            server_id=server_id,
            host=host,
            transport=transport,
            capabilities=capabilities or ["standard"],
            max_concurrency=max_concurrency,
            max_requests_per_minute=max_rpm,
            failure_threshold=circuit_failure_threshold or self.failure_threshold,
            recovery_timeout=circuit_recovery_timeout,
        )
        self.servers[server_id] = ep
        return ep

    def register_tool(
        self,
        server_id: str,
        tool_name: str,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        required_capabilities: Optional[List[str]] = None,
        is_sensitive: bool = False,
    ) -> MCPToolDescriptor:
        if server_id not in self.servers:
            raise KeyError(f"MCP server '{server_id}' not registered.")

        # REQ-MCP-003: Dynamic schema normalization
        normalized_input = self.normalize_tool_schema(input_schema or {})
        normalized_output = self.normalize_tool_schema(output_schema or {})

        tool = MCPToolDescriptor(
            tool_name=tool_name,
            description=description,
            input_schema=normalized_input,
            output_schema=normalized_output,
            required_capabilities=required_capabilities or [],
            server_id=server_id,
            is_sensitive=is_sensitive,
        )
        self.tools[tool_name] = tool
        return tool

    # -------------------------------------------------------------------------
    # REQ-MCP-003: Foreign Schema Translation & Argument Validation
    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_tool_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures standard JSON schema structure with type, properties, required."""
        norm = dict(schema)
        if "type" not in norm:
            norm["type"] = "object"
        if "properties" not in norm:
            norm["properties"] = {}
        if "required" not in norm:
            norm["required"] = []
        return norm

    def validate_tool_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        if tool_name not in self.tools:
            return False, f"Tool '{tool_name}' not found."

        schema = self.tools[tool_name].input_schema
        required_fields = schema.get("required", [])
        for field_name in required_fields:
            if field_name not in arguments:
                return False, f"Missing required parameter '{field_name}' for tool '{tool_name}'"

        props = schema.get("properties", {})
        for k, v in arguments.items():
            if k in props:
                expected_type = props[k].get("type")
                if expected_type == "integer" and not isinstance(v, int):
                    return False, f"Parameter '{k}' must be integer, got {type(v).__name__}"
                elif expected_type == "string" and not isinstance(v, str):
                    return False, f"Parameter '{k}' must be string, got {type(v).__name__}"
                elif expected_type == "boolean" and not isinstance(v, bool):
                    return False, f"Parameter '{k}' must be boolean, got {type(v).__name__}"

        return True, "Arguments valid"

    # -------------------------------------------------------------------------
    # REQ-MCP-002: Fine-Grained Per-Seat Capability Scopes
    # -------------------------------------------------------------------------
    def set_seat_scope(self, scope: SeatPermissionScope) -> None:
        self.seat_scopes[scope.seat_id] = scope

    def authorize_seat_tool_call(self, seat_id: str, tool_name: str) -> Tuple[bool, str]:
        if tool_name not in self.tools:
            return False, f"Tool '{tool_name}' not found."

        tool = self.tools[tool_name]
        scope = self.seat_scopes.get(
            seat_id,
            SeatPermissionScope(seat_id=seat_id, allowed_patterns=["*"], allow_sensitive=False),
        )

        # 1. Deny pattern check
        for den in scope.denied_patterns:
            if fnmatch.fnmatch(tool_name, den):
                return False, f"Access denied: tool '{tool_name}' matches denied pattern '{den}'"

        # 2. Allow pattern check
        allowed = any(fnmatch.fnmatch(tool_name, p) for p in scope.allowed_patterns)
        if not allowed:
            return False, f"Access denied: seat '{seat_id}' not allowed to invoke '{tool_name}'"

        # 3. Sensitive check
        if tool.is_sensitive and not scope.allow_sensitive:
            return False, f"Access denied: tool '{tool_name}' requires elevated sensitivity scope"

        return True, "Tool execution authorized"

    def list_tools_for_seat(self, seat_id: str) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for name, tool in self.tools.items():
            auth, _ = self.authorize_seat_tool_call(seat_id, name)
            if auth:
                result.append({
                    "tool_name": tool.tool_name,
                    "description": tool.description,
                    "server_id": tool.server_id,
                    "input_schema": tool.input_schema,
                    "is_sensitive": tool.is_sensitive,
                })
        return result

    # -------------------------------------------------------------------------
    # REQ-MCP-004: Rate-Limiting & Concurrency Quotas
    # -------------------------------------------------------------------------
    def acquire_execution_slot(self, server_id: str) -> Tuple[bool, str]:
        if server_id not in self.servers:
            return False, f"MCP server '{server_id}' not found."

        server = self.servers[server_id]

        # Circuit breaker check
        now = time.time()
        if server.circuit_state == CircuitState.OPEN:
            if now - server.last_failure_time >= server.recovery_timeout:
                server.circuit_state = CircuitState.HALF_OPEN
                logger.info("MCP server '%s' circuit transitioning to HALF_OPEN (probing)", server_id)
            else:
                return False, f"Server '{server_id}' circuit is OPEN (temporarily disabled)"

        # Concurrency limit check
        if server.active_jobs >= server.max_concurrency:
            return False, f"Server '{server_id}' concurrency limit reached ({server.active_jobs}/{server.max_concurrency})"

        # Rate limit check (sliding window)
        cutoff = now - 60.0
        server.request_timestamps = [t for t in server.request_timestamps if t > cutoff]
        if len(server.request_timestamps) >= server.max_requests_per_minute:
            return False, f"Server '{server_id}' rate limit exceeded ({server.max_requests_per_minute} req/min)"

        server.request_timestamps.append(now)
        server.active_jobs += 1
        return True, "Execution slot acquired"

    def release_execution_slot(self, server_id: str) -> None:
        if server_id in self.servers:
            server = self.servers[server_id]
            server.active_jobs = max(0, server.active_jobs - 1)

    # -------------------------------------------------------------------------
    # REQ-MCP-005: Health Monitoring & Circuit Breaker
    # -------------------------------------------------------------------------
    def record_server_failure(self, server_id: str) -> CircuitState:
        if server_id not in self.servers:
            return CircuitState.OPEN

        server = self.servers[server_id]
        server.consecutive_failures += 1
        server.last_failure_time = time.time()
        if server.consecutive_failures >= server.failure_threshold:
            server.circuit_state = CircuitState.OPEN
            logger.warning("MCP server '%s' circuit opened after %d failures", server_id, server.consecutive_failures)
        elif server.consecutive_failures >= max(2, server.failure_threshold // 2):
            server.circuit_state = CircuitState.DEGRADED

        return server.circuit_state

    def record_server_success(self, server_id: str) -> CircuitState:
        if server_id in self.servers:
            server = self.servers[server_id]
            server.consecutive_failures = 0
            if server.circuit_state != CircuitState.CLOSED:
                server.circuit_state = CircuitState.CLOSED
                logger.info("MCP server '%s' circuit recovered to CLOSED", server_id)
            return server.circuit_state
        return CircuitState.CLOSED

    def reset_server_breaker(self, server_id: str) -> bool:
        if server_id in self.servers:
            server = self.servers[server_id]
            server.consecutive_failures = 0
            server.circuit_state = CircuitState.CLOSED
            return True
        return False

    def get_mesh_status(self) -> Dict[str, Any]:
        return {
            "total_servers": len(self.servers),
            "total_tools": len(self.tools),
            "servers": {
                s_id: {
                    "host": s.host,
                    "transport": s.transport,
                    "active_jobs": s.active_jobs,
                    "max_concurrency": s.max_concurrency,
                    "circuit_state": s.circuit_state.value,
                    "consecutive_failures": s.consecutive_failures,
                }
                for s_id, s in self.servers.items()
            },
            "tools": list(self.tools.keys()),
        }
