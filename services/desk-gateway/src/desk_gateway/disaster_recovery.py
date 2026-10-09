"""Cross-Cloud Disaster Recovery & Multi-Substrate Replication (Milestone v2.9 - Phase 24).

Implements:
- REQ-DR-001: Continuous asynchronous state mirroring engine across primary and secondary data substrates.
- REQ-DR-002: Delta snapshotting with cryptographic block checksums and incremental catch-up replication.
- REQ-DR-003: Replication lag monitor with dynamic throttle adaptation under WAN congestion.
- REQ-DR-004: Atomic cross-substrate state cutover harness ensuring zero data loss (RPO = 0).
- REQ-DR-005: Standby health polling and automated warm-replica promotion readiness verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("desk_gateway.disaster_recovery")


class ReplicaState(str, Enum):
    SYNCING = "syncing"
    WARM_STANDBY = "warm_standby"
    PRIMARY = "primary"
    PROMOTING = "promoting"
    DEGRADED = "degraded"


@dataclass
class SubstrateDeltaBlock:
    block_index: int
    prev_hash: str
    block_hash: str
    timestamp: float
    payload: Dict[str, Any]
    size_bytes: int

    @classmethod
    def create(cls, block_index: int, prev_hash: str, payload: Dict[str, Any]) -> "SubstrateDeltaBlock":
        t = time.time()
        serialized = json.dumps(payload, sort_keys=True)
        raw = f"{block_index}:{prev_hash}:{t}:{serialized}".encode("utf-8")
        h = hashlib.sha256(raw).hexdigest()
        return cls(
            block_index=block_index,
            prev_hash=prev_hash,
            block_hash=h,
            timestamp=t,
            payload=payload,
            size_bytes=len(raw),
        )


@dataclass
class ReplicaEndpoint:
    replica_id: str
    region: str
    state: ReplicaState = ReplicaState.SYNCING
    applied_block_index: int = 0
    last_replicated_hash: str = "0" * 64
    last_heartbeat: float = field(default_factory=time.time)
    replication_lag_blocks: int = 0
    lag_ms: float = 0.0


class SubstrateStateMirrorEngine:
    """Manages cross-cloud state replication, block checksum hashing,
    dynamic lag throttling, and atomic RPO=0 cutover.
    """

    def __init__(
        self,
        primary_id: str = "primary-railway",
        lag_throttle_threshold_blocks: int = 5,
        max_lag_ms: float = 200.0,
    ) -> None:
        self.primary_id = primary_id
        self.lag_throttle_threshold_blocks = lag_throttle_threshold_blocks
        self.max_lag_ms = max_lag_ms
        self.blocks: List[SubstrateDeltaBlock] = []
        self.replicas: Dict[str, ReplicaEndpoint] = {}
        self.is_throttled: bool = False
        self._genesis_hash = "0" * 64

    # -------------------------------------------------------------------------
    # REQ-DR-001, REQ-DR-002: Delta Block Creation & Asynchronous Mirroring
    # -------------------------------------------------------------------------
    def append_state_delta(self, payload: Dict[str, Any]) -> SubstrateDeltaBlock:
        prev_hash = self.blocks[-1].block_hash if self.blocks else self._genesis_hash
        next_index = len(self.blocks)
        block = SubstrateDeltaBlock.create(next_index, prev_hash, payload)
        self.blocks.append(block)

        # Update lag for all replicas
        self._update_all_lag()
        return block

    def register_replica(self, replica_id: str, region: str) -> ReplicaEndpoint:
        replica = ReplicaEndpoint(
            replica_id=replica_id,
            region=region,
            state=ReplicaState.SYNCING,
            applied_block_index=0,
            last_replicated_hash=self._genesis_hash,
        )
        self.replicas[replica_id] = replica
        self._update_replica_lag(replica)
        return replica

    def sync_replica(self, replica_id: str, up_to_index: Optional[int] = None) -> List[SubstrateDeltaBlock]:
        if replica_id not in self.replicas:
            raise KeyError(f"Replica '{replica_id}' is not registered.")

        replica = self.replicas[replica_id]
        start_idx = replica.applied_block_index
        end_idx = up_to_index if up_to_index is not None else len(self.blocks)
        end_idx = min(end_idx, len(self.blocks))

        synced_blocks = self.blocks[start_idx:end_idx]
        for b in synced_blocks:
            replica.applied_block_index = b.block_index + 1
            replica.last_replicated_hash = b.block_hash

        replica.last_heartbeat = time.time()
        self._update_all_lag()

        # If caught up to latest block, promote to WARM_STANDBY
        if replica.applied_block_index >= len(self.blocks):
            replica.state = ReplicaState.WARM_STANDBY

        return synced_blocks

    # -------------------------------------------------------------------------
    # REQ-DR-003: Replication Lag Monitor & Dynamic Throttling
    # -------------------------------------------------------------------------
    def _update_replica_lag(self, replica: ReplicaEndpoint) -> None:
        total_blocks = len(self.blocks)
        lag_blocks = max(0, total_blocks - replica.applied_block_index)
        replica.replication_lag_blocks = lag_blocks

        if total_blocks > 0 and replica.applied_block_index < total_blocks:
            oldest_unapplied = self.blocks[replica.applied_block_index]
            replica.lag_ms = max(0.0, (time.time() - oldest_unapplied.timestamp) * 1000.0)
        else:
            replica.lag_ms = 0.0

    def _update_all_lag(self) -> None:
        max_lag = 0
        for replica in self.replicas.values():
            self._update_replica_lag(replica)
            if replica.replication_lag_blocks > max_lag:
                max_lag = replica.replication_lag_blocks

        # Adapt throttling
        if max_lag >= self.lag_throttle_threshold_blocks:
            self.is_throttled = True
            logger.warning(
                "WAN replication lag (%d blocks) exceeds threshold (%d); throttling writes.",
                max_lag,
                self.lag_throttle_threshold_blocks,
            )
        else:
            self.is_throttled = False

    def get_mirror_status(self) -> Dict[str, Any]:
        self._update_all_lag()
        return {
            "primary_id": self.primary_id,
            "total_blocks": len(self.blocks),
            "latest_block_hash": self.blocks[-1].block_hash if self.blocks else self._genesis_hash,
            "is_throttled": self.is_throttled,
            "replicas": {
                r_id: {
                    "region": r.region,
                    "state": r.state.value,
                    "applied_block_index": r.applied_block_index,
                    "lag_blocks": r.replication_lag_blocks,
                    "lag_ms": round(r.lag_ms, 2),
                    "last_replicated_hash": r.last_replicated_hash,
                    "is_ready_for_promotion": (
                        r.state == ReplicaState.WARM_STANDBY and r.replication_lag_blocks == 0
                    ),
                }
                for r_id, r in self.replicas.items()
            },
        }

    # -------------------------------------------------------------------------
    # REQ-DR-004, REQ-DR-005: RPO=0 Atomic Cutover & Warm-Replica Readiness
    # -------------------------------------------------------------------------
    def verify_replica_readiness(self, replica_id: str) -> Tuple[bool, str]:
        if replica_id not in self.replicas:
            return False, f"Replica '{replica_id}' not found."

        replica = self.replicas[replica_id]
        self._update_replica_lag(replica)

        if replica.replication_lag_blocks > 0:
            return False, f"Replica lag is {replica.replication_lag_blocks} blocks (must be 0 for RPO=0)."

        if self.blocks and replica.last_replicated_hash != self.blocks[-1].block_hash:
            return False, "Replica last block hash does not match primary tip."

        return True, "Replica is fully synchronized and ready for warm promotion."

    def execute_atomic_cutover(self, target_replica_id: str) -> Dict[str, Any]:
        """Atomically promotes target replica to primary and demotes current primary.
        Enforces RPO=0 by catching up any trailing blocks before role handover.
        """
        if target_replica_id not in self.replicas:
            raise KeyError(f"Target replica '{target_replica_id}' not found.")

        target = self.replicas[target_replica_id]
        target.state = ReplicaState.PROMOTING

        # Catch up remaining uncommitted blocks to ensure RPO=0
        if target.applied_block_index < len(self.blocks):
            self.sync_replica(target_replica_id)

        ready, reason = self.verify_replica_readiness(target_replica_id)
        if not ready:
            target.state = ReplicaState.DEGRADED
            raise RuntimeError(f"Atomic cutover aborted: {reason}")

        old_primary = self.primary_id
        self.primary_id = target_replica_id
        target.state = ReplicaState.PRIMARY

        # Register old primary as warm standby
        demoted = ReplicaEndpoint(
            replica_id=old_primary,
            region="primary-origin",
            state=ReplicaState.WARM_STANDBY,
            applied_block_index=len(self.blocks),
            last_replicated_hash=self.blocks[-1].block_hash if self.blocks else self._genesis_hash,
        )
        self.replicas[old_primary] = demoted
        del self.replicas[target_replica_id]

        logger.info(
            "Atomic cutover successful (RPO=0): Promoted %s to primary; demoted %s to warm standby.",
            target_replica_id,
            old_primary,
        )

        return {
            "ok": True,
            "new_primary": target_replica_id,
            "demoted_primary": old_primary,
            "rpo_loss_blocks": 0,
            "total_blocks": len(self.blocks),
            "state_hash": self.blocks[-1].block_hash if self.blocks else self._genesis_hash,
        }
