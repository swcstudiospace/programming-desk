"""Tests for Multi-Modal Sensory Memory Indexing and Streaming Verification (Phase 20-02)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.multimodal import (
    MultiModalArtifactPipeline,
    StreamCancellationSupervisor,
    StreamingToolBus,
)
from desk_gateway.multimodal_memory import (
    MultiModalStreamingVerifier,
    SensoryMemoryIndexer,
    cosine_similarity,
)
from desk_gateway.server import build_app


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert round(cosine_similarity(v1, v2), 4) == 1.0

    v3 = [0.0, 1.0, 0.0]
    assert round(cosine_similarity(v1, v3), 4) == 0.0

    v4 = [1.0, 1.0, 0.0]
    assert 0.70 < cosine_similarity(v1, v4) < 0.72


def test_sensory_memory_indexing_and_search():
    indexer = SensoryMemoryIndexer()
    rec1 = indexer.index(
        artifact_id="art-101",
        modality="image",
        embedding=[0.8, 0.6, 0.0],
        caption="System architecture diagram",
        ledger_ref="tx-voucher-99",
        tenant_id="tenant-prod",
    )
    rec2 = indexer.index(
        artifact_id="art-102",
        modality="audio",
        embedding=[0.0, 0.1, 0.99],
        caption="Audio memo regarding gateway failover",
        tenant_id="tenant-prod",
    )
    rec_other = indexer.index(
        artifact_id="art-103",
        modality="image",
        embedding=[0.8, 0.6, 0.0],
        caption="Diagram in other tenant",
        tenant_id="tenant-other",
    )

    # Search in tenant-prod
    results = indexer.search(
        query_embedding=[0.8, 0.6, 0.0],
        tenant_id="tenant-prod",
        min_score=0.9,
    )
    assert len(results) == 1
    assert results[0].record.memory_id == rec1.memory_id
    assert results[0].record.ledger_ref == "tx-voucher-99"

    # Search with modality filter
    audio_results = indexer.search(
        query_embedding=[0.0, 0.1, 0.99],
        tenant_id="tenant-prod",
        modality="audio",
    )
    assert len(audio_results) == 1
    assert audio_results[0].record.memory_id == rec2.memory_id


@pytest.mark.asyncio
async def test_multimodal_streaming_verifier():
    pipeline = MultiModalArtifactPipeline()
    supervisor = StreamCancellationSupervisor()
    bus = StreamingToolBus(supervisor=supervisor)
    indexer = SensoryMemoryIndexer()

    verifier = MultiModalStreamingVerifier(
        pipeline=pipeline,
        streaming_bus=bus,
        memory_indexer=indexer,
    )

    res = await verifier.verify_all(tenant_id="tenant-verify-suite")
    assert res["ok"] is True
    assert len(res["checks"]) == 3
    for check in res["checks"]:
        assert check["pass"] is True


def test_sensory_memory_api_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Index sensory memory
    resp = client.post(
        "/v1/multimodal/memory/index",
        json={
            "artifact_id": "art-api-test",
            "modality": "image",
            "embedding": [0.5, 0.5, 0.5, 0.5],
            "caption": "Cluster telemetry chart",
            "ledger_ref": "vouch-api-123",
            "tenant_id": "tenant-api",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    mem_id = data["memory"]["memory_id"]

    # 2. Search sensory memory
    search_resp = client.post(
        "/v1/multimodal/memory/search",
        json={
            "query_embedding": [0.5, 0.5, 0.5, 0.5],
            "tenant_id": "tenant-api",
            "min_score": 0.9,
        },
    )
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data["ok"] is True
    assert search_data["count"] >= 1
    assert search_data["results"][0]["memory_id"] == mem_id
    assert search_data["results"][0]["ledger_ref"] == "vouch-api-123"

    # 3. Multi-modal streaming verify endpoint
    verify_resp = client.post(
        "/v1/multimodal/streaming/verify",
        json={"tenant_id": "tenant-api-verify"},
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["ok"] is True
    assert len(verify_data["checks"]) == 3
