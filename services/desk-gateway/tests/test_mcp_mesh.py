"""Unit and integration tests for Dynamic MCP Tool Mesh Registry (Phase 28)."""

import pytest
import time
from starlette.testclient import TestClient

from desk_gateway.mcp_mesh import (
    DynamicMCPToolMeshRegistry,
    CircuitState,
    MCPToolDescriptor,
    MCPServerEndpoint,
    SeatPermissionScope,
)
from desk_gateway.server import build_app


def test_server_and_tool_registration():
    registry = DynamicMCPToolMeshRegistry()
    ep = registry.register_server(
        server_id="analysis-mcp",
        host="http://analysis-svc:9001",
        transport="sse",
        capabilities=["code-analysis", "ast-parse"],
        max_concurrency=3,
        max_rpm=30,
    )
    assert ep.server_id == "analysis-mcp"
    assert ep.max_concurrency == 3
    assert ep.circuit_state == CircuitState.CLOSED

    # Register tool with schema
    schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "line_number": {"type": "integer"},
        },
        "required": ["file_path"],
    }
    tool = registry.register_tool(
        server_id="analysis-mcp",
        tool_name="ast_parse_file",
        description="Parses AST of given file",
        input_schema=schema,
        required_capabilities=["ast-parse"],
        is_sensitive=False,
    )
    assert tool.tool_name == "ast_parse_file"
    assert "file_path" in tool.input_schema["properties"]

    # Unknown server raises KeyError
    with pytest.raises(KeyError):
        registry.register_tool(
            server_id="non-existent",
            tool_name="foo",
        )


def test_schema_normalization_and_validation():
    registry = DynamicMCPToolMeshRegistry()
    registry.register_server("server-1", "http://localhost:8000")

    # Loose schema without type normalized to object
    loose_schema = {
        "properties": {
            "threshold": {"type": "number"},
            "tag": {"type": "string"},
        },
        "required": ["tag"],
    }
    registry.register_tool(
        server_id="server-1",
        tool_name="filter_items",
        input_schema=loose_schema,
    )

    # Valid args
    valid, msg = registry.validate_tool_arguments("filter_items", {"tag": "prod", "threshold": 0.95})
    assert valid is True
    assert "valid" in msg.lower()

    # Missing required argument
    valid, msg = registry.validate_tool_arguments("filter_items", {"threshold": 0.5})
    assert valid is False
    assert "Missing required parameter" in msg

    # Invalid type
    valid, msg = registry.validate_tool_arguments("filter_items", {"tag": 12345})
    assert valid is False
    assert "must be string" in msg


def test_seat_scoping_and_authorization():
    registry = DynamicMCPToolMeshRegistry()
    registry.register_server("server-1", "http://localhost:8000")
    registry.register_tool("server-1", "git_status")
    registry.register_tool("server-1", "git_commit")
    registry.register_tool("server-1", "deploy_prod", is_sensitive=True)

    # Configure custom seat permissions
    registry.configure_seat_permission("junior-dev", SeatPermissionScope(
        seat_id="junior-dev",
        allowed_patterns=["git_status"],
        denied_patterns=["git_commit", "*prod*"],
        allow_sensitive=False,
    ))

    # Lead seat (wildcard allowed by default)
    lead_tools = [t["tool_name"] for t in registry.list_tools_for_seat("lead")]
    assert "git_status" in lead_tools
    assert "git_commit" in lead_tools
    assert "deploy_prod" in lead_tools

    ok, msg = registry.authorize_seat_tool_call("lead", "deploy_prod")
    assert ok is True

    # Junior dev seat
    junior_tools = [t["tool_name"] for t in registry.list_tools_for_seat("junior-dev")]
    assert "git_status" in junior_tools
    assert "git_commit" not in junior_tools
    assert "deploy_prod" not in junior_tools

    ok, msg = registry.authorize_seat_tool_call("junior-dev", "git_status")
    assert ok is True

    ok, msg = registry.authorize_seat_tool_call("junior-dev", "git_commit")
    assert ok is False
    assert "denied" in msg

    ok, msg = registry.authorize_seat_tool_call("junior-dev", "deploy_prod")
    assert ok is False


