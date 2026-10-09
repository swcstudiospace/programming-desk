"""Integration tests for Phase 41 Multi-Seat Synthesis Consensus REST Endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _ = build_app()
    return TestClient(app)


def test_synthesis_review_flow(client):
    # 1. Generate certificate
    verify_res = client.post(
        "/v1/verification/verify",
        json={
            "tool_name": "gateway_consensus_tool",
            "version": "1.0.0",
            "author_seat_id": "systems",
            "source_code": "def gateway_consensus_tool(x: int) -> int:\n    return x + 10\n",
            "param_types": {"x": "int"},
            "contracts": [
                {
                    "contract_id": "c-gt-10",
                    "invariant_type": "POST_CONDITION",
                    "expression": "result > x",
                }
            ],
            "trials": 10,
        },
    )
    assert verify_res.status_code == 200
    cert_id = verify_res.json()["certificate"]["certificate_id"]

    # 2. Initiate review session
    init_res = client.post(
        "/v1/synthesis/review/initiate",
        json={"certificate_id": cert_id, "threshold_ratio": 0.5},
    )
    assert init_res.status_code == 200
    consensus_id = init_res.json()["consensus_id"]

    # 3. Cast votes from multiple seats
    for seat in ["lead", "quality", "systems"]:
        v_res = client.post(
            "/v1/synthesis/review/vote",
            json={
                "consensus_id": consensus_id,
                "reviewer_seat_id": seat,
                "vote": "APPROVE",
                "critique_notes": f"{seat} approves",
            },
        )
        assert v_res.status_code == 200
        assert v_res.json()["ok"] is True

    # 4. Finalize session
    fin_res = client.post(
        "/v1/synthesis/review/finalize",
        json={"consensus_id": consensus_id},
    )
    assert fin_res.status_code == 200
    data = fin_res.json()
    assert data["ok"] is True
    assert data["receipt"]["state"] == "APPROVED"
    assert "ledger_root" in data

    # 5. Retrieve Merkle proof for the first receipt
    proof_res = client.get("/v1/synthesis/ledger/proof/0")
    assert proof_res.status_code == 200
    assert proof_res.json()["ok"] is True
    assert proof_res.json()["valid"] is True

    # 6. Solana export anchor
    sol_res = client.post(
        "/v1/synthesis/anchor/solana",
        json={"consensus_id": consensus_id},
    )
    assert sol_res.status_code == 200
    assert sol_res.json()["ok"] is True
    assert sol_res.json()["anchor"]["target"] == "solana_devnet"


def test_synthesis_drill_endpoint(client):
    res = client.post("/v1/synthesis/drill/simulate")
    assert res.status_code == 200
    drill = res.json()["drill"]
    assert drill["all_drills_passed"] is True
    assert drill["sound_tool_verdict"] == "APPROVED"
    assert drill["flawed_tool_verdict"] == "REJECTED"
