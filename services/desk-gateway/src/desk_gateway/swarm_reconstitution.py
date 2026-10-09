"""Swarm Self-Healing Reconstitution & Immune Memory Attestation.

Implements autonomous seat reconstitution from attested checkpoint baselines,
tamper-evident immune memory ledger, proactive federated antibody distribution,
progressive post-quarantine rehabilitation protocol, and chaos anomaly harness.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set

from desk_gateway.swarm_immune import (
    SeatContainmentState,
    SwarmImmuneEngine,
    calculate_shannon_entropy,
)


class RehabilitationStage(str, enum.Enum):
    RECONSTITUTING = "RECONSTITUTING"
    SYNTHETIC_BENCHMARK = "SYNTHETIC_BENCHMARK"
    SHADOW_MONITORING = "SHADOW_MONITORING"
    GRADUATED_HEALTHY = "GRADUATED_HEALTHY"
    FAILED = "FAILED"


@dataclasses.dataclass
class CheckpointBaseline:
    """Golden snapshot baseline for agent runtime context."""
    seat_id: str
    version: int
    allowed_capabilities: Set[str]
    runtime_env: Dict[str, Any]
    created_at: float
    hash_commitment: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "version": self.version,
            "allowed_capabilities": sorted(list(self.allowed_capabilities)),
            "runtime_env": self.runtime_env,
            "created_at": self.created_at,
            "hash_commitment": self.hash_commitment,
        }


@dataclasses.dataclass
class ImmuneMemoryEntry:
    """Tamper-evident block entry recording an attack signature or quarantine event."""
    index: int
    seat_id: str
    attack_signature: str
    anomaly_type: str
    mitigation_action: str
    timestamp: float
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "seat_id": self.seat_id,
            "attack_signature": self.attack_signature,
            "anomaly_type": self.anomaly_type,
            "mitigation_action": self.mitigation_action,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


class ImmuneMemoryLedger:
    """Tamper-evident SHA-256 block-chained ledger for swarm immune memory."""

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self):
        self.entries: List[ImmuneMemoryEntry] = []
        self._signatures_cache: List[str] = []

    def record_event(
        self,
        seat_id: str,
        attack_signature: str,
        anomaly_type: str,
        mitigation_action: str,
    ) -> ImmuneMemoryEntry:
        """Append a new attack signature / quarantine event to the block chain."""
        index = len(self.entries)
        prev_hash = self.entries[-1].entry_hash if self.entries else self.GENESIS_HASH
        ts = time.time()
        
        raw = f"{index}:{seat_id}:{attack_signature}:{anomaly_type}:{mitigation_action}:{ts}:{prev_hash}"
        entry_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        entry = ImmuneMemoryEntry(
            index=index,
            seat_id=seat_id,
            attack_signature=attack_signature,
            anomaly_type=anomaly_type,
            mitigation_action=mitigation_action,
            timestamp=ts,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self.entries.append(entry)
        self._signatures_cache.append(attack_signature)
        return entry

    def verify_integrity(self) -> bool:
        """Verify SHA-256 block hash integrity across the entire immune memory chain."""
        if not self.entries:
            return True
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i - 1].entry_hash if i > 0 else self.GENESIS_HASH
            if entry.prev_hash != expected_prev:
                return False
            raw = f"{entry.index}:{entry.seat_id}:{entry.attack_signature}:{entry.anomaly_type}:{entry.mitigation_action}:{entry.timestamp}:{entry.prev_hash}"
            calc_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if calc_hash != entry.entry_hash:
                return False
        return True

    def get_merkle_root(self) -> str:
        """Calculate Merkle root of all entry hashes."""
        if not self.entries:
            return self.GENESIS_HASH
        current_level = [e.entry_hash for e in self.entries]
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level
        return current_level[0]


@dataclasses.dataclass
class AntibodyPolicy:
    """An antibody rule specifying behavioral pattern rejection and mitigations."""
    antibody_id: str
    pattern_regex: Optional[str]
    max_entropy: float
    max_latency_ms: float
    target_tools: List[str]
    action: str  # "BLOCK" or "FORCE_SHADOW"
    origin_desk_id: str

    def matches(self, tool_name: str, payload: str, latency_ms: float = 0.0) -> bool:
        """Evaluate if an incoming execution matches this antibody threat signature."""
        if self.target_tools and "*" not in self.target_tools and tool_name not in self.target_tools:
            return False
        if self.pattern_regex:
            try:
                if re.search(self.pattern_regex, payload):
                    return True
            except re.error:
                pass
        if self.max_entropy > 0:
            ent = calculate_shannon_entropy(payload)
            if ent > self.max_entropy:
                return True
        if self.max_latency_ms > 0 and latency_ms > self.max_latency_ms:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "antibody_id": self.antibody_id,
            "pattern_regex": self.pattern_regex,
            "max_entropy": self.max_entropy,
            "max_latency_ms": self.max_latency_ms,
            "target_tools": self.target_tools,
            "action": self.action,
            "origin_desk_id": self.origin_desk_id,
        }


class AntibodyDistributionMesh:
    """Proactively shares verified attack heuristics across federated desks."""

    def __init__(self, desk_id: str = "desk-local", secret_key: str = "swarm-antibody-secret"):
        self.desk_id = desk_id
        self.secret_key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        self.antibodies: Dict[str, AntibodyPolicy] = {}

    def register_antibody(self, policy: AntibodyPolicy) -> None:
        """Register a local or received antibody policy."""
        self.antibodies[policy.antibody_id] = policy

    def export_distribution_package(self) -> Dict[str, Any]:
        """Create a cryptographically signed HMAC-SHA256 package of all active antibodies."""
        policies_dict = [p.to_dict() for p in self.antibodies.values()]
        payload_str = json.dumps(policies_dict, sort_keys=True)
        ts = time.time()
        sign_payload = f"{self.desk_id}:{ts}:{payload_str}"
        signature = hmac.new(self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "origin_desk_id": self.desk_id,
            "timestamp": ts,
            "policies": policies_dict,
            "signature": signature,
        }

    def ingest_distribution_package(self, package: Dict[str, Any]) -> int:
        """Verify and ingest antibodies from a peer desk package. Returns count of ingested policies."""
        origin_desk_id = package.get("origin_desk_id", "")
        ts = package.get("timestamp", 0.0)
        policies_raw = package.get("policies", [])
        sig = package.get("signature", "")

        payload_str = json.dumps(policies_raw, sort_keys=True)
        sign_payload = f"{origin_desk_id}:{ts}:{payload_str}"
        expected_sig = hmac.new(self.secret_key, sign_payload.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid antibody package HMAC signature")

        count = 0
        for p in policies_raw:
            policy = AntibodyPolicy(
                antibody_id=p["antibody_id"],
                pattern_regex=p.get("pattern_regex"),
                max_entropy=p.get("max_entropy", 0.0),
                max_latency_ms=p.get("max_latency_ms", 0.0),
                target_tools=p.get("target_tools", ["*"]),
                action=p.get("action", "BLOCK"),
                origin_desk_id=p.get("origin_desk_id", origin_desk_id),
            )
            self.register_antibody(policy)
            count += 1
        return count

    def check_threat(self, tool_name: str, payload: str, latency_ms: float = 0.0) -> Optional[AntibodyPolicy]:
        """Check if execution matches any active antibody."""
        for antibody in self.antibodies.values():
            if antibody.matches(tool_name, payload, latency_ms):
                return antibody
        return None


class ProgressiveRehabilitationProtocol:
    """Manages progressive rehabilitation drills validating reconstituted seats."""

    def __init__(self, immune_engine: SwarmImmuneEngine):
        self.immune_engine = immune_engine
        self.rehabilitation_states: Dict[str, Dict[str, Any]] = {}

    def start_rehabilitation(self, seat_id: str) -> Dict[str, Any]:
        """Initiate rehabilitation for a reconstituted seat."""
        entry = {
            "seat_id": seat_id,
            "stage": RehabilitationStage.SYNTHETIC_BENCHMARK.value,
            "benchmark_passed": 0,
            "benchmark_total": 0,
            "started_at": time.time(),
            "graduated": False,
        }
        self.rehabilitation_states[seat_id] = entry
        return entry

    def run_synthetic_benchmarks(
        self,
        seat_id: str,
        benchmark_tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Run synthetic test tasks against seat to measure baseline conformity."""
        if seat_id not in self.rehabilitation_states:
            self.start_rehabilitation(seat_id)

        tasks = benchmark_tasks or [
            {"tool": "read_manifest", "payload": "healthy_sample_payload", "should_fail": False},
            {"tool": "git_status", "payload": "clean status probe", "should_fail": False},
            {"tool": "verify_signature", "payload": "signature_challenge_payload", "should_fail": False},
        ]

        passed = 0
        results = []
        for task in tasks:
            # Simulate execution probe
            is_err = task.get("should_fail", False)
            latency = 25.0
            entropy = calculate_shannon_entropy(task["payload"])
            
            # Record telemetry through immune engine
            telemetry = self.immune_engine.record_telemetry(
                seat_id=seat_id,
                tool_name=task["tool"],
                payload=task["payload"],
                latency_ms=latency,
                is_error=is_err,
            )
            is_ok = (telemetry["state"] == SeatContainmentState.HEALTHY.value) and not is_err
            if is_ok:
                passed += 1
            results.append({"task": task["tool"], "passed": is_ok, "score": telemetry["anomaly_score"]})

        entry = self.rehabilitation_states[seat_id]
        entry["benchmark_total"] += len(tasks)
        entry["benchmark_passed"] += passed
        entry["task_results"] = results

        # Require 100% pass rate on synthetic benchmark drills
        if passed == len(tasks):
            entry["stage"] = RehabilitationStage.GRADUATED_HEALTHY.value
            entry["graduated"] = True
            self.immune_engine.unquarantine_seat(seat_id, reason="Graduated progressive rehabilitation benchmarks")
        else:
            entry["stage"] = RehabilitationStage.FAILED.value
            entry["graduated"] = False
            self.immune_engine.quarantine_seat(seat_id, reason="Failed progressive rehabilitation benchmarks")

        return entry


