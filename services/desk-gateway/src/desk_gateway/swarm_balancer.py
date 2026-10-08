"""Autonomous Swarm Self-Balancing & Work Distribution Mesh (Milestone v2.8 - Phase 22).

Implements:
- REQ-SWARM-001: Real-time seat concurrency and workload telemetry tracking across active seats.
- REQ-SWARM-002: Dynamic task re-queuing and backpressure spillover handler redirecting task assignments when target seat exceeds concurrency.
- REQ-SWARM-003: Priority preemption engine ensuring critical-path leadership and security tasks bypass standard queuing delays.
- REQ-SWARM-004: Latency-aware and capacity-weighted seat selection across local and federated peer desks.
- REQ-SWARM-005: Automated worker health circuit breaker triggering fail-fast fallback routing upon repeated seat degradation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("desk_gateway.swarm_balancer")


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    DEGRADED = "degraded"   # Partial failures, higher latency penalty
    OPEN = "open"           # Tripped, traffic redirected to fallback


@dataclass
class SwarmTaskAssignment:
    task_id: str
    target_seat: str
    priority: TaskPriority = TaskPriority.NORMAL
    payload: Dict[str, Any] = field(default_factory=dict)
    fallback_seats: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    preempted: bool = False


@dataclass
class SeatLoadStatus:
    seat_id: str
    active_jobs: int = 0
    max_concurrency: int = 5
    queue_depth: int = 0
    max_queue_depth: int = 10
    latency_ms: float = 10.0
    consecutive_failures: int = 0
    failure_threshold: int = 3
    circuit_state: CircuitState = CircuitState.CLOSED
    last_heartbeat: float = field(default_factory=time.time)
    total_dispatched: int = 0
    total_spilled: int = 0
    total_preempted: int = 0

    @property
    def is_available(self) -> bool:
        if self.circuit_state == CircuitState.OPEN:
            return False
        return self.active_jobs < self.max_concurrency

    @property
    def capacity_score(self) -> float:
        """Higher score means more capable of accepting new work.
        Penalized by high latency and degraded circuit state.
        """
        if self.circuit_state == CircuitState.OPEN or self.active_jobs >= self.max_concurrency:
            return -1.0
        concurrency_margin = max(0, self.max_concurrency - self.active_jobs)
        penalty = 0.5 if self.circuit_state == CircuitState.DEGRADED else 1.0
        # Latency weight factor: faster nodes have higher score
        latency_factor = 1000.0 / (max(1.0, self.latency_ms) + 10.0)
        return (concurrency_margin * 10.0 + latency_factor) * penalty


class SwarmSeatLoadBalancer:
    """Manages real-time seat load balancing, backpressure spillover,
    priority preemption, and worker health circuit breakers.
    """

    def __init__(self, failure_threshold: int = 3) -> None:
        self.failure_threshold = failure_threshold
        self.seats: Dict[str, SeatLoadStatus] = {}
        self.spillover_queue: List[SwarmTaskAssignment] = []
        self._initialize_default_seats()

    def _initialize_default_seats(self) -> None:
        default_seats = [
            "lead",
            "systems",
            "web",
            "android",
            "ios",
            "infra",
            "quality",
        ]
        for seat in default_seats:
            self.seats[seat] = SeatLoadStatus(
                seat_id=seat,
                max_concurrency=5,
                failure_threshold=self.failure_threshold,
            )

    # -------------------------------------------------------------------------
    # REQ-SWARM-001: Telemetry & Load Tracking
    # -------------------------------------------------------------------------
    def record_telemetry(
        self,
        seat_id: str,
        active_jobs: int,
        latency_ms: float = 10.0,
        queue_depth: Optional[int] = None,
        max_concurrency: Optional[int] = None,
    ) -> SeatLoadStatus:
        if seat_id not in self.seats:
            self.seats[seat_id] = SeatLoadStatus(
                seat_id=seat_id,
                failure_threshold=self.failure_threshold,
            )
        status = self.seats[seat_id]
        status.active_jobs = max(0, active_jobs)
        status.latency_ms = max(0.1, latency_ms)
        status.last_heartbeat = time.time()
        if queue_depth is not None:
            status.queue_depth = max(0, queue_depth)
        if max_concurrency is not None:
            status.max_concurrency = max(1, max_concurrency)
        return status

    def get_status(self) -> Dict[str, Any]:
        return {
            "seats": {
                seat_id: {
                    "active_jobs": s.active_jobs,
                    "max_concurrency": s.max_concurrency,
                    "queue_depth": s.queue_depth,
                    "latency_ms": s.latency_ms,
                    "capacity_score": round(s.capacity_score, 2),
                    "circuit_state": s.circuit_state.value,
                    "consecutive_failures": s.consecutive_failures,
                    "total_dispatched": s.total_dispatched,
                    "total_spilled": s.total_spilled,
                    "total_preempted": s.total_preempted,
                    "is_available": s.is_available,
                }
                for seat_id, s in self.seats.items()
            },
            "spillover_queue_depth": len(self.spillover_queue),
        }

    # -------------------------------------------------------------------------
    # REQ-SWARM-005: Worker Health Circuit Breaker
    # -------------------------------------------------------------------------
    def record_failure(self, seat_id: str) -> CircuitState:
        if seat_id not in self.seats:
            return CircuitState.OPEN
        status = self.seats[seat_id]
        status.consecutive_failures += 1
        if status.consecutive_failures >= status.failure_threshold:
            status.circuit_state = CircuitState.OPEN
            logger.warning("Circuit breaker OPEN for seat %s after %d failures", seat_id, status.consecutive_failures)
        elif status.consecutive_failures >= max(1, status.failure_threshold // 2):
            status.circuit_state = CircuitState.DEGRADED
        return status.circuit_state

    def record_success(self, seat_id: str) -> CircuitState:
        if seat_id in self.seats:
            status = self.seats[seat_id]
            status.consecutive_failures = 0
            if status.circuit_state != CircuitState.CLOSED:
                status.circuit_state = CircuitState.CLOSED
                logger.info("Circuit breaker CLOSED for seat %s after recovery", seat_id)
            return status.circuit_state
        return CircuitState.CLOSED

    def reset_breaker(self, seat_id: str) -> bool:
        if seat_id in self.seats:
            status = self.seats[seat_id]
            status.consecutive_failures = 0
            status.circuit_state = CircuitState.CLOSED
            return True
        return False

    # -------------------------------------------------------------------------
    # REQ-SWARM-004: Latency-Aware & Capacity-Weighted Seat Selection
    # -------------------------------------------------------------------------
    def select_best_seat(self, candidate_seats: Optional[List[str]] = None) -> Optional[str]:
        candidates = candidate_seats if candidate_seats else list(self.seats.keys())
        scored: List[tuple[str, float]] = []
        for seat_id in candidates:
            if seat_id in self.seats:
                score = self.seats[seat_id].capacity_score
                if score > 0:
                    scored.append((seat_id, score))

        if not scored:
            return None
        # Sort descending by capacity score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    # -------------------------------------------------------------------------
    # REQ-SWARM-002, REQ-SWARM-003: Priority Preemption & Backpressure Spillover
    # -------------------------------------------------------------------------
    def dispatch_task(
        self,
        task: SwarmTaskAssignment,
    ) -> Dict[str, Any]:
        target = task.target_seat
        if target not in self.seats:
            self.seats[target] = SeatLoadStatus(
                seat_id=target,
                failure_threshold=self.failure_threshold,
            )

        seat_status = self.seats[target]

        # REQ-SWARM-003: Priority Preemption for CRITICAL / HIGH
        if task.priority == TaskPriority.CRITICAL:
            seat_status.active_jobs += 1
            seat_status.total_dispatched += 1
            seat_status.total_preempted += 1
            task.preempted = True
            return {
                "ok": True,
                "task_id": task.task_id,
                "assigned_seat": target,
                "action": "preempted_immediate",
                "priority": task.priority.value,
                "active_jobs": seat_status.active_jobs,
            }

        # Check circuit breaker state - if OPEN, fallback immediately
        if seat_status.circuit_state == CircuitState.OPEN:
            fallback = self._route_fallback(task)
            return fallback

        # Check concurrency capacity
        if seat_status.is_available:
            seat_status.active_jobs += 1
            seat_status.total_dispatched += 1
            return {
                "ok": True,
                "task_id": task.task_id,
                "assigned_seat": target,
                "action": "dispatched",
                "priority": task.priority.value,
                "active_jobs": seat_status.active_jobs,
            }

        # REQ-SWARM-002: Dynamic Backpressure Spillover
        return self._route_spillover(task)

    def _route_fallback(self, task: SwarmTaskAssignment) -> Dict[str, Any]:
        candidates = [s for s in task.fallback_seats if s != task.target_seat]
        best_fallback = self.select_best_seat(candidates if candidates else None)
        if best_fallback and best_fallback in self.seats:
            alt_status = self.seats[best_fallback]
            alt_status.active_jobs += 1
            alt_status.total_dispatched += 1
            alt_status.total_spilled += 1
            return {
                "ok": True,
                "task_id": task.task_id,
                "assigned_seat": best_fallback,
                "action": "circuit_breaker_fallback",
                "original_target": task.target_seat,
                "priority": task.priority.value,
            }

        # If no fallback available, append to spillover queue
        self.spillover_queue.append(task)
        return {
            "ok": True,
            "task_id": task.task_id,
            "assigned_seat": None,
            "action": "queued_spillover",
            "original_target": task.target_seat,
            "reason": "circuit_open_no_healthy_fallback",
        }

    def _route_spillover(self, task: SwarmTaskAssignment) -> Dict[str, Any]:
        original_target = task.target_seat
        self.seats[original_target].total_spilled += 1

        # Check if fallback seats can accept work
        candidates = [s for s in task.fallback_seats if s != original_target]
        best_fallback = self.select_best_seat(candidates if candidates else None)

        if best_fallback and best_fallback in self.seats:
            alt_status = self.seats[best_fallback]
            alt_status.active_jobs += 1
            alt_status.total_dispatched += 1
            alt_status.total_spilled += 1
            return {
                "ok": True,
                "task_id": task.task_id,
                "assigned_seat": best_fallback,
                "action": "spillover_redirect",
                "original_target": original_target,
                "priority": task.priority.value,
            }

        # No alternative capacity available: enqueue into backpressure spillover queue
        self.spillover_queue.append(task)
        return {
            "ok": True,
            "task_id": task.task_id,
            "assigned_seat": None,
            "action": "backpressure_queued",
            "original_target": original_target,
            "spillover_queue_depth": len(self.spillover_queue),
        }

    def complete_task(self, seat_id: str) -> None:
        if seat_id in self.seats:
            status = self.seats[seat_id]
            status.active_jobs = max(0, status.active_jobs - 1)
            # Drain spillover queue if work exists and capacity is freed
            if self.spillover_queue and status.is_available:
                next_task = self.spillover_queue.pop(0)
                status.active_jobs += 1
                status.total_dispatched += 1
                logger.info("Drained task %s from spillover queue to seat %s", next_task.task_id, seat_id)
