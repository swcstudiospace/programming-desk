"""Gateway REST integration tests for Phase 46 & Phase 47."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def client(tmp_path):
    app, _ = build_app()
    return TestClient(app)


def test_swarm_workflow_gateway_routes(client):
    # 1. Compile DAG
    wf_spec = {
        "workflow_id": "api-wf-001",
        "name": "Integration Workflow",
        "tasks": [
            {"task_id": "task_1", "assigned_seat": "lead", "dependencies": []},
            {"task_id": "task_2", "assigned_seat": "systems", "dependencies": ["task_1"]},
        ],
    }
    compile_resp = client.post("/v1/swarm/workflows/compile", json=wf_spec)
    assert compile_resp.status_code == 200
    assert compile_resp.json()["ok"] is True
    assert compile_resp.json()["workflow"]["execution_order"] == ["task_1", "task_2"]

    # 2. Submit workflow
    submit_resp = client.post("/v1/swarm/workflows/submit", json=wf_spec)
    assert submit_resp.status_code == 200
    assert submit_resp.json()["status"] == "SUBMITTED"

    # 3. Step execution
    step_resp = client.post("/v1/swarm/workflows/api-wf-001/step")
    assert step_resp.status_code == 200
    assert step_resp.json()["ok"] is True

    # 4. Status check
    status_resp = client.get("/v1/swarm/workflows/api-wf-001/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["ok"] is True


def test_swarm_federation_and_drill_routes(client):
    # 1. Register & list capabilities
    cap_resp = client.post(
        "/v1/swarm/capabilities/register",
        json={"capability_name": "ai_debugger", "seat_id": "systems", "desk_id": "desk-gateway"},
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["ok"] is True

    list_resp = client.get("/v1/swarm/capabilities")
    assert list_resp.status_code == 200
    assert any(c["capability_name"] == "ai_debugger" for c in list_resp.json()["capabilities"])

    # 2. Run swarm drill
    drill_resp = client.post("/v1/swarm/workflows/drill/simulate", json={})
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["status"] == "PASS"
