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
