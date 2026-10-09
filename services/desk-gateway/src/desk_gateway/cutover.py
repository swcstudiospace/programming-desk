"""Production live traffic cutover, canary traffic splitting, and emergency seat isolation.

Provides runtime orchestration for:
- Live traffic migration from legacy stubs to federated VPS gateway endpoints with zero request drop (REQ-CUTOVER-001).
- Canary release traffic splitting mechanism admitting graduated percentages of external webhook intake (REQ-CUTOVER-004).
- Automated emergency rollback triggers isolating compromised or degraded seat instances within 5 seconds of anomaly detection (REQ-CUTOVER-005).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from desk_gateway.config import SEATS, Settings

logger = logging.getLogger("desk_gateway.cutover")


class CutoverError(Exception):
    """Base exception for cutover errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SeatIsolatedError(CutoverError):
    """Raised when an operation targets an isolated seat."""

    def __init__(self, seat: str, reason: str = "") -> None:
        msg = f"Seat '{seat}' is quarantined and isolated from traffic"
        if reason:
            msg += f": {reason}"
        super().__init__("seat_isolated", msg, 503)


@dataclass
class IsolationRecord:
    seat: str
    isolated_at: float
    reason: str
    actor: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "isolated_at": self.isolated_at,
            "reason": self.reason,
            "actor": self.actor,
            "metadata": self.metadata,
        }


