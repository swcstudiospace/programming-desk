"""Unit tests for Quantum Annealing & QUBO Optimization Mesh (Milestone v6.2 - Phases 90 & 91)."""

import pytest
from desk_gateway.quantum_annealing_mesh import (
    ChimeraGraphTopology,
    IsingHamiltonian,
    QUBOProblem,
    SimulatedQuantumAnnealer,
)
from desk_gateway.quantum_annealing_anchoring import (
    QuantumAnnealingMerkleLedger,
    QuantumAnnealingReceipt,
    QuantumAnnealingSolanaAnchor,
    SimulatedAnnealingVerificationDrill,
)


def test_qubo_to_ising_mapping():
    # 2-variable QUBO: minimize -x0 - x1 + 2 x0 x1
    # Global minimum is (1, 0) or (0, 1) with value -1.0
    qubo = QUBOProblem(
        num_variables=2,
        Q_matrix={(0, 0): -1.0, (1, 1): -1.0, (0, 1): 2.0},
    )
    ising = qubo.to_ising()

    assert ising.num_spins == 2
    assert isinstance(ising.linear_biases, dict)
    assert isinstance(ising.quadratic_couplings, dict)

    # Test spin energy matches QUBO energy for configurations
    for x0 in (0, 1):
        for x1 in (0, 1):
            s0 = 2 * x0 - 1
            s1 = 2 * x1 - 1
            q_val = qubo.evaluate_qubo([x0, x1])
            ising_val = ising.evaluate_energy([s0, s1])
            assert pytest.approx(q_val, abs=1e-5) == ising_val


def test_simulated_quantum_annealer():
    qubo = QUBOProblem(
        num_variables=3,
        Q_matrix={
            (0, 0): -2.0,
            (1, 1): -2.0,
            (2, 2): -2.0,
            (0, 1): 1.0,
            (1, 2): 1.0,
        },
    )
    ising = qubo.to_ising()
    annealer = SimulatedQuantumAnnealer(ising, num_trotter_slices=4)
    res = annealer.solve(num_sweeps=40, annealing_time_us=10.0)

    assert res.success is True
    assert len(res.best_spins) == 3
    assert len(res.best_binary) == 3
    for s in res.best_spins:
        assert s in (-1, 1)
    for b in res.best_binary:
        assert b in (0, 1)


def test_chimera_topology():
    couplings = ChimeraGraphTopology.generate_unit_cell_couplings(cell_id=0)
    assert len(couplings) == 16  # K_{4,4} bipartite graph has 4*4 = 16 edges
    assert (0, 4) in couplings
    assert (3, 7) in couplings


def test_quantum_annealing_merkle_ledger_and_anchor():
    ledger = QuantumAnnealingMerkleLedger()
    receipt1 = QuantumAnnealingReceipt(
        receipt_id="r1",
        problem_hash="prob-01",
        num_variables=2,
        num_spins=2,
        best_energy=-1.0,
        best_binary=[1, 0],
        num_sweeps=30,
        annealing_time_us=20.0,
    )
    receipt2 = QuantumAnnealingReceipt(
        receipt_id="r2",
        problem_hash="prob-02",
        num_variables=3,
        num_spins=3,
        best_energy=-2.0,
        best_binary=[1, 1, 0],
        num_sweeps=30,
        annealing_time_us=20.0,
    )

    ledger.add_receipt(receipt1)
    ledger.add_receipt(receipt2)

    root = ledger.get_merkle_root()
    assert isinstance(root, str)
    assert len(root) == 64

    anchor = QuantumAnnealingSolanaAnchor.export_anchor_instruction(root, len(ledger.receipts))
    assert anchor["instruction"] == "record_quantum_annealing_root"
    assert anchor["data"]["merkle_root"] == root
    assert anchor["data"]["total_receipts"] == 2


def test_annealing_5_stage_drill():
    drill_res = SimulatedAnnealingVerificationDrill.run_5_stage_drill()
    assert drill_res["all_passed"] is True
    assert len(drill_res["stages"]) == 5
    for stage_id, stage_info in drill_res["stages"].items():
        assert stage_info["status"] == "PASS"


def test_quantum_annealing_server_routes():
    from starlette.testclient import TestClient
    from desk_gateway.server import build_app

    app, _ = build_app()
    client = TestClient(app)

    # 1. Annealing solve route
    resp = client.post(
        "/v1/quantum/annealing/solve",
        json={
            "num_variables": 3,
            "Q_matrix": {
                "0,0": -1.0,
                "1,1": -1.0,
                "2,2": -1.0,
                "0,1": 1.5,
                "1,2": 1.5,
            },
            "num_sweeps": 25,
            "annealing_time_us": 10.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "solution" in data
    assert "ising" in data
    assert "receipt" in data
    assert "merkle_root" in data

    # 2. Anchor Export route
    resp_anchor = client.post("/v1/quantum/annealing/anchor/export")
    assert resp_anchor.status_code == 200
    data_anchor = resp_anchor.json()
    assert data_anchor["ok"] is True
    assert data_anchor["anchor"]["instruction"] == "record_quantum_annealing_root"
    assert data_anchor["anchor"]["data"]["total_receipts"] >= 1

    # 3. Drill Simulate route
    resp_drill = client.post("/v1/quantum/annealing/drill/simulate")
    assert resp_drill.status_code == 200
    data_drill = resp_drill.json()
    assert data_drill["ok"] is True
    assert data_drill["drill"]["all_passed"] is True
