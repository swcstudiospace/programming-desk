"""Unit tests for Phase 43: Sovereign Mesh Consensus & Cross-Region Quorum Healing."""

import pytest
from desk_gateway.sharding import (
    CRDTStore,
    ConsistentHashRing,
    GeoReplicationEngine,
    ShardNode,
)
from desk_gateway.mesh_consensus import (
    AntiEntropyGossip,
    GossipDigest,
    SplitBrainDetector,
    EpochCoordinator,
    PartitionHealingOrchestrator,
    GeoPartitionDrillSimulator,
)


def test_anti_entropy_gossip_digest():
    store_a = CRDTStore("us-east", "node-east")
    store_b = CRDTStore("us-west", "node-west")

    store_a.write_lww("key-1", "val-1")
    gossip_a = AntiEntropyGossip("us-east", store_a)
    digest_a = gossip_a.generate_digest()

    assert digest_a.region_id == "us-east"
    assert digest_a.vector_clock["us-east"] >= 1

    gossip_b = AntiEntropyGossip("us-west", store_b)
    comp = gossip_b.receive_digest(digest_a)
    assert comp["peer_region"] == "us-east"
    assert comp["status"] in ("lagging", "diverged")


def test_split_brain_quorum_and_epoch_lease():
    regions = ["us-east", "us-west", "eu-central"]
    detector = SplitBrainDetector(local_region="us-east", total_regions=regions)

    # All alive -> majority is true
    assert detector.update_peer_liveness(["us-east", "us-west", "eu-central"]) is True
    assert detector.can_write() is True

    coord = EpochCoordinator(node_id="node-east", region_id="us-east", split_detector=detector)
    lease = coord.acquire_lease(ttl_seconds=10.0)
    assert lease is not None
    assert coord.validate_lease(lease.epoch_id) is True

    # Network partition: minority group [us-east] isolated
    assert detector.update_peer_liveness(["us-east"]) is False
    assert detector.can_write() is False

    # Lease acquisition blocked in minority partition
    lease_blocked = coord.acquire_lease()
    assert lease_blocked is None
    assert coord.validate_lease(lease.epoch_id) is False


def test_partition_healing_and_convergence_drill():
    results = GeoPartitionDrillSimulator.run_partition_and_healing_drill()
    assert results["status"] == "PASS"
    assert results["normal_counter_converged"] is True
    assert results["majority_can_write"] is True
    assert results["minority_fenced"] is True
    assert results["lease_fencing_enforced"] is True
    assert results["post_healing_converged"] is True
    assert results["applied_deltas_count"] >= 1
