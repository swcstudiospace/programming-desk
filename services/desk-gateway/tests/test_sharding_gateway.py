"""Gateway REST integration tests for Phase 42 & Phase 43."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def client(tmp_path):
    app, _ = build_app()
    return TestClient(app)


def test_sharding_and_crdt_gateway_routes(client):
    # Register shard node
    reg_resp = client.post(
        "/v1/sharding/nodes/register",
        json={"node_id": "remote-node-eu", "region_id": "eu-central", "weight": 2},
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["ok"] is True

    # List shard nodes
    list_resp = client.get("/v1/sharding/nodes")
    assert list_resp.status_code == 200
    nodes = list_resp.json()["nodes"]
    assert any(n["node_id"] == "remote-node-eu" for n in nodes)

    # Route key
    route_resp = client.get("/v1/sharding/route/session-user-123")
    assert route_resp.status_code == 200
    assert route_resp.json()["ok"] is True
    assert route_resp.json()["routing"]["primary"] is not None

    # Write & read LWW
    write_resp = client.post(
        "/v1/sharding/crdt/write",
        json={"key": "state-test-key", "crdt_type": "lww", "value": "active_payload"},
    )
    assert write_resp.status_code == 200
    assert write_resp.json()["ok"] is True

    read_resp = client.get("/v1/sharding/crdt/read/state-test-key?crdt_type=lww")
    assert read_resp.status_code == 200
    assert read_resp.json()["value"] == "active_payload"

    # Counter write & read
    cnt_resp = client.post(
        "/v1/sharding/crdt/write",
        json={"key": "metric-counter", "crdt_type": "pn_counter", "delta": 10},
    )
    assert cnt_resp.status_code == 200
    assert cnt_resp.json()["value"] == 10


def test_mesh_consensus_gateway_routes(client):
    # Gossip digest route
    digest_resp = client.post("/v1/mesh/consensus/gossip/digest", json={})
    assert digest_resp.status_code == 200
    assert digest_resp.json()["ok"] is True
    assert "vector_clock" in digest_resp.json()["digest"]

    # Acquire lease
    lease_resp = client.post("/v1/mesh/consensus/lease/acquire", json={"ttl_seconds": 15.0})
    assert lease_resp.status_code == 200
    assert lease_resp.json()["ok"] is True
    assert lease_resp.json()["lease"]["epoch_id"] >= 1

    # Run partition drill
    drill_resp = client.post("/v1/mesh/consensus/drill/simulate", json={})
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["status"] == "PASS"
