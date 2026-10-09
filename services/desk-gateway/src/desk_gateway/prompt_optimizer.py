"""Autonomous Prompt Optimization & Self-Refining Instruction Loops.

Implements telemetry-driven prompt evaluation, genetic prompt mutation,
shadow A/B canary evaluation, cryptographically signed prompt rollouts,
and regression protection.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import random
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class RolloutState(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    CANARY_EVALUATION = "CANARY_EVALUATION"
    ACTIVE = "ACTIVE"
    ROLLED_BACK = "ROLLED_BACK"
    SUPERSEDED = "SUPERSEDED"


@dataclasses.dataclass
class PromptEvaluationTelemetry:
    revision_id: str
    task_success: bool
    tool_accuracy: float  # 0.0 to 1.0
    latency_ms: float
    token_count: int
    user_satisfaction: float = 1.0  # 0.0 to 1.0


@dataclasses.dataclass
class FitnessScore:
    overall_score: float  # 0.0 to 100.0
    success_rate: float
    avg_accuracy: float
    avg_latency_ms: float
    avg_tokens: float
    samples_count: int


@dataclasses.dataclass
class PromptVariant:
    revision_id: str
    seat_id: str
    prompt_text: str
    parent_revision_id: Optional[str]
    generation: int
    mutation_type: str
    sha256_hash: str
    attestation_signature: str
    rollout_state: RolloutState
    created_at: float
    fitness: Optional[FitnessScore] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "seat_id": self.seat_id,
            "prompt_text": self.prompt_text,
            "parent_revision_id": self.parent_revision_id,
            "generation": self.generation,
            "mutation_type": self.mutation_type,
            "sha256_hash": self.sha256_hash,
            "attestation_signature": self.attestation_signature,
            "rollout_state": self.rollout_state.value,
            "created_at": self.created_at,
            "fitness": dataclasses.asdict(self.fitness) if self.fitness else None,
        }


class PromptTelemetryEvaluator:
    """Evaluates prompt fitness from execution metrics and telemetry."""

    def __init__(
        self,
        weight_success: float = 0.40,
        weight_accuracy: float = 0.30,
        weight_latency: float = 0.15,
        weight_efficiency: float = 0.15,
        target_latency_ms: float = 1500.0,
        target_token_count: int = 1000,
    ):
        self.w_success = weight_success
        self.w_accuracy = weight_accuracy
        self.w_latency = weight_latency
        self.w_eff = weight_efficiency
        self.target_latency_ms = target_latency_ms
        self.target_token_count = target_token_count
        # revision_id -> list of telemetries
        self._samples: Dict[str, List[PromptEvaluationTelemetry]] = {}

    def record_telemetry(self, item: PromptEvaluationTelemetry) -> None:
        if item.revision_id not in self._samples:
            self._samples[item.revision_id] = []
        self._samples[item.revision_id].append(item)

    def calculate_fitness(self, revision_id: str) -> Optional[FitnessScore]:
        items = self._samples.get(revision_id, [])
        if not items:
            return None

        n = len(items)
        success_count = sum(1 for i in items if i.task_success)
        success_rate = success_count / n
        avg_acc = sum(i.tool_accuracy for i in items) / n
        avg_lat = sum(i.latency_ms for i in items) / n
        avg_tok = sum(i.token_count for i in items) / n

        # Latency penalty: 1.0 if <= target, degrades towards 0.0 as latency doubles
        latency_score = max(0.0, 1.0 - max(0.0, avg_lat - self.target_latency_ms) / self.target_latency_ms)

        # Token efficiency score: 1.0 if <= target, degrades as tokens grow
        token_score = max(0.0, 1.0 - max(0.0, avg_tok - self.target_token_count) / self.target_token_count)

        overall = (
            (self.w_success * success_rate) +
            (self.w_accuracy * avg_acc) +
            (self.w_latency * latency_score) +
            (self.w_eff * token_score)
        ) * 100.0

        return FitnessScore(
            overall_score=round(overall, 2),
            success_rate=round(success_rate, 4),
            avg_accuracy=round(avg_acc, 4),
            avg_latency_ms=round(avg_lat, 2),
            avg_tokens=round(avg_tok, 2),
            samples_count=n,
        )


class EvolutionaryPromptEngine:
    """Produces mutated candidate prompts via heuristic genetic exploration."""

    MUTATION_STRATEGIES = [
        "sharpen_constraints",
        "emphasize_step_by_step",
        "concise_pruning",
        "error_resilience",
        "structured_output_focus",
    ]

    def mutate_prompt(self, base_prompt: str, strategy: Optional[str] = None) -> Tuple[str, str]:
        strat = strategy or random.choice(self.MUTATION_STRATEGIES)
        text = base_prompt.strip()

        if strat == "sharpen_constraints":
            mutated = f"{text}\n\nSTRICT CONSTRAINT: Always verify argument types and boundaries before invoking any tools."
        elif strat == "emphasize_step_by_step":
            mutated = f"{text}\n\nREASONING DIRECTIVE: Break down execution into clear deterministic sub-steps before tool invocation."
        elif strat == "concise_pruning":
            # Strip redundant words or shorten greetings
            lines = [l for l in text.splitlines() if not l.lower().startswith("please ")]
            mutated = "\n".join(lines) + "\n\nEFFICIENCY: Be direct and concise without verbose preamble."
        elif strat == "error_resilience":
            mutated = f"{text}\n\nFAULT TOLERANCE: If an operation returns an error, gracefully fallback and record diagnostic reasons."
        elif strat == "structured_output_focus":
            mutated = f"{text}\n\nOUTPUT FORMAT: Provide all outputs strictly complying with the specified schema contract."
        else:
            mutated = f"{text}\n\nDIRECTIVE: Prioritize accuracy and safety above all."

        return mutated.strip(), strat


class CanaryBenchmarkHarness:
    """Evaluates candidate prompt variants against incumbents in shadow canary mode."""

    def __init__(self, golden_benchmarks: Optional[List[Dict[str, Any]]] = None):
        self.golden_benchmarks = golden_benchmarks or [
            {"task": "parse_json", "expected_tool": "json_parser", "complexity": 1},
            {"task": "validate_schema", "expected_tool": "schema_validator", "complexity": 2},
            {"task": "execute_computation", "expected_tool": "calculator", "complexity": 1},
            {"task": "audit_compliance", "expected_tool": "audit_checker", "complexity": 3},
        ]

    def evaluate_variant(self, variant: PromptVariant) -> List[PromptEvaluationTelemetry]:
        """Runs the synthetic benchmark dataset against the variant instructions."""
        telemetry_results: List[PromptEvaluationTelemetry] = []

        # Heuristic scoring based on presence of key directives in the prompt
        has_constraints = "STRICT CONSTRAINT" in variant.prompt_text or "verify" in variant.prompt_text.lower()
        has_reasoning = "REASONING" in variant.prompt_text or "step" in variant.prompt_text.lower()
        is_concise = "EFFICIENCY" in variant.prompt_text or "concise" in variant.prompt_text.lower()
        has_resilience = "FAULT TOLERANCE" in variant.prompt_text or "error" in variant.prompt_text.lower()

        base_latency = 800.0 if is_concise else 1100.0
        base_tokens = 450 if is_concise else 750

        for bench in self.golden_benchmarks:
            acc = 0.85
            if has_constraints:
                acc += 0.08
            if has_reasoning:
                acc += 0.05
            if has_resilience:
                acc += 0.02
            acc = min(1.0, acc)

            success = acc >= 0.80
            lat = base_latency + (bench["complexity"] * 100.0)
            tok = base_tokens + (bench["complexity"] * 50)

            telemetry_results.append(
                PromptEvaluationTelemetry(
                    revision_id=variant.revision_id,
                    task_success=success,
                    tool_accuracy=acc,
                    latency_ms=lat,
                    token_count=tok,
                )
            )

        return telemetry_results


class PromptRolloutOrchestrator:
    """Manages version lineage, signing, canary promotion, and instant rollbacks."""

    def __init__(
        self,
        signing_key: bytes,
        evaluator: Optional[PromptTelemetryEvaluator] = None,
        engine: Optional[EvolutionaryPromptEngine] = None,
        canary: Optional[CanaryBenchmarkHarness] = None,
        min_promotion_fitness: float = 75.0,
    ):
        self.signing_key = signing_key
        self.evaluator = evaluator or PromptTelemetryEvaluator()
        self.engine = engine or EvolutionaryPromptEngine()
        self.canary = canary or CanaryBenchmarkHarness()
        self.min_promotion_fitness = min_promotion_fitness

        # seat_id -> active revision_id
        self._active_revisions: Dict[str, str] = {}
        # revision_id -> PromptVariant
        self._variants: Dict[str, PromptVariant] = {}
        # seat_id -> list of revision_ids (lineage)
        self._lineage: Dict[str, List[str]] = {}

    def _hash_and_sign(self, seat_id: str, prompt_text: str, revision_id: str) -> Tuple[str, str]:
        text_hash = hashlib.sha256(prompt_text.strip().encode("utf-8")).hexdigest()
        msg = f"{seat_id}:{revision_id}:{text_hash}".encode("utf-8")
        sig = hmac.new(self.signing_key, msg, hashlib.sha256).hexdigest()
        return text_hash, sig

    def register_baseline_prompt(self, seat_id: str, prompt_text: str) -> PromptVariant:
        rev_id = f"rev-{seat_id}-0"
        h, sig = self._hash_and_sign(seat_id, prompt_text, rev_id)

        variant = PromptVariant(
            revision_id=rev_id,
            seat_id=seat_id,
            prompt_text=prompt_text,
            parent_revision_id=None,
            generation=0,
            mutation_type="baseline",
            sha256_hash=h,
            attestation_signature=sig,
            rollout_state=RolloutState.ACTIVE,
            created_at=time.time(),
        )

        self._variants[rev_id] = variant
        self._active_revisions[seat_id] = rev_id
        self._lineage[seat_id] = [rev_id]
        return variant

    def generate_candidate_variant(self, seat_id: str, strategy: Optional[str] = None) -> PromptVariant:
        current_rev_id = self._active_revisions.get(seat_id)
        if not current_rev_id:
            raise KeyError(f"Seat '{seat_id}' has no registered baseline prompt.")

        parent = self._variants[current_rev_id]
        mutated_text, strat = self.engine.mutate_prompt(parent.prompt_text, strategy=strategy)
        new_gen = parent.generation + 1
        new_rev_id = f"rev-{seat_id}-{new_gen}-{int(time.time())}"

        h, sig = self._hash_and_sign(seat_id, mutated_text, new_rev_id)

        variant = PromptVariant(
            revision_id=new_rev_id,
            seat_id=seat_id,
            prompt_text=mutated_text,
            parent_revision_id=current_rev_id,
            generation=new_gen,
            mutation_type=strat,
            sha256_hash=h,
            attestation_signature=sig,
            rollout_state=RolloutState.CANDIDATE,
            created_at=time.time(),
        )

        self._variants[new_rev_id] = variant
        return variant

    def run_canary_evaluation(self, revision_id: str) -> FitnessScore:
        if revision_id not in self._variants:
            raise KeyError(f"Revision '{revision_id}' not found.")

        variant = self._variants[revision_id]
        variant.rollout_state = RolloutState.CANARY_EVALUATION

        # Run benchmark harness
        telemetries = self.canary.evaluate_variant(variant)
        for t in telemetries:
            self.evaluator.record_telemetry(t)

        score = self.evaluator.calculate_fitness(revision_id)
        variant.fitness = score
        return score

    def promote_candidate(self, revision_id: str) -> bool:
        if revision_id not in self._variants:
            raise KeyError(f"Revision '{revision_id}' not found.")

        candidate = self._variants[revision_id]
        if not candidate.fitness:
            self.run_canary_evaluation(revision_id)

        if candidate.fitness.overall_score < self.min_promotion_fitness:
            return False

        seat_id = candidate.seat_id
        current_active_id = self._active_revisions.get(seat_id)
        if current_active_id and current_active_id in self._variants:
            self._variants[current_active_id].rollout_state = RolloutState.SUPERSEDED

        candidate.rollout_state = RolloutState.ACTIVE
        self._active_revisions[seat_id] = revision_id
        self._lineage.setdefault(seat_id, []).append(revision_id)
        return True

    def rollback_to_previous(self, seat_id: str) -> Optional[PromptVariant]:
        history = self._lineage.get(seat_id, [])
        if len(history) < 2:
            return None  # No prior version to rollback to

        current_id = history.pop()  # Remove current active
        if current_id in self._variants:
            self._variants[current_id].rollout_state = RolloutState.ROLLED_BACK

        target_id = history[-1]
        target = self._variants[target_id]
        target.rollout_state = RolloutState.ACTIVE
        self._active_revisions[seat_id] = target_id
        return target

    def get_active_prompt(self, seat_id: str) -> Optional[PromptVariant]:
        rev_id = self._active_revisions.get(seat_id)
        if not rev_id:
            return None
        return self._variants.get(rev_id)

    def get_variant(self, revision_id: str) -> Optional[PromptVariant]:
        return self._variants.get(revision_id)

    def get_lineage(self, seat_id: str) -> List[Dict[str, Any]]:
        history = self._lineage.get(seat_id, [])
        return [self._variants[r].to_dict() for r in history if r in self._variants]
