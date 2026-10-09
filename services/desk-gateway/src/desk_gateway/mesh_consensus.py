"""Sovereign Mesh Consensus & Cross-Region Quorum Healing.

Implements WAN anti-entropy gossip protocol, split-brain quorum detection,
epoch-fenced coordinator leases, automated partition healing resynchronization,
and end-to-end multi-region partition and healing drill simulators.
"""

from __future__ import annotations

import dataclasses
import hashlib
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from desk_gateway.sharding import (
    CRDTStore,
    ConsistentHashRing,
    GeoReplicationEngine,
    ReplicationDelta,
    ShardNode,
)


@dataclasses.dataclass
class GossipDigest:
    region_id: str
    vector_clock: Dict[str, int]
    known_keys_hash: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "vector_clock": self.vector_clock,
            "known_keys_hash": self.known_keys_hash,
            "timestamp": self.timestamp,
        }


class AntiEntropyGossip:
    """Detects cross-region state divergence via vector clock digests."""

    def __init__(self, region_id: str, store: CRDTStore) -> None:
        self.region_id = region_id
        self.store = store
        self.peer_digests: Dict[str, GossipDigest] = {}

    def generate_digest(self) -> GossipDigest:
        all_keys = sorted(
            list(self.store.lww_store.keys())
            + list(self.store.counter_store.keys())
            + list(self.store.set_store.keys())
        )
        keys_hash = hashlib.sha256(",".join(all_keys).encode("utf-8")).hexdigest()[:16]
        return GossipDigest(
            region_id=self.region_id,
            vector_clock=dict(self.store.vector_clock),
            known_keys_hash=keys_hash,
        )

    def receive_digest(self, digest: GossipDigest) -> Dict[str, Any]:
        self.peer_digests[digest.region_id] = digest
        local_clock = self.store.vector_clock

        divergent_regions = []
        is_behind = False
        is_ahead = False

        for r, remote_seq in digest.vector_clock.items():
            local_seq = local_clock.get(r, 0)
            if local_seq < remote_seq:
                is_behind = True
                divergent_regions.append(r)
            elif local_seq > remote_seq:
                is_ahead = True

        status = "synchronized"
        if is_behind and is_ahead:
            status = "diverged"
        elif is_behind:
            status = "lagging"
        elif is_ahead:
            status = "ahead"

        return {
            "peer_region": digest.region_id,
            "status": status,
            "divergent_regions": divergent_regions,
            "keys_match": digest.known_keys_hash == self.generate_digest().known_keys_hash,
        }


@dataclasses.dataclass
class EpochLease:
    epoch_id: int
    coordinator_node_id: str
    region_id: str
    expires_at: float
    quorum_size: int
    is_valid: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "epoch_id": self.epoch_id,
            "coordinator_node_id": self.coordinator_node_id,
            "region_id": self.region_id,
            "expires_at": self.expires_at,
            "quorum_size": self.quorum_size,
            "is_valid": self.is_valid and time.time() < self.expires_at,
        }


