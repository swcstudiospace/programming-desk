"""Gateway REST integration tests for Phase 48 & Phase 49."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def client(tmp_path):
    app, _ = build_app()
    return TestClient(app)


def test_dao_governance_gateway_routes(client):
    # 1. Create proposal
    create_resp = client.post(
        "/v1/dao/proposals/create",
        json={
            "proposer_seat": "lead",
            "title": "API Policy Change",
            "description": "Adjust timeout limit",
            "action_payload": {"timeout_seconds": 60},
            "timelock_delay_seconds": 10.0,
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["ok"] is True
    pid = create_resp.json()["proposal"]["proposal_id"]

    # 2. Vote
    vote_resp = client.post(
        f"/v1/dao/proposals/{pid}/vote",
        json={"voter_seat": "lead", "option": "YES"},
    )
    assert vote_resp.status_code == 200
    assert vote_resp.json()["ok"] is True
    assert vote_resp.json()["ballot"]["quadratic_weight"] > 0

    # 3. Resolve
    resolve_resp = client.post(f"/v1/dao/proposals/{pid}/resolve")
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["ok"] is True

    # 4. Execute with force_unlock
    exec_resp = client.post(
        f"/v1/dao/proposals/{pid}/execute",
        json={"force_unlock": True},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["ok"] is True
    assert exec_resp.json()["execution"]["status"] == "EXECUTED"


def test_tokenomics_gateway_routes(client):
    # 1. Pricing lookup
    price_resp = client.get("/v1/dao/tokenomics/pricing?node_load=0.75")
    assert price_resp.status_code == 200
    assert price_resp.json()["ok"] is True
    assert price_resp.json()["unit_price"] > 0.01

    # 2. Tokenomics drill simulation
    drill_resp = client.post("/v1/dao/tokenomics/drill/simulate", json={})
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["status"] == "PASS"
