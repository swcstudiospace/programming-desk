"""Tests for Autonomous Swarm Self-Balancing & Work Distribution Mesh (Milestone v2.8 - Phase 22).

Covers:
- REQ-SWARM-001: Real-time seat concurrency and workload telemetry tracking across active seats.
- REQ-SWARM-002: Dynamic task re-queuing and backpressure spillover handler redirecting task assignments.
- REQ-SWARM-003: Priority preemption engine ensuring critical-path leadership tasks bypass queuing delays.
- REQ-SWARM-004: Latency-aware and capacity-weighted seat selection across local and federated desks.
- REQ-SWARM-005: Automated worker health circuit breaker triggering fail-fast fallback routing.
- HTTP Gateway API routes in server.py.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.swarm_balancer import (
    CircuitState,
    SeatLoadStatus,
    SwarmSeatLoadBalancer,
    SwarmTaskAssignment,
    TaskPriority,
)


@pytest.fixture
def balancer() -> SwarmSeatLoadBalancer:
    return SwarmSeatLoadBalancer(failure_threshold=3)


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_swarm_telemetry_tracking(balancer: SwarmSeatLoadBalancer):
    """REQ-SWARM-001: Telemetry and load status tracking across active seats."""
    status = balancer.record_telemetry(seat_id="lead", active_jobs=2, latency_ms=15.0, queue_depth=1)
    assert status.seat_id == "lead"
    assert status.active_jobs == 2
    assert status.latency_ms == 15.0
    assert status.queue_depth == 1
    assert status.is_available is True

    snap = balancer.get_status()
    assert "lead" in snap["seats"]
    assert snap["seats"]["lead"]["active_jobs"] == 2
    assert snap["seats"]["lead"]["capacity_score"] > 0


def test_swarm_capacity_weighted_selection(balancer: SwarmSeatLoadBalancer):
    """REQ-SWARM-004: Latency-aware and capacity-weighted seat selection."""
    balancer.record_telemetry(seat_id="lead", active_jobs=4, latency_ms=100.0)
    balancer.record_telemetry(seat_id="systems", active_jobs=1, latency_ms=5.0)
    balancer.record_telemetry(seat_id="web", active_jobs=2, latency_ms=50.0)

    # systems has 4 available slots and lowest latency (5ms), should have highest capacity score
    best = balancer.select_best_seat(["lead", "systems", "web"])
    assert best == "systems"


def test_swarm_backpressure_spillover(balancer: SwarmSeatLoadBalancer):
    """REQ-SWARM-002: Dynamic task re-queuing and backpressure spillover handler."""
    # Saturate lead seat
    balancer.record_telemetry(seat_id="lead", active_jobs=5, max_concurrency=5)
    balancer.record_telemetry(seat_id="systems", active_jobs=1, max_concurrency=5)

    task = SwarmTaskAssignment(
        task_id="task-101",
        target_seat="lead",
        fallback_seats=["systems"],
        priority=TaskPriority.NORMAL,
    )

    res = balancer.dispatch_task(task)
    assert res["ok"] is True
    assert res["action"] == "spillover_redirect"
    assert res["assigned_seat"] == "systems"
    assert res["original_target"] == "lead"

    # Now saturate both lead and systems
    balancer.record_telemetry(seat_id="systems", active_jobs=5, max_concurrency=5)
    task2 = SwarmTaskAssignment(
        task_id="task-102",
        target_seat="lead",
        fallback_seats=["systems"],
        priority=TaskPriority.NORMAL,
    )
    res2 = balancer.dispatch_task(task2)
    assert res2["ok"] is True
    assert res2["action"] == "backpressure_queued"
    assert res2["assigned_seat"] is None
    assert len(balancer.spillover_queue) == 1

    # Draining spillover queue upon task completion
    balancer.complete_task("systems")
    # Systems active_jobs freed 1, but immediately accepted task2 from spillover
    assert len(balancer.spillover_queue) == 0


def test_swarm_priority_preemption(balancer: SwarmSeatLoadBalancer):
    """REQ-SWARM-003: Priority preemption engine ensuring critical-path leadership tasks bypass queuing delays."""
    balancer.record_telemetry(seat_id="lead", active_jobs=5, max_concurrency=5)

    critical_task = SwarmTaskAssignment(
        task_id="crit-task-99",
        target_seat="lead",
        priority=TaskPriority.CRITICAL,
    )

    res = balancer.dispatch_task(critical_task)
    assert res["ok"] is True
    assert res["action"] == "preempted_immediate"
    assert res["assigned_seat"] == "lead"
    assert res["active_jobs"] == 6


def test_swarm_circuit_breaker(balancer: SwarmSeatLoadBalancer):
    """REQ-SWARM-005: Automated worker health circuit breaker triggering fail-fast fallback routing."""
    balancer.record_telemetry(seat_id="infra", active_jobs=0, max_concurrency=5)
    balancer.record_telemetry(seat_id="systems", active_jobs=0, max_concurrency=5)

    # Failures
    balancer.record_failure("infra")
    assert balancer.seats["infra"].circuit_state == CircuitState.DEGRADED

    balancer.record_failure("infra")
    balancer.record_failure("infra")
    assert balancer.seats["infra"].circuit_state == CircuitState.OPEN
    assert balancer.seats["infra"].is_available is False

    # Dispatch to tripped seat routes immediately to fallback
    task = SwarmTaskAssignment(
        task_id="task-infra-01",
        target_seat="infra",
        fallback_seats=["systems"],
    )
    res = balancer.dispatch_task(task)
    assert res["ok"] is True
    assert res["action"] == "circuit_breaker_fallback"
    assert res["assigned_seat"] == "systems"

    # Reset breaker
    assert balancer.reset_breaker("infra") is True
    assert balancer.seats["infra"].circuit_state == CircuitState.CLOSED


def test_swarm_gateway_endpoints(client: TestClient):
    """Integration test verifying Starlette endpoints in server.py."""
    # 1. Update telemetry
    r = client.post("/v1/swarm/telemetry", json={
        "seat_id": "web",
        "active_jobs": 2,
        "latency_ms": 12.5,
        "max_concurrency": 4,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["seat_id"] == "web"
    assert data["active_jobs"] == 2

    # 2. Dispatch task
    r_disp = client.post("/v1/swarm/dispatch", json={
        "task_id": "task-test-http-1",
        "target_seat": "web",
        "priority": "high",
    })
    assert r_disp.status_code == 200
    disp_data = r_disp.json()
    assert disp_data["ok"] is True
    assert disp_data["assigned_seat"] == "web"

    # 3. Status inspection
    r_stat = client.get("/v1/swarm/status")
    assert r_stat.status_code == 200
    stat_data = r_stat.json()
    assert stat_data["ok"] is True
    assert "web" in stat_data["seats"]
    assert stat_data["seats"]["web"]["active_jobs"] == 3

    # 4. Record failure and reset
    r_fail = client.post("/v1/swarm/failure", json={"seat_id": "web"})
    assert r_fail.status_code == 200

    r_reset = client.post("/v1/swarm/reset-breaker", json={"seat_id": "web"})
    assert r_reset.status_code == 200
    assert r_reset.json()["reset"] is True
