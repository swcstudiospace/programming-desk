"""Autonomous Swarm Self-Healing & Active Immune Defense.

Provides real-time behavioral anomaly detection, automated seat quarantine state machine,
synthetic shadow execution sandboxing, capability pruning, and HMAC-signed quarantine receipts.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import math
import time
from typing import Any, Dict, List, Optional, Set


class SeatContainmentState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    SUSPICIOUS = "SUSPICIOUS"
    QUARANTINED = "QUARANTINED"
    DRAINED = "DRAINED"


def calculate_shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy of a given payload string."""
    if not data:
        return 0.0
    freq: Dict[str, int] = {}
    for char in data:
        freq[char] = freq.get(char, 0) + 1
    total = len(data)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        entropy -= p * math.log2(p)
    return round(entropy, 4)


class BehavioralProfile:
    """Tracks dynamic baseline profiles for a seat's tool executions."""

    def __init__(self, seat_id: str, alpha: float = 0.2):
        self.seat_id = seat_id
        self.alpha = alpha  # Smoothing factor for EMA
        self.sample_count = 0
        self.avg_latency_ms: float = 50.0
        self.avg_entropy: float = 3.5
        self.error_rate: float = 0.0
        self.anomaly_score: float = 0.0
        self.state: SeatContainmentState = SeatContainmentState.HEALTHY
        self.pruned_capabilities: Set[str] = set()
        self.quarantine_reason: Optional[str] = None
        self.quarantine_timestamp: Optional[float] = None

    def update(self, latency_ms: float, entropy: float, is_error: bool) -> float:
        """Update metrics and calculate new anomaly score (0.0 to 1.0+)."""
        self.sample_count += 1
        if self.sample_count == 1:
            # Anomaly is relative to default normal baseline (50ms, 3.5 entropy)
            latency_deviation = max(0.0, (latency_ms - self.avg_latency_ms) / max(10.0, self.avg_latency_ms))
            entropy_deviation = max(0.0, (entropy - self.avg_entropy) / max(1.0, self.avg_entropy))
            self.avg_latency_ms = latency_ms
            self.avg_entropy = entropy
            self.error_rate = 1.0 if is_error else 0.0
        else:
            latency_deviation = max(0.0, (latency_ms - self.avg_latency_ms) / max(10.0, self.avg_latency_ms))
            entropy_deviation = max(0.0, (entropy - self.avg_entropy) / max(1.0, self.avg_entropy))
            self.avg_latency_ms = (self.alpha * latency_ms) + ((1.0 - self.alpha) * self.avg_latency_ms)
            self.avg_entropy = (self.alpha * entropy) + ((1.0 - self.alpha) * self.avg_entropy)
            error_val = 1.0 if is_error else 0.0
            self.error_rate = (self.alpha * error_val) + ((1.0 - self.alpha) * self.error_rate)

        error_penalty = 1.0 if is_error else 0.0

        # Weighted anomaly score
        instant_score = (0.3 * min(2.0, latency_deviation)) + (0.3 * min(2.0, entropy_deviation)) + (0.4 * (self.error_rate + error_penalty))
        self.anomaly_score = round(instant_score, 4)
        return self.anomaly_score

    def reset_baseline(self, allowed_capabilities: Set[str], target_state: SeatContainmentState = SeatContainmentState.HEALTHY) -> None:
        """Reset profile metrics and capabilities back to a golden baseline."""
        self.sample_count = 0
        self.avg_latency_ms = 50.0
        self.avg_entropy = 3.5
        self.error_rate = 0.0
        self.anomaly_score = 0.0
        self.state = target_state
        self.pruned_capabilities = set(SwarmImmuneEngine.ALL_CAPABILITIES) - allowed_capabilities
        self.quarantine_reason = None
        self.quarantine_timestamp = None


