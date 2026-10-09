"""Tests for Quantum Tensor Networks, Matrix Product States (MPS) & DMRG Mesh (Milestone v7.5 - Phases 116 & 117)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_tensor_network_mesh import (
    DMRGVariationalEngine,
    LatticeModelType,
    MatrixProductState,
    PEPS2DContractionEngine,
    QuantumTensorNetworkMesh,
    TensorNetworkConfig,
    TensorNetworkSimulationResult,
)
from desk_gateway.quantum_tensor_network_anchoring import (
    QuantumTensorMerkleLedger,
    QuantumTensorReceipt,
    QuantumTensorSolanaAnchorExporter,
    QuantumTensorVerificationDrill,
)
from desk_gateway.server import build_app


def test_tensor_network_exact_analytical_energies():
    config_ising = TensorNetworkConfig(
        n_sites=8,
        model_type=LatticeModelType.TRANSVERSE_ISENG,
        coupling_j=1.0,
        transverse_field_h=1.0,
    )
    engine_ising = DMRGVariationalEngine(config_ising)
    e0_ising = engine_ising.compute_exact_analytical_ground_energy()
    assert e0_ising < -8.0
    assert config_ising.is_critical_point is True

    config_xxx = TensorNetworkConfig(
        n_sites=8,
        model_type=LatticeModelType.HEISENBERG_XXX,
        coupling_j=1.0,
    )
    engine_xxx = DMRGVariationalEngine(config_xxx)
    e0_xxx = engine_xxx.compute_exact_analytical_ground_energy()
    assert e0_xxx < -3.0
    assert config_xxx.is_critical_point is False


def test_matrix_product_state_initialization_and_norm():
    config = TensorNetworkConfig(n_sites=6, max_bond_dim_chi=8)
    mps = MatrixProductState(config)
    assert len(mps.tensors) == 6
    assert mps.compute_norm() == pytest.approx(1.0, rel=1e-5)

    mps.canonicalize(center=3)
    assert mps.orthogonality_center == 3


def test_dmrg_variational_optimization_convergence():
    config = TensorNetworkConfig(
        n_sites=8,
        model_type=LatticeModelType.TRANSVERSE_ISENG,
        coupling_j=1.0,
        transverse_field_h=1.0,
        max_bond_dim_chi=16,
        dmrg_sweeps=4,
    )
    engine = DMRGVariationalEngine(config)
    result = engine.run_dmrg_optimization("test-dmrg-run")

    assert result.convergence_sweeps == 4
    assert len(result.sweep_history) == 4
    assert result.energy_relative_error < 0.05
    assert result.area_law_satisfied is True
    assert result.merkle_leaf_hash != ""

    # Verify monotonic convergence of energy
    energies = [s.energy_estimate for s in result.sweep_history]
    for i in range(len(energies) - 1):
        assert energies[i + 1] <= energies[i]


def test_peps_2d_boundary_mps_contraction():
    engine = PEPS2DContractionEngine(lx=4, ly=4, bond_dim_d=2)
    res = engine.contract_boundary_mps(max_boundary_chi=8)

    assert res["boundary_perimeter"] == 16
    assert res["boundary_mps_bond_dim"] == 8
    assert res["2d_boundary_entropy"] > 0.0
    assert res["contraction_converged"] is True
    assert res["2d_area_law_verified"] is True


def test_quantum_tensor_merkle_ledger_and_inclusion_proofs():
    ledger = QuantumTensorMerkleLedger()
    receipt1 = QuantumTensorReceipt(
        receipt_id="rcpt-01",
        operation_type="DMRG_GROUND_STATE",
        model_type="TRANSVERSE_ISING",
        ground_state_energy=-10.1532,
        energy_relative_error=0.0012,
        max_bond_dim=16,
        entanglement_entropy=0.552,
        area_law_satisfied=True,
        status="GROUND_STATE_CONVERGED",
        parameters_digest="0"*64,
    )
    receipt2 = QuantumTensorReceipt(
        receipt_id="rcpt-02",
        operation_type="PEPS_2D_CONTRACTION",
        model_type="PEPS_2D_LATTICE",
        ground_state_energy=0.0,
        energy_relative_error=0.0,
        max_bond_dim=8,
        entanglement_entropy=0.88,
        area_law_satisfied=True,
        status="PEPS_CONTRACTED",
        parameters_digest="1"*64,
    )

    ledger.append_receipt(receipt1)
    ledger.append_receipt(receipt2)

    root = ledger.get_merkle_root()
    assert len(root) == 64

    proof0 = ledger.get_proof(0)
    assert QuantumTensorMerkleLedger.verify_proof(receipt1.compute_hash(), proof0, root) is True

    proof1 = ledger.get_proof(1)
    assert QuantumTensorMerkleLedger.verify_proof(receipt2.compute_hash(), proof1, root) is True


def test_quantum_tensor_solana_anchor_exporter():
    receipt = QuantumTensorReceipt(
        receipt_id="rcpt-solana-01",
        operation_type="DMRG_GROUND_STATE",
        model_type="TRANSVERSE_ISING",
        ground_state_energy=-10.1532,
        energy_relative_error=0.0012,
        max_bond_dim=16,
        entanglement_entropy=0.552,
        area_law_satisfied=True,
        status="GROUND_STATE_CONVERGED",
        parameters_digest="0"*64,
    )
    program_src = QuantumTensorSolanaAnchorExporter.generate_anchor_program()
    assert "quantum_tensor_anchor" in program_src
    assert "RecordTensorVerification" in program_src
    assert "Ten5orNetw0rk111111111111111111111111111111111" in program_src

    payload = QuantumTensorSolanaAnchorExporter.generate_instruction_payload(
        merkle_root="f"*64,
        receipt=receipt,
        proof=[("right", "a"*64)],
    )
    assert payload["instruction"] == "record_tensor_verification"
    assert payload["args"]["energy_rel_error_bps"] == 12
    assert payload["args"]["bond_dimension"] == 16
    assert payload["args"]["area_law_satisfied"] is True


def test_quantum_tensor_5_stage_verification_drill():
    drill = QuantumTensorVerificationDrill()
    res = drill.run_all_stages()
    assert res["overall_status"] == "ALL_STAGES_PASSED"
    assert len(res["stages"]) == 5
    for st in res["stages"]:
        assert st["status"] == "PASSED"


def test_quantum_tensor_gateway_rest_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. DMRG Simulate
    res_dmrg = client.post(
        "/v1/quantum/tensor/dmrg/simulate",
        json={
            "experiment_id": "test-exp-gw-01",
            "n_sites": 8,
            "model_type": "TRANSVERSE_ISING",
            "coupling_j": 1.0,
            "transverse_field_h": 1.0,
            "max_bond_dim_chi": 16,
            "sweeps": 4,
        },
    )
    assert res_dmrg.status_code == 200
    data_dmrg = res_dmrg.json()
    assert data_dmrg["ok"] is True
    assert data_dmrg["simulation"]["area_law_satisfied"] is True
    assert len(data_dmrg["merkle_root"]) == 64

    # 2. PEPS Contract
    res_peps = client.post(
        "/v1/quantum/tensor/peps/contract",
        json={
            "lx": 4,
            "ly": 4,
            "bond_dim": 2,
            "boundary_chi": 8,
        },
    )
    assert res_peps.status_code == 200
    data_peps = res_peps.json()
    assert data_peps["ok"] is True
    assert data_peps["contraction"]["contraction_converged"] is True

    # 3. Anchor Export
    res_anchor = client.post("/v1/quantum/tensor/anchor/export")
    assert res_anchor.status_code == 200
    data_anchor = res_anchor.json()
    assert data_anchor["ok"] is True
    assert "anchor" in data_anchor
    assert "program" in data_anchor

    # 4. Drill Simulate
    res_drill = client.post("/v1/quantum/tensor/drill/simulate")
    assert res_drill.status_code == 200
    data_drill = res_drill.json()
    assert data_drill["ok"] is True
    assert data_drill["drill"]["overall_status"] == "ALL_STAGES_PASSED"
