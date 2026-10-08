"""Synthetic chaos injection harness simulating network partitions, packet loss, and latency spikes (REQ-CHAOS-001).

Simulates faults across Railway dependencies:
- greptime
- timescale
- dragonfly
- hindsight
- ragflow
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("desk_gateway.chaos")

VALID_TARGETS = {"greptime", "timescale", "dragonfly", "hindsight", "ragflow", "all"}


class FaultType(str, Enum):
    LATENCY = "latency"          # Injects delay before upstream response
    PACKET_LOSS = "packet_loss"  # Probabilistically drops requests
    PARTITION = "partition"      # Simulates complete network partition / connection error
    ERROR_CODE = "error_code"    # Injects upstream HTTP 500/502/503 responses


class ChaosException(Exception):
    """Exception raised when a synthetic chaos fault is applied."""

    def __init__(self, target: str, fault_type: str, detail: str) -> None:
        super().__init__(f"Synthetic chaos [{fault_type}] on '{target}': {detail}")
        self.target = target
        self.fault_type = fault_type
        self.detail = detail


@dataclass
class ChaosRule:
    rule_id: str
    target: str  # greptime, timescale, dragonfly, hindsight, ragflow, or all
    fault_type: FaultType
    probability: float = 1.0  # 0.0 to 1.0
    delay_ms: float = 0.0
    error_code: int = 503
    error_message: str = "Synthetic chaos network partition"
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time)
    injected_count: int = 0

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "target": self.target,
            "fault_type": self.fault_type.value,
            "probability": self.probability,
            "delay_ms": self.delay_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "injected_count": self.injected_count,
            "active": not self.is_expired(),
        }


class ChaosHarness:
    """Evaluates and applies synthetic chaos faults to upstream services (REQ-CHAOS-001)."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._rules: dict[str, ChaosRule] = {}
        self._lock = threading.RLock()

    def add_rule(
        self,
        target: str,
        fault_type: FaultType | str,
        probability: float = 1.0,
        delay_ms: float = 0.0,
        error_code: int = 503,
        error_message: str = "Synthetic chaos fault",
        duration_sec: float | None = None,
        rule_id: str | None = None,
    ) -> ChaosRule:
        """Add or update an active chaos rule."""
        target_lower = target.lower()
        if target_lower not in VALID_TARGETS:
            raise ValueError(f"Target '{target}' invalid. Must be one of {sorted(VALID_TARGETS)}")

        f_type = FaultType(fault_type) if isinstance(fault_type, str) else fault_type
        now = time.time()
        expires = (now + duration_sec) if duration_sec else None
        rid = rule_id or f"chaos-{target_lower}-{f_type.value}-{int(now * 1000)}"

        rule = ChaosRule(
            rule_id=rid,
            target=target_lower,
            fault_type=f_type,
            probability=max(0.0, min(1.0, probability)),
            delay_ms=max(0.0, delay_ms),
            error_code=error_code,
            error_message=error_message,
            expires_at=expires,
            created_at=now,
        )

        with self._lock:
            self._rules[rid] = rule
            logger.warning("CHAOS RULE INJECTED: %s for target '%s'", rid, target_lower)
            return rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a specific chaos rule."""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                logger.info("Chaos rule '%s' removed", rule_id)
                return True
            return False

    def clear_rules(self) -> int:
        """Clear all active chaos rules."""
        with self._lock:
            count = len(self._rules)
            self._rules.clear()
            logger.info("All %d chaos rules cleared", count)
            return count

    def get_rules(self) -> list[ChaosRule]:
        """List all active non-expired rules."""
        with self._lock:
            now = time.time()
            active = []
            expired_keys = []
            for rid, r in self._rules.items():
                if r.expires_at and now > r.expires_at:
                    expired_keys.append(rid)
                else:
                    active.append(r)
            for k in expired_keys:
                del self._rules[k]
            return active

    async def apply_fault(self, target: str) -> None:
        """Asynchronously apply any active faults for target.

        Raises ChaosException if a drop or partition fault triggers.
        Applies delay if latency fault triggers.
        """
        if not self.enabled:
            return

        target_lower = target.lower()
        active_rules = self.get_rules()

        matching_rules = [
            r for r in active_rules
            if (r.target == target_lower or r.target == "all") and not r.is_expired()
        ]

        for rule in matching_rules:
            if random.random() <= rule.probability:
                rule.injected_count += 1
                if rule.fault_type == FaultType.LATENCY and rule.delay_ms > 0:
                    logger.debug("Applying chaos latency %.1fms to %s", rule.delay_ms, target)
                    await asyncio.sleep(rule.delay_ms / 1000.0)

                elif rule.fault_type == FaultType.PACKET_LOSS:
                    logger.warning("Applying chaos packet loss to %s", target)
                    raise ChaosException(target=target, fault_type="packet_loss", detail="Simulated packet drop")

                elif rule.fault_type == FaultType.PARTITION:
                    logger.warning("Applying chaos partition to %s", target)
                    raise ChaosException(target=target, fault_type="partition", detail=rule.error_message)

                elif rule.fault_type == FaultType.ERROR_CODE:
                    logger.warning("Applying chaos error code %d to %s", rule.error_code, target)
                    raise ChaosException(target=target, fault_type="error_code", detail=rule.error_message)
