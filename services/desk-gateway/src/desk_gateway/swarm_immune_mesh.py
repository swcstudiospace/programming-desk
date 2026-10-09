"""Autonomous Multi-Agent Self-Evolving Immune & Swarm Anti-Fragility Mesh (Milestone v4.8 - Phase 62).

Implements:
- ThreatVector / AttackSignature: Typed behavioral threat patterns (e.g. Byzantine prompt injection, latency poisoning, AST boundary breakout, entropy surges).
- ImmuneAntibody / NeutralizationPolicy: Cryptographically verifiable antibodies containing signature matchers, neutralization mitigation actions, and quarantine triggers.
- MutationHeuristic / DynamicEvolver: Genetic heuristic mutator dynamically evolving mitigation rules against zero-day mutated threat vectors.
- MultiSeatAntibodyDistributor: Peer-to-peer anti-entropy distribution propagating antibodies across federated seats with HMAC-SHA256 signatures.
- SwarmAntiFragilityEngine: Active stress-hardening engine applying controlled perturbations to test runtime resilience and measure post-perturbation fitness gain.
- RuntimeReconstitutionSupervisor: Automated state rollbacks, golden snapshot restoration, and progressive rehabilitation scoring.
"""

from __future__ import annotations

import collections
import enum
import hashlib
import hmac
import json
import math
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class ThreatSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatVectorType(str, enum.Enum):
    BYZANTINE_INJECTION = "byzantine_injection"
    LATENCY_POISONING = "latency_poisoning"
    MEMORY_CORRUPTION = "memory_corruption"
    AST_ESCAPE = "ast_escape"
    ENTROPY_BURST = "entropy_burst"
    SYBIL_IMPERSONATION = "sybil_impersonation"


class MitigationAction(str, enum.Enum):
    DROP_PAYLOAD = "drop_payload"
    THROTTLE_SEAT = "throttle_seat"
    QUARANTINE_ISOLATE = "quarantine_isolate"
    STATE_ROLLBACK = "state_rollback"
    DRAIN_AND_RECONSTITUTE = "drain_and_reconstitute"


@dataclass
class ThreatPattern:
    vector_type: ThreatVectorType
    indicator_pattern: str  # Substring or regex indicator
    entropy_threshold: float = 0.85
    latency_threshold_ms: float = 500.0

    def matches(self, payload: str, entropy: float = 0.0, latency_ms: float = 0.0) -> bool:
        if self.indicator_pattern.lower() in payload.lower():
            return True
        if self.vector_type == ThreatVectorType.ENTROPY_BURST and entropy >= self.entropy_threshold:
            return True
        if self.vector_type == ThreatVectorType.LATENCY_POISONING and latency_ms >= self.latency_threshold_ms:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vector_type": self.vector_type.value,
            "indicator_pattern": self.indicator_pattern,
            "entropy_threshold": round(self.entropy_threshold, 4),
            "latency_threshold_ms": round(self.latency_threshold_ms, 2),
        }


@dataclass
class ImmuneAntibody:
    antibody_id: str
    target_vector: ThreatVectorType
    pattern: ThreatPattern
    mitigation: MitigationAction
    severity: ThreatSeverity
    generation: int
    fitness_score: float  # [0.0, 1.0]
    issuer_seat: str
    signature: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "antibody_id": self.antibody_id,
            "target_vector": self.target_vector.value,
            "pattern": self.pattern.to_dict(),
            "mitigation": self.mitigation.value,
            "severity": self.severity.value,
            "generation": self.generation,
            "fitness_score": round(self.fitness_score, 4),
            "issuer_seat": self.issuer_seat,
            "signature": self.signature,
            "created_at": self.created_at,
        }


class GeneticAntibodyMutator:
    """Evolves and mutates antibodies through genetic operators to counter novel threat mutations."""

    def __init__(self, mutation_rate: float = 0.25) -> None:
        self.mutation_rate = mutation_rate

    def mutate(self, parent: ImmuneAntibody, hmac_key: bytes) -> ImmuneAntibody:
        new_gen = parent.generation + 1
        new_id = f"ab-gen{new_gen}-{secrets.token_hex(4)}"

        # Perturb threshold or broaden pattern
        orig_pattern = parent.pattern
        new_entropy = max(0.5, min(0.99, orig_pattern.entropy_threshold + secrets.choice([-0.05, 0.05])))
        new_lat = max(50.0, orig_pattern.latency_threshold_ms + secrets.choice([-50.0, 50.0]))
        new_indicator = orig_pattern.indicator_pattern

        # Sometimes add mutation variant
        if secrets.randbelow(100) < int(self.mutation_rate * 100):
            variants = ["_mutant", "_x", "_bypass", "_evade"]
            new_indicator = f"{orig_pattern.indicator_pattern}{secrets.choice(variants)}"

        new_pattern = ThreatPattern(
            vector_type=orig_pattern.vector_type,
            indicator_pattern=new_indicator,
            entropy_threshold=new_entropy,
            latency_threshold_ms=new_lat,
        )

        # Fitness slightly adjusted
        new_fitness = min(1.0, max(0.1, parent.fitness_score + 0.05))

        # Sign new antibody
        body = f"{new_id}:{parent.target_vector.value}:{new_pattern.indicator_pattern}:{new_gen}:{parent.issuer_seat}"
        sig = hmac.new(hmac_key, body.encode("utf-8"), hashlib.sha256).hexdigest()

        return ImmuneAntibody(
            antibody_id=new_id,
            target_vector=parent.target_vector,
            pattern=new_pattern,
            mitigation=parent.mitigation,
            severity=parent.severity,
            generation=new_gen,
            fitness_score=new_fitness,
            issuer_seat=parent.issuer_seat,
            signature=sig,
        )


