"""Tests for Autonomous Workload Rebalancing, DLQ Replay Orchestrator, and Resilience Verification Suite (REQ-CHAOS-003, REQ-CHAOS-004, REQ-CHAOS-005).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from desk_gateway.chaos import ChaosHarness
from desk_gateway.config import SEATS, Settings
from desk_gateway.dlq_replay import DLQReplayOrchestrator, ReplayResult
from desk_gateway.resilience import ResilienceVerifier
from desk_gateway.server import build_app
from desk_gateway.store import Store
from desk_gateway.supervisor import (
    SeatHealthStatus,
    SeatRuntimeProfile,
    SelfHealingSupervisor,
)
from desk_gateway.workload import WorkloadRebalancer
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for WorkloadRebalancer (REQ-CHAOS-003)
# ---------------------------------------------------------------------------


def test_workload_rebalancer_peer_selection():
    supervisor = SelfHealingSupervisor()
    rebalancer = WorkloadRebalancer(supervisor=supervisor)

    # By default, all seats are healthy. For failed 'systems', first choice is 'infra'
    target = rebalancer.find_healthy_peer("systems")
    assert target == "infra"

    # Degrade infra -> supervisor marks failing
    for _ in range(3):
        supervisor.record_seat_activity("infra", success=False, error_detail="fault")
    prof = supervisor.get_profile("infra")
    # Hot reconstitution restored it, but let's artificially set status to CORRUPTED
    prof.status = SeatHealthStatus.CORRUPTED

    # Now peer candidate falls back to 'lead'
    target2 = rebalancer.find_healthy_peer("systems")
    assert target2 == "lead"


def test_workload_rebalancer_task_graph_redistribution():
    rebalancer = WorkloadRebalancer(local_region_id="us-east")

    graph = {
        "graph_id": "graph-test-01",
        "vector_clock": {"us-east": 1},
        "nodes": {
            "t-1": {
                "node_id": "t-1",
                "title": "Migrate DB schema",
                "assignee": "systems",
                "status": "in_progress",
                "version": 1,
                "updated_at": time.time(),
                "data": {},
            },
            "t-2": {
                "node_id": "t-2",
                "title": "Write API docs",
                "assignee": "systems",
                "status": "done",  # already completed, should NOT rebalance
                "version": 1,
                "updated_at": time.time(),
                "data": {},
            },
        },
    }

    updated_graph, reassigned = rebalancer.rebalance_graph(graph, failed_seat="systems", target_seat="infra")
    assert len(reassigned) == 1
    assert reassigned[0]["node_id"] == "t-1"
    assert reassigned[0]["from_seat"] == "systems"
    assert reassigned[0]["to_seat"] == "infra"

    # Check updated graph
    nodes = updated_graph["nodes"]
    assert nodes["t-1"]["assignee"] == "infra"
    assert nodes["t-1"]["data"]["rebalanced_from"] == "systems"
    assert nodes["t-2"]["assignee"] == "systems"  # Remains unchanged
    assert updated_graph["vector_clock"]["us-east"] >= 2


# ---------------------------------------------------------------------------
# Unit tests for DLQReplayOrchestrator (REQ-CHAOS-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dlq_replay_exponential_backoff_and_jitter():
    orchestrator = DLQReplayOrchestrator(
        max_attempts=3,
        base_backoff_sec=0.02,
        max_backoff_sec=0.2,
    )

    attempts_seen = 0

    async def transient_handler(item: dict[str, Any]) -> None:
        nonlocal attempts_seen
        attempts_seen += 1
        if attempts_seen < 2:
            raise ConnectionError("Temporary upstream timeout")
        # Succeeds on attempt 2

    test_item = {"id": "dlq-item-1", "title": "Deploy update"}
    res = await orchestrator.replay_item(test_item, transient_handler)

    assert res.success is True
    assert res.attempts == 2
    assert res.quarantined is False


@pytest.mark.asyncio
async def test_dlq_replay_poison_pill_quarantine():
    orchestrator = DLQReplayOrchestrator(max_attempts=3, base_backoff_sec=0.01)

    async def failing_handler(item: dict[str, Any]) -> None:
        raise ValueError("Poison pill malformed syntax")

    poison_item = {"id": "poison-999", "corrupted": True}
    res = await orchestrator.replay_item(poison_item, failing_handler)

    assert res.success is False
    assert res.attempts == 3
    assert res.quarantined is True
    assert "Poison pill malformed syntax" in (res.error or "")

    quarantined = orchestrator.get_quarantined_items()
    assert len(quarantined) == 1
    assert quarantined[0]["item"]["id"] == "poison-999"


# ---------------------------------------------------------------------------
# Unit tests for ResilienceVerifier (REQ-CHAOS-005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resilience_verifier_rto_rpo_compliance():
    verifier = ResilienceVerifier()

    # Run seat failure benchmark
    drill_seat = await verifier.run_seat_failure_recovery_drill(target_seat="lead")
    assert drill_seat.passed is True
    assert drill_seat.rto_sla_met is True
    assert drill_seat.rto_seconds < 3.0  # RTO SLA < 3.0s
    assert drill_seat.rpo_sla_met is True
    assert drill_seat.rpo_lost_items == 0  # RPO SLA = 0

    # Run workload rebalance benchmark
    drill_rebalance = await verifier.run_workload_rebalance_drill(failed_seat="systems")
    assert drill_rebalance.passed is True
    assert drill_rebalance.rto_sla_met is True
    assert drill_rebalance.rto_seconds < 1.0  # < 3.0s
    assert drill_rebalance.rpo_sla_met is True
    assert drill_rebalance.rpo_lost_items == 0

    summary = verifier.get_summary()
    assert summary["all_slas_met"] is True
    assert summary["drills_total"] == 2
    assert summary["drills_passed"] == 2


# ---------------------------------------------------------------------------
# Integration tests for Rebalance, DLQ & Resilience REST Endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workload_dlq_and_resilience_endpoints(tmp_path: Path):
    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        intake_tokens={"github": INTAKE_TOKEN},
    )
    app, _ = build_app(settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Trigger workload rebalance via POST /v1/workload/rebalance
        res = await client.post(
            "/v1/workload/rebalance",
            json={"failed_seat": "systems", "target_seat": "infra"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["failed_seat"] == "systems"
        assert data["target_seat"] == "infra"

        # 2. Trigger DLQ replay via POST /v1/dlq/replay
        res = await client.post("/v1/dlq/replay")
        assert res.status_code == 200
        dlq_data = res.json()
        assert dlq_data["ok"] is True
        assert "replayed_count" in dlq_data

        # 3. Trigger Resilience Verification Drill via GET /v1/resilience/verify
        res = await client.get("/v1/resilience/verify")
        assert res.status_code == 200
        resil_data = res.json()
        assert resil_data["ok"] is True
        assert resil_data["summary"]["all_slas_met"] is True
        assert resil_data["summary"]["rto_sla_seconds"] == 3.0
        assert resil_data["summary"]["rpo_sla_lost_items"] == 0
        assert len(resil_data["drills"]) == 2
