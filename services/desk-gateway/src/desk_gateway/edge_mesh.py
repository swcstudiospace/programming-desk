"""Distributed Edge Compute Orchestration & Off-Chain Verification (Milestone v4.3 - Phase 53).

Implements:
- EdgeNode: Represents an edge compute node with hardware metrics, VRAM, and health status.
- EdgeComputeScheduler: Distributes inference tasks according to VRAM constraints and node load.
- InferenceProofEngine: Computes cryptographic HMAC-SHA256 inference attestation receipts.
- EdgeClusterMonitor: Tracks node health, latency, degradation, and triggers failover.
- EdgeCommitmentExporter: Anchors edge inference proofs and state roots to Solana devnet.
- DistillationEdgeDrillSimulator: Runs end-to-end distillation, edge scheduling, and failover drills.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EdgeNode:
    node_id: str
    region: str
    vram_mb: int
    used_vram_mb: int = 0
    active_tasks: int = 0
    is_healthy: bool = True
    latency_ms: float = 12.0
    supported_quantizations: List[str] = field(default_factory=lambda: ["INT8", "INT4"])


@dataclass
class InferenceProofReceipt:
    receipt_id: str
    task_id: str
    node_id: str
    artifact_id: str
    input_hash: str
    output_hash: str
    timestamp: float
    signature_proof: str
    metrics: Dict[str, Any] = field(default_factory=dict)


class EdgeComputeScheduler:
    """Schedules inference tasks across edge nodes with memory fencing."""

    def __init__(self):
        self._nodes: Dict[str, EdgeNode] = {}

    def register_node(self, node: EdgeNode) -> None:
        self._nodes[node.node_id] = node

    def list_nodes(self) -> List[EdgeNode]:
        return list(self._nodes.values())

    def get_node(self, node_id: str) -> Optional[EdgeNode]:
        return self._nodes.get(node_id)

    def schedule_inference(
        self, artifact_id: str, required_vram_mb: int, quantization: str
    ) -> Optional[EdgeNode]:
        """Finds the most suitable healthy edge node with sufficient VRAM."""
        candidates = [
            n for n in self._nodes.values()
            if n.is_healthy
            and (n.vram_mb - n.used_vram_mb) >= required_vram_mb
            and quantization in n.supported_quantizations
        ]
        if not candidates:
            return None

        # Sort by active tasks first, then by lowest latency
        candidates.sort(key=lambda n: (n.active_tasks, n.latency_ms))
        chosen = candidates[0]
        chosen.used_vram_mb += required_vram_mb
        chosen.active_tasks += 1
        return chosen

    def release_inference(self, node_id: str, released_vram_mb: int) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.used_vram_mb = max(0, node.used_vram_mb - released_vram_mb)
            node.active_tasks = max(0, node.active_tasks - 1)


class InferenceProofEngine:
    """Generates and verifies cryptographic HMAC-SHA256 inference proofs."""

    def __init__(self, secret_key: str = "desk-edge-attestation-secret"):
        self.secret_key = secret_key.encode()

    def generate_receipt(
        self,
        task_id: str,
        node_id: str,
        artifact_id: str,
        prompt_text: str,
        completion_text: str,
        latency_ms: float = 15.0,
    ) -> InferenceProofReceipt:
        input_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
        output_hash = hashlib.sha256(completion_text.encode()).hexdigest()
        ts = time.time()

        message = f"{task_id}:{node_id}:{artifact_id}:{input_hash}:{output_hash}:{ts}"
        sig = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()

        receipt_id = f"rcpt-{hashlib.sha256(sig.encode()).hexdigest()[:16]}"
        return InferenceProofReceipt(
            receipt_id=receipt_id,
            task_id=task_id,
            node_id=node_id,
            artifact_id=artifact_id,
            input_hash=input_hash,
            output_hash=output_hash,
            timestamp=ts,
            signature_proof=sig,
            metrics={"latency_ms": latency_ms, "prompt_len": len(prompt_text), "completion_len": len(completion_text)},
        )

    def verify_receipt(
        self, receipt: InferenceProofReceipt, prompt_text: str, completion_text: str
    ) -> bool:
        expected_in = hashlib.sha256(prompt_text.encode()).hexdigest()
        expected_out = hashlib.sha256(completion_text.encode()).hexdigest()

        if receipt.input_hash != expected_in or receipt.output_hash != expected_out:
            return False

        message = f"{receipt.task_id}:{receipt.node_id}:{receipt.artifact_id}:{expected_in}:{expected_out}:{receipt.timestamp}"
        expected_sig = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(receipt.signature_proof, expected_sig)


class EdgeClusterMonitor:
    """Monitors node health, triggers failover reassignments upon degradation."""

    def __init__(self, scheduler: EdgeComputeScheduler, latency_threshold_ms: float = 100.0):
        self.scheduler = scheduler
        self.latency_threshold_ms = latency_threshold_ms
        self.failover_events: List[Dict[str, Any]] = []

    def check_node_health(self, node_id: str, current_latency_ms: float) -> bool:
        node = self.scheduler.get_node(node_id)
        if not node:
            return False

        node.latency_ms = current_latency_ms
        if current_latency_ms > self.latency_threshold_ms:
            node.is_healthy = False
            self.failover_events.append({
                "node_id": node_id,
                "reason": f"Latency {current_latency_ms}ms exceeded {self.latency_threshold_ms}ms threshold",
                "timestamp": time.time(),
            })
            return False

        node.is_healthy = True
        return True

    def trigger_failover(
        self, degraded_node_id: str, required_vram_mb: int, quantization: str
    ) -> Optional[EdgeNode]:
        """Evacuates tasks from degraded node and schedules to alternative healthy node."""
        node = self.scheduler.get_node(degraded_node_id)
        if node:
            node.is_healthy = False
            # Evacuate current task
            node.used_vram_mb = max(0, node.used_vram_mb - required_vram_mb)
            node.active_tasks = max(0, node.active_tasks - 1)

        new_node = self.scheduler.schedule_inference(
            artifact_id="failover-task",
            required_vram_mb=required_vram_mb,
            quantization=quantization,
        )
        if new_node:
            self.failover_events.append({
                "from_node": degraded_node_id,
                "to_node": new_node.node_id,
                "timestamp": time.time(),
                "status": "failover_success",
            })
        return new_node


class EdgeCommitmentExporter:
    """Simulates on-chain anchoring of edge inference proof commitments to Solana devnet."""

    def __init__(self, devnet_program_id: str = "EdgeProof111111111111111111111111111111111"):
        self.program_id = devnet_program_id
        self.anchored_batches: List[Dict[str, Any]] = []

    def export_batch_commitment(
        self, receipts: List[InferenceProofReceipt]
    ) -> Dict[str, Any]:
        """Calculates Merkle root of receipts and anchors commitment."""
        if not receipts:
            return {"status": "empty_batch", "anchored": False}

        receipt_hashes = [
            hashlib.sha256(f"{r.receipt_id}:{r.signature_proof}".encode()).hexdigest()
            for r in receipts
        ]
        # Compute hierarchical root
        root_accumulator = "".join(sorted(receipt_hashes))
        batch_merkle_root = hashlib.sha256(root_accumulator.encode()).hexdigest()

        tx_signature = f"sol-tx-{hashlib.sha256(f'{batch_merkle_root}:{time.time()}'.encode()).hexdigest()[:32]}"
        anchor_record = {
            "batch_merkle_root": batch_merkle_root,
            "receipt_count": len(receipts),
            "solana_program_id": self.program_id,
            "tx_signature": tx_signature,
            "anchored_at": time.time(),
            "status": "confirmed_devnet",
        }
        self.anchored_batches.append(anchor_record)
        return anchor_record


class DistillationEdgeDrillSimulator:
    """Full end-to-end drill simulator verifying distillation, quantization, scheduling & failover."""

    def run_drill(self) -> Dict[str, Any]:
        from desk_gateway.model_distillation import (
            DistillationBenchmarker,
            EnsembleDistillationEngine,
            ModelArtifactRegistry,
            TeacherPrediction,
        )

        # 1. Distillation Step
        engine = EnsembleDistillationEngine(default_temperature=2.0, default_alpha=0.6)
        teacher_preds = [
            TeacherPrediction(model_id="teacher-llama-70b", weight=0.6, logits=[2.5, 0.1, -1.2, 0.8]),
            TeacherPrediction(model_id="teacher-qwen-72b", weight=0.4, logits=[2.2, 0.3, -0.9, 0.5]),
        ]
        student_logits = [1.8, 0.2, -0.8, 0.6]
        step_metrics = engine.compute_distillation_step(student_logits, teacher_preds, ground_truth_label=0)

        # 2. Quantization & Registration
        registry = ModelArtifactRegistry()
        weights = [0.12, -0.45, 0.98, -0.88, 0.05, 0.33, -0.12, 0.67]
        artifact = registry.store_artifact(
            model_name="student-desk-1.5b",
            quantization_type="INT4",
            weights=weights,
            metadata={"source": "milestone-v4.3-drill"},
        )

        # 3. Benchmarking
        benchmarker = DistillationBenchmarker()
        retention = benchmarker.evaluate_retention(teacher_accuracy=0.88, student_accuracy=0.84)
        ppl = benchmarker.evaluate_perplexity([0.15, 0.22, 0.18])

        # 4. Edge Scheduling
        scheduler = EdgeComputeScheduler()
        node_a = EdgeNode(node_id="edge-node-alpha", region="us-west-1", vram_mb=8192)
        node_b = EdgeNode(node_id="edge-node-beta", region="eu-central-1", vram_mb=4096)
        scheduler.register_node(node_a)
        scheduler.register_node(node_b)

        assigned_node = scheduler.schedule_inference(artifact.artifact_id, required_vram_mb=2048, quantization="INT4")

        # 5. Proof Generation & Verification
        proof_engine = InferenceProofEngine()
        receipt = proof_engine.generate_receipt(
            task_id="task-drill-001",
            node_id=assigned_node.node_id if assigned_node else "none",
            artifact_id=artifact.artifact_id,
            prompt_text="Write a Python unit test for edge inference",
            completion_text="def test_inference(): assert True",
        )
        is_verified = proof_engine.verify_receipt(
            receipt,
            prompt_text="Write a Python unit test for edge inference",
            completion_text="def test_inference(): assert True",
        )

        # 6. Monitor & Failover
        monitor = EdgeClusterMonitor(scheduler, latency_threshold_ms=50.0)
        is_healthy = monitor.check_node_health(node_a.node_id, current_latency_ms=120.0)
        failover_node = monitor.trigger_failover(node_a.node_id, required_vram_mb=2048, quantization="INT4")

        # 7. Anchor Exporter
        exporter = EdgeCommitmentExporter()
        anchor_rec = exporter.export_batch_commitment([receipt])

        return {
            "distillation": step_metrics,
            "artifact_id": artifact.artifact_id,
            "quantization": artifact.quantization_type,
            "retention": retention,
            "perplexity": ppl,
            "scheduled_node": assigned_node.node_id if assigned_node else None,
            "proof_verified": is_verified,
            "node_health_after_spike": is_healthy,
            "failover_target": failover_node.node_id if failover_node else None,
            "anchored_root": anchor_rec.get("batch_merkle_root"),
            "drill_status": "SUCCESS" if (is_verified and failover_node and retention["passed_gate"]) else "FAILED",
        }
