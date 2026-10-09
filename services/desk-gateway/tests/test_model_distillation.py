"""Tests for Model Distillation & Quantization Engine (Milestone v4.3 - Phase 52)."""

import pytest
from desk_gateway.model_distillation import (
    EnsembleDistillationEngine,
    QuantizationCompressor,
    DistillationBenchmarker,
    ModelArtifactRegistry,
    TeacherPrediction,
)


def test_ensemble_distillation_step():
    engine = EnsembleDistillationEngine(default_temperature=2.0, default_alpha=0.6)
    teachers = [
        TeacherPrediction(model_id="t1", weight=0.7, logits=[3.0, 0.5, -1.0]),
        TeacherPrediction(model_id="t2", weight=0.3, logits=[2.5, 0.8, -0.5]),
    ]
    student_logits = [2.0, 0.2, -0.8]

    metrics = engine.compute_distillation_step(
        student_logits=student_logits,
        teacher_predictions=teachers,
        ground_truth_label=0,
    )

    assert "total_loss" in metrics
    assert "distillation_loss" in metrics
    assert "student_ce_loss" in metrics
    assert metrics["total_loss"] > 0.0


def test_quantization_compressor_int8():
    weights = [0.15, -0.75, 1.25, -1.5, 0.0]
    quantized, scale, zero_pt = QuantizationCompressor.quantize_int8(weights)

    assert len(quantized) == len(weights)
    assert scale > 0.0
    assert zero_pt == 0
    assert all(-128 <= q <= 127 for q in quantized)

    dequantized = QuantizationCompressor.dequantize_int8(quantized, scale, zero_pt)
    for orig, deq in zip(weights, dequantized):
        assert abs(orig - deq) < 0.05


def test_quantization_compressor_int4():
    weights = [0.2, -0.6, 0.9, -0.95, 0.0]
    quantized, scale, zero_pt = QuantizationCompressor.quantize_int4(weights)

    assert len(quantized) == len(weights)
    assert all(-8 <= q <= 7 for q in quantized)

    dequantized = QuantizationCompressor.dequantize_int4(quantized, scale, zero_pt)
    for orig, deq in zip(weights, dequantized):
        assert abs(orig - deq) < 0.25


def test_distillation_benchmarker():
    benchmarker = DistillationBenchmarker()
    ppl = benchmarker.evaluate_perplexity([0.1, 0.2, 0.15])
    assert ppl >= 1.0

    eval_res = benchmarker.evaluate_retention(teacher_accuracy=0.90, student_accuracy=0.86)
    assert eval_res["passed_gate"] is True
    assert eval_res["retention_percentage"] > 90.0

    failed_res = benchmarker.evaluate_retention(teacher_accuracy=0.90, student_accuracy=0.60)
    assert failed_res["passed_gate"] is False


def test_model_artifact_registry():
    registry = ModelArtifactRegistry()
    job = registry.register_job("student-desk-7b", ["llama-70b", "qwen-72b"], temperature=2.5)
    assert job.student_model_name == "student-desk-7b"
    assert registry.get_job(job.job_id) is not None

    weights = [0.1, -0.2, 0.3, -0.4, 0.5]
    art = registry.store_artifact("student-desk-7b", "INT8", weights, {"author": "desk-lead"})
    assert art.quantization_type == "INT8"
    assert len(art.sha256_digest) == 64
    assert registry.get_artifact(art.artifact_id) is not None
    assert len(registry.list_artifacts()) == 1