class SplitBrainDetector:
    """Fences partitions and detects split-brain conditions across WAN regions."""

    def __init__(self, local_region: str, total_regions: List[str]) -> None:
        self.local_region = local_region
        self.all_regions = set(total_regions)
        self.active_peers: Set[str] = set(total_regions)
        self.fenced: bool = False

    def update_peer_liveness(self, alive_peers: List[str]) -> bool:
        self.active_peers = set(alive_peers)
        if self.local_region not in self.active_peers:
            self.active_peers.add(self.local_region)

        # Quorum rule: must be able to reach > len(all_regions) // 2
        majority_threshold = (len(self.all_regions) // 2) + 1
        has_quorum = len(self.active_peers) >= majority_threshold
        self.fenced = not has_quorum
        return has_quorum

    def can_write(self) -> bool:
        return not self.fenced


class EpochCoordinator:
    """Issues monotonic epoch leases preventing dual-primary writes during WAN splits."""

    def __init__(self, node_id: str, region_id: str, split_detector: SplitBrainDetector) -> None:
        self.node_id = node_id
        self.region_id = region_id
        self.split_detector = split_detector
        self.current_epoch: int = 1
        self.current_lease: Optional[EpochLease] = None

    def acquire_lease(self, ttl_seconds: float = 30.0) -> Optional[EpochLease]:
        if not self.split_detector.can_write():
            return None

        self.current_epoch += 1
        lease = EpochLease(
            epoch_id=self.current_epoch,
            coordinator_node_id=self.node_id,
            region_id=self.region_id,
            expires_at=time.time() + ttl_seconds,
            quorum_size=len(self.split_detector.active_peers),
            is_valid=True,
        )
        self.current_lease = lease
        return lease

    def validate_lease(self, epoch_id: int) -> bool:
        if not self.split_detector.can_write():
            return False
        if not self.current_lease or self.current_lease.epoch_id != epoch_id:
            return False
        return time.time() < self.current_lease.expires_at


class PartitionHealingOrchestrator:
    """Reconciles state divergence and resynchronizes deltas upon WAN partition recovery."""

    def __init__(
        self,
        store: CRDTStore,
        replicator: GeoReplicationEngine,
        split_detector: SplitBrainDetector,
    ) -> None:
        self.store = store
        self.replicator = replicator
        self.split_detector = split_detector
        self.healing_log: List[Dict[str, Any]] = []

    def reconcile_peer_deltas(
        self,
        peer_deltas: List[ReplicationDelta],
    ) -> Dict[str, Any]:
        applied_count = 0
        rejected_count = 0

        for delta in peer_deltas:
            # Verify cryptographic signature
            if not self.replicator.verify_delta(delta):
                rejected_count += 1
                continue

            success = self.store.apply_delta(delta)
            if success:
                applied_count += 1
            else:
                rejected_count += 1

        record = {
            "timestamp": time.time(),
            "applied_count": applied_count,
            "rejected_count": rejected_count,
            "current_vector_clock": dict(self.store.vector_clock),
        }
        self.healing_log.append(record)
        return record


class GeoPartitionDrillSimulator:
    """Exercises partition isolation, split-brain write fencing, and post-healing convergence."""

    @staticmethod
    def run_partition_and_healing_drill(
        regions: List[str] = None,
    ) -> Dict[str, Any]:
        regions = regions or ["us-east", "us-west", "eu-central"]
        node_east = ShardNode(node_id="desk-node-east", region_id="us-east")
        node_west = ShardNode(node_id="desk-node-west", region_id="us-west")
        node_eu = ShardNode(node_id="desk-node-eu", region_id="eu-central")

        ring = ConsistentHashRing()
        ring.add_node(node_east)
        ring.add_node(node_west)
        ring.add_node(node_eu)

        store_east = CRDTStore("us-east", "desk-node-east")
        store_west = CRDTStore("us-west", "desk-node-west")
        store_eu = CRDTStore("eu-central", "desk-node-eu")

        rep_east = GeoReplicationEngine("us-east", "shared-test-secret")
        rep_west = GeoReplicationEngine("us-west", "shared-test-secret")
        rep_eu = GeoReplicationEngine("eu-central", "shared-test-secret")

        detector_east = SplitBrainDetector("us-east", regions)
        detector_west = SplitBrainDetector("us-west", regions)
        detector_eu = SplitBrainDetector("eu-central", regions)

        coord_east = EpochCoordinator("desk-node-east", "us-east", detector_east)
        coord_eu = EpochCoordinator("desk-node-eu", "eu-central", detector_eu)

        healer_east = PartitionHealingOrchestrator(store_east, rep_east, detector_east)
        healer_west = PartitionHealingOrchestrator(store_west, rep_west, detector_west)
        healer_eu = PartitionHealingOrchestrator(store_eu, rep_eu, detector_eu)

        # 1. Normal state: write counter & LWW
        store_east.update_counter("tasks_completed", delta=5)
        delta1 = rep_east.create_delta("tasks_completed", "pn_counter", store_east.counter_store["tasks_completed"].to_dict(), store_east.vector_clock)
        store_west.apply_delta(delta1)
        store_eu.apply_delta(delta1)

        normal_counter_converged = (
            store_east.read_counter("tasks_completed")
            == store_west.read_counter("tasks_completed")
            == store_eu.read_counter("tasks_completed")
            == 5
        )

        # 2. Simulate Network Partition: eu-central is cut off from us-east and us-west
        # Majority group: [us-east, us-west] (size 2 >= 2)
        detector_east.update_peer_liveness(["us-east", "us-west"])
        detector_west.update_peer_liveness(["us-east", "us-west"])
        # Minority group: [eu-central] (size 1 < 2) -> Fenced
        detector_eu.update_peer_liveness(["eu-central"])

        majority_can_write = detector_east.can_write() and detector_west.can_write()
        minority_fenced = not detector_eu.can_write()

        # Attempt lease acquisition in minority (should fail) and majority (should succeed)
        minority_lease = coord_eu.acquire_lease()
        majority_lease = coord_east.acquire_lease()
        lease_fencing_enforced = (minority_lease is None) and (majority_lease is not None)

        # 3. Concurrent Writes during partition
        # Majority writes counter +3
        store_east.update_counter("tasks_completed", delta=3)
        delta_partition_majority = rep_east.create_delta("tasks_completed", "pn_counter", store_east.counter_store["tasks_completed"].to_dict(), store_east.vector_clock)
        store_west.apply_delta(delta_partition_majority)

        # 4. Partition heals: WAN connectivity restored
        detector_east.update_peer_liveness(regions)
        detector_west.update_peer_liveness(regions)
        detector_eu.update_peer_liveness(regions)

        # Heal & resync eu with missed delta
        reconcile_res = healer_eu.reconcile_peer_deltas([delta_partition_majority])
        post_healing_converged = (
            store_east.read_counter("tasks_completed")
            == store_west.read_counter("tasks_completed")
            == store_eu.read_counter("tasks_completed")
            == 8
        )

        return {
            "status": "PASS" if (normal_counter_converged and majority_can_write and minority_fenced and lease_fencing_enforced and post_healing_converged) else "FAIL",
            "normal_counter_converged": normal_counter_converged,
            "majority_can_write": majority_can_write,
            "minority_fenced": minority_fenced,
            "lease_fencing_enforced": lease_fencing_enforced,
            "post_healing_converged": post_healing_converged,
            "applied_deltas_count": reconcile_res["applied_count"],
        }
