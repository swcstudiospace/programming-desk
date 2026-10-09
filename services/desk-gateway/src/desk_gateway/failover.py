"""Automated multi-desk failover routing dynamically diverting seat dispatch (REQ-CUTOVER-002).

Coordinates with FederationRegistry and UpstreamHealthPoller to route
incoming seat requests to healthy peer desks during node outage or degradation.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from desk_gateway.config import SEATS, Settings
from desk_gateway.cutover import EmergencyIsolationManager
from desk_gateway.federation import FederationRegistry, PeerGateway
from desk_gateway.health import UpstreamHealthPoller

logger = logging.getLogger("desk_gateway.failover")


class FailoverError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass
class FailoverRouteOverride:
    seat: str
    target_desk_id: str
    reason: str
    diverted_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    manual: bool = False

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "target_desk_id": self.target_desk_id,
            "reason": self.reason,
            "diverted_at": self.diverted_at,
            "expires_at": self.expires_at,
            "manual": self.manual,
        }


class FailoverRouter:
    """Evaluates local seat health and determines whether seat dispatch should be diverted to peer desks.

    Implements REQ-CUTOVER-002: Automated multi-desk failover routing dynamically diverting
    seat dispatch to healthy peer desks upon gateway heartbeats/health failing threshold.
    """

    def __init__(
        self,
        registry: FederationRegistry,
        health_poller: UpstreamHealthPoller | None = None,
        isolation_manager: EmergencyIsolationManager | None = None,
        enabled: bool = True,
    ) -> None:
        self.registry = registry
        self.health_poller = health_poller
        self.isolation_manager = isolation_manager
        self.enabled = enabled
        self._lock = threading.RLock()
        self._overrides: dict[str, FailoverRouteOverride] = {}
        # Seat dependencies mapping seat to critical upstreams
        self.seat_upstream_dependencies: dict[str, list[str]] = {
            "systems": ["timescale", "dragonfly"],
            "lead": ["greptime"],
            "quality": ["greptime", "ragflow"],
            "infra": ["timescale", "dragonfly"],
            "web": ["dragonfly"],
            "android": ["dragonfly"],
            "ios": ["dragonfly"],
        }

    def set_manual_divert(
        self,
        seat: str,
        target_desk_id: str,
        reason: str = "manual operator failover",
        ttl_sec: float | None = None,
    ) -> FailoverRouteOverride:
        """Manually force seat divert to a target peer desk."""
        if seat not in SEATS:
            raise FailoverError("invalid_seat", f"Invalid seat '{seat}'", status_code=400)

        peer = self.registry.get_peer(target_desk_id)
        if not peer:
            raise FailoverError("unknown_peer", f"Target peer desk '{target_desk_id}' is not registered", status_code=404)
        if seat not in peer.seats:
            raise FailoverError(
                "peer_unsupported_seat",
                f"Target peer desk '{target_desk_id}' does not support seat '{seat}'",
                status_code=400,
            )

        now = time.time()
        expires = (now + ttl_sec) if ttl_sec else None
        override = FailoverRouteOverride(
            seat=seat,
            target_desk_id=target_desk_id,
            reason=reason,
            diverted_at=now,
            expires_at=expires,
            manual=True,
        )
        with self._lock:
            self._overrides[seat] = override

        logger.warning(
            "FAILOVER: Seat '%s' manually diverted to peer '%s': %s",
            seat,
            target_desk_id,
            reason,
        )
        return override

    def clear_divert(self, seat: str) -> bool:
        """Clear manual or active divert override for a seat."""
        with self._lock:
            if seat in self._overrides:
                del self._overrides[seat]
                logger.info("FAILOVER: Divert cleared for seat '%s', restored to local dispatch", seat)
                return True
            return False

    def get_divert(self, seat: str) -> FailoverRouteOverride | None:
        with self._lock:
            override = self._overrides.get(seat)
            if override and override.is_expired():
                del self._overrides[seat]
                return None
            return override

    def find_healthy_peer_for_seat(self, seat: str) -> PeerGateway | None:
        """Find the healthiest peer desk gateway capable of taking the seat."""
        peers = self.registry.list_peers()
        healthy_candidates = []
        for peer in peers:
            if peer.status == "active" and peer.circuit_state == "closed":
                if seat in peer.seats:
                    healthy_candidates.append(peer)

        if not healthy_candidates:
            return None

        # Sort by lowest failure count, then most recently seen
        healthy_candidates.sort(key=lambda p: (p.failure_count, -p.last_seen))
        return healthy_candidates[0]

    def should_divert_seat(self, seat: str) -> tuple[bool, str | None, str | None]:
        """Determine if a seat invocation should be diverted to a peer desk.

        Returns (should_divert, target_desk_id, reason).
        """
        if not self.enabled:
            return False, None, None

        with self._lock:
            # 1. Check explicit active override
            override = self._overrides.get(seat)
            if override:
                if override.is_expired():
                    del self._overrides[seat]
                else:
                    return True, override.target_desk_id, override.reason

            # 2. Check if seat is isolated locally
            if self.isolation_manager and self.isolation_manager.is_isolated(seat):
                rec = self.isolation_manager.get_isolation(seat)
                peer = self.find_healthy_peer_for_seat(seat)
                if peer:
                    reason = f"local seat isolated: {rec.reason if rec else 'quarantined'}"
                    return True, peer.desk_id, reason

            # 3. Check upstream health dependencies for this seat
            if self.health_poller:
                deps = self.seat_upstream_dependencies.get(seat, [])
                degraded_deps = [dep for dep in deps if not self.health_poller.is_upstream_healthy(dep)]
                if degraded_deps:
                    peer = self.find_healthy_peer_for_seat(seat)
                    if peer:
                        reason = f"local upstream dependencies degraded: {', '.join(degraded_deps)}"
                        return True, peer.desk_id, reason

        return False, None, None

    def get_status(self) -> dict[str, Any]:
        """Status of all seat failover routes and peer availability."""
        with self._lock:
            # Prune expired
            now = time.time()
            expired_seats = [s for s, o in self._overrides.items() if o.expires_at and now > o.expires_at]
            for s in expired_seats:
                del self._overrides[s]

            routes: dict[str, Any] = {}
            for seat in sorted(SEATS):
                divert, target, reason = self.should_divert_seat(seat)
                routes[seat] = {
                    "diverted": divert,
                    "target_desk_id": target if divert else "local",
                    "reason": reason if divert else "local_healthy",
                    "override": self._overrides[seat].to_dict() if seat in self._overrides else None,
                }

            return {
                "enabled": self.enabled,
                "routes": routes,
                "active_diverts_count": sum(1 for r in routes.values() if r["diverted"]),
                "available_peers_count": len([p for p in self.registry.list_peers() if p.status == "active"]),
                "timestamp": time.time(),
            }
