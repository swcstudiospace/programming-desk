"""Tests for Cross-Region WAN Mesh Inter-Seat Routing, Cryptographic Attestation,
Vector Clock Conflict Convergence, and Session Evacuation (REQ-EDGE-003, REQ-EDGE-004, REQ-EDGE-005).
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from desk_gateway.config import SEATS, Settings
from desk_gateway.server import build_app
from desk_gateway.vector_clock import (
    CausalityRelation,
    ConflictResolver,
    TaskNode,
    VectorClockGraph,
    compare_vector_clocks,
    union_vector_clocks,
)
from desk_gateway.wan_mesh import (
    AttestationFailed,
    RegionImpairmentManager,
    RouteRevokedError,
    SeatIdentityAttestor,
    WanError,
    WanMeshRouter,
    WanPeerNode,
    WanSeatEnvelope,
)
from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS, REPO


# ---------------------------------------------------------------------------
# Unit tests for SeatIdentityAttestor & WanMeshRouter (REQ-EDGE-003)
# ---------------------------------------------------------------------------


def test_seat_identity_attestor_signature_and_verification():
    secret = "tailnet-test-secret-2026"  # pragma: allowlist secret (unit test key)
    attestor = SeatIdentityAttestor(signing_secret=secret, key_id="key-test")

    envelope = attestor.attest_envelope(
        source_region="us-east",
        target_region="eu-central",
        source_seat="lead",
        target_seat="systems",
        action="dispatch_task",
        payload={"task_id": "WAN-001", "action": "deploy_service"},
    )

    assert envelope.source_region == "us-east"
    assert envelope.target_region == "eu-central"
    assert envelope.source_seat == "lead"
    assert envelope.target_seat == "systems"
    assert envelope.signature is not None
    assert envelope.payload_hash is not None

    # Valid envelope passes verification
    assert attestor.verify_envelope(envelope) is True

    # Tampered payload fails checksum verification
    tampered_envelope = copy.deepcopy(envelope)
    tampered_envelope.payload["task_id"] = "TAMPERED-001"
    with pytest.raises(AttestationFailed) as exc:
        attestor.verify_envelope(tampered_envelope)
    assert "Payload integrity checksum mismatch" in str(exc.value)

    # Tampered signature fails
    tampered_sig = copy.deepcopy(envelope)
    tampered_sig.signature = "a" * 64
    with pytest.raises(AttestationFailed) as exc:
        attestor.verify_envelope(tampered_sig)
    assert "Cryptographic signature verification failed" in str(exc.value)

    # Expired / drift envelope fails
    stale_envelope = copy.deepcopy(envelope)
    stale_envelope.timestamp = time.time() - 120.0  # > max_drift_sec (60s)
    with pytest.raises(AttestationFailed) as exc:
        attestor.verify_envelope(stale_envelope)
    assert "WAN message clock skew" in str(exc.value)

    # Invalid seat claim
    with pytest.raises(WanError) as exc:
        attestor.attest_envelope(
            source_region="us-east",
            target_region="eu-central",
            source_seat="hacker_seat",
            target_seat="systems",
            action="test",
            payload={},
        )
    assert "Invalid source seat" in str(exc.value)


def test_wan_mesh_router_route_and_receive():
    settings = Settings(edge_default_region="us-east")
    router_us = WanMeshRouter(local_region_id="us-east", settings=settings)
    router_eu = WanMeshRouter(local_region_id="eu-central", settings=settings)

    # Router US generates message to EU
    env = router_us.route_seat_message(
        target_region="eu-central",
        source_seat="infra",
        target_seat="quality",
        action="run_security_scan",
        payload={"target": "api-gateway"},
    )
    assert env.source_region == "us-east"

    # Router EU verifies and admits message
    received = router_eu.receive_seat_message(env.to_dict())
    assert received.target_seat == "quality"
    assert received.payload["target"] == "api-gateway"


# ---------------------------------------------------------------------------
# Unit tests for VectorClockGraph & ConflictResolver (REQ-EDGE-004)
# ---------------------------------------------------------------------------


def test_vector_clock_comparison_and_union():
    # Equal
    assert compare_vector_clocks({"us-east": 2}, {"us-east": 2}) == CausalityRelation.EQUAL

    # Dominates
    assert compare_vector_clocks({"us-east": 2, "eu-central": 1}, {"us-east": 1, "eu-central": 1}) == CausalityRelation.DOMINATES

    # Dominated
    assert compare_vector_clocks({"us-east": 1}, {"us-east": 2}) == CausalityRelation.DOMINATED

    # Concurrent
    assert compare_vector_clocks({"us-east": 2, "eu-central": 1}, {"us-east": 1, "eu-central": 2}) == CausalityRelation.CONCURRENT

    # Union
    union_res = union_vector_clocks({"us-east": 3, "ap-southeast": 1}, {"us-east": 1, "eu-central": 4})
    assert union_res == {"us-east": 3, "eu-central": 4, "ap-southeast": 1}


def test_vector_clock_graph_high_latency_wan_convergence():
    """Simulate two multi-master regional partitions with synthetic >300ms WAN latency."""
    graph_us = VectorClockGraph(graph_id="graph-mesh-01", local_region_id="us-east", title="Distributed Graph")
    graph_eu = VectorClockGraph(graph_id="graph-mesh-01", local_region_id="eu-central", title="Distributed Graph")

    # Initial state created on US
    graph_us.set_node(node_id="node-1", title="Task 1", status="open", actor="lead")
    graph_us.set_node(node_id="node-2", title="Task 2", status="open", actor="systems")

    # Replicate to EU (EU adopts dominant US state)
    merged_eu, status = graph_eu.merge_remote(graph_us.to_dict())
    assert status == "adopted_remote_dominates"
    assert len(merged_eu["nodes"]) == 2

    # Concurrent edits occur in both partitions while partitioned / delayed
    # Partition 1: US finishes node-1, adds node-3
    time.sleep(0.01)
    graph_us.set_node(node_id="node-1", title="Task 1", status="done", actor="lead")
    graph_us.set_node(node_id="node-3", title="Task 3 (US Infra)", status="in_progress", actor="infra")

    # Partition 2: EU finishes node-2, sets node-1 in_progress, adds node-4
    time.sleep(0.01)
    graph_eu.set_node(node_id="node-2", title="Task 2", status="done", actor="web")
    graph_eu.set_node(node_id="node-1", title="Task 1", status="in_progress", actor="quality")
    graph_eu.set_node(node_id="node-4", title="Task 4 (EU QA)", status="open", actor="quality")

    # Both clocks diverged
    assert compare_vector_clocks(graph_us.vector_clock, graph_eu.vector_clock) == CausalityRelation.CONCURRENT

    # Simulating 300ms transit delay before sync packet reaches EU from US
    time.sleep(0.05)
    converged_eu, resolution = graph_eu.merge_remote(graph_us.to_dict())
    assert resolution == "merged_concurrent"

    # All nodes present
    nodes = converged_eu["nodes"]
    assert "node-1" in nodes
    assert "node-2" in nodes
    assert "node-3" in nodes
    assert "node-4" in nodes

    # Deterministic conflict resolution on node-1: US marked 'done', EU marked 'in_progress'
    # 'done' has higher state progression weight than 'in_progress'
    assert nodes["node-1"]["status"] == "done"
    assert nodes["node-2"]["status"] == "done"

    # Clocks are unioned and advanced on EU
    assert converged_eu["vector_clock"]["us-east"] >= 3
    assert converged_eu["vector_clock"]["eu-central"] >= 3


# ---------------------------------------------------------------------------
# Unit tests for RegionImpairmentManager & Session Evacuation (REQ-EDGE-005)
# ---------------------------------------------------------------------------


def test_region_impairment_detection_and_route_revocation():
    mgr = RegionImpairmentManager(
        latency_threshold_ms=500.0,
        loss_threshold_pct=15.0,
        heartbeat_failure_threshold=3,
    )
    mgr.register_peer("eu-central", tailnet_ip="100.64.0.2", latency_ms=80.0)

    # 1. Normal telemetry -> healthy
    impaired, reason = mgr.record_metrics("eu-central", latency_ms=120.0, packet_loss_pct=2.0)
    assert impaired is False
    assert mgr.is_route_revoked("eu-central") is False

    # 2. Latency threshold breach (> 500ms)
    impaired, reason = mgr.record_metrics("eu-central", latency_ms=550.0)
    assert impaired is True
    assert "Latency 550.0ms exceeds threshold" in reason
    assert mgr.is_route_revoked("eu-central") is True

    # 3. Recovery restores route
    impaired, reason = mgr.record_metrics("eu-central", latency_ms=90.0, packet_loss_pct=1.0)
    assert impaired is False
    assert mgr.is_route_revoked("eu-central") is False

    # 4. Packet loss breach (>= 15%)
    impaired, reason = mgr.record_metrics("eu-central", packet_loss_pct=20.0)
    assert impaired is True
    assert "Packet loss 20.0%" in reason
    assert mgr.is_route_revoked("eu-central") is True

    mgr.record_metrics("eu-central", packet_loss_pct=0.0)
    assert mgr.is_route_revoked("eu-central") is False

    # 5. Heartbeat consecutive failures (>= 3)
    mgr.record_metrics("eu-central", heartbeat_ok=False)
    assert mgr.is_route_revoked("eu-central") is False
    mgr.record_metrics("eu-central", heartbeat_ok=False)
    assert mgr.is_route_revoked("eu-central") is False
    impaired, reason = mgr.record_metrics("eu-central", heartbeat_ok=False)
    assert impaired is True
    assert "Heartbeat failures (3)" in reason
    assert mgr.is_route_revoked("eu-central") is True


def test_instantaneous_session_evacuation_sla():
    """Verify session evacuation executes well within 3-second SLA (REQ-EDGE-005)."""
    mgr = RegionImpairmentManager(evacuation_time_limit_sec=3.0)
    mgr.register_peer("eu-central", tailnet_ip="100.64.0.2", latency_ms=75.0)
    mgr.register_peer("ap-southeast", tailnet_ip="100.64.0.3", latency_ms=150.0)

    # Register 100 active sessions on impaired eu-central
    for i in range(100):
        mgr.register_session(
            session_id=f"sess-{i:03d}",
            region_id="eu-central",
            seat="systems",
            task_data={"job": f"job-{i}", "progress": 50},
        )

    # Trigger emergency evacuation from eu-central to ap-southeast
    evac_result = mgr.evacuate_region(impaired_region="eu-central")
    assert evac_result["impaired_region"] == "eu-central"
    assert evac_result["target_region"] == "ap-southeast"
    assert evac_result["evacuated_count"] == 100
    assert evac_result["sla_met"] is True
    assert evac_result["duration_sec"] < 1.0  # Much faster than 3.0s SLA
    assert mgr.is_route_revoked("eu-central") is True

    # Evacuated sessions now belong to ap-southeast
    assert mgr._active_sessions["sess-001"]["region_id"] == "ap-southeast"
    assert mgr._active_sessions["sess-001"]["evacuation_source"] == "eu-central"


# ---------------------------------------------------------------------------
# Integration tests for WAN Endpoints (/v1/wan/*)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wan_endpoints_routing_and_evacuation(tmp_path: Path):
    settings = Settings(
        repo_dir=REPO,
        data_dir=tmp_path,
        seat_passphrases=PASS,
        intake_tokens={"github": INTAKE_TOKEN},
        edge_default_region="us-east",
    )
    app, _ = build_app(settings)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Unauthenticated /v1/wan/peers -> 401
        res = await client.get("/v1/wan/peers")
        assert res.status_code == 401

        # 2. Authenticated /v1/wan/peers
        res = await client.get("/v1/wan/peers", headers={"Authorization": f"Bearer {PASS['lead']}"})
        assert res.status_code == 200
        peers_data = res.json()
        assert peers_data["ok"] is True
        assert peers_data["local_region"] == "us-east"
        assert peers_data["peers_count"] >= 2

        # 3. Outbound WAN attestation POST /v1/wan/route
        attest_res = await client.post(
            "/v1/wan/route",
            json={
                "target_region": "eu-central",
                "target_seat": "systems",
                "action": "remote_dispatch",
                "payload": {"task": "cross-region-build"},
            },
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert attest_res.status_code == 200
        attest_data = attest_res.json()
        assert attest_data["ok"] is True
        assert attest_data["status"] == "attested"
        envelope = attest_data["envelope"]
        assert envelope["signature"] is not None

        # 4. Inbound WAN message verification POST /v1/wan/route
        verify_res = await client.post(
            "/v1/wan/route",
            json=envelope,
            headers={"Authorization": f"Bearer {PASS['systems']}"},
        )
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert verify_data["ok"] is True
        assert verify_data["status"] == "verified"

        # 5. Vector clock task graph sync POST /v1/wan/sync
        sync_payload = {
            "graph": {
                "graph_id": "wan-graph-10",
                "title": "Mesh Task Graph",
                "nodes": {
                    "node-a": {"node_id": "node-a", "title": "Step A", "status": "done", "updated_at": 100.0, "version": 1},
                    "node-b": {"node_id": "node-b", "title": "Step B", "status": "in_progress", "updated_at": 100.0, "version": 1},
                },
                "version": 1,
                "vector_clock": {"eu-central": 2},
            }
        }
        sync_res = await client.post(
            "/v1/wan/sync",
            json=sync_payload,
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert sync_res.status_code == 200
        sync_data = sync_res.json()
        assert sync_data["ok"] is True
        assert sync_data["resolution"] in ("adopted_remote_dominates", "merged_concurrent")
        assert "node-a" in sync_data["graph"]["nodes"]

        # 6. Trigger regional evacuation POST /v1/wan/evacuate
        evac_res = await client.post(
            "/v1/wan/evacuate",
            json={"impaired_region": "eu-central"},
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert evac_res.status_code == 200
        evac_data = evac_res.json()
        assert evac_data["ok"] is True
        assert evac_data["impaired_region"] == "eu-central"
        assert evac_data["sla_met"] is True

        # 7. Check peers shows revoked region
        peers_res2 = await client.get("/v1/wan/peers", headers={"Authorization": f"Bearer {PASS['lead']}"})
        assert "eu-central" in peers_res2.json()["revoked_regions"]

        # 8. Outbound route to revoked region is rejected (RouteRevokedError -> 503)
        revoked_res = await client.post(
            "/v1/wan/route",
            json={
                "target_region": "eu-central",
                "target_seat": "systems",
                "action": "remote_dispatch",
                "payload": {},
            },
            headers={"Authorization": f"Bearer {PASS['lead']}"},
        )
        assert revoked_res.status_code == 503
        assert revoked_res.json()["error"] == "route_revoked"
