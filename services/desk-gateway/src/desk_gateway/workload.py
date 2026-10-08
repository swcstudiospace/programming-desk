"""Autonomous task graph rebalancing algorithm dynamically redistributing unacknowledged seat workloads (REQ-CHAOS-003).

When a seat crashes, becomes unresponsive, or is quarantined by the self-healing supervisor:
- Identifies unacknowledged / in_progress task nodes assigned to the unresponsive seat.
- Evaluates healthy peer seat candidates matching capability matrix.
- Reassigns workloads and advances vector clocks with reassignment audit logs.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Any

from desk_gateway.config import SEATS
from desk_gateway.supervisor import SeatHealthStatus, SelfHealingSupervisor
from desk_gateway.vector_clock import VectorClockGraph

logger = logging.getLogger("desk_gateway.workload")

# Fallback capability mapping if a target seat is unresponsive
SEAT_FAILOVER_CAPABILITIES: dict[str, list[str]] = {
    "lead": ["systems", "infra", "quality"],
    "systems": ["infra", "lead", "quality"],
    "infra": ["systems", "lead", "quality"],
    "web": ["android", "ios", "systems"],
    "android": ["ios", "web", "systems"],
    "ios": ["android", "web", "systems"],
    "quality": ["systems", "infra", "lead"],
}


class WorkloadRebalancer:
    """Dynamically redistributes pending task graph workloads from impaired seats (REQ-CHAOS-003)."""

    def __init__(
        self,
        supervisor: SelfHealingSupervisor | None = None,
        store: Any = None,
        local_region_id: str = "us-east",
    ) -> None:
        self.supervisor = supervisor
        self.store = store
        self.local_region_id = local_region_id
        self._lock = threading.RLock()
        self._rebalance_history: list[dict[str, Any]] = []

    def find_healthy_peer(self, failed_seat: str) -> str | None:
        """Find the best healthy candidate seat capable of taking over the workload."""
        candidates = SEAT_FAILOVER_CAPABILITIES.get(failed_seat, [])

        if not self.supervisor:
            # Default to first candidate
            return candidates[0] if candidates else None

        for candidate in candidates:
            profile = self.supervisor.get_profile(candidate)
            if profile and profile.status == SeatHealthStatus.HEALTHY:
                return candidate

        # Fallback to any healthy seat
        for s in SEATS:
            if s != failed_seat:
                prof = self.supervisor.get_profile(s)
                if prof and prof.status == SeatHealthStatus.HEALTHY:
                    return s

        return None

    def rebalance_graph(
        self,
        graph_dict: dict[str, Any],
        failed_seat: str,
        target_seat: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Reassign pending tasks in graph_dict from failed_seat to healthy target_seat.

        Returns updated graph_dict and list of reassigned task summaries.
        """
        with self._lock:
            vc_graph = VectorClockGraph.from_dict(graph_dict, local_region_id=self.local_region_id)
            reassigned = []

            destination_seat = target_seat or self.find_healthy_peer(failed_seat)
            if not destination_seat:
                logger.warning("No healthy peer seat found to absorb workload of '%s'", failed_seat)
                return graph_dict, []

            for node_id, node in list(vc_graph.nodes.items()):
                # Reassign if assigned to failed_seat and task is not finished
                if node.assignee == failed_seat and node.status in ("open", "in_progress", "claimed"):
                    old_actor = node.assignee
                    node.assignee = destination_seat
                    node.data["rebalanced_from"] = old_actor
                    node.data["rebalanced_at"] = time.time()
                    node.data["rebalance_reason"] = f"Seat '{old_actor}' crashed or quarantined"

                    vc_graph.vector_clock[self.local_region_id] = vc_graph.vector_clock.get(self.local_region_id, 0) + 1
                    node.version += 1
                    node.updated_at = time.time()

                    summary = {
                        "node_id": node_id,
                        "title": node.title,
                        "from_seat": old_actor,
                        "to_seat": destination_seat,
                        "status": node.status,
                    }
                    reassigned.append(summary)
                    logger.info("WORKLOAD REBALANCED: Task '%s' reassigned %s -> %s", node_id, old_actor, destination_seat)

            updated_dict = vc_graph.to_dict()
            if reassigned:
                rec = {
                    "timestamp": time.time(),
                    "failed_seat": failed_seat,
                    "target_seat": destination_seat,
                    "tasks_count": len(reassigned),
                    "tasks": reassigned,
                }
                self._rebalance_history.append(rec)

            return updated_dict, reassigned

    def rebalance_all_stored_graphs(self, failed_seat: str, target_seat: str | None = None) -> list[dict[str, Any]]:
        """Scan all stored task graphs and redistribute workloads from failed_seat."""
        if not self.store:
            return []

        all_reassigned: list[dict[str, Any]] = []
        with self._lock:
            stored_graphs = self.store.task_graphs()
            modified = False

            for gid, gdict in stored_graphs.items():
                updated_graph, reassigned = self.rebalance_graph(gdict, failed_seat, target_seat)
                if reassigned:
                    stored_graphs[gid] = updated_graph
                    all_reassigned.extend(reassigned)
                    modified = True

            if modified:
                self.store._write("task_graphs", stored_graphs)

        return all_reassigned

    def get_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rebalance_history)
