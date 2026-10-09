"""Autonomous Epistemic Calibration & Self-Reflective Metacognition (Milestone v4.6 - Phase 58).

Implements:
- CalibratedConfidence: Output container for uncalibrated and calibrated posterior probability.
- ConfidenceBucket: Histogram bin for calibration curve evaluation.
- EpistemicCalibrator: Temperature scaling & empirical Platt calibration with Brier score and ECE calculation.
- CognitiveBiasReport: Diagnostics on detected biases (overconfidence, circularity, confirmation bias, drift).
- SelfReflectionTrace: Record of introspected reasoning step with critique and bias findings.
- MetacognitiveIntrospector: Inspects agent reasoning chains for logical loops, premature termination, and bias.
- BeliefNode: Discrete hypothesis state with probability prior, likelihood accumulator, and uncertainty.
- BeliefUpdate: Receipt of an evidence assimilation step.
- EpistemicBeliefNetwork: Bayesian belief assimilation network with aleatoric and epistemic entropy separation.
- ReasoningStrategy: Enum for metacognitive cognitive processing modes.
- IntrospectiveStrategyOptimizer: Dynamically selects deliberative execution strategy based on epistemic entropy.
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
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CalibratedConfidence:
    raw_confidence: float
    calibrated_probability: float
    temperature: float
    expected_calibration_error: float
    brier_score: float
    calibration_method: str = "temperature_scaling"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_confidence": round(self.raw_confidence, 4),
            "calibrated_probability": round(self.calibrated_probability, 4),
            "temperature": round(self.temperature, 4),
            "expected_calibration_error": round(self.expected_calibration_error, 4),
            "brier_score": round(self.brier_score, 4),
            "calibration_method": self.calibration_method,
        }


@dataclass
class ConfidenceBucket:
    bin_lower: float
    bin_upper: float
    samples_count: int = 0
    correct_count: int = 0
    confidence_sum: float = 0.0

    @property
    def accuracy(self) -> float:
        return self.correct_count / self.samples_count if self.samples_count > 0 else 0.0

    @property
    def avg_confidence(self) -> float:
        return self.confidence_sum / self.samples_count if self.samples_count > 0 else 0.0


class EpistemicCalibrator:
    """Calibrates raw neural confidence into true empirical probabilities using Platt/temperature scaling,

    evaluating Brier score and Expected Calibration Error (ECE) across confidence bins.
    """

    def __init__(self, num_bins: int = 10, default_temperature: float = 1.35) -> None:
        self.num_bins = num_bins
        self.temperature = default_temperature
        self.history: List[Tuple[float, bool]] = []  # (raw_conf, is_correct)

    def record_outcome(self, raw_confidence: float, is_correct: bool) -> None:
        clamped_conf = max(1e-4, min(1.0 - 1e-4, float(raw_confidence)))
        self.history.append((clamped_conf, bool(is_correct)))

    def fit_temperature(self) -> float:
        """Finds temperature parameter T > 0 minimizing cross-entropy loss over historical outcomes."""
        if len(self.history) < 5:
            return self.temperature

        # Grid search over T in [0.2, 3.5] with step 0.05
        best_t = self.temperature
        best_nll = float("inf")

        for t_candidate_int in range(4, 70):
            t = t_candidate_int * 0.05
            nll = 0.0
            for raw_conf, correct in self.history:
                # Logit conversion
                logit = math.log(raw_conf / (1.0 - raw_conf))
                calib_prob = 1.0 / (1.0 + math.exp(-logit / t))
                calib_prob = max(1e-6, min(1.0 - 1e-6, calib_prob))
                if correct:
                    nll -= math.log(calib_prob)
                else:
                    nll -= math.log(1.0 - calib_prob)
            if nll < best_nll:
                best_nll = nll
                best_t = t

        self.temperature = round(best_t, 3)
        return self.temperature

    def calibrate(self, raw_confidence: float) -> CalibratedConfidence:
        """Applies temperature scaling to raw confidence and computes calibration metrics."""
        conf = max(1e-4, min(1.0 - 1e-4, float(raw_confidence)))
        logit = math.log(conf / (1.0 - conf))
        calibrated_prob = 1.0 / (1.0 + math.exp(-logit / self.temperature))

        ece = self.compute_ece()
        brier = self.compute_brier_score()

        return CalibratedConfidence(
            raw_confidence=conf,
            calibrated_probability=calibrated_prob,
            temperature=self.temperature,
            expected_calibration_error=ece,
            brier_score=brier,
        )

    def compute_brier_score(self) -> float:
        """Computes mean squared error between forecast probability and binary outcome."""
        if not self.history:
            return 0.0
        total_sq_err = 0.0
        for conf, correct in self.history:
            target = 1.0 if correct else 0.0
            total_sq_err += (conf - target) ** 2
        return total_sq_err / len(self.history)

    def compute_ece(self) -> float:
        """Computes Expected Calibration Error (ECE) across M equal-width bins."""
        if not self.history:
            return 0.0

        bin_width = 1.0 / self.num_bins
        bins = [
            ConfidenceBucket(bin_lower=i * bin_width, bin_upper=(i + 1) * bin_width)
            for i in range(self.num_bins)
        ]

        total_samples = len(self.history)
        for conf, correct in self.history:
            bin_idx = min(self.num_bins - 1, int(conf / bin_width))
            b = bins[bin_idx]
            b.samples_count += 1
            if correct:
                b.correct_count += 1
            b.confidence_sum += conf

        ece = 0.0
        for b in bins:
            if b.samples_count > 0:
                ece += (b.samples_count / total_samples) * abs(b.accuracy - b.avg_confidence)
        return ece


@dataclass
class CognitiveBiasReport:
    detected_biases: List[str]
    circular_reasoning_detected: bool
    overconfidence_detected: bool
    confirmation_bias_detected: bool
    premature_convergence_detected: bool
    drift_score: float
    introspection_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected_biases": self.detected_biases,
            "circular_reasoning_detected": self.circular_reasoning_detected,
            "overconfidence_detected": self.overconfidence_detected,
            "confirmation_bias_detected": self.confirmation_bias_detected,
            "premature_convergence_detected": self.premature_convergence_detected,
            "drift_score": round(self.drift_score, 4),
            "introspection_summary": self.introspection_summary,
        }


@dataclass
class SelfReflectionTrace:
    trace_id: str
    step_number: int
    premise: str
    conclusion: str
    claimed_confidence: float
    critique: str
    biases: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "step_number": self.step_number,
            "premise": self.premise,
            "conclusion": self.conclusion,
            "claimed_confidence": round(self.claimed_confidence, 4),
            "critique": self.critique,
            "biases": self.biases,
            "timestamp": self.timestamp,
        }


class MetacognitiveIntrospector:
    """Inspects reasoning traces for logical loops, ungrounded confidence jumps,

    confirmation bias, and premature convergence.
    """

    def __init__(self, overconfidence_threshold: float = 0.90) -> None:
        self.overconfidence_threshold = overconfidence_threshold
        self.reflection_history: List[SelfReflectionTrace] = []

    def introspect_reasoning_chain(
        self,
        reasoning_steps: List[Dict[str, Any]],
        calibrator: Optional[EpistemicCalibrator] = None,
    ) -> CognitiveBiasReport:
        detected_biases: List[str] = []
        circular = False
        overconf = False
        confirmation = False
        premature = False

        conclusions: List[str] = []
        premises: List[str] = []
        confidences: List[float] = []

        for idx, step in enumerate(reasoning_steps):
            premise = str(step.get("premise", "")).strip().lower()
            conclusion = str(step.get("conclusion", "")).strip().lower()
            conf = float(step.get("confidence", 0.5))

            premises.append(premise)
            conclusions.append(conclusion)
            confidences.append(conf)

            # 1. Circular Reasoning Check: Conclusion appears as an earlier premise, or premise matches conclusion
            if conclusion and conclusion in premises[:-1]:
                circular = True
            if premise and conclusion and premise == conclusion:
                circular = True

            # 2. Overconfidence Check
            if conf >= self.overconfidence_threshold:
                if calibrator and calibrator.compute_brier_score() > 0.25:
                    overconf = True

            # Record reflection trace
            step_biases: List[str] = []
            if circular:
                step_biases.append("circular_reasoning")
            trace = SelfReflectionTrace(
                trace_id=f"trace-{secrets.token_hex(4)}",
                step_number=idx + 1,
                premise=premise,
                conclusion=conclusion,
                claimed_confidence=conf,
                critique=f"Evaluated step {idx + 1} with confidence {conf:.2f}",
                biases=step_biases,
            )
            self.reflection_history.append(trace)

        # 3. Confirmation Bias: All steps seek confirmation, no alternative or negative probes
        has_negative_probe = any(
            any(word in p or word in c for word in ["unless", "however", "counter", "refute", "falsify", "not"])
            for p, c in zip(premises, conclusions)
        )
        if len(reasoning_steps) >= 3 and not has_negative_probe:
            confirmation = True

        # 4. Premature Convergence: Complex reasoning finished in <= 1 step with maximum confidence
        if len(reasoning_steps) == 1 and confidences and confidences[0] >= 0.95:
            premature = True

        # 5. Cognitive Drift: Variance of confidence across steps
        if len(confidences) > 1:
            mean_c = sum(confidences) / len(confidences)
            drift_score = math.sqrt(sum((c - mean_c) ** 2 for c in confidences) / len(confidences))
        else:
            drift_score = 0.0

        if circular:
            detected_biases.append("CIRCULAR_REASONING")
        if overconf:
            detected_biases.append("OVERCONFIDENCE")
        if confirmation:
            detected_biases.append("CONFIRMATION_BIAS")
        if premature:
            detected_biases.append("PREMATURE_CONVERGENCE")
        if drift_score > 0.35:
            detected_biases.append("COGNITIVE_DRIFT")

        summary = f"Analyzed {len(reasoning_steps)} steps; {len(detected_biases)} cognitive biases identified."

        return CognitiveBiasReport(
            detected_biases=detected_biases,
            circular_reasoning_detected=circular,
            overconfidence_detected=overconf,
            confirmation_bias_detected=confirmation,
            premature_convergence_detected=premature,
            drift_score=drift_score,
            introspection_summary=summary,
        )


@dataclass
class BeliefNode:
    hypothesis_id: str
    description: str
    prior_probability: float
    current_probability: float
    evidence_count: int = 0
    epistemic_uncertainty: float = 0.5  # Deficiency of evidence in [0, 1]
    aleatoric_uncertainty: float = 0.1  # Inherent stochasticity in [0, 1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "prior_probability": round(self.prior_probability, 4),
            "current_probability": round(self.current_probability, 4),
            "evidence_count": self.evidence_count,
            "epistemic_uncertainty": round(self.epistemic_uncertainty, 4),
            "aleatoric_uncertainty": round(self.aleatoric_uncertainty, 4),
        }


@dataclass
class BeliefUpdate:
    update_id: str
    hypothesis_id: str
    likelihood_ratio: float
    prior: float
    posterior: float
    epistemic_entropy_before: float
    epistemic_entropy_after: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update_id,
            "hypothesis_id": self.hypothesis_id,
            "likelihood_ratio": round(self.likelihood_ratio, 4),
            "prior": round(self.prior, 4),
            "posterior": round(self.posterior, 4),
            "epistemic_entropy_before": round(self.epistemic_entropy_before, 4),
            "epistemic_entropy_after": round(self.epistemic_entropy_after, 4),
            "timestamp": self.timestamp,
        }


class EpistemicBeliefNetwork:
    """Maintains Bayesian probability distributions over mutually competitive or independent hypotheses,

    decomposing uncertainty into aleatoric (data variance) and epistemic (lack of observations).
    """

    def __init__(self, network_id: str = "default-epistemic-net") -> None:
        self.network_id = network_id
        self.nodes: Dict[str, BeliefNode] = {}
        self.update_history: List[BeliefUpdate] = []

    def register_hypothesis(
        self,
        hypothesis_id: str,
        description: str,
        prior: float = 0.5,
        aleatoric_noise: float = 0.1,
    ) -> BeliefNode:
        clamped_prior = max(0.01, min(0.99, float(prior)))
        node = BeliefNode(
            hypothesis_id=hypothesis_id,
            description=description,
            prior_probability=clamped_prior,
            current_probability=clamped_prior,
            evidence_count=0,
            epistemic_uncertainty=1.0,  # Initially max epistemic uncertainty
            aleatoric_uncertainty=aleatoric_noise,
        )
        self.nodes[hypothesis_id] = node
        return node

    def compute_epistemic_entropy(self) -> float:
        """Computes Shannon entropy across registered hypothesis probabilities H = -sum(p log2 p + (1-p) log2 (1-p))."""
        if not self.nodes:
            return 0.0
        total_entropy = 0.0
        for node in self.nodes.values():
            p = max(1e-6, min(1.0 - 1e-6, node.current_probability))
            entropy = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))
            # Scale with remaining epistemic uncertainty
            total_entropy += entropy * node.epistemic_uncertainty
        return total_entropy / len(self.nodes)

    def assimilate_evidence(self, hypothesis_id: str, likelihood_ratio: float) -> BeliefUpdate:
        """Bayesian update via Bayes factor: Posterior Odds = Prior Odds * Likelihood Ratio.

        LR > 1 supports hypothesis; LR < 1 refutes hypothesis.
        """
        node = self.nodes.get(hypothesis_id)
        if not node:
            raise KeyError(f"Hypothesis '{hypothesis_id}' not found in network")

        entropy_before = self.compute_epistemic_entropy()
        prior_prob = node.current_probability

        # Prior odds
        prior_odds = prior_prob / (1.0 - prior_prob)
        posterior_odds = prior_odds * max(1e-4, float(likelihood_ratio))
        posterior_prob = posterior_odds / (1.0 + posterior_odds)
        posterior_prob = max(1e-4, min(1.0 - 1e-4, posterior_prob))

        node.current_probability = posterior_prob
        node.evidence_count += 1
        # Epistemic uncertainty decreases asymptotically with evidence count N: 1 / sqrt(N + 1)
        node.epistemic_uncertainty = max(0.05, 1.0 / math.sqrt(node.evidence_count + 1))

        entropy_after = self.compute_epistemic_entropy()

        update = BeliefUpdate(
            update_id=f"bup-{secrets.token_hex(4)}",
            hypothesis_id=hypothesis_id,
            likelihood_ratio=likelihood_ratio,
            prior=prior_prob,
            posterior=posterior_prob,
            epistemic_entropy_before=entropy_before,
            epistemic_entropy_after=entropy_after,
        )
        self.update_history.append(update)
        return update


class ReasoningStrategy(str, enum.Enum):
    FAST_HEURISTIC = "FAST_HEURISTIC"  # System 1: Low entropy, high confidence, direct execution
    DELIBERATE_VERIFICATION = "DELIBERATE_VERIFICATION"  # System 2: Medium entropy, step-by-step verification
    ADVERSARIAL_DEBATE = "ADVERSARIAL_DEBATE"  # High entropy: synthesize counter-arguments & red team
    DEEP_CONSENSUS = "DEEP_CONSENSUS"  # Critical risk: cross-seat multi-agent voting & formal proving


class IntrospectiveStrategyOptimizer:
    """Selects the optimal cognitive reasoning mode based on epistemic entropy and task risk tier."""

    def __init__(self, fast_threshold: float = 0.35, deliberate_threshold: float = 0.70) -> None:
        self.fast_threshold = fast_threshold
        self.deliberate_threshold = deliberate_threshold

    def select_strategy(
        self,
        epistemic_entropy: float,
        task_criticality: str = "medium",  # "low", "medium", "critical"
    ) -> Dict[str, Any]:
        criticality = task_criticality.lower()

        if criticality == "critical":
            if epistemic_entropy > self.fast_threshold:
                strategy = ReasoningStrategy.DEEP_CONSENSUS
                rationale = "Critical task with non-trivial epistemic entropy requires deep multi-desk consensus proving."
            else:
                strategy = ReasoningStrategy.DELIBERATE_VERIFICATION
                rationale = "Critical task requires deliberate verification despite low epistemic entropy."
        elif epistemic_entropy < self.fast_threshold:
            strategy = ReasoningStrategy.FAST_HEURISTIC
            rationale = "Low epistemic entropy allows high-speed System 1 heuristic execution."
        elif epistemic_entropy < self.deliberate_threshold:
            strategy = ReasoningStrategy.DELIBERATE_VERIFICATION
            rationale = "Moderate epistemic entropy warrants step-by-step System 2 verification."
        else:
            strategy = ReasoningStrategy.ADVERSARIAL_DEBATE
            rationale = "High epistemic entropy requires adversarial red-teaming and counter-evidence synthesis."

        return {
            "selected_strategy": strategy.value,
            "epistemic_entropy": round(epistemic_entropy, 4),
            "task_criticality": criticality,
            "rationale": rationale,
        }