class SwarmReconstitutionEngine:
    """Orchestrates golden checkpoint baselines, reconstitution, and immune ledger."""

    def __init__(
        self,
        immune_engine: SwarmImmuneEngine,
        desk_id: str = "desk-local",
        secret_key: str = "swarm-reconstitution-secret",
    ):
        self.immune_engine = immune_engine
        self.desk_id = desk_id
        self.secret_key = secret_key
        self.baselines: Dict[str, CheckpointBaseline] = {}
        self.ledger = ImmuneMemoryLedger()
        self.antibody_mesh = AntibodyDistributionMesh(desk_id=desk_id, secret_key=secret_key)
        self.rehabilitation = ProgressiveRehabilitationProtocol(self.immune_engine)

        # Register standard baseline
        self._init_default_baselines()

    def _init_default_baselines(self) -> None:
        """Initialize golden baseline checkpoints for standard swarm seats."""
        for seat in ["lead", "backend", "web", "android", "ios", "infra", "qa"]:
            self.register_checkpoint(
                seat_id=seat,
                version=1,
                capabilities=self.immune_engine.ALL_CAPABILITIES,
                runtime_env={"memory_limit_mb": 4096, "cpu_quota": 2.0, "clean_sandbox": True},
            )

    def register_checkpoint(
        self,
        seat_id: str,
        version: int,
        capabilities: Set[str],
        runtime_env: Dict[str, Any],
    ) -> CheckpointBaseline:
        """Register an attested golden snapshot baseline for a seat."""
        ts = time.time()
        raw = f"{seat_id}:{version}:{sorted(list(capabilities))}:{json.dumps(runtime_env, sort_keys=True)}:{ts}"
        commitment = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        baseline = CheckpointBaseline(
            seat_id=seat_id,
            version=version,
            allowed_capabilities=set(capabilities),
            runtime_env=runtime_env,
            created_at=ts,
            hash_commitment=commitment,
        )
        self.baselines[seat_id] = baseline
        return baseline

    def reconstitute_seat(self, seat_id: str, reason: str = "Autonomous self-healing") -> Dict[str, Any]:
        """Regenerate a clean agent runtime context from attested golden baseline."""
        baseline = self.baselines.get(seat_id)
        if not baseline:
            # Fallback baseline
            baseline = self.register_checkpoint(
                seat_id=seat_id,
                version=1,
                capabilities=self.immune_engine.ALL_CAPABILITIES,
                runtime_env={"memory_limit_mb": 4096, "clean_sandbox": True},
            )

        # 1. Reset immune profile metrics
        profile = self.immune_engine.get_or_create_profile(seat_id)
        quarantine_reason = profile.quarantine_reason or reason
        profile.reset_baseline(
            allowed_capabilities=baseline.allowed_capabilities,
            target_state=SeatContainmentState.SUSPICIOUS,
        )

        # 2. Record to tamper-evident immune memory ledger
        attack_sig = hashlib.sha256(f"{seat_id}:{quarantine_reason}".encode("utf-8")).hexdigest()[:16]
        entry = self.ledger.record_event(
            seat_id=seat_id,
            attack_signature=f"sig-{attack_sig}",
            anomaly_type="BEHAVIORAL_ANOMALY",
            mitigation_action=f"RECONSTITUTED_FROM_BASELINE_v{baseline.version}",
        )

        # 3. Formulate an active antibody rule if quarantine reason indicates an attack pattern
        antibody = AntibodyPolicy(
            antibody_id=f"ab-{attack_sig}",
            pattern_regex=r"(?i)(exploit|malicious|byzantine_attack|unauthorized_shell|replicate_fork)",
            max_entropy=6.8,
            max_latency_ms=8000.0,
            target_tools=["*"],
            action="BLOCK",
            origin_desk_id=self.desk_id,
        )
        self.antibody_mesh.register_antibody(antibody)

        # 4. Initiate progressive rehabilitation
        rehab_status = self.rehabilitation.start_rehabilitation(seat_id)

        return {
            "reconstituted": True,
            "seat_id": seat_id,
            "baseline_version": baseline.version,
            "baseline_commitment": baseline.hash_commitment,
            "ledger_entry": entry.to_dict(),
            "antibody_generated": antibody.antibody_id,
            "rehabilitation": rehab_status,
        }


