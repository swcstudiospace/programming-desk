"""Tests for Quantum State Tomography (QST) & Randomized Benchmarking (RB) Mesh (Milestone v7.2 - Phases 110 & 111)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_tomography_mesh import (
    DensityMatrix,
    QSTMeasurementCount,
    QSTResult,
    QuantumStateTomographyEngine,
    QuantumTomographyBenchmarkingMesh,
    RBResult,
    RandomizedBenchmarkingEngine,
)
from desk_gateway.quantum_tomography_anchoring import (
    QuantumTomographyMerkleLedger,
    QuantumTomographyReceipt,
    QuantumTomographySolanaAnchorExporter,
    QuantumTomographyVerificationDrill,
)
from desk_gateway.server import build_app


def test_qst_density_matrix_properties():
    engine = QuantumStateTomographyEngine()
    bell_rho = engine.create_bell_state_density_matrix("phi_plus")
    assert bell_rho.num_qubits == 2
    assert bell_rho.dimension == 4
    # Trace should be 1.0
    tr = bell_rho.trace()
    assert abs(tr.real - 1.0) < 1e-6
    assert abs(tr.imag) < 1e-6
    # Pure state purity Tr(rho^2) == 1.0
    assert abs(bell_rho.purity() - 1.0) < 1e-6

    # Apply depolarizing noise
    depol_rho = engine.apply_depolarizing_channel(bell_rho, depolarizing_p=0.2)
    assert depol_rho.purity() < 1.0
    assert abs(depol_rho.trace().real - 1.0) < 1e-6


def test_qst_measurement_and_mle_reconstruction():
    engine = QuantumStateTomographyEngine()
    # 1-qubit |+> state
    inv_sqrt2 = 1.0 / (2.0 ** 0.5)
    plus_rho = engine.create_pure_state_density_matrix([complex(inv_sqrt2, 0), complex(inv_sqrt2, 0)])

    measurements = engine.simulate_tomography_measurements(
        rho=plus_rho,
        shots_per_basis=2000,
        depolarizing_noise=0.01,
        seed=42,
    )
    assert len(measurements) == 3  # X, Y, Z
    for m in measurements:
        assert m.total_shots == 2000
        assert sum(m.outcome_counts.values()) == 2000

    result = engine.reconstruct_maximum_likelihood(
        measurements=measurements,
        num_qubits=1,
        max_iterations=100,
        target_rho=plus_rho,
    )
    assert result.fidelity >= 0.95
    assert result.trace_distance <= 0.15
    assert result.is_positive_semidefinite
    assert result.purity >= 0.90
    assert result.mle_converged


def test_randomized_benchmarking_simulation():
    rb_engine = RandomizedBenchmarkingEngine()
    res = rb_engine.simulate_rb_experiment(
        clifford_lengths=[1, 2, 4, 8, 16],
        sequences_per_length=15,
        shots_per_sequence=800,
        depolarizing_error_per_gate=0.003,
        seed=101,
    )
    assert res.num_qubits == 1
    assert len(res.clifford_lengths) == 5
    assert len(res.survival_probabilities) == 5
    # Decays over sequence length
    assert res.survival_probabilities[0] > res.survival_probabilities[-1]
    assert res.average_gate_fidelity >= 0.98
    assert res.error_per_clifford <= 0.02
    assert res.r_squared >= 0.70


def test_tomography_merkle_ledger_and_anchor():
    ledger = QuantumTomographyMerkleLedger()
    rcpt1 = QuantumTomographyReceipt(
        receipt_id="rcpt-1",
        benchmark_type="STATE_TOMOGRAPHY",
        num_qubits=2,
        fidelity=0.985,
        error_metric=0.03,
        purity=0.97,
        mle_converged=True,
        status="VERIFIED",
        parameters_digest="hash1",
    )
    rcpt2 = QuantumTomographyReceipt(
        receipt_id="rcpt-2",
        benchmark_type="RANDOMIZED_BENCHMARKING",
        num_qubits=1,
        fidelity=0.998,
        error_metric=0.002,
        purity=1.0,
        mle_converged=True,
        status="CALIBRATED",
        parameters_digest="hash2",
    )
    ledger.append_receipt(rcpt1)
    ledger.append_receipt(rcpt2)

    root = ledger.get_merkle_root()
    assert len(root) == 64

    proof0 = ledger.get_proof(0)
    assert QuantumTomographyMerkleLedger.verify_proof(rcpt1.compute_hash(), proof0, root)

    payload = QuantumTomographySolanaAnchorExporter.generate_instruction_payload(
        merkle_root=root,
        receipt=rcpt1,
        proof=proof0,
    )
    assert payload["program_id"] == QuantumTomographySolanaAnchorExporter.PROGRAM_ID
    assert payload["data"]["fidelity_bps"] == 9850

    program = QuantumTomographySolanaAnchorExporter.generate_anchor_program()
    assert "quantum_tomography_mesh" in program
    assert "verify_quantum_calibration_receipt" in program


def test_tomography_verification_drill():
    drill = QuantumTomographyVerificationDrill()
    res = drill.run_all_stages()
    assert res["all_passed"] is True
    stages = res["stages"]
    assert stages["stage1_state_prep_measurement"] is True
    assert stages["stage2_mle_reconstruction"] is True
    assert stages["stage3_rb_sequence_decay"] is True
    assert stages["stage4_gate_fidelity_and_epc"] is True
    assert stages["stage5_anchor_merkle_audit"] is True


def test_gateway_quantum_tomography_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. State Tomography POST /v1/quantum/tomography/qst/run
    qst_payload = {
        "state_type": "bell_phi_plus",
        "shots_per_basis": 1000,
        "depolarizing_noise": 0.01,
        "seed": 42,
    }
    resp = client.post("/v1/quantum/tomography/qst/run", json=qst_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["tomography"]["fidelity"] >= 0.90
    assert "density_matrix" in data["tomography"]
    assert data["receipt"]["benchmark_type"] == "STATE_TOMOGRAPHY"
    assert len(data["merkle_root"]) == 64

    # 2. Randomized Benchmarking POST /v1/quantum/tomography/rb/run
    rb_payload = {
        "clifford_lengths": [1, 2, 4, 8],
        "depolarizing_error": 0.003,
        "seed": 99,
    }
    resp2 = client.post("/v1/quantum/tomography/rb/run", json=rb_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ok"] is True
    assert data2["benchmarking"]["average_gate_fidelity"] >= 0.95
    assert data2["receipt"]["benchmark_type"] == "RANDOMIZED_BENCHMARKING"

    # 3. Anchor Export POST /v1/quantum/tomography/anchor/export
    resp3 = client.post("/v1/quantum/tomography/anchor/export", json={})
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["ok"] is True
    assert "anchor" in data3
    assert "program" in data3
    assert data3["anchor"]["program_id"] == QuantumTomographySolanaAnchorExporter.PROGRAM_ID

    # 4. Drill Simulation POST /v1/quantum/tomography/drill/simulate
    resp4 = client.post("/v1/quantum/tomography/drill/simulate", json={})
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert data4["ok"] is True
    assert data4["drill"]["all_passed"] is True
