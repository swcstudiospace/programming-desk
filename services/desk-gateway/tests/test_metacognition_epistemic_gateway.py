"""Integration tests for Metacognition & Epistemic Mesh REST routes in desk-gateway (Milestone v4.6)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, settings = build_app()
    with TestClient(app) as c:
        yield c


def test_metacognition_calibrate_and_introspect_routes(client):
    # 1. Calibrate Route
    r1 = client.post(
        "/v1/metacognition/calibrate",
        json={
            "raw_confidence": 0.88,
            "history_samples": [
                {"confidence": 0.9, "is_correct": True},
                {"confidence": 0.95, "is_correct": True},
                {"confidence": 0.85, "is_correct": False},
            ],
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "calibrated_probability" in r1.json()["calibration"]

    # 2. Introspect Route (Circular Reasoning)
    r2 = client.post(
        "/v1/metacognition/introspect",
        json={
            "reasoning_steps": [
                {"premise": "Database is synced", "conclusion": "Quorum reached", "confidence": 0.9},
                {"premise": "Quorum reached", "conclusion": "Database is synced", "confidence": 0.95},
            ]
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    report = r2.json()["bias_report"]
    assert report["circular_reasoning_detected"] is True
    assert "CIRCULAR_REASONING" in report["detected_biases"]


def test_metacognition_beliefs_and_strategy_routes(client):
    # 1. Add Hypothesis
    r1 = client.post(
        "/v1/metacognition/beliefs",
        json={
            "hypothesis_id": "H_GATEWAY_HEALTHY",
            "description": "Gateway latency is below SLO threshold",
            "prior": 0.6,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True

    # 2. Assimilate Evidence
    r2 = client.post(
        "/v1/metacognition/beliefs/H_GATEWAY_HEALTHY/assimilate",
        json={"likelihood_ratio": 2.5},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["update"]["posterior"] > 0.6

    # 3. Strategy Selection
    r3 = client.post(
        "/v1/metacognition/strategy/select",
        json={"task_criticality": "critical"},
    )
    assert r3.status_code == 200
    assert r3.json()["ok"] is True
    assert "selected_strategy" in r3.json()


def test_epistemic_challenge_coherence_and_anchor_routes(client):
    # 1. Socratic Challenge
    r1 = client.post(
        "/v1/epistemic/socratic/challenge",
        json={
            "hypothesis_id": "H_GATEWAY_HEALTHY",
            "description": "Gateway latency is below SLO threshold",
            "current_probability": 0.85,
            "probe_type": "boundary_falsification",
        },
    )
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert "challenge_id" in r1.json()["challenge"]

    # 2. Epistemic Coherence
    r2 = client.post(
        "/v1/epistemic/coherence/verify",
        json={
            "seat_beliefs": {
                "seat_lead": {"H1": 0.7, "H2": 0.3},
                "seat_worker": {"H1": 0.68, "H2": 0.32},
            },
            "divergence_threshold": 0.15,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True
    assert r2.json()["coherence"]["is_coherent"] is True

    # 3. Ledger Receipt & Anchor Export
    r3 = client.post(
        "/v1/epistemic/ledger/receipts",
        json={
            "network_id": "net-gateway-test",
            "receipt_type": "BELIEF_UPDATE",
            "payload": {"h_id": "H1", "new_prob": 0.7},
        },
    )
    assert r3.status_code == 200
    assert r3.json()["ok"] is True

    r4 = client.post("/v1/epistemic/anchor/export")
    assert r4.status_code == 200
    assert r4.json()["ok"] is True
    assert r4.json()["anchor"]["status"] == "CONFIRMED"


def test_metacognitive_epistemic_drill_simulate_route(client):
    r = client.post("/v1/metacognition/drill/simulate")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["drill"]["drill_status"] == "SUCCESS"
    assert r.json()["drill"]["circular_reasoning_caught"] is True