class EmergencyIsolationManager:
    """Manages immediate quarantine and restoration of seat instances (REQ-CUTOVER-005).

    Guarantees isolation state is applied in-memory within milliseconds of detection.
    """

    def __init__(self, initial_isolated_seats: list[str] | None = None) -> None:
        self._lock = threading.RLock()
        self._isolated: dict[str, IsolationRecord] = {}
        if initial_isolated_seats:
            now = time.time()
            for seat in initial_isolated_seats:
                if seat in SEATS:
                    self._isolated[seat] = IsolationRecord(
                        seat=seat,
                        isolated_at=now,
                        reason="configured at startup",
                        actor="config",
                    )

    def isolate_seat(
        self,
        seat: str,
        reason: str = "anomaly detected",
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> IsolationRecord:
        """Quarantine a seat immediately."""
        if seat not in SEATS:
            raise CutoverError("unknown_seat", f"Unknown seat '{seat}'", 400)

        with self._lock:
            record = IsolationRecord(
                seat=seat,
                isolated_at=time.time(),
                reason=reason,
                actor=actor,
                metadata=metadata or {},
            )
            self._isolated[seat] = record
            logger.warning(
                "EMERGENCY ISOLATION: seat '%s' quarantined by %s. Reason: %s",
                seat,
                actor,
                reason,
            )
            return record

    def restore_seat(self, seat: str, actor: str = "operator") -> bool:
        """Remove a seat from quarantine."""
        with self._lock:
            if seat in self._isolated:
                del self._isolated[seat]
                logger.info("RESTORED: seat '%s' unquarantined by %s", seat, actor)
                return True
            return False

    def is_isolated(self, seat: str) -> bool:
        """Check if a seat is currently isolated."""
        with self._lock:
            return seat in self._isolated

    def get_isolation(self, seat: str) -> IsolationRecord | None:
        with self._lock:
            return self._isolated.get(seat)

    def list_isolated(self) -> list[IsolationRecord]:
        with self._lock:
            return list(self._isolated.values())


class CanaryRouter:
    """Deterministic percentage-based traffic splitting for intake and webhooks (REQ-CUTOVER-004).

    Splits traffic between canary (live new VPS endpoints) and baseline (legacy stubs)
    based on a hash of the partition key (e.g., idempotency_key, origin + title, or request identifier)
    or sequential evaluation when partition key is absent.
    """

    def __init__(self, canary_percentage: int = 100) -> None:
        self._lock = threading.RLock()
        self.set_percentage(canary_percentage)

    def set_percentage(self, percentage: int) -> None:
        if not (0 <= percentage <= 100):
            raise CutoverError("invalid_percentage", "Canary percentage must be between 0 and 100", 400)
        with self._lock:
            self._percentage = percentage
            logger.info("Canary intake percentage set to %d%%", percentage)

    @property
    def percentage(self) -> int:
        with self._lock:
            return self._percentage

    def should_route_to_canary(self, partition_key: str | None = None) -> bool:
        """Determine if a request should route to canary or legacy.

        Returns True if routed to canary (new VPS implementation), False if routed to legacy stub.
        """
        pct = self.percentage
        if pct >= 100:
            return True
        if pct <= 0:
            return False

        if partition_key:
            # Deterministic bucket assignment [0..99] using SHA-256
            h = hashlib.sha256(partition_key.encode("utf-8")).hexdigest()
            bucket = int(h[:8], 16) % 100
            return bucket < pct
        else:
            # Fallback to pseudo-random based on current time
            bucket = int(time.time() * 1000000) % 100
            return bucket < pct


@dataclass
class CutoverState:
    enabled: bool
    phase: str  # "legacy", "canary", "live", "rollback"
    canary_percentage: int
    active_ingress_target: str  # "vps_gateway" or "legacy_stub"
    switched_at: float
    isolated_seats: list[str]


class CutoverOrchestrator:
    """Manages production live traffic cutover transitions (REQ-CUTOVER-001).

    Controls transitioning ingress routing from legacy stubs to VPS gateway endpoints
    with zero request drop, tracking migration phases, canary splitting, and isolation status.
    """

    def __init__(self, settings: Settings, isolation_manager: EmergencyIsolationManager | None = None) -> None:
        self.settings = settings
        self.isolation_manager = isolation_manager or EmergencyIsolationManager(settings.isolated_seats)
        self.canary_router = CanaryRouter(settings.canary_percentage)
        self._lock = threading.RLock()
        self._enabled = settings.cutover_enabled
        self._ingress_target = "vps_gateway" if self._enabled else "legacy_stub"
        self._phase = "live" if (self._enabled and self.canary_router.percentage == 100) else (
            "canary" if self._enabled else "legacy"
        )
        self._switched_at = time.time()
        self._cutover_history: list[dict[str, Any]] = [
            {
                "timestamp": self._switched_at,
                "phase": self._phase,
                "ingress_target": self._ingress_target,
                "canary_percentage": self.canary_router.percentage,
                "reason": "initialization",
            }
        ]

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    @property
    def phase(self) -> str:
        with self._lock:
            return self._phase

    @property
    def ingress_target(self) -> str:
        with self._lock:
            return self._ingress_target

    def get_status(self) -> dict[str, Any]:
        """Return full cutover status report."""
        with self._lock:
            isolated = [r.to_dict() for r in self.isolation_manager.list_isolated()]
            return {
                "ok": True,
                "cutover_enabled": self._enabled,
                "phase": self._phase,
                "ingress_target": self._ingress_target,
                "canary_percentage": self.canary_router.percentage,
                "switched_at": self._switched_at,
                "isolated_seats": isolated,
                "history": list(self._cutover_history),
            }

    def set_cutover_state(
        self,
        enabled: bool,
        canary_percentage: int | None = None,
        reason: str = "manual update",
    ) -> dict[str, Any]:
        """Transition live cutover state safely without dropping requests (REQ-CUTOVER-001)."""
        with self._lock:
            now = time.time()
            self._enabled = enabled
            if canary_percentage is not None:
                self.canary_router.set_percentage(canary_percentage)

            pct = self.canary_router.percentage
            if not enabled:
                self._ingress_target = "legacy_stub"
                self._phase = "legacy"
            elif pct == 100:
                self._ingress_target = "vps_gateway"
                self._phase = "live"
            elif pct == 0:
                self._ingress_target = "legacy_stub"
                self._phase = "legacy"
            else:
                self._ingress_target = "vps_gateway"
                self._phase = "canary"

            self._switched_at = now
            entry = {
                "timestamp": now,
                "phase": self._phase,
                "ingress_target": self._ingress_target,
                "canary_percentage": pct,
                "reason": reason,
            }
            self._cutover_history.append(entry)
            logger.info("Cutover state updated: phase=%s target=%s canary=%d%% reason=%s", self._phase, self._ingress_target, pct, reason)
            return self.get_status()

    def rollback(self, reason: str = "emergency rollback") -> dict[str, Any]:
        """Roll back all traffic immediately to legacy stub (REQ-CUTOVER-001, REQ-CUTOVER-005)."""
        with self._lock:
            now = time.time()
            self._enabled = False
            self.canary_router.set_percentage(0)
            self._ingress_target = "legacy_stub"
            self._phase = "rollback"
            self._switched_at = now
            entry = {
                "timestamp": now,
                "phase": self._phase,
                "ingress_target": self._ingress_target,
                "canary_percentage": 0,
                "reason": reason,
            }
            self._cutover_history.append(entry)
            logger.warning("CUTOVER ROLLBACK TRIGGERED: reason=%s", reason)
            return self.get_status()
