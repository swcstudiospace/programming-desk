"""Tests for Quantum Non-Locality, Bell Inequality Violations & Device-Independent QKD (Milestone v6.7 - Phases 100 & 101)."""

import math
import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_nonlocality_mesh import (
    CHSHBellInequalityEngine,
    DeviceIndependentQKDEngine,
    DeviceIndependentRandomnessExpander,
    MultipartiteMerminGHZEngine,
    QuantumNonLocalityMesh,
)
from desk_gateway.quantum_nonlocality_anchoring import (
    QuantumNonLocalityMerkleLedger,
    QuantumNonLocalityReceipt,
    QuantumNonLocalitySolanaAnchorExporter,
    QuantumNonLocalityVerificationDrill,
)
from desk_gateway.server import build_app


def test_chsh_bell_inequality_violation() -> None:
    engine = CHSHBellInequalityEngine(rng_seed=42)
    # Ideal noise-free test
    summary = engine.run_chsh_test(num_trials=2500, noise_depolarizing=0.0)

    assert summary.quantum_violation
    assert summary.chsh_parameter_s > 2.2
    assert summary.chsh_parameter_s <= summary.tsirelson_bound + 0.1
    assert summary.classical_bound == 2.0
    assert summary.p_value_classical_refutation < 1e-4

    # Depolarizing noise reducing correlation below classical threshold
    noisy_summary = engine.run_chsh_test(num_trials=2500, noise_depolarizing=0.6)
    assert not noisy_summary.quantum_violation
    assert noisy_summary.chsh_parameter_s < 2.0


def test_ghz_mermin_multipartite_nonlocality() -> None:
    engine = MultipartiteMerminGHZEngine(rng_seed=42)
    summary = engine.run_mermin_test(num_trials_per_setting=600, noise_depolarizing=0.0)

    assert summary.quantum_violation
    # Ideal expectation is 4.0; empirical with 600 trials per setting should be close to 4.0 and > 3.0
    assert summary.mermin_operator_expectation > 3.2
    assert summary.mermin_operator_expectation <= 4.0
    assert summary.classical_bound == 2.0
    assert summary.quantum_bound == 4.0


def test_di_randomness_expansion() -> None:
    expander = DeviceIndependentRandomnessExpander()

    # When S = 2*sqrt(2), min-entropy is 1.0 bit per round
    h_max = expander.calculate_min_entropy(2.0 * math.sqrt(2.0))
    assert abs(h_max - 1.0) < 1e-5

    # When S <= 2.0, no certifiable randomness
    h_zero = expander.calculate_min_entropy(2.0)
    assert h_zero == 0.0

    # Intermediate CHSH violation S = 2.4
    h_mid = expander.calculate_min_entropy(2.4)
    assert 0.0 < h_mid < 1.0

    res = expander.expand_randomness(seed_bits="00110011", bell_s=2.8, num_expansion_rounds=500)
    assert res.min_entropy_per_bit > 0.7
    assert res.total_certified_random_bits > 350.0
    assert len(res.expanded_bits) == int(res.total_certified_random_bits)


def test_di_qkd_key_rate_and_session() -> None:
    di_engine = DeviceIndependentQKDEngine()

    # Rate calculation
    rate_optimal = di_engine.calculate_di_key_rate(bell_s=2.8284, qber=0.01)
    assert rate_optimal > 0.5

    rate_zero = di_engine.calculate_di_key_rate(bell_s=2.0, qber=0.01)
    assert rate_zero == 0.0

    rate_noisy = di_engine.calculate_di_key_rate(bell_s=2.2, qber=0.15)
    assert rate_noisy == 0.0

    # Execute session
    session_res = di_engine.execute_di_qkd_session(num_pairs=2000, noise_depolarizing=0.01)
    assert session_res.security_certified
    assert session_res.secret_key_rate > 0.0
    assert session_res.final_secure_key_length > 0
    assert len(session_res.secure_key_hex) > 0


