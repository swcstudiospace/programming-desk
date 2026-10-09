"""Tests for Distributed Edge Compute Mesh (Milestone v4.3 - Phase 53)."""

import pytest
from desk_gateway.edge_mesh import (
    EdgeNode,
    EdgeComputeScheduler,
    InferenceProofEngine,
    EdgeClusterMonitor,
    EdgeCommitmentExporter,
    DistillationEdgeDrillSimulator,
)


def test_edge_compute_scheduler():
    scheduler = EdgeComputeScheduler()
    node1 = EdgeNode(node_id="edge-1", region="us-east", vram_mb=4096)
    node2 = EdgeNode(node_id="edge-2", region="us-west", vram_mb=8192)
    scheduler.register_node(node1)
    scheduler.register_node(node2)

    scheduled = scheduler.schedule_inference("art-1", required_vram_mb=2048, quantization="INT8")
    assert scheduled is not None
    assert scheduled.node_id in ("edge-1", "edge-2")
    assert scheduled.used_vram_mb == 2048
    assert scheduled.active_tasks == 1

    scheduler.release_inference(scheduled.node_id, released_vram_mb=2048)
    assert scheduled.used_vram_mb == 0
    assert scheduled.active_tasks == 0


def test_inference_proof_engine():
    engine = InferenceProofEngine(secret_key="test-secret")
    receipt = engine.generate_receipt(
        task_id="t-1",
        node_id="edge-1",
        artifact_id="art-1",
        prompt_text="hello world",
        completion_text="hi there",
    )
    assert receipt.receipt_id.startswith("rcpt-")
    assert engine.verify_receipt(receipt, prompt_text="hello world", completion_text="hi there") is True
    assert engine.verify_receipt(receipt, prompt_text="hello world", completion_text="tampered") is False


def test_edge_cluster_monitor_and_failover():
    scheduler = EdgeComputeScheduler()
    node1 = EdgeNode(node_id="edge-degraded", region="eu-central", vram_mb=4096)
    node2 = EdgeNode(node_id="edge-healthy", region="eu-west", vram_mb=4096)
    scheduler.register_node(node1)
    scheduler.register_node(node2)

    monitor = EdgeClusterMonitor(scheduler, latency_threshold_ms=50.0)
    assert monitor.check_node_health("edge-degraded", current_latency_ms=120.0) is False
    assert node1.is_healthy is False

    failover_node = monitor.trigger_failover("edge-degraded", required_vram_mb=1024, quantization="INT8")
    assert failover_node is not None
    assert failover_node.node_id == "edge-healthy"
    assert len(monitor.failover_events) == 2


def test_edge_commitment_exporter():
    engine = InferenceProofEngine()
    r1 = engine.generate_receipt("t1", "node1", "art1", "p1", "c1")
    r2 = engine.generate_receipt("t2", "node2", "art1", "p2", "c2")

    exporter = EdgeCommitmentExporter()
    commitment = exporter.export_batch_commitment([r1, r2])
    assert commitment["status"] == "confirmed_devnet"
    assert "batch_merkle_root" in commitment
    assert commitment["receipt_count"] == 2
    assert len(exporter.anchored_batches) == 1


def test_distillation_edge_drill_simulator():
    drill = DistillationEdgeDrillSimulator()
    result = drill.run_drill()
    assert result["drill_status"] == "SUCCESS"
    assert result["proof_verified"] is True
    assert result["failover_target"] is not None
    assert "anchored_root" in result
