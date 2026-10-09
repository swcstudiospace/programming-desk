"""Unit and regression tests for Autonomous Prompt Optimization & Self-Refining Instruction Loops (Phase 37).

Tests genetic mutation strategies, telemetry scoring, shadow canary evaluation,
cryptographic SHA-256 version lineage, and rollback safety.
"""

import pytest
import hmac
import hashlib
from desk_gateway.prompt_optimizer import (
    PromptRolloutOrchestrator,
    PromptTelemetryEvaluator,
    EvolutionaryPromptEngine,
    CanaryBenchmarkHarness,
    PromptEvaluationTelemetry,
    RolloutState,
)


def test_evolutionary_prompt_mutation_strategies():
    engine = EvolutionaryPromptEngine()
    base = "You are an autonomous engineering seat executing code reviews."

    for strat in engine.MUTATION_STRATEGIES:
        mutated, returned_strat = engine.mutate_prompt(base, strategy=strat)
        assert returned_strat == strat
        assert base in mutated
        assert len(mutated) > len(base)


def test_prompt_telemetry_evaluator_fitness():
    evaluator = PromptTelemetryEvaluator(target_latency_ms=1000.0, target_token_count=500)
    rev_id = "rev-test-1"

    # Perfect telemetries
    for _ in range(5):
        evaluator.record_telemetry(
            PromptEvaluationTelemetry(
                revision_id=rev_id,
                task_success=True,
                tool_accuracy=1.0,
                latency_ms=900.0,
                token_count=450,
            )
        )

    score = evaluator.calculate_fitness(rev_id)
    assert score is not None
    assert score.success_rate == 1.0
    assert score.avg_accuracy == 1.0
    assert score.overall_score >= 95.0


def test_canary_benchmark_and_promotion_flow():
    secret_key = b"prompt-test-key-32b-length-at-least"
    orchestrator = PromptRolloutOrchestrator(signing_key=secret_key, min_promotion_fitness=70.0)

    # 1. Register baseline
    base_text = "You are the QA seat. Test thoroughly and report bugs."
    baseline = orchestrator.register_baseline_prompt("qa", base_text)
    assert baseline.generation == 0
    assert baseline.rollout_state == RolloutState.ACTIVE
    assert orchestrator.get_active_prompt("qa").revision_id == baseline.revision_id

    # 2. Mutate to candidate
    candidate = orchestrator.generate_candidate_variant("qa", strategy="sharpen_constraints")
    assert candidate.generation == 1
    assert candidate.parent_revision_id == baseline.revision_id
    assert candidate.rollout_state == RolloutState.CANDIDATE

    # Verify signature
    computed_hash = hashlib.sha256(candidate.prompt_text.strip().encode("utf-8")).hexdigest()
    expected_sig = hmac.new(
        secret_key,
        f"qa:{candidate.revision_id}:{computed_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert candidate.attestation_signature == expected_sig

    # 3. Canary evaluation
    fitness = orchestrator.run_canary_evaluation(candidate.revision_id)
    assert fitness is not None
    assert fitness.overall_score > 70.0

    # 4. Promote candidate
    promoted = orchestrator.promote_candidate(candidate.revision_id)
    assert promoted is True
    assert candidate.rollout_state == RolloutState.ACTIVE
    assert baseline.rollout_state == RolloutState.SUPERSEDED
    assert orchestrator.get_active_prompt("qa").revision_id == candidate.revision_id

    # 5. Rollback to baseline
    reverted = orchestrator.rollback_to_previous("qa")
    assert reverted.revision_id == baseline.revision_id
    assert baseline.rollout_state == RolloutState.ACTIVE
    assert candidate.rollout_state == RolloutState.ROLLED_BACK
    assert orchestrator.get_active_prompt("qa").revision_id == baseline.revision_id
