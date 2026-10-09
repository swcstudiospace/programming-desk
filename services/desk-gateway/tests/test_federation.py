from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from desk_gateway.config import SEATS, Settings
from desk_gateway.federation import (
    FederatedTokenValidator,
    FederationError,
    FederationRegistry,
    InvalidTokenError,
    PeerDeskClient,
    PeerGateway,
    RoleNegotiationError,
)
from desk_gateway.server import build_app
from tests.conftest import REPO


def generate_rsa_key_pair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


@pytest.fixture
def rsa_keys():
    priv, pub = generate_rsa_key_pair()
    return {"kid": "key-2026-test-01", "priv": priv, "pub": pub}


@pytest.fixture
def rotated_rsa_keys():
    priv, pub = generate_rsa_key_pair()
    return {"kid": "key-2026-test-02", "priv": priv, "pub": pub}


def make_federated_token(
    kid: str,
    priv_pem: str,
    iss: str = "desk-beta.swcstudio.space",
    sub: str = "bot-00-programming-lead",
    aud: str | None = None,
    seat: str | None = None,
    seats: list[str] | None = None,
    roles: list[str] | None = None,
    ttl_sec: int = 300,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": iss,
        "sub": sub,
        "iat": now,
        "exp": now + ttl_sec,
    }
    if aud:
        payload["aud"] = aud
    if seat:
        payload["seat"] = seat
    if seats:
        payload["seats"] = seats
    if roles:
        payload["roles"] = roles

    token = jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    return token


# -----------------------------------------------------------------------------
# Unit Tests: Registry, Validator & Role Negotiation
# -----------------------------------------------------------------------------

def test_federation_registry_and_peer_registration(rsa_keys):
    settings = Settings(
        public_host="desk-alpha.swcstudio.space",
        federation_enabled=True,
        federation_peers={"desk-gamma": "https://desk-gamma.swcstudio.space"},
    )
    reg = FederationRegistry(settings)
    assert reg.get_peer("desk-gamma") is not None

    # Register new peer (REQ-FED-001)
    peer = reg.register_peer(
        desk_id="desk-beta",
        url="https://desk-beta.swcstudio.space",
        public_keys={rsa_keys["kid"]: rsa_keys["pub"]},
        capabilities=["intake", "dispatch"],
        seats=["lead", "systems", "web"],
    )
    assert peer.desk_id == "desk-beta"
    assert reg.get_key(rsa_keys["kid"]) == rsa_keys["pub"]

    # Invalid desk_id format
    with pytest.raises(FederationError) as exc_info:
        reg.register_peer(desk_id="Invalid Desk ID", url="https://beta.desk")
    assert exc_info.value.code == "invalid_desk_id"


def test_federation_multi_tenant_key_rotation(rsa_keys, rotated_rsa_keys):
    """REQ-FED-002: Multi-tenant key rotation support."""
    settings = Settings(federation_enabled=True)
    reg = FederationRegistry(settings)

    # Initial key
    reg.rotate_key(rsa_keys["kid"], rsa_keys["pub"], desk_id="desk-beta")
    assert reg.get_key(rsa_keys["kid"]) == rsa_keys["pub"]

    validator = FederatedTokenValidator(reg, local_desk_id="desk-alpha")

    token1 = make_federated_token(rsa_keys["kid"], rsa_keys["priv"], seat="systems")
    claims1 = validator.decode_and_verify(token1, required_seat="systems")
    assert claims1["seat"] == "systems"

    # Rotate key to kid-02
    reg.rotate_key(rotated_rsa_keys["kid"], rotated_rsa_keys["pub"], desk_id="desk-beta")
    token2 = make_federated_token(rotated_rsa_keys["kid"], rotated_rsa_keys["priv"], seat="systems")
    claims2 = validator.decode_and_verify(token2, required_seat="systems")
    assert claims2["sub"] == "bot-00-programming-lead"

    # Missing kid in registry raises InvalidTokenError
    unknown_token = make_federated_token("non-existent-kid", rsa_keys["priv"])
    with pytest.raises(InvalidTokenError) as exc_info:
        validator.decode_and_verify(unknown_token)
    assert "Unknown key ID" in str(exc_info.value)


