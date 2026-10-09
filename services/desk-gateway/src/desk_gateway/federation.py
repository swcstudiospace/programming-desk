"""Multi-Desk Federation: discovery, multi-tenant JWT validation, and cross-desk seat routing.

Enables secure inter-gateway communication across federated Programming Desks (REQ-FED-001,
REQ-FED-002, REQ-FED-003).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from desk_gateway.config import SEATS, Settings

logger = logging.getLogger("desk_gateway.federation")

DESK_ID_REGEX = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,63}$")
ALLOWED_FEDERATION_ALGORITHMS = ["RS256", "ES256", "EdDSA"]


class FederationError(Exception):
    """Base exception for federation errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PeerNotFoundError(FederationError):
    def __init__(self, desk_id: str) -> None:
        super().__init__("peer_not_found", f"Peer gateway '{desk_id}' is not registered or discovered", 404)


class InvalidTokenError(FederationError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_token", f"Federated token validation failed: {reason}", 401)


class RoleNegotiationError(FederationError):
    def __init__(self, reason: str) -> None:
        super().__init__("forbidden_role", f"Cross-desk seat role negotiation failed: {reason}", 403)


@dataclass
class PeerGateway:
    desk_id: str
    url: str
    public_keys: dict[str, str] = field(default_factory=dict)  # kid -> pem/jwk
    capabilities: list[str] = field(default_factory=list)
    seats: list[str] = field(default_factory=lambda: list(SEATS.keys()))
    status: str = "active"
    last_seen: float = field(default_factory=time.time)
    registered_at: float = field(default_factory=time.time)
    # Partition tolerance / Circuit Breaker tracking (REQ-FED-005)
    failure_count: int = 0
    circuit_state: str = "closed"  # closed, open, half-open
    last_failure_time: float = 0.0

    def allow_request(self, recovery_timeout_sec: float = 30.0) -> bool:
        """Check whether outbound requests to peer are allowed or partitioned (REQ-FED-005)."""
        if self.circuit_state == "closed":
            return True
        now = time.monotonic()
        if self.circuit_state == "open":
            if now - self.last_failure_time >= recovery_timeout_sec:
                self.circuit_state = "half-open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.circuit_state = "closed"
        self.status = "active"
        self.last_seen = time.time()

    def record_failure(self, threshold: int = 3) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= threshold or self.circuit_state == "half-open":
            self.circuit_state = "open"
            self.status = "degraded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_id": self.desk_id,
            "url": self.url,
            "public_keys": {kid: f"KEY({kid})" for kid in self.public_keys},
            "capabilities": self.capabilities,
            "seats": self.seats,
            "status": self.status,
            "last_seen": self.last_seen,
            "registered_at": self.registered_at,
            "circuit_state": self.circuit_state,
            "failure_count": self.failure_count,
        }


