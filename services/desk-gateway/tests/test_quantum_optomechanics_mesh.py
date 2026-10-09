"""Tests for Quantum Coherent Optomechanics & Phononic Cavity Routing Mesh (Milestone v7.3 - Phases 112 & 113)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_optomechanics_mesh import (
    CoherentOptomechanicsEngine,
    OptomechanicalCavityParams,
    OptomechanicalState,
    PhononicCavityRoutingEngine,
    PhononicRoutingResult,
    QuantumOptomechanicsMesh,
    SidebandDetuningMode,
)
from desk_gateway.quantum_optomechanics_anchoring import (
    QuantumOptomechanicsMerkleLedger,
    QuantumOptomechanicsReceipt,
    QuantumOptomechanicsSolanaAnchorExporter,
    QuantumOptomechanicsVerificationDrill,
)
from desk_gateway.server import build_app


def test_optomechanical_resolved_sideband_parameters():
    engine = CoherentOptomechanicsEngine()
    params = engine.params
    assert params.is_resolved_sideband is True
    assert params.omega_m_mhz == 50.0
    assert params.kappa_mhz == 2.0
    # Cryogenic thermal occupation
    n_th = params.thermal_phonon_occupation()
    assert n_th > 0.0


def test_sideband_cooling_and_ground_state_occupation():
    engine = CoherentOptomechanicsEngine()
    cooling_state = engine.simulate_interaction(
        mode=SidebandDetuningMode.RED_SIDEBAND_COOLING,
        laser_power_uw=60.0,
    )
    assert cooling_state.cooperativity > 1.0
    assert cooling_state.optical_damping_khz > 0.0
    # Red-detuned cooling brings mechanical motion into quantum ground state
    assert cooling_state.effective_phonon_occupation < 1.0
    assert cooling_state.ground_state_cooled is True
    assert cooling_state.state_transfer_fidelity > 0.70


def test_blue_sideband_amplification_and_squeezing():
    engine = CoherentOptomechanicsEngine()
    amp_state = engine.simulate_interaction(
        mode=SidebandDetuningMode.BLUE_SIDEBAND_AMPLIFY,
        laser_power_uw=40.0,
    )
    assert amp_state.optical_damping_khz < 0.0  # Parametric amplification / anti-damping
    assert amp_state.effective_phonon_occupation > 1.0

    sq_state = engine.simulate_interaction(
        mode=SidebandDetuningMode.RESONANT,
        laser_power_uw=80.0,
    )
    assert sq_state.ponderomotive_squeezing_db > 0.0


def test_phononic_cavity_routing_dijkstra():
    routing = PhononicCavityRoutingEngine()
    optomech = CoherentOptomechanicsEngine()

    result = routing.route_quantum_state("node-alpha", "node-delta", optomech)
    assert result.source_node == "node-alpha"
    assert result.destination_node == "node-delta"
    assert len(result.path) >= 3
    assert result.total_loss_db > 0.0
    assert result.end_to_end_fidelity > 0.70
    assert result.quantum_state_preserved is True


def test_optomechanics_merkle_ledger_and_proofs():
    ledger = QuantumOptomechanicsMerkleLedger()

    r1 = QuantumOptomechanicsReceipt(
        receipt_id="rcpt-01",
        operation_type="SIDEBAND_COOLING",
        cavity_or_route_id="node-alpha",
        cooperativity=85.0,
        effective_phonon_n=0.03,
        fidelity_or_efficiency=0.98,
        status="GROUND_STATE_COOLED",
        parameters_digest="hash01",
    )
    r2 = QuantumOptomechanicsReceipt(
        receipt_id="rcpt-02",
        operation_type="PHONONIC_ROUTING",
        cavity_or_route_id="qroute-alpha-delta",
        cooperativity=45.0,
        effective_phonon_n=0.08,
        fidelity_or_efficiency=0.88,
        status="ROUTED_OPTIMAL",
        parameters_digest="hash02",
    )

    ledger.append_receipt(r1)
    ledger.append_receipt(r2)

    root = ledger.get_merkle_root()
    assert len(root) == 64

    proof0 = ledger.get_proof(0)
    assert ledger.verify_proof(r1.compute_hash(), proof0, root) is True

    proof1 = ledger.get_proof(1)
    assert ledger.verify_proof(r2.compute_hash(), proof1, root) is True


def test_solana_anchor_exporter():
    ledger = QuantumOptomechanicsMerkleLedger()
    rcpt = QuantumOptomechanicsReceipt(
        receipt_id="rcpt-anchor-01",
        operation_type="SIDEBAND_COOLING",
        cavity_or_route_id="node-alpha",
        cooperativity=100.0,
        effective_phonon_n=0.02,
        fidelity_or_efficiency=0.96,
        status="GROUND_STATE_COOLED",
        parameters_digest="0" * 64,
    )
    ledger.append_receipt(rcpt)

    root = ledger.get_merkle_root()
    proof = ledger.get_proof(0)
    payload = QuantumOptomechanicsSolanaAnchorExporter.generate_instruction_payload(root, rcpt, proof)

    assert payload["program_id"] == QuantumOptomechanicsSolanaAnchorExporter.PROGRAM_ID
    assert payload["parameters"]["ground_state_verified"] is True
    assert payload["parameters"]["fidelity_scaled"] >= 7000

    anchor_code = QuantumOptomechanicsSolanaAnchorExporter.generate_anchor_program()
    assert "quantum_optomechanics_ledger" in anchor_code
    assert "OptomechError" in anchor_code


def test_optomechanics_5_stage_verification_drill():
    drill = QuantumOptomechanicsVerificationDrill()
    res = drill.run_all_stages()

    assert res["all_passed"] is True
    assert len(res["stages"]) == 5
    for stage in res["stages"]:
        assert stage["passed"] is True


def test_server_routes_quantum_optomechanics():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Cooling route
    res_cool = client.post("/v1/quantum/optomechanics/cooling/simulate", json={"cavity_id": "node-alpha", "laser_power_uw": 50.0})
    assert res_cool.status_code == 200
    data_cool = res_cool.json()
    assert data_cool["ok"] is True
    assert data_cool["state"]["ground_state_cooled"] is True
    assert "receipt" in data_cool

    # 2. Phononic routing route
    res_route = client.post("/v1/quantum/optomechanics/route/execute", json={"source_node": "node-alpha", "destination_node": "node-delta"})
    assert res_route.status_code == 200
    data_route = res_route.json()
    assert data_route["ok"] is True
    assert data_route["routing"]["quantum_state_preserved"] is True

    # 3. Anchor export route
    res_anchor = client.post("/v1/quantum/optomechanics/anchor/export", json={})
    assert res_anchor.status_code == 200
    data_anchor = res_anchor.json()
    assert data_anchor["ok"] is True
    assert "program" in data_anchor

    # 4. Drill route
    res_drill = client.post("/v1/quantum/optomechanics/drill/simulate", json={})
    assert res_drill.status_code == 200
    data_drill = res_drill.json()
    assert data_drill["ok"] is True
    assert data_drill["drill"]["all_passed"] is True
