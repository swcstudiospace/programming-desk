"""Unit and Integration Tests for Continuous-Variable QKD (CV-QKD) & Gaussian Modulation Mesh (v7.0 - Phases 106 & 107)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_cvqkd_mesh import (
    CVQKDChannelEstimator,
    CVQKDMesh,
    ChannelParameters,
    DetectionMode,
    GG02ProtocolEngine,
    GaussianCoherentState,
    HolevoInformationEvaluator,
    QuadratureType,
)
from desk_gateway.quantum_cvqkd_anchoring import (
    CVQKDMerkleLedger,
    CVQKDReceipt,
    CVQKDSolanaAnchorExporter,
    CVQKDVerificationDrill,
)
from desk_gateway.server import build_app


def test_gaussian_coherent_state_creation():
    state = GaussianCoherentState(
        state_id="state-test-1",
        q=1.25,
        p=-0.85,
        shot_noise_variance=1.0,
        modulation_variance=4.0,
    )
    d = state.to_dict()
    assert d["state_id"] == "state-test-1"
    assert d["q"] == 1.25
    assert d["p"] == -0.85
    assert d["shot_noise_variance"] == 1.0


def test_channel_parameters():
    params = ChannelParameters(
        fiber_length_km=10.0,
        attenuation_db_per_km=0.2,
        excess_noise_xi=0.01,
        detector_efficiency_eta=0.7,
    )
    # T = 10^(-2.0 / 10) = 10^(-0.2) ~ 0.630957
    assert 0.60 <= params.channel_transmittance <= 0.65
    assert 0.40 <= params.total_transmittance <= 0.46
    assert params.total_noise_referred_to_input > 0.0


def test_gg02_protocol_engine_homodyne():
    engine = GG02ProtocolEngine(
        modulation_variance_va=4.0,
        channel_params=ChannelParameters(fiber_length_km=5.0),
        detection_mode=DetectionMode.HOMODYNE,
    )
    states = engine.generate_alice_states(num_states=100)
    assert len(states) == 100

    alice_logs, bob_meas = engine.transmit_and_detect(states)
    assert len(alice_logs) == 100
    assert len(bob_meas) == 100
    for m in bob_meas:
        assert m["quadrature"] in [QuadratureType.Q.value, QuadratureType.P.value]
        assert isinstance(m["measured_value"], float)


def test_gg02_protocol_engine_heterodyne():
    engine = GG02ProtocolEngine(
        modulation_variance_va=4.0,
        channel_params=ChannelParameters(fiber_length_km=5.0),
        detection_mode=DetectionMode.HETERODYNE,
    )
    states = engine.generate_alice_states(num_states=50)
    alice_logs, bob_meas = engine.transmit_and_detect(states)
    assert len(bob_meas) == 50
    for m in bob_meas:
        assert m["quadrature"] == "HETERODYNE_QP"
        assert "measured_q" in m
        assert "measured_p" in m


def test_holevo_information_evaluator():
    i_ab, chi_be, rate = HolevoInformationEvaluator.compute_asymptotic_secret_key_rate(
        v_a=4.0,
        transmittance=0.63,
        excess_noise=0.005,
        beta=0.95,
        detection_mode=DetectionMode.HOMODYNE,
    )
    assert i_ab > 0.0
    assert chi_be >= 0.0
    assert rate > 0.0


def test_cvqkd_channel_estimator():
    estimator = CVQKDChannelEstimator()
    # Mock data with sqrt(T)=0.8 (T=0.64)
    alice_data = [float(i) for i in range(-50, 50)]
    bob_data = [0.8 * x for x in alice_data]
    est = estimator.estimate_channel(alice_data, bob_data)
    assert 0.60 <= est["transmittance_est"] <= 0.68
    assert est["snr"] > 1.0


def test_cvqkd_mesh_full_session():
    mesh = CVQKDMesh()
    res = mesh.run_cv_qkd_session(
        session_id="test-session-100",
        num_pulses=1500,
        modulation_va=4.0,
        fiber_length_km=5.0,
        excess_noise=0.008,
        detection_mode=DetectionMode.HOMODYNE,
        beta=0.95,
    )
    assert res.session_id == "test-session-100"
    assert res.pulses_transmitted == 1500
    assert res.channel_transmittance_estimated > 0.0
    assert res.asymptotic_secret_key_rate > 0.0
    assert res.total_distilled_key_bits > 0
    assert res.security_verified is True
    assert res.reconciliation_passed is True


def test_cvqkd_merkle_ledger_and_proofs():
    ledger = CVQKDMerkleLedger()
    r1 = CVQKDReceipt(
        receipt_id="rcpt-test-1",
        session_id="sess-1",
        detection_mode="HOMODYNE",
        pulses_transmitted=1000,
        transmittance_estimated=0.63,
        excess_noise_estimated=0.005,
        mutual_information_i_ab=1.2,
        holevo_bound_chi_be=0.4,
        secret_key_rate=0.74,
        distilled_key_bits=740,
        security_verified=True,
        channel_params_hash="hash_param_1",
    )
    r2 = CVQKDReceipt(
        receipt_id="rcpt-test-2",
        session_id="sess-2",
        detection_mode="HETERODYNE",
        pulses_transmitted=2000,
        transmittance_estimated=0.55,
        excess_noise_estimated=0.010,
        mutual_information_i_ab=1.1,
        holevo_bound_chi_be=0.5,
        secret_key_rate=0.54,
        distilled_key_bits=1080,
        security_verified=True,
        channel_params_hash="hash_param_2",
    )

    leaf1 = ledger.append_receipt(r1)
    leaf2 = ledger.append_receipt(r2)
    root = ledger.get_merkle_root()

    assert root != ""
    assert len(ledger.receipts) == 2

    proof0 = ledger.get_proof(0)
    assert CVQKDMerkleLedger.verify_proof(leaf1, proof0, root) is True

    proof1 = ledger.get_proof(1)
    assert CVQKDMerkleLedger.verify_proof(leaf2, proof1, root) is True


def test_cvqkd_solana_anchor_exporter():
    program = CVQKDSolanaAnchorExporter.generate_anchor_program()
    assert "cv_qkd_anchoring" in program
    assert CVQKDSolanaAnchorExporter.PROGRAM_ID in program

    rcpt = CVQKDReceipt(
        receipt_id="rcpt-anchor-test",
        session_id="sess-anchor",
        detection_mode="HOMODYNE",
        pulses_transmitted=1000,
        transmittance_estimated=0.63,
        excess_noise_estimated=0.005,
        mutual_information_i_ab=1.2,
        holevo_bound_chi_be=0.4,
        secret_key_rate=0.74,
        distilled_key_bits=740,
        security_verified=True,
        channel_params_hash="dummy_hash",
    )
    payload = CVQKDSolanaAnchorExporter.generate_instruction_payload(
        merkle_root="abc123root",
        receipt=rcpt,
        proof=[{"position": "right", "hash": "def456"}],
    )
    assert payload["program_id"] == CVQKDSolanaAnchorExporter.PROGRAM_ID
    assert payload["parameters"]["secret_key_rate_bps"] == 7400
    assert payload["parameters"]["excess_noise_bps"] == 50


def test_cvqkd_verification_drill():
    drill = CVQKDVerificationDrill()
    res = drill.run_all_stages()
    assert res["all_passed"] is True
    assert res["stage_1_state_generation"]["passed"] is True
    assert res["stage_2_channel_and_parameter_estimation"]["passed"] is True
    assert res["stage_3_holevo_bound_and_key_rate"]["passed"] is True
    assert res["stage_4_merkle_ledger_proofs"]["passed"] is True
    assert res["stage_5_solana_anchor_export"]["passed"] is True


def test_server_cvqkd_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Test Holevo evaluation endpoint
    resp = client.post(
        "/v1/quantum/cvqkd/holevo/evaluate",
        json={
            "modulation_va": 4.0,
            "transmittance": 0.63,
            "excess_noise": 0.005,
            "beta": 0.95,
            "detection_mode": "HOMODYNE",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["asymptotic_secret_key_rate"] > 0.0
    assert data["secure"] is True

    # 2. Test CV-QKD Session Run endpoint
    resp2 = client.post(
        "/v1/quantum/cvqkd/session/run",
        json={
            "session_id": "test-http-cvqkd",
            "num_pulses": 1500,
            "modulation_va": 4.0,
            "fiber_length_km": 8.0,
            "excess_noise": 0.008,
            "detection_mode": "HOMODYNE",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ok"] is True
    assert data2["session"]["security_verified"] is True
    assert "merkle_root" in data2

    # 3. Test Solana Anchor Export endpoint
    resp3 = client.post("/v1/quantum/cvqkd/anchor/export")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["ok"] is True
    assert "anchor" in data3
    assert "program" in data3

    # 4. Test Automated Drill endpoint
    resp4 = client.post("/v1/quantum/cvqkd/drill/simulate")
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert data4["ok"] is True
    assert data4["drill"]["all_passed"] is True
