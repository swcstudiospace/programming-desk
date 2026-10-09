"""Unit and integration tests for Dynamic Context Window Compression & Semantic Pruning (Phase 31)."""

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.context_compressor import (
    ContextCompressionEngine,
    ModelTier,
    CompressionMode,
    ContextSegment,
    LosslessCompactor,
    SemanticPruner,
    HierarchicalRollupEngine,
    DynamicWindowAdapter,
    ContextFidelityVerifier,
    estimate_token_count,
)
from desk_gateway.server import build_app


SAMPLE_CODE = """
def process_data(records: list[dict]) -> dict:
    # This is a sample function with lots of redundant comments and explanations
    # that should normally be pruned while maintaining balanced braces and quotes
    results = {}
    for r in records:
        key = r.get("id")
        if key is not None:
            results[key] = r.get("value", 0) * 2
    return results
"""

SAMPLE_LONG_PROMPT = """
Here is an overview of the system architecture and historical log entries:
1. Event PR-42 merged to main branch with commit 0xabcdef1234567890.
2. The user requested an update to the deployment manifest.
3. Seat lead reviewed the pull request and approved execution.
4. Additional logs and debug information that adds large token overhead:
   the quick brown fox jumps over the lazy dog repeatedly in order to inflate
   the context window size beyond normal tier bounds and test compaction.
"""


def test_lossless_compactor_roundtrip():
    """REQ-GRAPH-006: Lossless token compression and context-window compaction pipeline."""
    compactor = LosslessCompactor()
    text = SAMPLE_CODE + SAMPLE_LONG_PROMPT * 10
    orig_tokens = estimate_token_count(text)
    assert orig_tokens > 50

    payload = compactor.compress_text(text)
    assert payload.original_size_bytes > payload.compressed_size_bytes
    assert payload.compression_ratio > 1.0
    assert len(payload.checksum_sha256) == 64

    # Decompress and verify bit-for-bit exact match
    decompressed = compactor.decompress_text(payload)
    assert decompressed == text


def test_semantic_pruner_preserves_syntactic_validity():
    """REQ-GRAPH-007: Semantic relevance pruning removing low-salience tokens while preserving syntactic validity."""
    pruner = SemanticPruner()
    text = SAMPLE_CODE

    pruned_text, ratio = pruner.prune_text(text, salience_threshold=0.35, preserve_syntax=True)
    assert len(pruned_text) < len(text)
    assert ratio >= 1.0

    # Verify structural delimiters match in balance
    verifier = ContextFidelityVerifier()
    assert verifier.verify_syntactic_validity(pruned_text)

    # Braces and parens in code must remain balanced
    for op, cl in [("(", ")"), ("{", "}"), ("[", "]")]:
        assert pruned_text.count(op) == pruned_text.count(cl)


def test_hierarchical_rollup_and_eviction_proof():
    """REQ-GRAPH-008: Hierarchical summary rollups and long-context eviction proofs."""
    engine = HierarchicalRollupEngine(signing_secret="test-secret-key")

    segments = [
        ContextSegment(
            segment_id=f"seg-{i}",
            content=f"Log entry {i}: Task executed successfully for seat lead with parameters x={i}",
            token_count=18,
            modality="text",
            salience_score=0.4 + (i * 0.1),
        )
        for i in range(7)
    ]

    rollups = engine.rollup_segments(segments, chunk_size=3, level=1)
    assert len(rollups) == 3 # 7 segments / 3 = 3 chunks
    assert rollups[0].level == 1
    assert len(rollups[0].child_segment_ids) == 3

    # Generate eviction proof
    proof = engine.evict_and_prove(segments)
    assert proof.evicted_tokens_count == sum(s.token_count for s in segments)
    assert len(proof.evicted_segment_ids) == 7
    assert len(proof.signature) == 64

    # Verify proof passes validation
    assert engine.verify_eviction_proof(proof) is True

    # Tampered proof must fail
    tampered_proof = proof.to_dict()
    tampered_proof["evicted_tokens_count"] = 9999
    from desk_gateway.context_compressor import EvictionProof
    t_obj = EvictionProof(**tampered_proof)
    assert engine.verify_eviction_proof(t_obj) is False


