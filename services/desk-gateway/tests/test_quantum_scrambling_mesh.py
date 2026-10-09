"""Tests for Quantum Many-Body Scrambling, OTOCs & Hayden-Preskill Mesh (Milestone v7.4 - Phases 114 & 115)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_scrambling_mesh import (
    HaydenPreskillProtocolEngine,
    HaydenPreskillResult,
    OTOCMeasurementPoint,
    QuantumScramblingEngine,
    QuantumScramblingMesh,
    ScramblerType,
    ScramblingSystemConfig,
)
from desk_gateway.quantum_scrambling_anchoring import (
    QuantumScramblingMerkleLedger,
    QuantumScramblingReceipt,
    QuantumScramblingSolanaAnchorExporter,
    QuantumScramblingVerificationDrill,
)
from desk_gateway.server import build_app


def test_quantum_scrambling_mss_bound_and_timescale():
    config = ScramblingSystemConfig(n_qubits=6, temperature_k=1.2, lyapunov_bound_hbar_scale=1.0)
    assert config.mss_lyapunov_bound == pytest.approx(2.0 * 3.1415926535 * 1.2, rel=1e-3)
    assert config.theoretical_scrambling_time > 0.0


def test_otoc_decay_and_commutator_growth():
    engine = QuantumScramblingEngine(ScramblingSystemConfig(n_qubits=6, scrambler_type=ScramblerType.RANDOM_CLIFFORD))
    evolution = engine.compute_otoc_evolution(steps=8)
    assert len(evolution) == 9

    init_pt = evolution[0]
    final_pt = evolution[-1]

    assert init_pt.otoc_f_re > 0.80
    assert final_pt.otoc_f_re < 0.20
    assert final_pt.otoc_commutator_c > 1.60
    assert final_pt.tripartite_mutual_info_i3 < -1.0
    assert final_pt.scrambled is True


def test_integrable_non_scrambler_behavior():
    engine = QuantumScramblingEngine(ScramblingSystemConfig(n_qubits=6, scrambler_type=ScramblerType.INTEGRABLE_REGULAR))
    evolution = engine.compute_otoc_evolution(steps=8)
    final_pt = evolution[-1]
    # Integrable systems do not have exponential OTOC decay to zero
    assert final_pt.otoc_f_re > 0.60
    assert final_pt.scrambled is False


def test_hayden_preskill_retrieval_success():
    engine = HaydenPreskillProtocolEngine()
    result = engine.execute_retrieval_protocol(
        experiment_id="hp-test-1",
        n_black_hole_qubits=6,
        k_secret_qubits=1,
        epsilon_qubits=2,
        scrambler=ScramblerType.RANDOM_CLIFFORD,
    )
    assert result.experiment_id == "hp-test-1"
    assert result.n_black_hole_qubits == 6
    assert result.k_secret_qubits == 1
    assert result.c_late_radiation_qubits == 3
    assert result.epsilon_qubits == 2
    assert result.theoretical_max_error == 2.0 ** (-4)
    assert result.reconstruction_fidelity >= 0.85
    assert result.teleportation_successful is True


def test_hayden_preskill_integrable_failure():
    engine = HaydenPreskillProtocolEngine()
    result = engine.execute_retrieval_protocol(
        experiment_id="hp-test-integrable",
        n_black_hole_qubits=6,
        k_secret_qubits=1,
        epsilon_qubits=2,
        scrambler=ScramblerType.INTEGRABLE_REGULAR,
    )
    assert result.teleportation_successful is False
    assert result.reconstruction_fidelity < 0.80


def test_quantum_scrambling_merkle_ledger_and_proof():
    ledger = QuantumScramblingMerkleLedger()

    r1 = QuantumScramblingReceipt(
        receipt_id="rcpt-scramble-01",
        operation_type="OTOC_DECAY_ANALYSIS",
        scrambler_type="RANDOM_CLIFFORD",
        otoc_f_or_fidelity=0.045,
        lyapunov_or_epsilon=6.28,
        tripartite_i3=-1.91,
        status="SCRAMBLED_BOUND_SATURATED",
        parameters_digest="hash01",
    )
    r2 = QuantumScramblingReceipt(
        receipt_id="rcpt-scramble-02",
        operation_type="HAYDEN_PRESKILL_RETRIEVAL",
        scrambler_type="SYK_CHAOTIC_CHAIN",
        otoc_f_or_fidelity=0.97,
        lyapunov_or_epsilon=2.0,
        tripartite_i3=-1.95,
        status="RETRIEVAL_VERIFIED",
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
    ledger = QuantumScramblingMerkleLedger()
    rcpt = QuantumScramblingReceipt(
        receipt_id="rcpt-anchor-01",
        operation_type="HAYDEN_PRESKILL_RETRIEVAL",
        scrambler_type="RANDOM_CLIFFORD",
        otoc_f_or_fidelity=0.965,
        lyapunov_or_epsilon=2.0,
        tripartite_i3=-1.93,
        status="RETRIEVAL_VERIFIED",
        parameters_digest="hash_anchor",
    )
    ledger.append_receipt(rcpt)
    root = ledger.get_merkle_root()
    proof = ledger.get_proof(0)

    payload = QuantumScramblingSolanaAnchorExporter.generate_instruction_payload(
        merkle_root=root,
        receipt=rcpt,
        proof=proof,
    )
    assert payload["program_id"] == QuantumScramblingSolanaAnchorExporter.PROGRAM_ID
    assert payload["args"]["reconstruction_fidelity_bps"] == 9650
    assert payload["args"]["tripartite_i3_negative"] is True

    prog = QuantumScramblingSolanaAnchorExporter.generate_anchor_program()
    assert "verify_scrambling_and_hayden_preskill" in prog
    assert "InsufficientFidelity" in prog


def test_verification_drill_full_suite():
    drill = QuantumScramblingVerificationDrill()
    res = drill.run_all_stages()
    assert res["all_stages_passed"] is True
    assert len(res["stages"]) == 5
    for st in res["stages"]:
        assert st["status"] == "PASSED"


def test_server_rest_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. OTOC simulation endpoint
    resp = client.post(
        "/v1/quantum/scrambling/otoc/simulate",
        json={
            "n_qubits": 6,
            "scrambler_type": "RANDOM_CLIFFORD",
            "temperature_k": 1.0,
            "steps": 6,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["otoc_analysis"]["is_fast_scrambled"] is True
    assert "merkle_root" in data

    # 2. Hayden-Preskill teleportation endpoint
    resp2 = client.post(
        "/v1/quantum/scrambling/hayden-preskill/teleport",
        json={
            "experiment_id": "hp-endpoint-test-01",
            "n_black_hole_qubits": 6,
            "k_secret_qubits": 1,
            "epsilon_qubits": 2,
            "scrambler_type": "RANDOM_CLIFFORD",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ok"] is True
    assert data2["hayden_preskill"]["teleportation_successful"] is True

    # 3. Anchor export endpoint
    resp3 = client.post("/v1/quantum/scrambling/anchor/export", json={})
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["ok"] is True
    assert "program" in data3
    assert "anchor" in data3

    # 4. Drill simulate endpoint
    resp4 = client.post("/v1/quantum/scrambling/drill/simulate", json={})
    assert resp4.status_code == 200
    data4 = resp4.json()
    assert data4["ok"] is True
    assert data4["drill"]["all_stages_passed"] is True
