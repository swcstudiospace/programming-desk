"""Cross-Desk Distributed Neural Routing & Semantic Dispatch Engine.

Implements multi-objective neural routing across federated desks, capability embeddings,
cross-desk context forwarding, dynamic circuit-breaking, and HMAC-attested decision receipts.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CircuitState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OPEN = "OPEN"


@dataclass
class DeskCapabilityProfile:
    desk_id: str
    seat_ids: List[str]
    domains: List[str]
    supported_tools: List[str]
    capacity_limit: int = 100
    active_load: int = 0
    base_latency_ms: float = 25.0
    cost_per_1k_tokens: float = 0.002
    vector_signature: Optional[List[float]] = None

    @property
    def load_ratio(self) -> float:
        if self.capacity_limit <= 0:
            return 1.0
        return min(1.0, max(0.0, self.active_load / self.capacity_limit))


@dataclass
class IntentVector:
    domain_weights: Dict[str, float]
    complexity_score: float
    required_tools: List[str]
    max_latency_budget_ms: float = 500.0
    max_cost_budget: float = 0.05
    semantic_embedding: List[float] = field(default_factory=list)


@dataclass
class ContextForwardingEnvelope:
    envelope_id: str
    source_desk_id: str
    target_desk_id: str
    target_seat_id: str
    task_id: str
    conversation_state: Dict[str, Any]
    sensory_context: Dict[str, Any]
    forwarding_timestamp: float
    signature: str


@dataclass
class RoutingDecisionReceipt:
    receipt_id: str
    task_id: str
    selected_desk_id: str
    selected_seat_id: str
    composite_score: float
    candidate_scores: Dict[str, float]
    estimated_latency_ms: float
    routing_timestamp: float
    signature: str


class IntentVectorizer:
    """Vectorizes task text and capability requirements into structured intent spaces."""

    DOMAIN_KEYWORDS: Dict[str, List[str]] = {
        "systems_backend": ["database", "postgres", "redis", "gateway", "substrate", "backend", "concurrency", "socket", "api"],
        "web_edge": ["frontend", "react", "html", "css", "dom", "edge", "ui", "browser", "component"],
        "mobile_native": ["android", "ios", "kotlin", "swift", "mobile", "compose", "swiftui"],
        "infrastructure": ["docker", "kubernetes", "vps", "tailscale", "caddy", "linux", "cloud", "ansible", "nginx"],
        "security_quality": ["audit", "compliance", "zero-trust", "ast", "test", "verification", "sandbox", "crypto", "vulnerability"],
        "governance": ["consensus", "proposal", "vote", "byzantine", "ballot", "quorum", "veto"],
    }

    @classmethod
    def vectorize(
        cls,
        task_text: str,
        required_tools: Optional[List[str]] = None,
        max_latency_budget_ms: float = 500.0,
        max_cost_budget: float = 0.05,
    ) -> IntentVector:
        lowered = task_text.lower()
        words = lowered.split()
        total_words = max(1, len(words))

        domain_weights: Dict[str, float] = {}
        for domain, keywords in cls.DOMAIN_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in lowered)
            domain_weights[domain] = round(matches / (len(keywords) * 0.5 + 1e-6), 4)

        # Normalize domain weights
        max_w = max(domain_weights.values()) if domain_weights else 0.0
        if max_w > 0:
            domain_weights = {k: round(v / max_w, 4) for k, v in domain_weights.items()}
        else:
            domain_weights["systems_backend"] = 0.5

        # Estimate complexity based on text length and technical term count
        complexity = min(1.0, max(0.1, (len(words) / 80.0) + (len(required_tools or []) * 0.15)))

        # Deterministic pseudo-embedding from SHA-256 hash segments
        h = hashlib.sha256(task_text.encode("utf-8")).digest()
        embedding = [round(b / 255.0, 4) for b in h[:8]]

        return IntentVector(
            domain_weights=domain_weights,
            complexity_score=round(complexity, 4),
            required_tools=list(required_tools or []),
            max_latency_budget_ms=max_latency_budget_ms,
            max_cost_budget=max_cost_budget,
            semantic_embedding=embedding,
        )


class RoutingCircuitBreaker:
    """Maintains circuit-breaker states for federated desk targets."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_time_seconds: float = 30.0,
        probe_latency_threshold_ms: float = 1500.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        self.probe_latency_threshold_ms = probe_latency_threshold_ms
        self._consecutive_failures: Dict[str, int] = {}
        self._last_state_change: Dict[str, float] = {}
        self._circuit_states: Dict[str, CircuitState] = {}
        self._recent_latencies: Dict[str, List[float]] = {}

    def get_state(self, desk_id: str) -> CircuitState:
        now = time.time()
        current = self._circuit_states.get(desk_id, CircuitState.HEALTHY)
        if current == CircuitState.OPEN:
            last_change = self._last_state_change.get(desk_id, 0.0)
            if now - last_change >= self.recovery_time_seconds:
                # Half-open/degraded probe window
                self._circuit_states[desk_id] = CircuitState.DEGRADED
                return CircuitState.DEGRADED
        return current

    def record_probe(self, desk_id: str, success: bool, latency_ms: float) -> CircuitState:
        now = time.time()
        lat_list = self._recent_latencies.setdefault(desk_id, [])
        lat_list.append(latency_ms)
        if len(lat_list) > 10:
            lat_list.pop(0)

        if not success or latency_ms > self.probe_latency_threshold_ms:
            fails = self._consecutive_failures.get(desk_id, 0) + 1
            self._consecutive_failures[desk_id] = fails
            if fails >= self.failure_threshold:
                self._circuit_states[desk_id] = CircuitState.OPEN
                self._last_state_change[desk_id] = now
            else:
                self._circuit_states[desk_id] = CircuitState.DEGRADED
                self._last_state_change[desk_id] = now
        else:
            self._consecutive_failures[desk_id] = 0
            self._circuit_states[desk_id] = CircuitState.HEALTHY
            self._last_state_change[desk_id] = now

        return self._circuit_states[desk_id]


