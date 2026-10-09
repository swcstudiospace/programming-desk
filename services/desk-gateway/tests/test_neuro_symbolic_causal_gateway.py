"""Integration tests for Neuro-Symbolic & Causal Mesh REST routes in desk-gateway (Milestone v4.5)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_neuro_symbolic_fact_rule_deduce_routes(client):
    # 1. Add Facts
    r1 = client.post("/v1/neuro-symbolic/facts", json={"name": "seat_active", "args": ["seat_lead"], "truth_val": 1.0})
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # 2. Add Horn Rule: seat_active(?s) -> seat_can_dispatch(?s)
    r2 = client.post(
        "/v1/neuro-symbolic/rules",
        json={
            "rule_id": "r_dispatch",
            "antecedents": [{"name": "seat_active", "args": ["?s"]}],
            "consequent": {"name": "seat_can_dispatch", "args": ["?s"]},
            "confidence": 1.0,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # 3. Deduce
    r3 = client.post("/v1/neuro-symbolic/deduce")
    assert r3.status_code == 200
    facts = r3.json()["inferred_facts"]
    assert any("seat_can_dispatch(seat_lead)" in f for f in facts)

    # 4. Query
    r4 = client.post("/v1/neuro-symbolic/query", json={"name": "seat_can_dispatch", "args": ["?who"]})
    assert r4.status_code == 200
    assert r4.json()["matches_count"] >= 1
    assert r4.json()["bindings"][0]["?who"] == "seat_lead"


def test_neuro_symbolic_concept_and_search_routes(client):
    # Add Concept
    r1 = client.post(
        "/v1/neuro-symbolic/concepts",
        json={
            "node_id": "concept_compiler",
            "name": "CompilerNode",
            "category": "service",
            "embedding": [0.8, 0.2, 0.1, 0.0],
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # Similarity Search
    r2 = client.post(
        "/v1/neuro-symbolic/concepts/search",
        json={"query_embedding": [0.85, 0.15, 0.05, 0.0], "top_k": 1},
    )
    assert r2.status_code == 200
    results = r2.json()["results"]
    assert len(results) == 1
    assert results[0]["node_id"] == "concept_compiler"


def test_causal_mesh_dag_intervene_counterfactual_routes(client):
    # 1. Create Causal DAG
    r1 = client.post(
        "/v1/causal/dags/create",
        json={
            "dag_id": "gateway-causal-v1",
            "variables": [
                {"name": "V1", "base_mean": 10.0},
                {"name": "V2", "base_mean": 2.0},
            ],
            "edges": [
                {"source": "V1", "target": "V2", "weight": 0.5},
            ],
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # 2. Intervene via Do-Calculus
    r2 = client.post(
        "/v1/causal/intervene",
        json={
            "dag_id": "gateway-causal-v1",
            "treatment": "V1",
            "intervention_value": 30.0,
            "outcome": "V2",
        },
    )
    assert r2.status_code == 200
    # Expected V2 = base_mean(2.0) + 0.5 * 30.0 = 17.0
    assert abs(r2.json()["expected_outcome"] - 17.0) < 1e-3

    # 3. Counterfactual Query
    r3 = client.post(
        "/v1/causal/counterfactual",
        json={
            "dag_id": "gateway-causal-v1",
            "factual_evidence": {"V1": 20.0, "V2": 15.0},
            "counterfactual_intervention": {"V1": 10.0},
            "target_variable": "V2",
        },
    )
    assert r3.status_code == 200
    # Factual: V2 = 2.0 + 0.5 * 20.0 + U_V2 = 12.0 + U_V2 = 15.0 => U_V2 = 3.0
    # Counterfactual: V1=10.0 => V2 = 2.0 + 0.5 * 10.0 + 3.0 = 10.0
    assert abs(r3.json()["counterfactual_prediction"] - 10.0) < 1e-3


def test_neuro_symbolic_drill_simulate_route(client):
    resp = client.post("/v1/neuro-symbolic/drill/simulate")
    assert resp.status_code == 200
    drill = resp.json()["drill"]
    assert drill["drill_status"] == "SUCCESS"
    assert drill["invariant_violation_caught"] is True
    assert drill["d_separation_verified"] is True
    assert drill["solana_commitment_root"] is not None
