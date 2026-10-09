"""Unit tests for Autonomous Epistemic Calibration & Self-Reflective Metacognition (Phase 58)."""

import pytest

from desk_gateway.metacognition import (
    BeliefNode,
    CalibratedConfidence,
    EpistemicBeliefNetwork,
    EpistemicCalibrator,
    IntrospectiveStrategyOptimizer,
    MetacognitiveIntrospector,
    ReasoningStrategy,
)


def test_epistemic_calibrator_temperature_and_metrics():
    calibrator = EpistemicCalibrator(num_bins=5, default_temperature=1.0)
    assert calibrator.compute_brier_score() == 0.0
    assert calibrator.compute_ece() == 0.0

    # Record synthetic calibration samples
    for _ in range(12):
        calibrator.record_outcome(0.9, True)
    for _ in range(8):
        calibrator.record_outcome(0.8, False)

    brier = calibrator.compute_brier_score()
    assert brier > 0.0

    ece = calibrator.compute_ece()
    assert ece >= 0.0

    fitted_t = calibrator.fit_temperature()
    assert fitted_t > 0.0

    calibrated = calibrator.calibrate(0.85)
    assert isinstance(calibrated, CalibratedConfidence)
    assert 0.0 <= calibrated.calibrated_probability <= 1.0
    assert calibrated.expected_calibration_error == calibrator.compute_ece()


def test_metacognitive_introspector_bias_detection():
    introspector = MetacognitiveIntrospector(overconfidence_threshold=0.85)

    # 1. Circular Reasoning Chain
    chain_circular = [
        {"premise": "Tool X is secure", "conclusion": "Tool X can run in production", "confidence": 0.9},
        {"premise": "Tool X can run in production", "conclusion": "Tool X is secure", "confidence": 0.95},
    ]
    report_circ = introspector.introspect_reasoning_chain(chain_circular)
    assert report_circ.circular_reasoning_detected is True
    assert "CIRCULAR_REASONING" in report_circ.detected_biases

    # 2. Premature Convergence
    chain_premature = [
        {"premise": "Input received", "conclusion": "Final answer reached immediately", "confidence": 0.99},
    ]
    report_prem = introspector.introspect_reasoning_chain(chain_premature)
    assert report_prem.premature_convergence_detected is True
    assert "PREMATURE_CONVERGENCE" in report_prem.detected_biases


def test_epistemic_belief_network_bayesian_updates():
    net = EpistemicBeliefNetwork("test-net")
    node = net.register_hypothesis(
        hypothesis_id="H_CACHE_HIT",
        description="Cache latency is sub-millisecond",
        prior=0.4,
    )
    assert node.current_probability == 0.4
    assert node.epistemic_uncertainty == 1.0

    initial_entropy = net.compute_epistemic_entropy()
    assert initial_entropy > 0.0

    # Assimilate positive evidence (Likelihood Ratio = 3.0)
    update = net.assimilate_evidence("H_CACHE_HIT", likelihood_ratio=3.0)
    assert update.posterior > update.prior
    assert node.evidence_count == 1
    assert node.epistemic_uncertainty < 1.0

    # Assimilate refuting evidence (Likelihood Ratio = 0.2)
    update2 = net.assimilate_evidence("H_CACHE_HIT", likelihood_ratio=0.2)
    assert update2.posterior < update2.prior
    assert node.evidence_count == 2


def test_introspective_strategy_optimizer():
    optimizer = IntrospectiveStrategyOptimizer(fast_threshold=0.3, deliberate_threshold=0.7)

    # Low entropy -> System 1 Fast Heuristic
    res_fast = optimizer.select_strategy(epistemic_entropy=0.15, task_criticality="low")
    assert res_fast["selected_strategy"] == ReasoningStrategy.FAST_HEURISTIC.value

    # Moderate entropy -> System 2 Deliberate Verification
    res_delib = optimizer.select_strategy(epistemic_entropy=0.55, task_criticality="medium")
    assert res_delib["selected_strategy"] == ReasoningStrategy.DELIBERATE_VERIFICATION.value

    # High entropy -> Adversarial Debate
    res_adv = optimizer.select_strategy(epistemic_entropy=0.85, task_criticality="medium")
    assert res_adv["selected_strategy"] == ReasoningStrategy.ADVERSARIAL_DEBATE.value

    # Critical risk -> Deep Consensus
    res_crit = optimizer.select_strategy(epistemic_entropy=0.5, task_criticality="critical")
    assert res_crit["selected_strategy"] == ReasoningStrategy.DEEP_CONSENSUS.value
