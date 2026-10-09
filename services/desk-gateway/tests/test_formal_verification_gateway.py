"""Integration tests for Phase 40 Formal Verification REST Endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _ = build_app()
    return TestClient(app)


def test_verification_verify_and_get_certificate(client):
    sound_code = """
def multiply_by_two(val: int) -> int:
    return val * 2
"""
    payload = {
        "tool_name": "multiply_by_two",
        "version": "1.0.0",
        "author_seat_id": "systems",
        "source_code": sound_code,
        "param_types": {"val": "int"},
        "contracts": [
            {
                "contract_id": "c-even",
                "invariant_type": "POST_CONDITION",
                "expression": "result % 2 == 0",
                "description": "Output must be even",
            }
        ],
        "trials": 20,
    }

    res = client.post("/v1/verification/verify", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    cert = data["certificate"]
    assert cert["verdict"] == "PROVED"
    assert cert["contracts_evaluated"] == 1
    cert_id = cert["certificate_id"]

    # Verify retrieval
    res_get = client.get(f"/v1/verification/certificate/{cert_id}")
    assert res_get.status_code == 200
    get_data = res_get.json()
    assert get_data["ok"] is True
    assert get_data["valid"] is True
    assert get_data["certificate"]["certificate_id"] == cert_id


def test_verification_triage_endpoint(client):
    triage_payload = {
        "counterexamples": [
            {
                "contract_id": "c-overflow",
                "invariant_type": "POST_CONDITION",
                "expression": "result < 50",
                "inputs": {"val": 100},
                "output": 200,
                "error_message": "Invariant violated: expression 'result < 50' evaluated to False",
                "suggested_patch": "Clamp maximum value",
            }
        ]
    }

    res = client.post("/v1/verification/triage", json=triage_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["triage"]["violations_count"] == 1
    assert data["triage"]["diagnostics"][0]["issue_type"] == "numeric_range_violation"
