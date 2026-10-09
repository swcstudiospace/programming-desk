"""Integration tests for Prompt Optimization Gateway Routes (Phase 37)."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def test_client():
    app, _ = build_app()
    return TestClient(app)


def test_gateway_prompt_evolution_full_lifecycle(test_client):
    seat_id = "lead"
    base_text = "Coordinate desk engineering decisions and code dispatch."

    # 1. Register baseline
    res_base = test_client.post(
        "/v1/evolution/prompts/baseline",
        json={"seat_id": seat_id, "prompt_text": base_text},
    )
    assert res_base.status_code == 200
    base_data = res_base.json()
    assert base_data["ok"] is True
    base_rev_id = base_data["variant"]["revision_id"]

    # 2. Mutate candidate
    res_mut = test_client.post(
        "/v1/evolution/prompts/mutate",
        json={"seat_id": seat_id, "strategy": "emphasize_step_by_step"},
    )
    assert res_mut.status_code == 200
    cand_data = res_mut.json()
    assert cand_data["ok"] is True
    cand_rev_id = cand_data["candidate"]["revision_id"]

    # 3. Canary benchmark evaluation
    res_can = test_client.post(
        "/v1/evolution/prompts/canary",
        json={"revision_id": cand_rev_id},
    )
    assert res_can.status_code == 200
    can_data = res_can.json()
    assert can_data["ok"] is True
    assert can_data["fitness"]["overall_score"] > 60.0

    # 4. Promote candidate
    res_prom = test_client.post(
        "/v1/evolution/prompts/promote",
        json={"revision_id": cand_rev_id},
    )
    assert res_prom.status_code == 200
    prom_data = res_prom.json()
    assert prom_data["promoted"] is True

    # 5. Check Lineage
    res_lin = test_client.get(f"/v1/evolution/prompts/lineage/{seat_id}")
    assert res_lin.status_code == 200
    lin_data = res_lin.json()
    assert lin_data["active"]["revision_id"] == cand_rev_id
    assert len(lin_data["lineage"]) == 2

    # 6. Rollback to baseline
    res_rb = test_client.post(
        "/v1/evolution/prompts/rollback",
        json={"seat_id": seat_id},
    )
    assert res_rb.status_code == 200
    rb_data = res_rb.json()
    assert rb_data["ok"] is True
    assert rb_data["reverted_to"]["revision_id"] == base_rev_id
