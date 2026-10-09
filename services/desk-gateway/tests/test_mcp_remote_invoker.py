"""Unit and integration tests for Cross-Desk Distributed Remote Tool Invocation & Attested Receipts (Phase 29)."""

import asyncio
import pytest
from starlette.testclient import TestClient

from desk_gateway.mcp_mesh import DynamicMCPToolMeshRegistry
from desk_gateway.mcp_remote_invoker import (
    MCPRemoteExecutionSupervisor,
    ExecutionReceipt,
    InvocationStatus,
)
from desk_gateway.server import build_app


@pytest.fixture
def mesh_and_supervisor():
    mesh = DynamicMCPToolMeshRegistry()
    mesh.register_server(
        server_id="worker-node-1",
        host="http://worker-1:8080",
        capabilities=["compute", "git"],
        max_concurrency=5,
        max_rpm=60,
    )
    mesh.register_tool(
        server_id="worker-node-1",
        tool_name="run_compute_task",
        description="Executes a computation task",
        input_schema={
            "type": "object",
            "properties": {"task_name": {"type": "string"}, "cycles": {"type": "integer"}},
            "required": ["task_name"],
        },
    )
    supervisor = MCPRemoteExecutionSupervisor(registry=mesh, signing_secret="test-secret-key")
    return mesh, supervisor


@pytest.mark.asyncio
async def test_remote_invocation_success_and_receipt(mesh_and_supervisor):
    mesh, supervisor = mesh_and_supervisor

    async def custom_executor(args):
        return {"result": f"Done {args['task_name']}", "cycles_run": args.get("cycles", 10)}

    success, output, receipt = await supervisor.invoke_remote_tool(
        tool_name="run_compute_task",
        arguments={"task_name": "benchmark", "cycles": 50},
        source_seat="lead",
        remote_executor_callable=custom_executor,
    )

    assert success is True
    assert output["result"] == "Done benchmark"
    assert output["cycles_run"] == 50
    assert receipt.status == InvocationStatus.COMPLETED
    assert receipt.tool_name == "run_compute_task"
    assert receipt.source_seat == "lead"
    assert receipt.target_server_id == "worker-node-1"
    assert len(receipt.input_hash) == 64
    assert len(receipt.output_hash) == 64
    assert len(receipt.signature) == 64

    # Non-repudiation cryptographic verification (REQ-MCP-007, REQ-MCP-010)
    assert supervisor.verify_execution_receipt(receipt) is True

    # Tampering with receipt invalidates verification
    tampered_receipt = ExecutionReceipt(
        invocation_id=receipt.invocation_id,
        tool_name=receipt.tool_name,
        source_seat=receipt.source_seat,
        target_server_id=receipt.target_server_id,
        status=receipt.status,
        input_hash=receipt.input_hash,
        output_hash="tampered_hash_value_1234567890abcdef1234567890abcdef1234567890abcdef",
        duration_ms=receipt.duration_ms,
        timestamp=receipt.timestamp,
        signature=receipt.signature,
    )
    assert supervisor.verify_execution_receipt(tampered_receipt) is False


@pytest.mark.asyncio
async def test_remote_invocation_timeout_supervision(mesh_and_supervisor):
    mesh, supervisor = mesh_and_supervisor

    async def slow_executor(args):
        await asyncio.sleep(0.5)
        return {"done": True}

    # Set 0.1s timeout (REQ-MCP-009)
    success, output, receipt = await supervisor.invoke_remote_tool(
        tool_name="run_compute_task",
        arguments={"task_name": "slow_task"},
        source_seat="lead",
        timeout_seconds=0.1,
        remote_executor_callable=slow_executor,
    )

    assert success is False
    assert receipt.status == InvocationStatus.TIMED_OUT
    assert "error" in output
    assert "timed out" in output["error"].lower()
    assert supervisor.verify_execution_receipt(receipt) is True


@pytest.mark.asyncio
async def test_streaming_execution_proxy(mesh_and_supervisor):
    mesh, supervisor = mesh_and_supervisor

    chunks = []
    async for chunk in supervisor.stream_tool_execution("run_compute_task", {"task_name": "stream_task"}, steps=3):
        chunks.append(chunk)

    assert len(chunks) == 4
    assert chunks[0].seq == 1
    assert chunks[0].data["progress_percent"] == 33.3
    assert chunks[-1].seq == 4
    assert chunks[-1].data["status"] == "completed"


def test_gateway_mcp_remote_invoke_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Register server & tool
    resp = client.post("/v1/mcp-mesh/server/register", json={
        "server_id": "remote-cluster-alpha",
        "host": "http://alpha:9000",
        "transport": "sse",
        "capabilities": ["remote-code"],
        "max_concurrency": 2,
    })
    assert resp.status_code == 200

    resp = client.post("/v1/mcp-mesh/tool/register", json={
        "server_id": "remote-cluster-alpha",
        "tool_name": "remote_echo",
        "description": "Echoes back input payload",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    })
    assert resp.status_code == 200

    # 2. Invoke remote tool
    resp = client.post("/v1/mcp-mesh/invoke", json={
        "tool_name": "remote_echo",
        "arguments": {"message": "hello from distributed test"},
        "source_seat": "lead",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    receipt_dict = data["receipt"]
    inv_id = receipt_dict["invocation_id"]
    assert receipt_dict["status"] == "completed"

    # 3. Retrieve receipt
    resp = client.get(f"/v1/mcp-mesh/receipts/{inv_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["receipt"]["invocation_id"] == inv_id

    # 4. Cryptographically verify receipt
    resp = client.post("/v1/mcp-mesh/receipts/verify", json={"receipt": receipt_dict})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["valid"] is True
