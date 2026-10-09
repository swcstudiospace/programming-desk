"""Tests for Cross-Cloud Disaster Recovery & Multi-Substrate Replication (Milestone v2.9 - Phase 24).

Covers:
- REQ-DR-001: Continuous asynchronous state mirroring engine across primary and secondary data substrates.
- REQ-DR-002: Delta snapshotting with cryptographic block checksums and incremental catch-up replication.
- REQ-DR-003: Replication lag monitor with dynamic throttle adaptation under WAN congestion.
- REQ-DR-004: Atomic cross-substrate state cutover harness ensuring zero data loss (RPO = 0).
- REQ-DR-005: Standby health polling and automated warm-replica promotion readiness verification.
- Starlette HTTP API routes in server.py.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from desk_gateway.disaster_recovery import (
    ReplicaState,
    SubstrateDeltaBlock,
    SubstrateStateMirrorEngine,
)
from desk_gateway.server import build_app


@pytest.fixture
def mirror_engine() -> SubstrateStateMirrorEngine:
    return SubstrateStateMirrorEngine(
        primary_id="primary-dc1",
        lag_throttle_threshold_blocks=3,
        max_lag_ms=100.0,
    )


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_delta_block_chaining_and_checksums(mirror_engine: SubstrateStateMirrorEngine):
    """REQ-DR-001, REQ-DR-002: Delta snapshotting with cryptographic block hashes."""
    b0 = mirror_engine.append_state_delta({"table": "ledger", "tx": 100})
    assert b0.block_index == 0
    assert b0.prev_hash == "0" * 64
    assert len(b0.block_hash) == 64

    b1 = mirror_engine.append_state_delta({"table": "ledger", "tx": 101})
    assert b1.block_index == 1
    assert b1.prev_hash == b0.block_hash
    assert b1.block_hash != b0.block_hash
    assert len(mirror_engine.blocks) == 2


def test_replica_registration_and_incremental_sync(mirror_engine: SubstrateStateMirrorEngine):
    """REQ-DR-001, REQ-DR-002: Register replica and incrementally catch up blocks."""
    # Write initial data
    mirror_engine.append_state_delta({"v": 1})
    mirror_engine.append_state_delta({"v": 2})

    rep = mirror_engine.register_replica("replica-eu", region="eu-central-1")
    assert rep.replica_id == "replica-eu"
    assert rep.state == ReplicaState.SYNCING
    assert rep.replication_lag_blocks == 2

    # Partial sync
    synced = mirror_engine.sync_replica("replica-eu", up_to_index=1)
    assert len(synced) == 1
    assert rep.applied_block_index == 1
    assert rep.replication_lag_blocks == 1

    # Full sync to tip
    synced_remaining = mirror_engine.sync_replica("replica-eu")
    assert len(synced_remaining) == 1
    assert rep.applied_block_index == 2
    assert rep.replication_lag_blocks == 0
    assert rep.state == ReplicaState.WARM_STANDBY


def test_replication_lag_and_dynamic_throttling(mirror_engine: SubstrateStateMirrorEngine):
    """REQ-DR-003: Lag monitor and dynamic throttling under WAN lag."""
    mirror_engine.register_replica("replica-us-west", region="us-west-2")
    assert mirror_engine.is_throttled is False

    # Append 3 blocks (matches threshold=3)
    mirror_engine.append_state_delta({"data": "b1"})
    mirror_engine.append_state_delta({"data": "b2"})
    assert mirror_engine.is_throttled is False

    mirror_engine.append_state_delta({"data": "b3"})
    assert mirror_engine.is_throttled is True

    # Sync catches up and relieves throttle
    mirror_engine.sync_replica("replica-us-west")
    assert mirror_engine.is_throttled is False


def test_atomic_rpo0_cutover_and_readiness(mirror_engine: SubstrateStateMirrorEngine):
    """REQ-DR-004, REQ-DR-005: RPO=0 zero-loss atomic cutover."""
    mirror_engine.register_replica("replica-dr", region="ap-southeast-1")
    mirror_engine.append_state_delta({"balance": 5000})

    # Initially lagging
    ready, msg = mirror_engine.verify_replica_readiness("replica-dr")
    assert ready is False
    assert "must be 0" in msg

    # Execute cutover - engine auto-syncs remaining blocks before handover
    result = mirror_engine.execute_atomic_cutover("replica-dr")
    assert result["ok"] is True
    assert result["new_primary"] == "replica-dr"
    assert result["demoted_primary"] == "primary-dc1"
    assert result["rpo_loss_blocks"] == 0

    # Old primary is now warm standby, replica is new primary
    assert mirror_engine.primary_id == "replica-dr"
    assert "primary-dc1" in mirror_engine.replicas
    assert mirror_engine.replicas["primary-dc1"].state == ReplicaState.WARM_STANDBY


def test_disaster_recovery_gateway_endpoints(client: TestClient):
    """Starlette API integration tests for disaster recovery."""
    # 1. Register replica
    r_reg = client.post("/v1/dr/replica/register", json={
        "replica_id": "api-replica-1",
        "region": "us-east-1",
    })
    assert r_reg.status_code == 200
    assert r_reg.json()["ok"] is True
    assert r_reg.json()["state"] == "syncing"

    # 2. Append delta block
    r_block = client.post("/v1/dr/mirror/block", json={
        "payload": {"tx_id": "tx-1234", "amount": 100},
    })
    assert r_block.status_code == 200
    b_data = r_block.json()
    assert b_data["ok"] is True
    assert b_data["block_index"] == 0

    # 3. Status inspection
    r_stat = client.get("/v1/dr/mirror/status")
    assert r_stat.status_code == 200
    stat_data = r_stat.json()
    assert stat_data["ok"] is True
    assert stat_data["total_blocks"] == 1
    assert "api-replica-1" in stat_data["replicas"]

    # 4. Sync replica
    r_sync = client.post("/v1/dr/replica/sync", json={"replica_id": "api-replica-1"})
    assert r_sync.status_code == 200
    assert r_sync.json()["synced_blocks_count"] == 1

    # 5. Cutover
    r_cut = client.post("/v1/dr/cutover", json={"target_replica_id": "api-replica-1"})
    assert r_cut.status_code == 200
    assert r_cut.json()["new_primary"] == "api-replica-1"
    assert r_cut.json()["rpo_loss_blocks"] == 0
