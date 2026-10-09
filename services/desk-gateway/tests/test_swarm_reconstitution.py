"""Unit and integration tests for Swarm Self-Healing Reconstitution & Immune Memory Attestation (Milestone v3.4 - Phase 35)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.swarm_immune import (
    SeatContainmentState,
    SwarmImmuneEngine,
)
from desk_gateway.swarm_reconstitution import (
    AntibodyDistributionMesh,
    AntibodyPolicy,
    CheckpointBaseline,
    ChaosAnomalyHarness,
    ImmuneMemoryLedger,
    ProgressiveRehabilitationProtocol,
    RehabilitationStage,
    SwarmReconstitutionEngine,
)


def test_checkpoint_baseline():
    engine = SwarmImmuneEngine()
    reconstituter = SwarmReconstitutionEngine(immune_engine=engine, desk_id="desk-test")
    
    baseline = reconstituter.register_checkpoint(
        seat_id="lead",
        version=2,
        capabilities={"mcp_tool_execute", "git_read"},
        runtime_env={"memory_limit_mb": 8192},
    )
    assert baseline.seat_id == "lead"
    assert baseline.version == 2
    assert "mcp_tool_execute" in baseline.allowed_capabilities
    assert len(baseline.hash_commitment) == 64


def test_immune_memory_ledger_integrity_and_merkle_root():
    ledger = ImmuneMemoryLedger()
    assert ledger.verify_integrity() is True
    assert ledger.get_merkle_root() == ledger.GENESIS_HASH

    # Record two events
    e1 = ledger.record_event(
        seat_id="seat-backend",
        attack_signature="sig-abc123",
        anomaly_type="ENTROPY_SPIKE",
        mitigation_action="QUARANTINE",
    )
    e2 = ledger.record_event(
        seat_id="seat-infra",
        attack_signature="sig-def456",
        anomaly_type="LATENCY_POISONING",
        mitigation_action="RECONSTITUTE",
    )

    assert len(ledger.entries) == 2
    assert e2.prev_hash == e1.entry_hash
    assert ledger.verify_integrity() is True
    
    root = ledger.get_merkle_root()
    assert len(root) == 64
    assert root != ledger.GENESIS_HASH

    # Tamper test
    ledger.entries[0].attack_signature = "sig-tampered"
    assert ledger.verify_integrity() is False


def test_antibody_distribution_and_threat_matching():
    mesh1 = AntibodyDistributionMesh(desk_id="desk-a", secret_key="mesh-secret")
    mesh2 = AntibodyDistributionMesh(desk_id="desk-b", secret_key="mesh-secret")

    policy = AntibodyPolicy(
        antibody_id="ab-exploit-rule",
        pattern_regex=r"(?i)malicious_injection",
        max_entropy=6.0,
        max_latency_ms=5000.0,
        target_tools=["exec_cmd", "write_file"],
        action="BLOCK",
        origin_desk_id="desk-a",
    )
    mesh1.register_antibody(policy)

    # Export & ingest
    pkg = mesh1.export_distribution_package()
    count = mesh2.ingest_distribution_package(pkg)
    assert count == 1
    assert "ab-exploit-rule" in mesh2.antibodies

    # Test threat matching
    # Tool not in target
    assert mesh2.check_threat(tool_name="git_status", payload="malicious_injection") is None
    # Matching regex
    matched = mesh2.check_threat(tool_name="exec_cmd", payload="echo malicious_injection")
    assert matched is not None
    assert matched.antibody_id == "ab-exploit-rule"

    # Matching latency
    matched_lat = mesh2.check_threat(tool_name="exec_cmd", payload="hello", latency_ms=6000.0)
    assert matched_lat is not None

    # Invalid signature fails
    pkg_tampered = dict(pkg)
    pkg_tampered["signature"] = "00000000000000000000"
    with pytest.raises(ValueError, match="Invalid antibody package HMAC signature"):
        mesh2.ingest_distribution_package(pkg_tampered)


def test_swarm_reconstitution_and_rehabilitation():
    immune = SwarmImmuneEngine()
    reconstituter = SwarmReconstitutionEngine(immune_engine=immune, desk_id="test-desk")

    # Quarantine seat
    immune.quarantine_seat("backend", reason="Exceeded entropy threshold")
    assert immune.get_or_create_profile("backend").state == SeatContainmentState.QUARANTINED

    # Autonomous reconstitution
    res = reconstituter.reconstitute_seat("backend", reason="Autonomous healing")
    assert res["reconstituted"] is True
    assert immune.get_or_create_profile("backend").state == SeatContainmentState.SUSPICIOUS
    assert immune.get_or_create_profile("backend").quarantine_reason is None

    # Progressive rehabilitation: pass synthetic benchmarks
    rehab_res = reconstituter.rehabilitation.run_synthetic_benchmarks("backend")
    assert rehab_res["graduated"] is True
    assert rehab_res["stage"] == RehabilitationStage.GRADUATED_HEALTHY.value
    assert immune.get_or_create_profile("backend").state == SeatContainmentState.HEALTHY


def test_progressive_rehabilitation_failure_handling():
    immune = SwarmImmuneEngine()
    reconstituter = SwarmReconstitutionEngine(immune_engine=immune, desk_id="test-desk")

    # Benchmarks with a failing probe
    bad_benchmarks = [
        {"tool": "probe_1", "payload": "healthy_probe", "should_fail": False},
        {"tool": "probe_2", "payload": "failing_probe", "should_fail": True},
    ]
    rehab_res = reconstituter.rehabilitation.run_synthetic_benchmarks("web", benchmark_tasks=bad_benchmarks)
    assert rehab_res["graduated"] is False
    assert rehab_res["stage"] == RehabilitationStage.FAILED.value
    assert immune.get_or_create_profile("web").state == SeatContainmentState.QUARANTINED


def test_chaos_anomaly_harness_full_drill():
    immune = SwarmImmuneEngine()
    reconstituter = SwarmReconstitutionEngine(immune_engine=immune, desk_id="test-desk")
    chaos = ChaosAnomalyHarness(immune_engine=immune, reconstitution_engine=reconstituter)

    drill_result = chaos.run_chaos_resilience_drill(seat_id="chaos-agent")
    assert drill_result["quarantine_verified"] is True
    assert drill_result["reconstitution_success"] is True
    assert drill_result["rehabilitation_graduated"] is True
    assert drill_result["ledger_verified"] is True
    assert drill_result["final_state"] == SeatContainmentState.HEALTHY.value


def test_server_immune_reconstitution_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Quarantine lead seat
    q_resp = client.post("/v1/immune/seat/quarantine", json={"seat_id": "lead", "reason": "Anomaly spike"})
    assert q_resp.status_code == 200
    assert q_resp.json()["result"]["new_state"] == "QUARANTINED"

    # 2. Trigger reconstitution
    rec_resp = client.post("/v1/immune/reconstitute", json={"seat_id": "lead", "reason": "Self-heal drill"})
    assert rec_resp.status_code == 200
    assert rec_resp.json()["result"]["reconstituted"] is True

    # 3. Progressive rehabilitation benchmark
    bench_resp = client.post("/v1/immune/rehabilitate/benchmark", json={"seat_id": "lead"})
    assert bench_resp.status_code == 200
    assert bench_resp.json()["rehabilitation"]["graduated"] is True

    # 4. Immune memory ledger inspect
    ledger_resp = client.get("/v1/immune/memory/ledger")
    assert ledger_resp.status_code == 200
    ledger_data = ledger_resp.json()
    assert ledger_data["ok"] is True
    assert ledger_data["valid"] is True
    assert len(ledger_data["entries"]) >= 1

    # 5. Antibodies broadcast and ingest
    bcast_resp = client.post("/v1/immune/antibodies/broadcast")
    assert bcast_resp.status_code == 200
    pkg = bcast_resp.json()["package"]
    assert "signature" in pkg

    ingest_resp = client.post("/v1/immune/antibodies/ingest", json={"package": pkg})
    assert ingest_resp.status_code == 200
    assert ingest_resp.json()["ingested_count"] >= 1

    # 6. Chaos injection drill
    chaos_resp = client.post("/v1/immune/chaos/inject", json={"seat_id": "chaos-test-seat"})
    assert chaos_resp.status_code == 200
    drill = chaos_resp.json()["drill"]
    assert drill["reconstitution_success"] is True
    assert drill["rehabilitation_graduated"] is True