def test_dynamic_context_window_adaptation():
    """REQ-GRAPH-009: Dynamic context window adaptation based on model tier and budget ceilings."""
    adapter = DynamicWindowAdapter()
    pruner = SemanticPruner()
    rollup = HierarchicalRollupEngine()

    segments = [
        ContextSegment(
            segment_id=f"seg-{i}",
            content=f"Detailed execution transcript chunk {i} containing long context logs {SAMPLE_LONG_PROMPT}",
            token_count=120,
            modality="tool_trace",
            salience_score=0.2 if i < 3 else 0.8,
        )
        for i in range(10)
    ]
    total_tokens = sum(s.token_count for s in segments)
    assert total_tokens == 1200

    # Adapt to high budget (Tier 1 Premium): no compaction needed
    res_t1 = adapter.adapt_context(segments, tier=ModelTier.TIER_1_PREMIUM, hard_budget_ceiling=2000)
    assert res_t1["mode"] == CompressionMode.LOSSLESS.value
    assert res_t1["final_tokens"] == total_tokens

    # Adapt to constrained budget: forces semantic pruning / rollup
    res_constrained = adapter.adapt_context(segments, tier=ModelTier.TIER_3_ECONOMY, hard_budget_ceiling=400, pruner=pruner, rollup_engine=rollup)
    assert res_constrained["final_tokens"] <= 500
    assert res_constrained["eviction_proof"] is not None
    assert len(res_constrained["rollup_summaries"]) > 0


def test_context_fidelity_and_reconstruction_verification():
    """REQ-GRAPH-010: End-to-end context fidelity and reconstruction verification suite."""
    verifier = ContextFidelityVerifier()
    test_content = (
        "def compute_hash(data: str) -> str:\n"
        "    # Compute SHA-256 hash securely\n"
        "    return hashlib.sha256(data.encode('utf-8')).hexdigest()\n"
    )

    report = verifier.run_verification(test_content=test_content, test_id="test-fid-01")
    assert report.test_id == "test-fid-01"
    assert report.roundtrip_lossless_passed is True
    assert report.syntax_valid is True
    assert report.eviction_proof_valid is True
    assert report.semantic_fidelity_score > 0.5
    assert report.passed is True


def test_context_compression_http_endpoints():
    """Integration test verifying Starlette endpoints on desk-gateway."""
    app, _ = build_app()
    client = TestClient(app)

    # 1. POST /v1/context/compress
    resp_comp = client.post("/v1/context/compress", json={"text": SAMPLE_CODE})
    assert resp_comp.status_code == 200
    comp_json = resp_comp.json()
    assert comp_json["ok"] is True
    compressed = comp_json["compressed"]
    assert "compressed_b64" in compressed
    assert "checksum_sha256" in compressed

    # 2. POST /v1/context/decompress
    resp_decomp = client.post("/v1/context/decompress", json=compressed)
    assert resp_decomp.status_code == 200
    decomp_json = resp_decomp.json()
    assert decomp_json["ok"] is True
    assert decomp_json["text"] == SAMPLE_CODE

    # 3. POST /v1/context/prune
    resp_prune = client.post("/v1/context/prune", json={
        "text": SAMPLE_CODE,
        "salience_threshold": 0.35,
        "preserve_syntax": True,
    })
    assert resp_prune.status_code == 200
    prune_json = resp_prune.json()
    assert prune_json["ok"] is True
    assert "pruned_text" in prune_json

    # 4. POST /v1/context/rollup
    resp_rollup = client.post("/v1/context/rollup", json={
        "segments": [
            {"segment_id": "seg-1", "content": "alpha task 1", "token_count": 10},
            {"segment_id": "seg-2", "content": "beta task 2", "token_count": 15},
            {"segment_id": "seg-3", "content": "gamma task 3", "token_count": 20},
        ],
        "chunk_size": 2,
    })
    assert resp_rollup.status_code == 200
    rollup_json = resp_rollup.json()
    assert rollup_json["ok"] is True
    assert len(rollup_json["rollups"]) == 2
    assert "eviction_proof" in rollup_json

    # 5. POST /v1/context/adapt
    resp_adapt = client.post("/v1/context/adapt", json={
        "segments": [
            {"segment_id": "seg-1", "content": "alpha task 1 " + SAMPLE_LONG_PROMPT, "token_count": 100, "salience_score": 0.2},
            {"segment_id": "seg-2", "content": "beta task 2 " + SAMPLE_LONG_PROMPT, "token_count": 100, "salience_score": 0.9},
        ],
        "tier": "tier_3_economy",
        "budget_ceiling": 120,
    })
    assert resp_adapt.status_code == 200
    adapt_json = resp_adapt.json()
    assert adapt_json["ok"] is True
    assert adapt_json["final_tokens"] <= 150

    # 6. POST /v1/context/verify
    resp_verify = client.post("/v1/context/verify", json={
        "content": SAMPLE_CODE,
        "test_id": "api-verify-test",
    })
    assert resp_verify.status_code == 200
    verify_json = resp_verify.json()
    assert verify_json["ok"] is True
    assert verify_json["verification"]["passed"] is True
