"""Tests for Continuous Merkle Proof Verification & Immutable Audit Export (Milestone v3.0 - Phase 27).

Covers:
- REQ-ZERO-006: Continuous incremental Merkle tree aggregator over all desk operations.
- REQ-ZERO-007: Cryptographic inclusion & consistency proof generator for arbitrary time windows.
- REQ-ZERO-008: External immutable audit log export adapter supporting WORM/Solana devnet anchoring.
- REQ-ZERO-009: Automated tamper-detection audit scrubber identifying manipulated log entries.
- REQ-ZERO-010: End-to-end zero-trust compliance verification suite with signed attestation receipts.
- Starlette HTTP API routes in server.py.
"""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.merkle_audit import (
    AuditLeaf,
    AuditLogScrubber,
    ImmutableAuditExporter,
    IncrementalMerkleTree,
    ZeroTrustComplianceVerifier,
)
from desk_gateway.server import build_app


@pytest.fixture
def tree() -> IncrementalMerkleTree:
    return IncrementalMerkleTree()


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_merkle_tree_append_and_root_update(tree: IncrementalMerkleTree):
    """REQ-ZERO-006: Continuous incremental Merkle tree aggregator."""
    assert tree.get_root_hash() == "0" * 64

    leaf0 = tree.append_leaf(seat_id="lead", operation="deploy", payload={"target": "prod"})
    assert leaf0.index == 0
    assert len(leaf0.leaf_hash) == 64
    root0 = tree.get_root_hash()
    assert root0 == leaf0.leaf_hash

    leaf1 = tree.append_leaf(seat_id="systems", operation="contract_verify", payload={"contract": "auth.proto"})
    assert leaf1.index == 1
    root1 = tree.get_root_hash()
    assert root1 != root0
    assert len(root1) == 64


def test_cryptographic_inclusion_proof_and_verification(tree: IncrementalMerkleTree):
    """REQ-ZERO-007: Inclusion proof generation and validation."""
    for i in range(5):
        tree.append_leaf(seat_id="infra", operation=f"op_{i}", payload={"step": i})

    root = tree.get_root_hash()

    # Generate proof for leaf index 2
    target_hash, proof_path = tree.generate_inclusion_proof(2)
    assert target_hash == tree.leaves[2].leaf_hash
    assert len(proof_path) > 0

    # Verify inclusion proof
    is_valid = IncrementalMerkleTree.verify_inclusion_proof(
        leaf_hash=target_hash,
        proof_path=proof_path,
        expected_root=root,
    )
    assert is_valid is True

    # Tampered leaf hash fails
    is_invalid = IncrementalMerkleTree.verify_inclusion_proof(
        leaf_hash="deadbeef" * 8,
        proof_path=proof_path,
        expected_root=root,
    )
    assert is_invalid is False


def test_immutable_audit_exporter_anchor_generation():
    """REQ-ZERO-008: WORM / Solana devnet anchor batch export and HMAC signing."""
    exporter = ImmutableAuditExporter()
    batch = exporter.export_anchor(
        batch_id="batch-001",
        merkle_root="3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b",
        leaf_count=100,
        start_t=1000.0,
        end_t=2000.0,
        anchor_target="solana_devnet",
    )
    assert batch.batch_id == "batch-001"
    assert batch.anchor_target == "solana_devnet"
    assert len(batch.signature) == 64


def test_audit_log_scrubber_tamper_detection(tree: IncrementalMerkleTree):
    """REQ-ZERO-009: Automated tamper-detection scrubber."""
    tree.append_leaf(seat_id="lead", operation="tx", payload={"val": 10})
    tree.append_leaf(seat_id="web", operation="tx", payload={"val": 20})

    # Clean leaves pass scrub
    passed, anomalies = AuditLogScrubber.scrub(tree.leaves)
    assert passed is True
    assert len(anomalies) == 0

    # Corrupt a leaf hash
    tree.leaves[1].leaf_hash = "bad_hash_value"
    passed_bad, anomalies_bad = AuditLogScrubber.scrub(tree.leaves)
    assert passed_bad is False
    assert len(anomalies_bad) == 1
    assert "Tampered leaf hash" in anomalies_bad[0]


def test_zero_trust_compliance_verifier_drill(tree: IncrementalMerkleTree):
    """REQ-ZERO-010: Zero-trust compliance verification drill and signature."""
    tree.append_leaf(seat_id="lead", operation="genesis", payload={"ready": True})
    verifier = ZeroTrustComplianceVerifier(tree=tree)

    receipt = verifier.run_compliance_drill(receipt_id="rec-compliance-01")
    assert receipt.receipt_id == "rec-compliance-01"
    assert receipt.scrub_passed is True
    assert len(receipt.signature) == 64

    # Verify signature
    assert verifier.verify_compliance_receipt(receipt) is True


def test_merkle_audit_gateway_endpoints(client: TestClient):
    """Starlette API integration tests for Merkle Audit routes."""
    # 1. Append leaf
    r_app = client.post("/v1/audit/merkle/append", json={
        "seat_id": "lead",
        "operation": "audit_test",
        "payload": {"num": 42},
    })
    assert r_app.status_code == 200
    data = r_app.json()
    assert data["ok"] is True
    assert data["leaf_index"] == 0
    root = data["merkle_root"]

    # 2. Get Root
    r_root = client.get("/v1/audit/merkle/root")
    assert r_root.status_code == 200
    assert r_root.json()["merkle_root"] == root

    # 3. Inclusion Proof
    r_proof = client.post("/v1/audit/merkle/proof", json={"leaf_index": 0})
    assert r_proof.status_code == 200
    p_data = r_proof.json()
    assert p_data["ok"] is True

    # 4. Verify Proof
    r_ver = client.post("/v1/audit/merkle/verify", json={
        "leaf_hash": p_data["target_hash"],
        "proof_path": p_data["proof_path"],
        "expected_root": p_data["merkle_root"],
    })
    assert r_ver.status_code == 200
    assert r_ver.json()["valid"] is True

    # 5. Export Anchor
    r_exp = client.post("/v1/audit/export/anchor", json={"anchor_target": "worm_s3"})
    assert r_exp.status_code == 200
    assert r_exp.json()["anchor_target"] == "worm_s3"

    # 6. Scrub
    r_scrub = client.post("/v1/audit/scrub")
    assert r_scrub.status_code == 200
    assert r_scrub.json()["passed"] is True

    # 7. Compliance Drill
    r_drill = client.post("/v1/audit/compliance/drill", json={})
    assert r_drill.status_code == 200
    assert r_drill.json()["valid"] is True
    assert r_drill.json()["receipt"]["scrub_passed"] is True