class ChaosAnomalyHarness:
    """Chaos anomaly injection harness for testing swarm immune defenses."""

    def __init__(self, immune_engine: SwarmImmuneEngine, reconstitution_engine: SwarmReconstitutionEngine):
        self.immune_engine = immune_engine
        self.reconstitution_engine = reconstitution_engine

    def inject_high_entropy_surge(self, seat_id: str) -> Dict[str, Any]:
        """Inject random high-entropy payload surge (e.g. encrypted exfiltration)."""
        noisy_payload = "".join([chr((i * 37) % 94 + 32) for i in range(1000)])
        return self.immune_engine.record_telemetry(
            seat_id=seat_id,
            tool_name="file_export",
            payload=noisy_payload,
            latency_ms=25000.0,
            is_error=True,
        )

    def inject_latency_poisoning(self, seat_id: str, latency_ms: float = 30000.0) -> Dict[str, Any]:
        """Inject extreme latency spike simulating hanging or resource exhaustion."""
        return self.immune_engine.record_telemetry(
            seat_id=seat_id,
            tool_name="db_query",
            payload="SELECT * FROM cluster_state WHERE heavy_computation=1",
            latency_ms=latency_ms,
            is_error=True,
        )

    def inject_byzantine_failure_burst(self, seat_id: str, count: int = 5) -> List[Dict[str, Any]]:
        """Inject burst of tool execution errors."""
        results = []
        for i in range(count):
            res = self.immune_engine.record_telemetry(
                seat_id=seat_id,
                tool_name=f"critical_rpc_{i}",
                payload=f"error_trigger_{i}",
                latency_ms=150.0,
                is_error=True,
            )
            results.append(res)
        return results

    def run_chaos_resilience_drill(self, seat_id: str = "chaos-seat") -> Dict[str, Any]:
        """Full end-to-end chaos anomaly injection and autonomous self-healing drill."""
        # 1. Baseline status
        initial_status = self.immune_engine.get_or_create_profile(seat_id).state.value

        # 2. Chaos Injection: Spike errors & entropy
        self.inject_high_entropy_surge(seat_id)
        self.inject_latency_poisoning(seat_id, latency_ms=15000.0)
        self.inject_byzantine_failure_burst(seat_id, count=6)

        quarantined_state = self.immune_engine.get_or_create_profile(seat_id).state
        quarantine_verified = (quarantined_state in (SeatContainmentState.QUARANTINED, SeatContainmentState.DRAINED))

        # 3. Autonomous Reconstitution
        reconstitute_res = self.reconstitution_engine.reconstitute_seat(
            seat_id=seat_id,
            reason="Chaos anomaly drill autonomous reconstitution",
        )

        # 4. Progressive Rehabilitation Drill
        rehab_res = self.reconstitution_engine.rehabilitation.run_synthetic_benchmarks(seat_id)

        # 5. Ledger Integrity Check
        ledger_valid = self.reconstitution_engine.ledger.verify_integrity()
        merkle_root = self.reconstitution_engine.ledger.get_merkle_root()

        # 6. Final Status
        final_state = self.immune_engine.get_or_create_profile(seat_id).state.value

        return {
            "seat_id": seat_id,
            "initial_state": initial_status,
            "quarantine_verified": quarantine_verified,
            "quarantined_state": quarantined_state.value,
            "reconstitution_success": reconstitute_res["reconstituted"],
            "rehabilitation_graduated": rehab_res["graduated"],
            "ledger_verified": ledger_valid,
            "immune_merkle_root": merkle_root,
            "final_state": final_state,
        }