def test_nonlocality_merkle_ledger_and_anchor() -> None:
    ledger = QuantumNonLocalityMerkleLedger()
    rcpt1 = QuantumNonLocalityReceipt(
        receipt_id="rcpt-chsh-test-1",
        test_type="CHSH_BELL",
        parameter_value=2.81,
        classical_bound=2.0,
        quantum_violation=True,
        num_trials=2000,
        p_value=1e-9,
        extra_data_hash="abc123hash",
    )
    rcpt2 = QuantumNonLocalityReceipt(
        receipt_id="rcpt-mermin-test-2",
        test_type="GHZ_MERMIN",
        parameter_value=3.95,
        classical_bound=2.0,
        quantum_violation=True,
        num_trials=1600,
        p_value=1e-12,
        extra_data_hash="def456hash",
    )

    ledger.add_receipt(rcpt1)
    ledger.add_receipt(rcpt2)

    root = ledger.get_merkle_root()
    assert len(root) == 64
    assert ledger.verify_ledger_integrity()

    payload = QuantumNonLocalitySolanaAnchorExporter.generate_instruction_payload(
        merkle_root=root,
        num_receipts=len(ledger.receipts),
        mean_chsh_s=2.81,
        certified_random_bits=850.0,
        di_key_rate=0.35,
    )
    assert payload["program_id"] == QuantumNonLocalitySolanaAnchorExporter.ANCHOR_PROGRAM_ID
    assert payload["data"]["merkle_root"] == root
    assert payload["data"]["mean_chsh_s_scaled"] == 28100
    assert "anchor_nonlocality_di_root" in payload["instruction"]

    program = QuantumNonLocalitySolanaAnchorExporter.export_anchor_program()
    assert "declare_id!" in program
    assert "mean_chsh_s_scaled" in program
    assert "TsirelsonBoundExceeded" in program


def test_nonlocality_verification_drill() -> None:
    drill = QuantumNonLocalityVerificationDrill(rng_seed=42)
    drill_res = drill.run_drill()

    assert drill_res["all_passed"]
    assert len(drill_res["stages"]) == 5
    for stage_key, stage_info in drill_res["stages"].items():
        assert stage_info["passed"], f"Stage {stage_key} failed: {stage_info}"
    assert len(drill_res["merkle_root"]) == 64


def test_nonlocality_api_endpoints() -> None:
    app, _ = build_app()
    client = TestClient(app)

    # 1. CHSH evaluation
    resp = client.post("/v1/quantum/nonlocality/chsh", json={"num_trials": 1500, "noise_depolarizing": 0.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["chsh"]["quantum_violation"]
    assert data["chsh"]["chsh_parameter_s"] > 2.2
    assert len(data["merkle_root"]) == 64

    # 2. GHZ Mermin evaluation
    resp = client.post("/v1/quantum/nonlocality/mermin", json={"num_trials_per_setting": 300, "noise_depolarizing": 0.0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["mermin"]["quantum_violation"]
    assert data["mermin"]["mermin_operator_expectation"] > 3.0

    # 3. DI Randomness expansion
    resp = client.post(
        "/v1/quantum/nonlocality/randomness/expand",
        json={"seed_bits": "11001100", "bell_s": 2.82, "num_rounds": 500},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["randomness"]["min_entropy_per_bit"] > 0.7
    assert data["randomness"]["total_certified_random_bits"] > 350.0

    # 4. DI QKD session
    resp = client.post("/v1/quantum/nonlocality/qkd/session", json={"num_pairs": 1500, "noise_depolarizing": 0.01})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["qkd"]["security_certified"]
    assert data["qkd"]["final_secure_key_length"] > 0

    # 5. Anchor export
    resp = client.post("/v1/quantum/nonlocality/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert "anchor" in data
    assert "program" in data

    # 6. Verification drill simulate
    resp = client.post("/v1/quantum/nonlocality/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["drill"]["all_passed"]