class NeuralRoutingEngine:
    """Core engine orchestrating distributed neural routing and attested dispatch."""

    def __init__(self, signing_secret: str = "desk-neural-routing-secret-key") -> None:
        self.signing_secret = signing_secret.encode("utf-8")
        self.desks: Dict[str, DeskCapabilityProfile] = {}
        self.circuit_breaker = RoutingCircuitBreaker()
        self.decision_receipts: Dict[str, RoutingDecisionReceipt] = {}

    def register_desk(self, profile: DeskCapabilityProfile) -> None:
        self.desks[profile.desk_id] = profile

    def update_desk_load(self, desk_id: str, active_load: int) -> None:
        if desk_id in self.desks:
            self.desks[desk_id].active_load = max(0, active_load)

    def score_desk(self, intent: IntentVector, desk: DeskCapabilityProfile) -> Tuple[float, Dict[str, float]]:
        state = self.circuit_breaker.get_state(desk.desk_id)
        if state == CircuitState.OPEN:
            return 0.0, {"circuit_open": 0.0}

        # 1. Tool capability match score (0.0 to 1.0)
        if intent.required_tools:
            matched_tools = sum(1 for t in intent.required_tools if t in desk.supported_tools)
            tool_score = matched_tools / len(intent.required_tools)
        else:
            tool_score = 1.0

        # Hard rejection if required tools are missing completely
        if intent.required_tools and tool_score < 0.5:
            return 0.0, {"tool_score": tool_score, "rejected": 1.0}

        # 2. Domain relevance score
        desk_domains = set(desk.domains)
        domain_score = 0.1
        for dom, weight in intent.domain_weights.items():
            if dom in desk_domains:
                domain_score += weight
        domain_score = min(1.0, domain_score)

        # 3. Capacity & load score
        load_score = max(0.0, 1.0 - desk.load_ratio)

        # 4. Latency score
        est_latency = desk.base_latency_ms * (1.0 + (desk.load_ratio * 1.5))
        if est_latency > intent.max_latency_budget_ms:
            lat_score = 0.2
        else:
            lat_score = 1.0 - (est_latency / (intent.max_latency_budget_ms * 1.5))
        lat_score = max(0.0, min(1.0, lat_score))

        # 5. Cost score
        if desk.cost_per_1k_tokens > intent.max_cost_budget:
            cost_score = 0.1
        else:
            cost_score = 1.0 - (desk.cost_per_1k_tokens / (intent.max_cost_budget * 2.0))
        cost_score = max(0.0, min(1.0, cost_score))

        # Degraded circuit penalty
        circuit_factor = 0.5 if state == CircuitState.DEGRADED else 1.0

        # Multi-objective weighted sum
        composite = (
            (0.35 * tool_score)
            + (0.25 * domain_score)
            + (0.20 * load_score)
            + (0.10 * lat_score)
            + (0.10 * cost_score)
        ) * circuit_factor

        details = {
            "tool_score": round(tool_score, 4),
            "domain_score": round(domain_score, 4),
            "load_score": round(load_score, 4),
            "lat_score": round(lat_score, 4),
            "cost_score": round(cost_score, 4),
            "composite": round(composite, 4),
            "estimated_latency_ms": round(est_latency, 2),
        }
        return composite, details

    def route_task(
        self,
        task_id: str,
        task_text: str,
        required_tools: Optional[List[str]] = None,
        max_latency_budget_ms: float = 500.0,
        max_cost_budget: float = 0.05,
    ) -> Tuple[RoutingDecisionReceipt, Optional[DeskCapabilityProfile]]:
        intent = IntentVectorizer.vectorize(
            task_text=task_text,
            required_tools=required_tools,
            max_latency_budget_ms=max_latency_budget_ms,
            max_cost_budget=max_cost_budget,
        )

        candidate_scores: Dict[str, float] = {}
        candidate_details: Dict[str, Dict[str, float]] = {}

        for d_id, desk in self.desks.items():
            comp_score, details = self.score_desk(intent, desk)
            candidate_scores[d_id] = comp_score
            candidate_details[d_id] = details

        if not candidate_scores or max(candidate_scores.values(), default=0.0) <= 0.0:
            # Fallback or rejection
            receipt_id = f"rcpt-fail-{hashlib.sha256(f'{task_id}-{time.time()}'.encode()).hexdigest()[:12]}"
            receipt = RoutingDecisionReceipt(
                receipt_id=receipt_id,
                task_id=task_id,
                selected_desk_id="none",
                selected_seat_id="none",
                composite_score=0.0,
                candidate_scores=candidate_scores,
                estimated_latency_ms=0.0,
                routing_timestamp=time.time(),
                signature=self._sign_payload(f"{receipt_id}:none:0.0"),
            )
            self.decision_receipts[receipt_id] = receipt
            return receipt, None

        best_desk_id = max(candidate_scores.keys(), key=lambda k: candidate_scores[k])
        best_desk = self.desks[best_desk_id]
        best_score = candidate_scores[best_desk_id]
        est_lat = candidate_details[best_desk_id].get("estimated_latency_ms", best_desk.base_latency_ms)

        # Select seat based on load/round-robin hash
        seat_index = int(hashlib.sha256(task_id.encode()).hexdigest(), 16) % max(1, len(best_desk.seat_ids))
        selected_seat_id = best_desk.seat_ids[seat_index] if best_desk.seat_ids else f"{best_desk_id}-seat-0"

        receipt_id = f"rcpt-{hashlib.sha256(f'{task_id}-{best_desk_id}-{time.time()}'.encode()).hexdigest()[:12]}"
        sig_body = f"{receipt_id}:{task_id}:{best_desk_id}:{selected_seat_id}:{best_score}"
        signature = self._sign_payload(sig_body)

        receipt = RoutingDecisionReceipt(
            receipt_id=receipt_id,
            task_id=task_id,
            selected_desk_id=best_desk_id,
            selected_seat_id=selected_seat_id,
            composite_score=best_score,
            candidate_scores=candidate_scores,
            estimated_latency_ms=est_lat,
            routing_timestamp=time.time(),
            signature=signature,
        )
        self.decision_receipts[receipt_id] = receipt
        return receipt, best_desk

    def create_context_envelope(
        self,
        task_id: str,
        source_desk_id: str,
        target_desk_id: str,
        target_seat_id: str,
        conversation_state: Dict[str, Any],
        sensory_context: Optional[Dict[str, Any]] = None,
    ) -> ContextForwardingEnvelope:
        sensory = sensory_context or {}
        now = time.time()
        envelope_id = f"env-{hashlib.sha256(f'{task_id}-{source_desk_id}-{target_desk_id}-{now}'.encode()).hexdigest()[:12]}"
        sig_body = f"{envelope_id}:{task_id}:{source_desk_id}:{target_desk_id}:{target_seat_id}:{len(conversation_state)}"
        signature = self._sign_payload(sig_body)

        return ContextForwardingEnvelope(
            envelope_id=envelope_id,
            source_desk_id=source_desk_id,
            target_desk_id=target_desk_id,
            target_seat_id=target_seat_id,
            task_id=task_id,
            conversation_state=conversation_state,
            sensory_context=sensory,
            forwarding_timestamp=now,
            signature=signature,
        )

    def verify_envelope(self, envelope: ContextForwardingEnvelope) -> bool:
        sig_body = f"{envelope.envelope_id}:{envelope.task_id}:{envelope.source_desk_id}:{envelope.target_desk_id}:{envelope.target_seat_id}:{len(envelope.conversation_state)}"
        expected = self._sign_payload(sig_body)
        return hmac.compare_digest(envelope.signature, expected)

    def _sign_payload(self, body: str) -> str:
        return hmac.new(self.signing_secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
