"""Unit and integration tests for Quantum Counterfactual Communication & Ghost Imaging Mesh (Milestone v6.9 - Phases 104 & 105)."""

import json
import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_counterfactual_mesh import (
    CounterfactualDirectCommunication,
    GhostImageReconstruction,
    InteractionFreeMeasurement,
    QuantumCounterfactualMesh,
    QuantumGhostImagingEngine,
)
from desk_gateway.quantum_counterfactual_anchoring import (
    QuantumCounterfactualMerkleLedger,
    QuantumCounterfactualReceipt,
    QuantumCounterfactualSolanaAnchorExporter,
    QuantumCounterfactualVerificationDrill,
)
from desk_gateway.server import build_app


def test_interaction_free_measurement_elitzur_vaidman():
    engine = InteractionFreeMeasurement(default_zeno_cycles=40)
    
    # Test without object
    res_no_obj = engine.elitzur_vaidman_single_stage(object_present=False)
    assert not res_no_obj.object_present
    assert not res_no_obj.photon_absorbed
    assert res_no_obj.counterfactual_efficiency == 1.0

    # Test with object present across multiple trials
    absorbed_count = 0
    detected_count = 0
    inconclusive_count = 0
    trials = 1000

    for _ in range(trials):
        res = engine.elitzur_vaidman_single_stage(object_present=True)
        assert res.object_present
        if res.photon_absorbed:
            absorbed_count += 1
        elif res.detection_successful:
            detected_count += 1
        else:
            inconclusive_count += 1

    # Theoretical probabilities: 50% absorbed, 25% detected dark port, 25% inconclusive
    assert 400 < absorbed_count < 600
    assert 180 < detected_count < 320
    assert 180 < inconclusive_count < 320


def test_chained_quantum_zeno_efficiency():
    engine = InteractionFreeMeasurement()
    
    # 50 cycles: theoretical survival cos(pi/100)^100 ~ 97.5%
    res = engine.chained_zeno_interrogation(object_present=True, cycles=50)
    assert res.object_present
    assert res.zeno_cycles == 50
    assert res.counterfactual_efficiency >= 0.85
    assert res.channel_leakage_probability <= 0.15


def test_counterfactual_direct_communication():
    comm = CounterfactualDirectCommunication(outer_cycles=20, inner_cycles=20)
    msg = "1011001"
    res = comm.transmit_message(msg)

    assert res.message_bits == msg
    assert len(res.received_bits) == len(msg)
    assert res.counterfactual_purity >= 0.85
    assert res.channel_traversed_photons <= len(msg) * 0.20
    assert res.bit_error_rate < 0.25


def test_quantum_ghost_imaging_reconstruction():
    engine = QuantumGhostImagingEngine(default_resolution=(8, 8))
    target = engine.create_synthetic_target("cross", (8, 8))
    assert len(target) == 8
    assert len(target[0]) == 8

    recon = engine.simulate_ghost_imaging(pattern_name="cross", resolution=(8, 8), photon_pairs=4000)
    assert recon.resolution == (8, 8)
    assert recon.pattern_name == "cross"
    assert recon.visibility >= 0.50
    assert recon.snr_db >= 5.0
    assert recon.total_photon_pairs == 4000
    assert len(recon.reconstructed_matrix) == 8


def test_quantum_counterfactual_merkle_ledger():
    ledger = QuantumCounterfactualMerkleLedger()
    r1 = QuantumCounterfactualReceipt(
        receipt_id="r1",
        operation_type="INTERACTION_FREE_MEASUREMENT",
        channel_id="chan-zeno",
        purity_or_efficiency=0.97,
        channel_leakage=0.03,
        cycles_or_photons=50,
        success=True,
        spatial_contrast=0.0,
        extra_data_hash="abc",
    )
    r2 = QuantumCounterfactualReceipt(
        receipt_id="r2",
        operation_type="COUNTERFACTUAL_COMMUNICATION",
        channel_id="chan-comm",
        purity_or_efficiency=0.98,
        channel_leakage=0.02,
        cycles_or_photons=16,
        success=True,
        spatial_contrast=0.0,
        extra_data_hash="def",
    )

    ledger.append_receipt(r1)
    ledger.append_receipt(r2)

    root = ledger.get_merkle_root()
    assert len(root) == 64

    proof = ledger.get_proof(1)
    valid = QuantumCounterfactualMerkleLedger.verify_proof(r2.compute_hash(), proof, root)
    assert valid


def test_quantum_counterfactual_solana_anchor_export():
    ledger = QuantumCounterfactualMerkleLedger()
    r = QuantumCounterfactualReceipt(
        receipt_id="r-export",
        operation_type="GHOST_IMAGING",
        channel_id="ghost-spdc",
        purity_or_efficiency=0.95,
        channel_leakage=0.05,
        cycles_or_photons=2000,
        success=True,
        spatial_contrast=0.85,
        extra_data_hash="123",
    )
    ledger.append_receipt(r)
    root = ledger.get_merkle_root()
    proof = ledger.get_proof(0)

    payload = QuantumCounterfactualSolanaAnchorExporter.generate_instruction_payload(root, r, proof)
    assert payload["program_id"] == QuantumCounterfactualSolanaAnchorExporter.PROGRAM_ID
    assert payload["parameters"]["purity_bps"] == 9500
    assert payload["parameters"]["spatial_contrast_bps"] == 8500

    program = QuantumCounterfactualSolanaAnchorExporter.generate_anchor_program()
    assert "declare_id!" in program
    assert "CounterfactualError::PurityTooLow" in program


def test_quantum_counterfactual_verification_drill():
    drill = QuantumCounterfactualVerificationDrill()
    summary = drill.run_all_stages()

    assert summary["all_passed"] is True
    assert summary["stage_1_interaction_free_measurement"]["passed"] is True
    assert summary["stage_2_counterfactual_communication"]["passed"] is True
    assert summary["stage_3_ghost_imaging"]["passed"] is True
    assert summary["stage_4_merkle_ledger_proofs"]["passed"] is True
    assert summary["stage_5_solana_anchor_export"]["passed"] is True


def test_counterfactual_gateway_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Test IFM interrogate route
    resp = client.post("/v1/quantum/counterfactual/ifm/interrogate", json={"object_present": True, "cycles": 40})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "measurement" in data
    assert "receipt" in data
    assert len(data["merkle_root"]) == 64

    # 2. Test counterfactual direct transmit route
    resp = client.post("/v1/quantum/counterfactual/direct/transmit", json={"message_bits": "10011"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["transmission"]["message_bits"] == "10011"
    assert data["receipt"]["operation_type"] == "COUNTERFACTUAL_COMMUNICATION"

    # 3. Test ghost imaging reconstruction route
    resp = client.post("/v1/quantum/counterfactual/ghost/reconstruct", json={"pattern_name": "slit", "photon_pairs": 2500})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["reconstruction"]["pattern_name"] == "slit"
    assert data["receipt"]["operation_type"] == "GHOST_IMAGING"

    # 4. Test anchor export route
    resp = client.post("/v1/quantum/counterfactual/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "anchor" in data
    assert "program" in data

    # 5. Test drill simulation route
    resp = client.post("/v1/quantum/counterfactual/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["drill"]["all_passed"] is True
