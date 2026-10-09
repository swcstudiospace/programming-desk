"""Integration tests for Skill Synthesis Gateway Routes (Phase 36)."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def test_client():
    app, _ = build_app()
    return TestClient(app)


def test_gateway_skill_deploy_and_invoke(test_client):
    deploy_payload = {
        "tool_name": "string_reverser",
        "version": "1.0.0",
        "description": "Reverses any string",
        "author_seat_id": "systems",
        "python_source": """
def string_reverser(s: str) -> str:
    return s[::-1]
""",
        "parameters": [
            {"name": "s", "type_name": "str", "description": "target string"}
        ],
        "test_cases": [
            {"input_args": {"s": "abc"}, "expected_output": "cba"}
        ],
        "required_permissions": ["text:transform"],
    }

    # 1. Deploy skill
    res = test_client.post("/v1/evolution/skills/deploy", json=deploy_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["ok"] is True
    assert data["receipt"]["tool_name"] == "string_reverser"
    assert data["receipt"]["lifecycle_state"] == "ACTIVE"

    # 2. Invoke skill
    res_inv = test_client.post(
        "/v1/evolution/skills/invoke",
        json={"tool_name": "string_reverser", "arguments": {"s": "radar"}},
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["result"] == "radar"

    # 3. List active skills
    res_list = test_client.get("/v1/evolution/skills/list")
    assert res_list.status_code == 200
    tools = res_list.json()["tools"]
    assert any(t["tool_name"] == "string_reverser" for t in tools)

    # 4. Deprecate skill
    res_dep = test_client.post(
        "/v1/evolution/skills/lifecycle",
        json={"tool_name": "string_reverser", "action": "deprecate"},
    )
    assert res_dep.status_code == 200
    assert res_dep.json()["metrics"]["lifecycle_state"] == "DEPRECATED"