def test_federation_inter_seat_role_negotiation(rsa_keys):
    """REQ-FED-003: Seat boundary enforcement."""
    settings = Settings(federation_enabled=True)
    reg = FederationRegistry(settings)
    reg.rotate_key(rsa_keys["kid"], rsa_keys["pub"])
    validator = FederatedTokenValidator(reg)

    # Token scoped only to 'web' trying to dispatch to 'systems' -> RoleNegotiationError
    token_web = make_federated_token(rsa_keys["kid"], rsa_keys["priv"], sub="bot-02-web", seat="web")
    with pytest.raises(RoleNegotiationError) as exc_info:
        validator.decode_and_verify(token_web, required_seat="systems")
    assert "cannot access target seat 'systems'" in str(exc_info.value)

    # Token scoped to 'systems' can access 'systems'
    token_sys = make_federated_token(rsa_keys["kid"], rsa_keys["priv"], sub="bot-01-systems", seat="systems")
    verified = validator.decode_and_verify(token_sys, required_seat="systems")
    assert verified["seat"] == "systems"

    # Token from peer LEAD can negotiate dispatch across all seats
    token_lead = make_federated_token(rsa_keys["kid"], rsa_keys["priv"], sub="bot-00-programming-lead", seat="lead")  # pragma: allowlist secret
    for seat in SEATS:
        v = validator.decode_and_verify(token_lead, required_seat=seat)
        assert v["sub"] == "bot-00-programming-lead"

    # Target seat not in standard SEATS roster
    with pytest.raises(RoleNegotiationError) as exc_info:
        validator.decode_and_verify(token_lead, required_seat="invalid-seat")
    assert "Unknown target seat" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Integration Tests: Gateway Endpoints (/v1/federation/*)
# -----------------------------------------------------------------------------

async def test_federation_handshake_and_peers_endpoint(tmp_path, rsa_keys):
    """REQ-FED-001: Discovery and handshake API."""
    settings = Settings(
        public_host="desk-primary.swcstudio.space",
        data_dir=tmp_path / "fed_data",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=True,
    )
    application, _ = build_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Successful Handshake
            handshake_payload = {
                "desk_id": "desk-secondary",
                "url": "https://desk-secondary.swcstudio.space",
                "public_keys": {rsa_keys["kid"]: rsa_keys["pub"]},
                "capabilities": ["intake", "dispatch", "telemetry"],
                "seats": ["lead", "systems", "web", "infra"],
            }
            resp = await client.post("/v1/federation/handshake", json=handshake_payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["desk_id"] == "desk-primary.swcstudio.space"

            # 2. Query /v1/federation/peers
            peers_resp = await client.get("/v1/federation/peers")
            assert peers_resp.status_code == 200
            peers_data = peers_resp.json()
            assert peers_data["count"] == 1
            assert peers_data["peers"][0]["desk_id"] == "desk-secondary"
            assert peers_data["peers"][0]["status"] == "active"


async def test_federation_disabled_returns_501(tmp_path):
    settings = Settings(
        public_host="desk-primary.swcstudio.space",
        data_dir=tmp_path / "fed_disabled",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=False,
    )
    application, _ = build_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/v1/federation/handshake", json={"desk_id": "d1", "url": "https://d1"})
            assert resp.status_code == 501
            assert resp.json()["error"] == "federation_disabled"

            resp_route = await client.post("/v1/federation/route", json={})
            assert resp_route.status_code == 501


async def test_federation_route_endpoint_with_jwt_and_seat_negotiation(tmp_path, rsa_keys):
    """REQ-FED-002 & REQ-FED-003: Cross-desk route endpoint with JWT and seat validation."""
    settings = Settings(
        public_host="desk-primary.swcstudio.space",
        data_dir=tmp_path / "fed_route_data",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=True,
        federation_peer_keys={rsa_keys["kid"]: rsa_keys["pub"]},
    )
    application, _ = build_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Token from peer LEAD allowing cross-desk dispatch
            token = make_federated_token(
                kid=rsa_keys["kid"],
                priv_pem=rsa_keys["priv"],
                iss="desk-secondary.swcstudio.space",
                sub="bot-00-programming-lead",
                seat="lead",
            )

            # Valid dispatch to systems
            req_body = {
                "target_seat": "systems",
                "action": "dispatch_task",
                "payload": {"task_id": "FED-001", "instruction": "Implement federated schema sync"},
            }
            res = await client.post(
                "/v1/federation/route",
                headers={"Authorization": f"Bearer {token}"},
                json=req_body,
            )
            assert res.status_code == 200
            body = res.json()
            assert body["ok"] is True
            assert body["status"] == "routed"
            assert body["target_seat"] == "systems"
            assert body["issuer"] == "desk-secondary.swcstudio.space"

            # Cross-desk unauthorized role attempt: token scoped only to 'ios' trying to access 'infra'
            ios_token = make_federated_token(
                kid=rsa_keys["kid"],
                priv_pem=rsa_keys["priv"],
                iss="desk-secondary.swcstudio.space",
                sub="bot-04-ios",
                seat="ios",
            )
            res_bad_seat = await client.post(
                "/v1/federation/route",
                headers={"Authorization": f"Bearer {ios_token}"},
                json={"target_seat": "infra", "action": "deploy"},
            )
            assert res_bad_seat.status_code == 403
            assert res_bad_seat.json()["error"] == "forbidden_role"

            # Corrupted / unverifiable signature
            corrupt_token = token[:-10] + "abcdefghij"
            res_corrupt = await client.post(
                "/v1/federation/route",
                headers={"Authorization": f"Bearer {corrupt_token}"},
                json={"target_seat": "systems"},
            )
            assert res_corrupt.status_code == 401
            assert res_corrupt.json()["error"] == "invalid_token"


async def test_peer_desk_client_handshake_and_forwarding(tmp_path, rsa_keys):
    """REQ-FED-001 & REQ-FED-003: PeerDeskClient handshake and cross-desk forwarding loopback."""
    settings = Settings(
        public_host="desk-a.swcstudio.space",
        data_dir=tmp_path / "peer_client_data",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=True,
    )
    application, _ = build_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            client_registry = FederationRegistry(settings)
            peer_client = PeerDeskClient(client_registry, http_client=test_client)

            # Handshake with local test server
            hs_result = await peer_client.handshake(
                peer_url="http://testserver",
                local_desk_id="desk-remote",
                local_public_keys={rsa_keys["kid"]: rsa_keys["pub"]},
            )
            assert hs_result["ok"] is True
            assert hs_result["desk_id"] == "desk-a.swcstudio.space"

            # Check peer is now registered in client_registry
            peer = client_registry.get_peer("desk-a.swcstudio.space")
            assert peer is not None
            assert peer.url == "http://testserver"

            # Cross-desk forwarding via PeerDeskClient (REQ-FED-003)
            # Register signing key on target
            token = make_federated_token(
                kid=rsa_keys["kid"],
                priv_pem=rsa_keys["priv"],
                iss="desk-remote",
                sub="bot-00-programming-lead",
                seat="lead",
            )
            # Register key in target server app's registry
            target_reg: FederationRegistry = application.state["federation_registry"]
            target_reg.rotate_key(rsa_keys["kid"], rsa_keys["pub"])

            forward_body = json.dumps({"target_seat": "web", "action": "build_assets"}).encode()
            forward_res = await peer_client.forward_cross_desk_route(
                target_desk_id="desk-a.swcstudio.space",
                target_seat="web",
                path="/v1/federation/route",
                method="POST",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                body=forward_body,
            )
            assert forward_res.status_code == 200
            res_json = forward_res.json()
            assert res_json["ok"] is True
            assert res_json["target_seat"] == "web"
            assert res_json["issuer"] == "desk-remote"


async def test_task_graph_synchronization_and_conflict_resolution(tmp_path):
    """REQ-FED-004: Distributed task graph synchronization, vector clocks, and deterministic convergence."""
    from desk_gateway.store import Store

    store_a = Store(tmp_path / "desk_a_store")
    store_b = Store(tmp_path / "desk_b_store")

    # 1. Desk A creates task graph version 1
    g1 = store_a.upsert_task_graph(
        graph_id="graph-alpha",
        title="Cross-Desk Feature",
        nodes={
            "task-01": {"title": "Init Schema", "status": "done", "updated_at": 100.0},
            "task-02": {"title": "Build API", "status": "open", "updated_at": 100.0},
        },
        version=1,
        origin_desk="desk-a",
        updated_at=100.0,
    )
    assert g1["version"] == 1
    assert g1["vector_clock"]["desk-a"] == 1

    # Desk B merges graph from Desk A (initial adoption)
    merged_b, status = store_b.merge_task_graph(g1)
    assert status == "adopted_remote"
    assert merged_b["graph_id"] == "graph-alpha"
    assert len(merged_b["nodes"]) == 2

    # 2. Desk B updates task-02 independently (version 2 on B)
    g2_b = store_b.upsert_task_graph(
        graph_id="graph-alpha",
        title="Cross-Desk Feature",
        nodes={
            "task-01": {"title": "Init Schema", "status": "done", "updated_at": 100.0},
            "task-02": {"title": "Build API", "status": "done", "updated_at": 200.0},
            "task-03": {"title": "Frontend Connect", "status": "in_progress", "updated_at": 200.0},
        },
        version=2,
        vector_clock=merged_b["vector_clock"],
        origin_desk="desk-b",
        updated_at=200.0,
    )
    assert g2_b["vector_clock"]["desk-b"] == 2

    # Desk A syncs with Desk B's update (strictly dominating)
    merged_a, status = store_a.merge_task_graph(g2_b)
    assert status == "adopted_remote"
    assert merged_a["nodes"]["task-02"]["status"] == "done"
    assert "task-03" in merged_a["nodes"]

    # 3. Concurrent divergent updates on both partitioned desks:
    # Desk A updates task-03 to done
    nodes_a = dict(merged_a["nodes"])
    nodes_a["task-03"] = {"title": "Frontend Connect", "status": "done", "updated_at": 300.0}
    nodes_a["task-04-a"] = {"title": "Desk A QA", "status": "open", "updated_at": 300.0}
    g3_a = store_a.upsert_task_graph(
        graph_id="graph-alpha",
        title="Cross-Desk Feature (Desk A edit)",
        nodes=nodes_a,
        version=3,
        vector_clock=merged_a["vector_clock"],
        origin_desk="desk-a",
        updated_at=300.0,
    )

    # Desk B concurrently adds task-04-b
    nodes_b = dict(g2_b["nodes"])
    nodes_b["task-04-b"] = {"title": "Desk B Infra", "status": "open", "updated_at": 305.0}
    g3_b = store_b.upsert_task_graph(
        graph_id="graph-alpha",
        title="Cross-Desk Feature (Desk B edit)",
        nodes=nodes_b,
        version=3,
        vector_clock=g2_b["vector_clock"],
        origin_desk="desk-b",
        updated_at=305.0,
    )

    # Reconnection: Desk A merges concurrent Desk B graph
    final_merged, res_status = store_a.merge_task_graph(g3_b)
    assert res_status == "merged_concurrent"
    # Deterministic convergence: both concurrent tasks (task-04-a and task-04-b) are present!
    assert "task-04-a" in final_merged["nodes"]
    assert "task-04-b" in final_merged["nodes"]
    # Task 3 was done on A vs in_progress on B: done preserved
    assert final_merged["nodes"]["task-03"]["status"] == "done"
    # Vector clock combined
    assert final_merged["vector_clock"]["desk-a"] >= 3
    assert final_merged["vector_clock"]["desk-b"] >= 3


async def test_federation_graph_sync_endpoint(tmp_path, rsa_keys):
    """REQ-FED-004: POST /v1/federation/graphs/sync and GET /v1/federation/graphs/{graph_id}."""
    settings = Settings(
        public_host="desk-sync.swcstudio.space",
        data_dir=tmp_path / "sync_data",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=True,
    )
    application, _ = build_app(settings)
    async with LifespanManager(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Register remote key
            reg: FederationRegistry = application.state["federation_registry"]
            reg.rotate_key(rsa_keys["kid"], rsa_keys["pub"])

            token = make_federated_token(
                kid=rsa_keys["kid"],
                priv_pem=rsa_keys["priv"],
                iss="desk-remote",
                sub="bot-00-programming-lead",
                seat="lead",
            )  # pragma: allowlist secret

            graph_data = {
                "graph_id": "graph-sync-100",
                "title": "Federated Multi-Desk Graph",
                "nodes": {
                    "node-1": {"title": "Spec Architecture", "status": "done", "updated_at": 100.0},
                    "node-2": {"title": "Build Protocol", "status": "in_progress", "updated_at": 110.0},
                },
                "version": 1,
                "vector_clock": {"desk-remote": 1},
                "origin_desk": "desk-remote",
                "updated_at": 110.0,
            }

            # Sync to gateway
            sync_res = await client.post(
                "/v1/federation/graphs/sync",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"graph": graph_data},
            )
            assert sync_res.status_code == 200
            sync_json = sync_res.json()
            assert sync_json["ok"] is True
            assert sync_json["resolution"] == "adopted_remote"
            assert sync_json["graph"]["graph_id"] == "graph-sync-100"

            # Fetch via GET
            get_res = await client.get("/v1/federation/graphs/graph-sync-100")
            assert get_res.status_code == 200
            get_json = get_res.json()
            assert get_json["ok"] is True
            assert get_json["graph"]["title"] == "Federated Multi-Desk Graph"
            assert len(get_json["graph"]["nodes"]) == 2

            # GET non-existent
            missing_res = await client.get("/v1/federation/graphs/non-existent-graph")
            assert missing_res.status_code == 404
            assert missing_res.json()["error"] == "graph_not_found"


async def test_federation_partition_tolerance_and_circuit_breaking(tmp_path, rsa_keys):
    """REQ-FED-005: Circuit breaking and partition-tolerant fail-open routing for peer desks."""
    settings = Settings(
        public_host="desk-local.swcstudio.space",
        data_dir=tmp_path / "partition_data",
        repo_dir=REPO,
        repo_branch="HEAD",
        federation_enabled=True,
    )
    reg = FederationRegistry(settings)
    reg.register_peer(
        desk_id="desk-partitioned.swcstudio.space",
        url="http://unreachable-peer.internal",
        public_keys={rsa_keys["kid"]: rsa_keys["pub"]},
    )
    peer = reg.get_peer("desk-partitioned.swcstudio.space")
    assert peer is not None
    assert peer.circuit_state == "closed"
    assert peer.allow_request() is True

    # Mock client with mock transport simulating unreachable network partitions
    mock_handler = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("Connection refused by peer")))
    async with httpx.AsyncClient(transport=mock_handler) as mock_http:
        client = PeerDeskClient(reg, http_client=mock_http)

        token = make_federated_token(
            kid=rsa_keys["kid"],
            priv_pem=rsa_keys["priv"],
            iss="desk-local",
            sub="bot-01-systems",
            seat="systems",
        )

        # 1st failure: fail-open returns 504 and increments failure_count
        resp1 = await client.forward_cross_desk_route(
            target_desk_id="desk-partitioned.swcstudio.space",
            target_seat="systems",
            path="/v1/test",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            fail_open=True,
        )
        assert resp1.status_code == 504
        assert resp1.json()["error"] == "peer_unreachable"
        assert peer.failure_count == 1
        assert peer.circuit_state == "closed"

        # 2nd failure
        await client.forward_cross_desk_route(
            target_desk_id="desk-partitioned.swcstudio.space",
            target_seat="systems",
            path="/v1/test",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            fail_open=True,
        )
        assert peer.failure_count == 2
        assert peer.circuit_state == "closed"

        # 3rd failure: threshold reached -> circuit trips to OPEN and peer marked degraded
        await client.forward_cross_desk_route(
            target_desk_id="desk-partitioned.swcstudio.space",
            target_seat="systems",
            path="/v1/test",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            fail_open=True,
        )
        assert peer.failure_count == 3
        assert peer.circuit_state == "open"
        assert peer.status == "degraded"
        assert peer.allow_request() is False

        # Next request fails fast with 503 circuit_open without trying network
        resp_fast_fail = await client.forward_cross_desk_route(
            target_desk_id="desk-partitioned.swcstudio.space",
            target_seat="systems",
            path="/v1/test",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            fail_open=True,
        )
        assert resp_fast_fail.status_code == 503
        assert resp_fast_fail.json()["error"] == "peer_circuit_open"

        # When network recovers: record success resets circuit to closed and status to active
        peer.record_success()
        assert peer.circuit_state == "closed"
        assert peer.status == "active"
        assert peer.failure_count == 0
        assert peer.allow_request() is True

