"""Integration tests for Swarm Immune & DePIN Physical Resource Mesh REST endpoints (Milestone v4.8)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_immune_antibodies_routes(client):
    # 1. GET /v1/immune/mesh/antibodies (initially empty or default)
    r1 = client.get("/v1/immune/mesh/antibodies")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert isinstance(r1.json()["antibodies"], list)

    # 2. POST /v1/immune/mesh/antibodies/create
    r2 = client.post(
        "/v1/immune/mesh/antibodies/create",
        json={
            "vector_type": "byzantine_injection",
            "indicator_pattern": "SQL_INJECTION_OR_1=1",
            "mitigation": "quarantine_isolate",
            "severity": "critical",
            "fitness_score": 0.95,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["antibody"]["target_vector"] == "byzantine_injection"
    assert r2.json()["antibody"]["fitness_score"] == 0.95


def test_immune_perturb_and_reconstitute_routes(client):
    # 1. POST /v1/immune/mesh/perturb
    r1 = client.post(
        "/v1/immune/mesh/perturb",
        json={
            "seat_id": "bot-04-ios",
            "vector_type": "latency_poisoning",
            "payload": "SLOW_PACKET_BURST",
            "entropy": 0.88,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "outcome" in r1.json()["perturbation"]

    # 2. POST /v1/immune/mesh/reconstitute
    r2 = client.post(
        "/v1/immune/mesh/reconstitute",
        json={"seat_id": "bot-04-ios"},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["reconstitution"]["new_state"] == "REHABILITATING"


def test_depin_nodes_and_lease_routes(client):
    # 1. GET /v1/depin/nodes
    r1 = client.get("/v1/depin/nodes")
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert len(r1.json()["nodes"]) >= 4

    # 2. POST /v1/depin/lease
    r2 = client.post(
        "/v1/depin/lease",
        json={
            "consumer_seat": "bot-01-systems-backend",
            "resource_type": "gpu_cluster",
            "units": 150.0,
            "duration_seconds": 1800.0,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["lease"]["allocated_units"] == 150.0
    assert r2.json()["lease"]["status"] == "ACTIVE"


def test_depin_popw_and_anchor_routes(client):
    # 1. POST /v1/depin/popw/generate
    r1 = client.post(
        "/v1/depin/popw/generate",
        json={
            "node_id": "depin-us-east-gpu-0",
            "work_units": 150.0,
            "workload_payload": "INFERENCE_BATCH_64_LLM",
            "elapsed_ms": 18.5,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["proof"]["work_units_completed"] == 150.0

    # 2. POST /v1/depin/anchor/export
    r2 = client.post("/v1/depin/anchor/export")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["anchor"]["status"] == "CONFIRMED_ON_SOLANA_DEVNET"
    assert "transaction_signature" in r2.json()["anchor"]


def test_swarm_immune_depin_drill_simulate_route(client):
    r = client.post("/v1/immune/drill/simulate")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    drill = r.json()["drill"]
    assert drill["drill_status"] == "ALL_CHECKS_PASSED"
    assert drill["antibody_distribution_and_sync"]["status"] == "PASSED"
    assert drill["antifragility_and_genetic_evolution"]["status"] == "PASSED"
    assert drill["runtime_reconstitution"]["status"] == "PASSED"
    assert drill["depin_resource_leasing_and_popw"]["status"] == "PASSED"
    assert drill["depin_ledger_and_solana_anchor"]["status"] == "PASSED"
