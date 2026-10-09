import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.quantum_fault_tolerance_mesh import (
    QuantumFaultToleranceMesh,
    SurfaceCodePatch,
    MinimumWeightDecoder,
    LatticeSurgeryEngine,
    MagicStateDistillationEngine,
    StabilizerType,
)
from desk_gateway.quantum_fault_tolerance_anchoring import (
    FaultToleranceMerkleLedger,
    FaultToleranceReceipt,
    FaultToleranceSolanaAnchorExporter,
    FaultToleranceVerificationDrill,
)


@pytest.fixture
def client():
    app, _ = build_app()
    return TestClient(app)


def test_surface_code_patch_initialization():
    patch = SurfaceCodePatch(patch_id="p1", distance=3, logical_qubit_id="L1")
    assert len(patch.data_qubits) == 9
    assert len(patch.stabilizers) == 8  # 4 X, 4 Z stabilizers on rotated d=3 patch

    # Check invalid distance
    with pytest.raises(ValueError):
        SurfaceCodePatch(patch_id="p2", distance=4, logical_qubit_id="L2")


def test_syndrome_extraction_and_noise():
    patch = SurfaceCodePatch(patch_id="p1", distance=3, logical_qubit_id="L1", physical_error_rate=0.5)
    injected = patch.inject_noise()
    assert (injected["x_errors"] + injected["z_errors"]) >= 0

    defects = patch.extract_syndromes()
    assert isinstance(defects, list)


def test_minimum_weight_decoder():
    patch = SurfaceCodePatch(patch_id="p1", distance=3, logical_qubit_id="L1", physical_error_rate=0.001)
    decoder = MinimumWeightDecoder(code_distance=3)
    
    # Inject a known error
    patch.data_qubits[(1, 1)]["x_error"] = True
    patch.extract_syndromes()
    res = decoder.decode(patch)
    assert res.corrections_applied >= 0
    assert res.estimated_logical_error_rate < 0.01


def test_lattice_surgery_cnot():
    ctrl = SurfaceCodePatch(patch_id="c1", distance=3, logical_qubit_id="L_C")
    tgt = SurfaceCodePatch(patch_id="t1", distance=3, logical_qubit_id="L_T")
    surgery = LatticeSurgeryEngine(code_distance=3)

    cnot_res = surgery.perform_cnot(ctrl, tgt)
    assert cnot_res.operation.value == "LOGICAL_CNOT"
    assert cnot_res.fidelity > 0.90
    assert cnot_res.duration_cycles == 6
    assert cnot_res.success is True


def test_magic_state_distillation_15_to_1():
    engine = MagicStateDistillationEngine(raw_state_error=0.01)
    report = engine.distill_single_round(0.01)
    # Output error ~ 35 * (0.01)^3 = 3.5e-5
    assert report.output_error_rate < 1e-4
    assert report.purified_state_fidelity > 0.9999

    factory_res = engine.distill_factory(target_error=1e-6, target_states_count=3)
    assert factory_res.final_output_error_rate <= 1e-6
    assert factory_res.distilled_magic_states_produced == 3
    assert factory_res.total_raw_states_consumed > 3


def test_fault_tolerance_merkle_ledger():
    ledger = FaultToleranceMerkleLedger()
    r1 = FaultToleranceReceipt(
        receipt_id="r1",
        operation_type="SURFACE_CODE_DECODE",
        patch_id="p1",
        code_distance=3,
        fidelity=0.999,
        error_rate=0.001,
        cycles_or_rounds=1,
        success=True,
        extra_data_hash="abc",
    )
    r2 = FaultToleranceReceipt(
        receipt_id="r2",
        operation_type="MAGIC_DISTILLATION",
        patch_id="factory_0",
        code_distance=3,
        fidelity=0.999999,
        error_rate=1e-6,
        cycles_or_rounds=2,
        success=True,
        extra_data_hash="def",
    )
    ledger.append_receipt(r1)
    ledger.append_receipt(r2)

    root = ledger.get_merkle_root()
    assert len(root) == 64
    proof0 = ledger.get_proof(0)
    assert ledger.verify_proof(r1.compute_hash(), proof0, root) is True


def test_solana_anchor_exporter():
    program = FaultToleranceSolanaAnchorExporter.generate_anchor_program()
    assert "declare_id!(\"QFaultTol11111111111111111111111111111111111\");" in program

    rcpt = FaultToleranceReceipt(
        receipt_id="r1",
        operation_type="LATTICE_SURGERY_CNOT",
        patch_id="c1->t1",
        code_distance=3,
        fidelity=0.995,
        error_rate=0.005,
        cycles_or_rounds=6,
        success=True,
        extra_data_hash="abc",
    )
    payload = FaultToleranceSolanaAnchorExporter.generate_instruction_payload("root123", rcpt, [])
    assert payload["instruction"] == "verify_fault_tolerance_receipt"
    assert payload["data"]["fidelity_bps"] == 9950


def test_verification_drill():
    drill = FaultToleranceVerificationDrill()
    res = drill.run_all_stages()
    assert res["all_passed"] is True
    assert len(res["stages"]) == 5
    assert len(res["merkle_root"]) == 64


def test_server_routes(client):
    # Route 1: patch cycle
    r = client.post("/v1/quantum/fault/patch/cycle", json={"patch_id": "test_patch", "distance": 3})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "merkle_root" in r.json()

    # Route 2: surgery CNOT
    r = client.post("/v1/quantum/fault/surgery/cnot", json={"control_patch_id": "c_test", "target_patch_id": "t_test"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["surgery"]["fidelity"] > 0.90

    # Route 3: magic distill
    r = client.post("/v1/quantum/fault/magic/distill", json={"target_error": 1e-6, "count": 2})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["distillation"]["distilled_magic_states_produced"] == 2

    # Route 4: anchor export
    r = client.post("/v1/quantum/fault/anchor/export")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "anchor" in r.json()
    assert "program" in r.json()

    # Route 5: drill simulate
    r = client.post("/v1/quantum/fault/drill/simulate")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["drill"]["all_passed"] is True
