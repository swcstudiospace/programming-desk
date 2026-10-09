"""Integration tests for Milestone v5.7 Quantum Machine Learning REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_ml_train_and_predict(client):
    # 1. Train step
    train_resp = client.post("/v1/quantum/ml/train/step", json={
        "features": [0.6, -0.4],
        "target_label": 1.0,
        "learning_rate": 0.15,
    })
    assert train_resp.status_code == 200
    t_data = train_resp.json()
    assert t_data["ok"] is True
    assert "epoch" in t_data
    assert "receipt" in t_data

    # 2. Predict
    pred_resp = client.post("/v1/quantum/ml/predict", json={
        "features": [0.6, -0.4],
    })
    assert pred_resp.status_code == 200
    p_data = pred_resp.json()
    assert p_data["ok"] is True
    assert -1.0 <= p_data["prediction"] <= 1.0
    assert len(p_data["weights"]) == 3


def test_rest_quantum_ml_anchor_and_drill(client):
    # Anchor
    anchor_resp = client.post("/v1/quantum/ml/anchor/export")
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["ok"] is True
    assert anchor_resp.json()["anchor"]["status"] == "confirmed"

    # Drill
    drill_resp = client.post("/v1/quantum/ml/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["ok"] is True
    assert drill_resp.json()["drill"]["all_passed"] is True