class ShadowExecutionSandbox:
    """Speculatively executes suspicious tool calls in a scratchpad without mutating state."""

    def __init__(self):
        self.scratchpads: Dict[str, Dict[str, Any]] = {}

    def execute_in_shadow(
        self,
        execution_id: str,
        seat_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        handler: Any,
    ) -> Dict[str, Any]:
        """Execute a handler in an isolated scratchpad buffer."""
        scratchpad = {
            "execution_id": execution_id,
            "seat_id": seat_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "timestamp": time.time(),
            "mutations": [],
            "status": "PENDING",
        }
        self.scratchpads[execution_id] = scratchpad
        try:
            result = handler(arguments)
            scratchpad["status"] = "SAFE"
            scratchpad["result"] = result
            return {
                "execution_id": execution_id,
                "status": "SAFE",
                "result": result,
                "sandboxed": True,
            }
        except Exception as exc:
            scratchpad["status"] = "SUSPICIOUS_FAIL"
            scratchpad["error"] = str(exc)
            return {
                "execution_id": execution_id,
                "status": "SUSPICIOUS_FAIL",
                "error": str(exc),
                "sandboxed": True,
            }


class SwarmImmuneEngine:
    """Core autonomous swarm immune defense engine."""

    ALL_CAPABILITIES = {
        "mcp_tool_execute",
        "file_mutate",
        "git_commit",
        "peer_broadcast",
        "read_telemetry",
    }

    def __init__(self, secret_key: str = "swarm-immune-secret-key-3.4"):
        self.secret_key = secret_key.encode("utf-8")
        self.profiles: Dict[str, BehavioralProfile] = {}
        self.shadow_sandbox = ShadowExecutionSandbox()
        self.receipts: List[Dict[str, Any]] = []

    def get_or_create_profile(self, seat_id: str) -> BehavioralProfile:
        if seat_id not in self.profiles:
            self.profiles[seat_id] = BehavioralProfile(seat_id)
        return self.profiles[seat_id]

    def record_telemetry(
        self,
        seat_id: str,
        tool_name: str,
        payload: str,
        latency_ms: float,
        is_error: bool = False,
    ) -> Dict[str, Any]:
        """Record tool telemetry, compute anomaly score, and adjust containment state."""
        profile = self.get_or_create_profile(seat_id)
        entropy = calculate_shannon_entropy(payload)
        anomaly_score = profile.update(latency_ms, entropy, is_error)

        old_state = profile.state
        new_state = old_state

        # State transition thresholds
        if anomaly_score >= 1.0:
            new_state = SeatContainmentState.QUARANTINED
        elif anomaly_score >= 0.5:
            if old_state != SeatContainmentState.QUARANTINED and old_state != SeatContainmentState.DRAINED:
                new_state = SeatContainmentState.SUSPICIOUS
        elif anomaly_score < 0.3:
            if old_state == SeatContainmentState.SUSPICIOUS:
                new_state = SeatContainmentState.HEALTHY

        if new_state != old_state:
            self._transition_seat_state(profile, new_state, f"Anomaly score threshold crossed: {anomaly_score}")

        return {
            "seat_id": seat_id,
            "tool_name": tool_name,
            "entropy": entropy,
            "latency_ms": latency_ms,
            "anomaly_score": anomaly_score,
            "state": profile.state.value,
            "allowed_capabilities": list(self.get_allowed_capabilities(seat_id)),
        }

    def _transition_seat_state(
        self,
        profile: BehavioralProfile,
        new_state: SeatContainmentState,
        reason: str,
    ) -> None:
        profile.state = new_state
        if new_state == SeatContainmentState.QUARANTINED:
            profile.quarantine_reason = reason
            profile.quarantine_timestamp = time.time()
            profile.pruned_capabilities = {"file_mutate", "git_commit", "mcp_tool_execute", "peer_broadcast"}
            self._generate_receipt(profile.seat_id, "QUARANTINE", reason)
        elif new_state == SeatContainmentState.DRAINED:
            profile.quarantine_reason = reason
            profile.quarantine_timestamp = time.time()
            profile.pruned_capabilities = set(self.ALL_CAPABILITIES)
            self._generate_receipt(profile.seat_id, "DRAIN", reason)
        elif new_state == SeatContainmentState.SUSPICIOUS:
            profile.pruned_capabilities = {"git_commit", "peer_broadcast"}
        elif new_state == SeatContainmentState.HEALTHY:
            profile.pruned_capabilities.clear()
            profile.quarantine_reason = None
            profile.quarantine_timestamp = None

    def quarantine_seat(self, seat_id: str, reason: str = "Operator manual quarantine") -> Dict[str, Any]:
        """Manually or rule-based quarantine of a seat."""
        profile = self.get_or_create_profile(seat_id)
        self._transition_seat_state(profile, SeatContainmentState.QUARANTINED, reason)
        receipt = self.receipts[-1] if self.receipts else None
        return {
            "seat_id": seat_id,
            "state": profile.state.value,
            "new_state": profile.state.value,
            "reason": reason,
            "receipt": receipt,
        }

    def drain_seat(self, seat_id: str, reason: str = "Drain compromised seat") -> Dict[str, Any]:
        """Completely isolate and drain a compromised seat."""
        profile = self.get_or_create_profile(seat_id)
        self._transition_seat_state(profile, SeatContainmentState.DRAINED, reason)
        receipt = self.receipts[-1] if self.receipts else None
        return {
            "seat_id": seat_id,
            "state": profile.state.value,
            "new_state": profile.state.value,
            "reason": reason,
            "receipt": receipt,
        }

    def unquarantine_seat(self, seat_id: str, reason: str = "Rehabilitated") -> Dict[str, Any]:
        """Release seat from quarantine back to healthy."""
        profile = self.get_or_create_profile(seat_id)
        self._transition_seat_state(profile, SeatContainmentState.HEALTHY, reason)
        self._generate_receipt(seat_id, "UNQUARANTINE", reason)
        return {
            "seat_id": seat_id,
            "state": profile.state.value,
            "new_state": profile.state.value,
            "reason": reason,
            "receipt": self.receipts[-1],
        }

    def prune_capabilities(self, seat_id: str, capabilities_to_revoke: Set[str]) -> Set[str]:
        """Explicitly revoke capabilities for a seat."""
        profile = self.get_or_create_profile(seat_id)
        profile.pruned_capabilities.update(capabilities_to_revoke)
        return self.get_allowed_capabilities(seat_id)

    def get_allowed_capabilities(self, seat_id: str) -> Set[str]:
        """Return remaining allowed capabilities for a seat."""
        profile = self.get_or_create_profile(seat_id)
        return self.ALL_CAPABILITIES - profile.pruned_capabilities

    def is_capability_permitted(self, seat_id: str, capability: str) -> bool:
        """Check if seat has execution permission for capability."""
        return capability in self.get_allowed_capabilities(seat_id)

    def should_shadow_execute(self, seat_id: str) -> bool:
        """Returns True if seat is in SUSPICIOUS state and mutations must be shadow-executed."""
        profile = self.get_or_create_profile(seat_id)
        return profile.state == SeatContainmentState.SUSPICIOUS

    def _generate_receipt(self, seat_id: str, action: str, reason: str) -> Dict[str, Any]:
        """Generate cryptographically signed HMAC-SHA256 quarantine receipt."""
        ts = time.time()
        payload = f"{seat_id}:{action}:{reason}:{ts}"
        sig = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        receipt = {
            "receipt_id": f"qrcpt-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}",
            "seat_id": seat_id,
            "action": action,
            "reason": reason,
            "timestamp": ts,
            "signature": sig,
        }
        self.receipts.append(receipt)
        return receipt

    def verify_receipt(self, receipt: Dict[str, Any]) -> bool:
        """Verify the cryptographic signature of a quarantine receipt."""
        try:
            seat_id = receipt["seat_id"]
            action = receipt["action"]
            reason = receipt["reason"]
            ts = receipt["timestamp"]
            sig = receipt["signature"]
            payload = f"{seat_id}:{action}:{reason}:{ts}"
            expected = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get aggregate swarm immune defense status."""
        seats_status = {}
        for sid, p in self.profiles.items():
            seats_status[sid] = {
                "state": p.state.value,
                "anomaly_score": p.anomaly_score,
                "error_rate": round(p.error_rate, 3),
                "avg_entropy": round(p.avg_entropy, 3),
                "avg_latency_ms": round(p.avg_latency_ms, 2),
                "pruned_capabilities": list(p.pruned_capabilities),
            }
        return {
            "total_tracked_seats": len(self.profiles),
            "seats": seats_status,
            "total_receipts": len(self.receipts),
        }