def test_rate_limiting_and_concurrency_slots():
    registry = DynamicMCPToolMeshRegistry()
    registry.register_server(
        "limited-svc",
        "http://localhost:8000",
        max_concurrency=2,
        max_rpm=3,
    )

    # Slot 1 acquired
    ok, _ = registry.acquire_execution_slot("limited-svc")
    assert ok is True
    # Slot 2 acquired
    ok, _ = registry.acquire_execution_slot("limited-svc")
    assert ok is True

    # Concurrency limit hit (max_concurrency=2)
    ok, msg = registry.acquire_execution_slot("limited-svc")
    assert ok is False
    assert "concurrency limit reached" in msg.lower()

    # Release 1 slot
    registry.release_execution_slot("limited-svc")
    # Slot 3 acquired (3rd within minute)
    ok, _ = registry.acquire_execution_slot("limited-svc")
    assert ok is True

    # Release slot, now attempt 4th call -> RPM limit hit
    registry.release_execution_slot("limited-svc")
    ok, msg = registry.acquire_execution_slot("limited-svc")
    assert ok is False
    assert "rate limit exceeded" in msg.lower()


def test_circuit_breaker_transitions():
    registry = DynamicMCPToolMeshRegistry()
    registry.register_server(
        "fragile-svc",
        "http://localhost:8000",
        circuit_failure_threshold=3,
        circuit_recovery_timeout=0.2,  # 200ms for test speed
    )

    assert registry.servers["fragile-svc"].circuit_state == CircuitState.CLOSED

    # Failure 1: Still CLOSED
    registry.record_server_failure("fragile-svc")
    assert registry.servers["fragile-svc"].circuit_state == CircuitState.CLOSED
    assert registry.servers["fragile-svc"].consecutive_failures == 1

    # Failure 2: Transitions to DEGRADED
    registry.record_server_failure("fragile-svc")
    assert registry.servers["fragile-svc"].circuit_state == CircuitState.DEGRADED

    # Failure 3: Transitions to OPEN
    registry.record_server_failure("fragile-svc")
    assert registry.servers["fragile-svc"].circuit_state == CircuitState.OPEN

    # Cannot acquire slot when OPEN
    ok, msg = registry.acquire_execution_slot("fragile-svc")
    assert ok is False
    assert "circuit is open" in msg.lower()

    # Wait for recovery timeout to pass
    time.sleep(0.25)

    # Next attempt transitions to HALF_OPEN and permits probe
    ok, msg = registry.acquire_execution_slot("fragile-svc")
    assert ok is True
    assert registry.servers["fragile-svc"].circuit_state == CircuitState.HALF_OPEN

    # On success probe, circuit resets to CLOSED
    registry.record_server_success("fragile-svc")
    assert registry.servers["fragile-svc"].circuit_state == CircuitState.CLOSED
    assert registry.servers["fragile-svc"].consecutive_failures == 0


def test_gateway_mcp_mesh_api_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Register server
    resp = client.post("/v1/mcp-mesh/server/register", json={
        "server_id": "api-tester-mcp",
        "host": "http://10.0.0.1:9090",
        "transport": "sse",
        "capabilities": ["http", "json"],
        "max_concurrency": 4,
        "max_rpm": 50,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["server_id"] == "api-tester-mcp"

    # 2. Register tool
    resp = client.post("/v1/mcp-mesh/tool/register", json={
        "server_id": "api-tester-mcp",
        "tool_name": "http_ping",
        "description": "Send ping to endpoint",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"]
        },
        "is_sensitive": False
    })
    assert resp.status_code == 200
    assert resp.json()["tool_name"] == "http_ping"

    # 3. List tools
    resp = client.get("/v1/mcp-mesh/tools?seat_id=lead")
    assert resp.status_code == 200
    tool_names = [t["tool_name"] for t in resp.json()["tools"]]
    assert "http_ping" in tool_names

    # 4. Authorize tool call
    # Valid call
    resp = client.post("/v1/mcp-mesh/tools/authorize", json={
        "seat_id": "lead",
        "tool_name": "http_ping",
        "arguments": {"target": "http://example.com"}
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["valid_args"] is True

    # Invalid arguments (missing required target)
    resp = client.post("/v1/mcp-mesh/tools/authorize", json={
        "seat_id": "lead",
        "tool_name": "http_ping",
        "arguments": {}
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert resp.json()["valid_args"] is False

    # 5. Acquire and release slots
    resp = client.post("/v1/mcp-mesh/slot/acquire", json={"server_id": "api-tester-mcp"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = client.post("/v1/mcp-mesh/slot/release", json={"server_id": "api-tester-mcp"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 6. Check mesh status
    resp = client.get("/v1/mcp-mesh/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["total_servers"] >= 1
    assert status["total_tools"] >= 1
    assert "api-tester-mcp" in status["servers"]
