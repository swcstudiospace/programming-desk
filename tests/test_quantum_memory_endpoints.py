"""Integration tests for Milestone v5.2 Quantum Memory & Continuous-Variable REST endpoints."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app


@pytest.fixture
def client():
    app, _settings = build_app()
    return TestClient(app)


def test_rest_quantum_memory_store_and_retrieve(client):
    # 1. Store state in desk-alpha AFC memory
    store_resp = client.post("/v1/quantum/memory/store", json={
        "node_id": "desk-alpha",
        "buffer_type": "AFC",
        "t1_relaxation_us": 8000.0,
        "t2_dephasing_us": 4000.0,
        "peak_efficiency": 0.95,
        "state_repr": {"mode": "spin_wave", "fidelity": 0.99},
    })
    assert store_resp.status_code == 200
    store_data = store_resp.json()
    assert store_data["ok"] is True
    cell = store_data["cell"]
    assert cell["buffer_type"] == "AFC"
    assert "receipt" in store_data

    # 2. List cells
    list_resp = client.get("/v1/quantum/memory/cells?node_id=desk-alpha")
    assert list_resp.status_code == 200
    cells = list_resp.json()["cells"]
    assert any(c["cell_id"] == cell["cell_id"] for c in cells)

    # 3. Retrieve state
    ret_resp = client.post("/v1/quantum/memory/retrieve", json={
        "node_id": "desk-alpha",
        "cell_id": cell["cell_id"],
    })
    assert ret_resp.status_code == 200
    ret_data = ret_resp.json()
    assert ret_data["ok"] is True
    assert ret_data["fidelity"] > 0.85
    assert ret_data["state"]["mode"] == "spin_wave"


def test_rest_quantum_cv_squeezing_and_beam_splitter(client):
    # 1. Create two squeezed states
    sqz1_resp = client.post("/v1/quantum/cv/squeezed/create", json={
        "node_id": "desk-alpha",
        "squeezing_r": 1.1,
        "squeezing_phi": 0.0,
        "mean_q": 1.0,
        "mean_p": 0.0,
    })
    assert sqz1_resp.status_code == 200
    s1 = sqz1_resp.json()["squeezed_state"]

    sqz2_resp = client.post("/v1/quantum/cv/squeezed/create", json={
        "node_id": "desk-alpha",
        "squeezing_r": 1.1,
        "squeezing_phi": 3.14159,
        "mean_q": -1.0,
        "mean_p": 0.0,
    })
    assert sqz2_resp.status_code == 200
    s2 = sqz2_resp.json()["squeezed_state"]

    # 2. Beam splitter
    bs_resp = client.post("/v1/quantum/cv/beam-splitter", json={
        "state_id_1": s1["state_id"],
        "state_id_2": s2["state_id"],
        "transmissivity": 0.5,
    })
    assert bs_resp.status_code == 200
    bs_data = bs_resp.json()
    assert bs_data["ok"] is True
    assert "out_state_1" in bs_data
    assert "out_state_2" in bs_data

    # 3. Homodyne measurement on output port
    homo_resp = client.post("/v1/quantum/cv/homodyne", json={
        "state_id": bs_data["out_state_1"]["state_id"],
        "measurement_type": "POSITION",
        "detector_efficiency": 0.98,
    })
    assert homo_resp.status_code == 200
    meas = homo_resp.json()["measurement"]
    assert meas["measured_quadrature"] == "q"


def test_rest_quantum_cv_swap(client):
    swap_resp = client.post("/v1/quantum/cv/swap", json={
        "node_a": "desk-alpha",
        "repeater_node": "repeater-1",
        "node_b": "desk-beta",
        "squeezing_r": 1.25,
        "detector_efficiency": 0.98,
    })
    assert swap_resp.status_code == 200
    res = swap_resp.json()
    assert res["ok"] is True
    assert res["swap_result"]["is_entangled"] is True
    assert res["swap_result"]["swapped_fidelity"] > 0.70


def test_rest_quantum_memory_anchor_and_drill(client):
    # Anchor export
    anchor_resp = client.post("/v1/quantum/memory/anchor/export")
    assert anchor_resp.status_code == 200
    anchor_data = anchor_resp.json()
    assert anchor_data["ok"] is True
    assert anchor_data["anchor"]["status"] == "confirmed"

    # Drill simulate
    drill_resp = client.post("/v1/quantum/memory/drill/simulate")
    assert drill_resp.status_code == 200
    drill_data = drill_resp.json()
    assert drill_data["ok"] is True
    assert drill_data["drill"]["all_passed"] is True