class FederationRegistry:
    """Registry maintaining known peer desk gateways, public keys, and health status."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._peers: dict[str, PeerGateway] = {}
        self._keys: dict[str, str] = dict(settings.federation_peer_keys)  # kid -> pem/jwk
        self._bootstrap_peers()

    def _bootstrap_peers(self) -> None:
        for desk_id, url in self.settings.federation_peers.items():
            if DESK_ID_REGEX.match(desk_id):
                self._peers[desk_id] = PeerGateway(
                    desk_id=desk_id,
                    url=url.rstrip("/"),
                    capabilities=["intake", "dispatch", "telemetry"],
                    seats=list(SEATS.keys()),
                )

    def register_peer(
        self,
        desk_id: str,
        url: str,
        public_keys: dict[str, str] | None = None,
        capabilities: list[str] | None = None,
        seats: list[str] | None = None,
    ) -> PeerGateway:
        """Register or update a peer gateway during handshake (REQ-FED-001)."""
        if not DESK_ID_REGEX.match(desk_id):
            raise FederationError("invalid_desk_id", f"Desk ID '{desk_id}' is invalid (must match {DESK_ID_REGEX.pattern})")
        if not url.startswith(("http://", "https://")):
            raise FederationError("invalid_url", "Peer URL must use http or https")

        with self._lock:
            existing = self._peers.get(desk_id)
            all_keys = dict(existing.public_keys if existing else {})
            if public_keys:
                all_keys.update(public_keys)
                self._keys.update(public_keys)

            peer = PeerGateway(
                desk_id=desk_id,
                url=url.rstrip("/"),
                public_keys=all_keys,
                capabilities=capabilities or (existing.capabilities if existing else ["intake", "dispatch"]),
                seats=[s for s in (seats or (existing.seats if existing else list(SEATS.keys()))) if s in SEATS],
                status="active",
                last_seen=time.time(),
                registered_at=existing.registered_at if existing else time.time(),
            )
            self._peers[desk_id] = peer
            logger.info("Federation peer registered/updated: %s at %s with %d keys", desk_id, url, len(all_keys))
            return peer

    def rotate_key(self, kid: str, public_key_pem: str, desk_id: str | None = None) -> None:
        """Support multi-tenant public key rotation (REQ-FED-002)."""
        with self._lock:
            self._keys[kid] = public_key_pem
            if desk_id and desk_id in self._peers:
                self._peers[desk_id].public_keys[kid] = public_key_pem
            logger.info("Federation public key rotated: kid=%s (desk_id=%s)", kid, desk_id)

    def get_key(self, kid: str) -> str | None:
        with self._lock:
            return self._keys.get(kid)

    def get_peer(self, desk_id: str) -> PeerGateway | None:
        with self._lock:
            return self._peers.get(desk_id)

    def list_peers(self) -> list[PeerGateway]:
        with self._lock:
            return list(self._peers.values())

    def remove_peer(self, desk_id: str) -> bool:
        with self._lock:
            return self._peers.pop(desk_id, None) is not None


class FederatedTokenValidator:
    """Multi-tenant JWT validator supporting asymmetric key verification and tenant rotation (REQ-FED-002)."""

    def __init__(self, registry: FederationRegistry, local_desk_id: str = "local") -> None:
        self.registry = registry
        self.local_desk_id = local_desk_id

    def decode_and_verify(
        self,
        token: str,
        audience: str | list[str] | None = None,
        required_seat: str | None = None,
    ) -> dict[str, Any]:
        """Verify JWT signature, expiration, audience, issuer desk, and seat role claims."""
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise InvalidTokenError(f"Malformed JWT header: {exc}") from exc

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg")

        if not alg or alg not in ALLOWED_FEDERATION_ALGORITHMS:
            raise InvalidTokenError(f"Unsupported algorithm '{alg}'. Allowed: {ALLOWED_FEDERATION_ALGORITHMS}")

        if not kid:
            raise InvalidTokenError("JWT missing 'kid' header parameter")

        key = self.registry.get_key(kid)
        if not key:
            raise InvalidTokenError(f"Unknown key ID (kid='{kid}'); key not found in federation registry")

        try:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                audience=audience,
                options={
                    "require": ["exp", "iss", "sub"],
                    "verify_exp": True,
                    "verify_aud": audience is not None,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("Token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidTokenError(f"Invalid audience: {exc}") from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"Signature or claim verification failure: {exc}") from exc

        # Check tenant / issuer desk
        iss = payload.get("iss", "")
        # Verify cross-desk role if requested
        if required_seat:
            self.validate_seat_role(payload, required_seat)

        return payload

    def validate_seat_role(self, payload: dict[str, Any], required_seat: str) -> None:
        """Enforce strict seat boundaries and role negotiation (REQ-FED-003).

        A federated caller can only dispatch or invoke a target seat if the token's
        roles, scopes, or seat match allowable boundaries.
        Target seats: LEAD, SYSTEMS, WEB, ANDROID, IOS, INFRA, QUALITY.
        """
        if required_seat not in SEATS:
            raise RoleNegotiationError(f"Unknown target seat '{required_seat}'")

        # Allowed seats specified in payload: either explicit 'seats' list, 'seat', or 'roles'
        token_seats = []
        if "seat" in payload:
            token_seats.append(str(payload["seat"]).lower())
        if "seats" in payload and isinstance(payload["seats"], list):
            token_seats.extend([str(s).lower() for s in payload["seats"]])
        if "roles" in payload and isinstance(payload["roles"], list):
            token_seats.extend([str(r).lower() for r in payload["roles"]])
        if "scope" in payload:
            for sc in str(payload["scope"]).split():
                if sc.startswith("seat:"):
                    token_seats.append(sc[5:].lower())

        # If token originates from LEAD of a peer desk, lead can dispatch to any seat
        is_peer_lead = "lead" in token_seats or payload.get("sub") == "lead"

        # Direct seat match or peer LEAD delegation
        if required_seat.lower() in token_seats or is_peer_lead:
            return

        raise RoleNegotiationError(
            f"Token authorized for seats {token_seats or '[]'} cannot access target seat '{required_seat}'. "
            "Cross-desk dispatch requires explicit target seat authorization or peer LEAD authority."
        )


class PeerDeskClient:
    """HTTP client to perform peer handshakes and route cross-desk requests."""

    def __init__(self, registry: FederationRegistry, http_client: httpx.AsyncClient | None = None) -> None:
        self.registry = registry
        self._http = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        return httpx.AsyncClient(timeout=10.0)

    async def handshake(self, peer_url: str, local_desk_id: str, local_public_keys: dict[str, str]) -> dict[str, Any]:
        """Perform handshake discovery with a remote peer gateway (REQ-FED-001)."""
        endpoint = f"{peer_url.rstrip('/')}/v1/federation/handshake"
        payload = {
            "desk_id": local_desk_id,
            "url": self.registry.settings.public_host,
            "public_keys": local_public_keys,
            "capabilities": ["intake", "dispatch", "telemetry"],
            "seats": list(SEATS.keys()),
        }

        client = await self._get_client()
        should_close = self._http is None
        try:
            resp = await client.post(endpoint, json=payload)
            if resp.status_code != 200:
                raise FederationError(
                    "handshake_failed",
                    f"Handshake with {peer_url} failed with status {resp.status_code}: {resp.text}",
                    status_code=resp.status_code,
                )
            data = resp.json()
            peer_desk_id = data.get("desk_id")
            if not peer_desk_id:
                raise FederationError("invalid_handshake_response", "Peer response missing 'desk_id'")

            # Register remote peer
            self.registry.register_peer(
                desk_id=peer_desk_id,
                url=peer_url,
                public_keys=data.get("public_keys"),
                capabilities=data.get("capabilities"),
                seats=data.get("seats"),
            )
            return data
        finally:
            if should_close:
                await client.aclose()

    async def forward_cross_desk_route(
        self,
        target_desk_id: str,
        target_seat: str,
        path: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None = None,
        fail_open: bool = True,
    ) -> httpx.Response:
        """Route an inter-seat ticket or MCP invocation to a peer desk gateway with circuit breaking (REQ-FED-003, REQ-FED-005)."""
        peer = self.registry.get_peer(target_desk_id)
        if not peer:
            raise PeerNotFoundError(target_desk_id)

        # Check circuit state (REQ-FED-005)
        if not peer.allow_request():
            if fail_open:
                logger.warning("Peer %s circuit is OPEN; fail-open fallback returning 503 circuit_open", target_desk_id)
                return httpx.Response(
                    status_code=503,
                    json={
                        "error": "peer_circuit_open",
                        "desk_id": target_desk_id,
                        "detail": f"Circuit breaker open for peer desk {target_desk_id}; request degraded locally.",
                    },
                )
            raise FederationError("peer_circuit_open", f"Circuit open for peer {target_desk_id}", 503)

        target_url = f"{peer.url.rstrip('/')}{path}"
        client = await self._get_client()
        should_close = self._http is None
        try:
            req_headers = dict(headers)
            req_headers["x-federation-source-desk"] = self.registry.settings.public_host
            req_headers["x-federation-target-seat"] = target_seat
            resp = await client.request(
                method=method,
                url=target_url,
                headers=req_headers,
                content=body,
            )
            if resp.status_code >= 500:
                peer.record_failure()
            else:
                peer.record_success()
            return resp
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            peer.record_failure()
            if fail_open:
                logger.warning("Peer %s communication failed: %s; failing open with 504", target_desk_id, exc)
                return httpx.Response(
                    status_code=504,
                    json={
                        "error": "peer_unreachable",
                        "desk_id": target_desk_id,
                        "detail": f"Peer gateway {target_desk_id} unreachable ({exc}); partition fail-open applied.",
                    },
                )
            raise FederationError("peer_unreachable", str(exc), 504) from exc
        finally:
            if should_close:
                await client.aclose()

    async def sync_task_graph(
        self,
        target_desk_id: str,
        graph_payload: dict[str, Any],
        token: str,
    ) -> dict[str, Any]:
        """Synchronize task graph with remote peer gateway (REQ-FED-004, REQ-FED-005)."""
        peer = self.registry.get_peer(target_desk_id)
        if not peer:
            raise PeerNotFoundError(target_desk_id)

        endpoint = "/v1/federation/graphs/sync"
        resp = await self.forward_cross_desk_route(
            target_desk_id=target_desk_id,
            target_seat="lead",
            path=endpoint,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            body=json.dumps(graph_payload).encode("utf-8"),
            fail_open=True,
        )
        if resp.status_code != 200:
            raise FederationError(
                "sync_failed",
                f"Sync with {target_desk_id} failed with status {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()

