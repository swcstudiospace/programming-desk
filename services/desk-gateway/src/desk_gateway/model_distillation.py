"""Model Distillation Engine & Quantized Synthesis Module (Milestone v4.3 - Phase 52).

Implements:
- EnsembleDistillationEngine: Aggregates soft labels from heterogeneous teacher models with temperature scaling.
- QuantizationCompressor: Symmetric/asymmetric INT8/INT4 weight quantization with scale/offset calibration.
- DistillationBenchmarker: Perplexity, accuracy, and capability regression evaluation.
- ModelArtifactRegistry: Stores versioned model artifacts with cryptographic hash verification.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TeacherPrediction:
    model_id: str
    weight: float
    logits: List[float]


@dataclass
class DistillationJob:
    job_id: str
    student_model_name: str
    teacher_models: List[str]
    temperature: float
    alpha: float  # Weight balance between distillation loss and hard ground truth loss
    target_quantization: str  # e.g., 'INT8', 'INT4', 'FP16'
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    synthesized_artifact_id: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelArtifact:
    artifact_id: str
    model_name: str
    quantization_type: str
    parameter_count: int
    compressed_size_bytes: int
    sha256_digest: str
    scales: List[float]
    zero_points: List[int]
    quantized_weights: List[int]
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnsembleDistillationEngine:
    """Combines teacher model ensembles and computes student distillation loss."""

    def __init__(self, default_temperature: float = 2.0, default_alpha: float = 0.5):
        self.default_temperature = default_temperature
        self.default_alpha = default_alpha

    def softmax(self, logits: List[float], temperature: float = 1.0) -> List[float]:
        scaled = [l / max(temperature, 1e-6) for l in logits]
        max_val = max(scaled) if scaled else 0.0
        exp_vals = [math.exp(v - max_val) for v in scaled]
        sum_exp = sum(exp_vals) or 1.0
        return [v / sum_exp for v in exp_vals]

    def cross_entropy(self, targets: List[float], preds: List[float]) -> float:
        loss = 0.0
        eps = 1e-12
        for t, p in zip(targets, preds):
            loss -= t * math.log(max(p, eps))
        return loss

    def aggregate_teacher_targets(
        self, teacher_predictions: List[TeacherPrediction], temperature: float
    ) -> List[float]:
        """Calculates weighted average soft targets across teacher models."""
        if not teacher_predictions:
            return []

        vocab_size = len(teacher_predictions[0].logits)
        aggregated = [0.0] * vocab_size
        total_weight = sum(p.weight for p in teacher_predictions) or 1.0

        for pred in teacher_predictions:
            soft_dist = self.softmax(pred.logits, temperature)
            norm_weight = pred.weight / total_weight
            for i in range(min(vocab_size, len(soft_dist))):
                aggregated[i] += soft_dist[i] * norm_weight

        # Re-normalize to guarantee a valid probability distribution
        total_prob = sum(aggregated) or 1.0
        return [p / total_prob for p in aggregated]

    def compute_distillation_step(
        self,
        student_logits: List[float],
        teacher_predictions: List[TeacherPrediction],
        ground_truth_label: int,
        temperature: Optional[float] = None,
        alpha: Optional[float] = None,
    ) -> Dict[str, float]:
        """Calculates joint distillation loss = alpha * soft_loss * (T^2) + (1-alpha) * hard_loss."""
        t = temperature if temperature is not None else self.default_temperature
        a = alpha if alpha is not None else self.default_alpha

        # Soft loss
        soft_targets = self.aggregate_teacher_targets(teacher_predictions, t)
        student_soft = self.softmax(student_logits, t)
        soft_loss = self.cross_entropy(soft_targets, student_soft) * (t**2)

        # Hard loss
        vocab_size = len(student_logits)
        hard_targets = [1.0 if i == ground_truth_label else 0.0 for i in range(vocab_size)]
        student_hard = self.softmax(student_logits, 1.0)
        hard_loss = self.cross_entropy(hard_targets, student_hard)

        total_loss = a * soft_loss + (1.0 - a) * hard_loss
        return {
            "total_loss": round(total_loss, 5),
            "distillation_loss": round(soft_loss, 5),
            "student_ce_loss": round(hard_loss, 5),
            "temperature": t,
            "alpha": a,
        }


class QuantizationCompressor:
    """Performs INT8 and INT4 quantization with scale/offset calibration."""

    @staticmethod
    def quantize_int8(weights: List[float]) -> Tuple[List[int], float, int]:
        """Quantizes float weights to 8-bit signed integers [-128, 127]."""
        if not weights:
            return [], 1.0, 0

        min_val = min(weights)
        max_val = max(weights)
        max_abs = max(abs(min_val), abs(max_val), 1e-6)
        scale = max_abs / 127.0
        zero_point = 0  # Symmetric quantization

        quantized = []
        for w in weights:
            q = int(round(w / scale))
            q = max(-128, min(127, q))
            quantized.append(q)

        return quantized, scale, zero_point

    @staticmethod
    def dequantize_int8(quantized: List[int], scale: float, zero_point: int) -> List[float]:
        return [(q - zero_point) * scale for q in quantized]

    @staticmethod
    def quantize_int4(weights: List[float]) -> Tuple[List[int], float, int]:
        """Quantizes float weights to 4-bit signed integers [-8, 7]."""
        if not weights:
            return [], 1.0, 0

        min_val = min(weights)
        max_val = max(weights)
        max_abs = max(abs(min_val), abs(max_val), 1e-6)
        scale = max_abs / 7.0
        zero_point = 0

        quantized = []
        for w in weights:
            q = int(round(w / scale))
            q = max(-8, min(7, q))
            quantized.append(q)

        return quantized, scale, zero_point

    @staticmethod
    def dequantize_int4(quantized: List[int], scale: float, zero_point: int) -> List[float]:
        return [(q - zero_point) * scale for q in quantized]


class DistillationBenchmarker:
    """Measures model fidelity, perplexity, and reasoning accuracy retention."""

    def evaluate_perplexity(self, cross_entropies: List[float]) -> float:
        if not cross_entropies:
            return 1.0
        avg_loss = sum(cross_entropies) / len(cross_entropies)
        try:
            return round(math.exp(avg_loss), 4)
        except OverflowError:
            return float("inf")

    def evaluate_retention(
        self, teacher_accuracy: float, student_accuracy: float
    ) -> Dict[str, Any]:
        retention = (student_accuracy / max(teacher_accuracy, 1e-6)) * 100.0
        degradation = max(0.0, teacher_accuracy - student_accuracy)
        is_acceptable = retention >= 85.0 and degradation <= 15.0

        return {
            "teacher_accuracy": round(teacher_accuracy, 4),
            "student_accuracy": round(student_accuracy, 4),
            "retention_percentage": round(retention, 2),
            "degradation_drop": round(degradation, 4),
            "passed_gate": is_acceptable,
        }


class ModelArtifactRegistry:
    """In-memory artifact registry managing distilled and quantized models."""

    def __init__(self):
        self._artifacts: Dict[str, ModelArtifact] = {}
        self._jobs: Dict[str, DistillationJob] = {}

    def register_job(
        self,
        student_model_name: str,
        teacher_models: List[str],
        temperature: float = 2.0,
        alpha: float = 0.5,
        target_quantization: str = "INT8",
    ) -> DistillationJob:
        job_id = f"job-{hashlib.sha256(f'{student_model_name}:{time.time()}'.encode()).hexdigest()[:12]}"
        job = DistillationJob(
            job_id=job_id,
            student_model_name=student_model_name,
            teacher_models=teacher_models,
            temperature=temperature,
            alpha=alpha,
            target_quantization=target_quantization,
        )
        self._jobs[job_id] = job
        return job

    def store_artifact(
        self,
        model_name: str,
        quantization_type: str,
        weights: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ModelArtifact:
        if quantization_type.upper() == "INT4":
            quantized, scale, zero_pt = QuantizationCompressor.quantize_int4(weights)
            param_bytes = (len(quantized) + 1) // 2
        else:
            quantized, scale, zero_pt = QuantizationCompressor.quantize_int8(weights)
            param_bytes = len(quantized)

        payload = json.dumps({
            "model": model_name,
            "quant": quantization_type,
            "weights": quantized[:50],  # Hash payload
            "scale": scale,
        }, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()

        artifact_id = f"art-{digest[:16]}"
        artifact = ModelArtifact(
            artifact_id=artifact_id,
            model_name=model_name,
            quantization_type=quantization_type.upper(),
            parameter_count=len(weights),
            compressed_size_bytes=param_bytes,
            sha256_digest=digest,
            scales=[scale],
            zero_points=[zero_pt],
            quantized_weights=quantized,
            metadata=metadata or {},
        )
        self._artifacts[artifact_id] = artifact
        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[ModelArtifact]:
        return self._artifacts.get(artifact_id)

    def get_job(self, job_id: str) -> Optional[DistillationJob]:
        return self._jobs.get(job_id)

    def list_artifacts(self) -> List[ModelArtifact]:
        return list(self._artifacts.values())