class MultiSeatAntibodyDistributor:
    """Manages anti-entropy peer distribution and verification of antibodies across federated seats."""

    def __init__(self, seat_id: str, hmac_key: Optional[bytes] = None) -> None:
        self.seat_id = seat_id
        self.hmac_key = hmac_key or b"swarm-immune-distribution-master-key"  # pragma: allowlist secret default test HMAC key
        self.antibodies: Dict[str, ImmuneAntibody] = {}
        self.peer_digests: Dict[str, str] = {}
        self.propagation_log: List[Dict[str, Any]] = []

    def register_antibody(self, antibody: ImmuneAntibody) -> bool:
        if not self._verify_signature(antibody):
            return False
        self.antibodies[antibody.antibody_id] = antibody
        self.propagation_log.append({
            "action": "REGISTERED",
            "antibody_id": antibody.antibody_id,
            "target": antibody.target_vector.value,
            "timestamp": time.time(),
        })
        return True

    def create_and_sign(
        self,
        vector_type: ThreatVectorType,
        indicator_pattern: str,
        mitigation: MitigationAction = MitigationAction.QUARANTINE_ISOLATE,
        severity: ThreatSeverity = ThreatSeverity.HIGH,
        fitness_score: float = 0.85,
    ) -> ImmuneAntibody:
        ab_id = f"ab-{secrets.token_hex(6)}"
        pattern = ThreatPattern(vector_type=vector_type, indicator_pattern=indicator_pattern)
        body = f"{ab_id}:{vector_type.value}:{indicator_pattern}:0:{self.seat_id}"
        sig = hmac.new(self.hmac_key, body.encode("utf-8"), hashlib.sha256).hexdigest()

        antibody = ImmuneAntibody(
            antibody_id=ab_id,
            target_vector=vector_type,
            pattern=pattern,
            mitigation=mitigation,
            severity=severity,
            generation=0,
            fitness_score=fitness_score,
            issuer_seat=self.seat_id,
            signature=sig,
        )
        self.antibodies[ab_id] = antibody
        return antibody

    def _verify_signature(self, antibody: ImmuneAntibody) -> bool:
        body = f"{antibody.antibody_id}:{antibody.target_vector.value}:{antibody.pattern.indicator_pattern}:{antibody.generation}:{antibody.issuer_seat}"
        expected = hmac.new(self.hmac_key, body.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(antibody.signature, expected)

    def compute_local_catalog_digest(self) -> str:
        sorted_ids = sorted(self.antibodies.keys())
        raw = "|".join(f"{ab_id}:{self.antibodies[ab_id].signature}" for ab_id in sorted_ids)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def sync_with_peer(self, peer_seat: str, peer_antibodies: List[ImmuneAntibody]) -> Dict[str, Any]:
        accepted = 0
        rejected = 0
        for ab in peer_antibodies:
            if ab.antibody_id not in self.antibodies:
                if self.register_antibody(ab):
                    accepted += 1
                else:
                    rejected += 1

        self.peer_digests[peer_seat] = self.compute_local_catalog_digest()
        return {
            "peer_seat": peer_seat,
            "accepted_count": accepted,
            "rejected_count": rejected,
            "total_local_antibodies": len(self.antibodies),
            "catalog_digest": self.peer_digests[peer_seat],
        }


class SwarmAntiFragilityEngine:
    """Applies controlled perturbations to agent seats, measures post-stress resilience, and mutates immune defenses."""

    def __init__(self, distributor: MultiSeatAntibodyDistributor) -> None:
        self.distributor = distributor
        self.mutator = GeneticAntibodyMutator()
        self.seat_resilience_scores: Dict[str, float] = collections.defaultdict(lambda: 1.0)
        self.seat_states: Dict[str, str] = collections.defaultdict(lambda: "HEALTHY")
        self.perturbation_history: List[Dict[str, Any]] = []

    def evaluate_payload(
        self,
        seat_id: str,
        payload: str,
        entropy: float = 0.0,
        latency_ms: float = 0.0,
    ) -> Tuple[bool, Optional[ImmuneAntibody]]:
        """Evaluates incoming transaction against known antibodies. Returns (is_threat, matching_antibody)."""
        for ab in self.distributor.antibodies.values():
            if ab.pattern.matches(payload, entropy=entropy, latency_ms=latency_ms):
                # Trigger action on seat
                if ab.mitigation in (MitigationAction.QUARANTINE_ISOLATE, MitigationAction.DRAIN_AND_RECONSTITUTE):
                    self.seat_states[seat_id] = "QUARANTINED"
                elif ab.mitigation == MitigationAction.THROTTLE_SEAT:
                    self.seat_states[seat_id] = "THROTTLED"

                # Degrade resilience score slightly
                self.seat_resilience_scores[seat_id] = max(0.1, self.seat_resilience_scores[seat_id] - 0.15)
                return True, ab

        return False, None

    def inject_chaos_perturbation(
        self,
        target_seat: str,
        vector_type: ThreatVectorType,
        attack_payload: str,
        simulated_entropy: float = 0.9,
    ) -> Dict[str, Any]:
        """Injects a perturbation drill. If intercepted, rewards seat resilience; if breached, evolves antibodies."""
        is_blocked, matching_ab = self.evaluate_payload(
            seat_id=target_seat,
            payload=attack_payload,
            entropy=simulated_entropy,
        )

        evolved_ab = None
        if not is_blocked:
            # Threat bypassed existing antibodies: Synthesize & evolve novel antibody
            base_ab = self.distributor.create_and_sign(
                vector_type=vector_type,
                indicator_pattern=attack_payload[:8],
                mitigation=MitigationAction.QUARANTINE_ISOLATE,
                severity=ThreatSeverity.CRITICAL,
                fitness_score=0.9,
            )
            # Mutate to create generational defense
            evolved_ab = self.mutator.mutate(base_ab, self.distributor.hmac_key)
            self.distributor.register_antibody(evolved_ab)
            post_status = "EVOLVED_IMMUNITY_GAINED"
            self.seat_resilience_scores[target_seat] = min(1.0, self.seat_resilience_scores[target_seat] + 0.1)
        else:
            post_status = "NEUTRALIZED_BY_EXISTING_ANTIBODY"
            # Antifragility gain: seat gains resilience from successfully repelling stress
            self.seat_resilience_scores[target_seat] = min(1.0, self.seat_resilience_scores[target_seat] + 0.05)

        record = {
            "target_seat": target_seat,
            "vector_type": vector_type.value,
            "is_blocked": is_blocked,
            "matching_antibody_id": matching_ab.antibody_id if matching_ab else None,
            "evolved_antibody_id": evolved_ab.antibody_id if evolved_ab else None,
            "post_resilience_score": round(self.seat_resilience_scores[target_seat], 4),
            "seat_status": self.seat_states[target_seat],
            "outcome": post_status,
            "timestamp": time.time(),
        }
        self.perturbation_history.append(record)
        return record


class RuntimeReconstitutionSupervisor:
    """Orchestrates runtime state rollbacks, golden checkpoint reconstitutions, and progressive rehabilitation."""

    def __init__(self, antifragility_engine: SwarmAntiFragilityEngine) -> None:
        self.engine = antifragility_engine
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        self.reconstitution_log: List[Dict[str, Any]] = []

    def capture_golden_snapshot(self, seat_id: str, state_data: Dict[str, Any]) -> str:
        snapshot_id = f"snap-{seat_id}-{secrets.token_hex(4)}"
        serialized = json.dumps(state_data, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        self.snapshots[seat_id] = {
            "snapshot_id": snapshot_id,
            "seat_id": seat_id,
            "state_data": state_data,
            "digest": digest,
            "timestamp": time.time(),
        }
        return snapshot_id

    def reconstitute_seat(self, seat_id: str) -> Dict[str, Any]:
        snapshot = self.snapshots.get(seat_id)
        if not snapshot:
            # Fallback to pristine empty state
            snapshot = {
                "snapshot_id": f"pristine-{seat_id}",
                "seat_id": seat_id,
                "state_data": {"pristine": True},
                "digest": hashlib.sha256(b"pristine").hexdigest(),
                "timestamp": time.time(),
            }

        # Reset seat status to REHABILITATING
        self.engine.seat_states[seat_id] = "REHABILITATING"
        self.engine.seat_resilience_scores[seat_id] = 0.75  # Provisional rehabilitation baseline

        event = {
            "seat_id": seat_id,
            "restored_snapshot_id": snapshot["snapshot_id"],
            "snapshot_digest": snapshot["digest"],
            "new_state": "REHABILITATING",
            "timestamp": time.time(),
        }
        self.reconstitution_log.append(event)
        return event

    def graduate_rehabilitation(self, seat_id: str, drill_score: float) -> Dict[str, Any]:
        if drill_score >= 0.8:
            self.engine.seat_states[seat_id] = "HEALTHY"
            self.engine.seat_resilience_scores[seat_id] = max(0.9, drill_score)
            status = "GRADUATED_HEALTHY"
        else:
            self.engine.seat_states[seat_id] = "QUARANTINED"
            status = "FAILED_REHABILITATION"

        return {
            "seat_id": seat_id,
            "drill_score": round(drill_score, 4),
            "final_status": self.engine.seat_states[seat_id],
            "outcome": status,
        }
