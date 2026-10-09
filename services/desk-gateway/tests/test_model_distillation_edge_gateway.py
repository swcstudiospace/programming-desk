"""Integration tests for Model Distillation and Edge Gateway Endpoints (Milestone v4.3)."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _ = build_app()
    return TestClient(app)


def test_distillation_endpoints(client):
    # 1. Distillation Step
    step_resp = client.post(
        "/v1/distillation/step",
        json={
            "student_logits": [2.0, 0.5, -1.0],
            "teacher_predictions": [
                {"model_id": "teacher-1", "weight": 1.0, "logits": [2.5, 0.2, -0.8]}
            ],
            "ground_truth_label": 0,
            "temperature": 2.0,
            "alpha": 0.5,
        },
    )
    assert step_resp.status_code == 200
    assert step_resp.json()["ok"] is True
    assert "metrics" in step_resp.json()

    # 2. Distillation Job Creation
    job_resp = client.post(
        "/v1/distillation/jobs",
        json={
            "student_model": "student-desk-edge",
            "teacher_models": ["t1", "t2"],
            "target_quantization": "INT8",
        },
    )
    assert job_resp.status_code == 200
    assert job_resp.json()["ok"] is True
    assert "job_id" in job_resp.json()

    # 3. Store Artifact
    art_resp = client.post(
        "/v1/distillation/artifacts",
        json={
            "model_name": "student-desk-edge",
            "quantization_type": "INT8",
            "weights": [0.1, -0.4, 0.8, -0.2],
        },
    )
    assert art_resp.status_code == 200
    art_id = art_resp.json()["artifact_id"]

    # 4. Get Artifact
    get_art_resp = client.get(f"/v1/distillation/artifacts/{art_id}")
    assert get_art_resp.status_code == 200
    assert get_art_resp.json()["artifact"]["artifact_id"] == art_id

    # 5. Benchmark Retention
    bench_resp = client.post(
        "/v1/distillation/benchmark/retention",
        json={"teacher_accuracy": 0.92, "student_accuracy": 0.88},
    )
    assert bench_resp.status_code == 200
    assert bench_resp.json()["evaluation"]["passed_gate"] is True


def test_edge_endpoints(client):
    # 1. Edge Nodes
    nodes_resp = client.get("/v1/edge/nodes")
    assert nodes_resp.status_code == 200
    assert len(nodes_resp.json()["nodes"]) >= 2

    # 2. Edge Schedule
    sched_resp = client.post(
        "/v1/edge/schedule",
        json={"artifact_id": "art-test", "required_vram_mb": 1024, "quantization": "INT8"},
    )
    assert sched_resp.status_code == 200
    assert sched_resp.json()["ok"] is True

    # 3. Edge Inference Proof
    proof_resp = client.post(
        "/v1/edge/inference/prove",
        json={
            "prompt": "Summarize edge mesh architecture",
            "completion": "Edge mesh orchestrates quantized student models across nodes.",
        },
    )
    assert proof_resp.status_code == 200
    receipt = proof_resp.json()["receipt"]
    assert receipt["receipt_id"].startswith("rcpt-")

    # 4. Edge Commitment Export
    commit_resp = client.post("/v1/edge/commitments/export", json={"receipts": [receipt]})
    assert commit_resp.status_code == 200
    assert commit_resp.json()["commitment"]["status"] == "confirmed_devnet"

    # 5. Distillation & Edge Drill
    drill_resp = client.post("/v1/distillation/drill/simulate")
    assert drill_resp.status_code == 200
    assert drill_resp.json()["drill"]["drill_status"] == "SUCCESS"
