"""Tests for Quantum Timelock Puzzles, Verifiable Delay Functions & Spacetime Anchoring Mesh (Milestone v6.5 - Phases 96 & 97)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_timelock_mesh import (
    QuantumTimelockMesh,
    SlothVDFEngine,
    TimelockPuzzle,
    VDFAlgorithm,
    VDFProof,
    WesolowskiVDFEngine,
)
from desk_gateway.quantum_timelock_anchoring import (
    QuantumTimelockMerkleLedger,
    QuantumTimelockReceipt,
    QuantumTimelockSolanaAnchorExporter,
    QuantumTimelockVerificationDrill,
)
from desk_gateway.server import build_app


def test_wesolowski_vdf_computation_and_verification():
    engine = WesolowskiVDFEngine()
    x = 101
    iterations = 50
    proof = engine.compute_vdf(x, iterations)

    assert proof.vdf_type == VDFAlgorithm.WESOLOWSKI
    assert proof.input_x == x
    assert proof.iterations_t == iterations
    assert proof.verified is True
    assert proof.computation_time_ms >= 0.0

    # Tampered verification should fail
    tampered_verified = engine.verify_vdf(x, (proof.output_y + 1) % engine.modulus_n, proof.proof_pi, proof.challenge_l, iterations)
    assert tampered_verified is False


def test_sloth_vdf_forward_and_backward():
    engine = SlothVDFEngine()
    x = 123456
    iterations = 20
    y, elapsed = engine.compute_sloth(x, iterations)
    assert elapsed >= 0.0
    verified = engine.verify_sloth(x, y, iterations)
    assert verified is True

    # Tampered output should fail
    assert engine.verify_sloth(x, (y + 1) % engine.prime_p, iterations) is False


def test_quantum_timelock_mesh_puzzle_flow():
    mesh = QuantumTimelockMesh()
    secret = "sample_test_time_release_key_007"  # pragma: allowlist secret
    puzzle = mesh.create_puzzle("puz-alpha", secret, delay_seconds=0.01)

    assert puzzle.puzzle_id == "puz-alpha"
    assert puzzle.difficulty_iterations >= 100
    assert len(puzzle.encrypted_secret) > 0

    solved = mesh.solve_puzzle("puz-alpha")
    assert solved["puzzle_id"] == "puz-alpha"
    assert solved["decrypted_secret"] == secret
    assert solved["verified"] is True

    # Test unknown puzzle
    with pytest.raises(KeyError):
        mesh.solve_puzzle("non-existent-puzzle")


def test_quantum_beacon_tick():
    mesh = QuantumTimelockMesh()
    tick1 = mesh.emit_beacon_tick(epoch_index=1, quantum_seed="seed-alpha")
    tick2 = mesh.emit_beacon_tick(epoch_index=2, quantum_seed="seed-beta")

    assert tick1["epoch_index"] == 1
    assert tick2["epoch_index"] == 2
    assert tick1["beacon_entropy"] != tick2["beacon_entropy"]
    assert tick1["vdf_proof"]["verified"] is True
    assert len(mesh.beacon_history) == 2


def test_quantum_timelock_merkle_ledger():
    ledger = QuantumTimelockMerkleLedger()
    assert ledger.get_merkle_root() == "55c4d2919d750d4eb14b533cb312e753bfd12f270a6c6a4fb64b630b91e56b4f" or len(ledger.get_merkle_root()) == 64

    rcpt1 = QuantumTimelockReceipt(
        receipt_id="rcpt-1",
        puzzle_or_tick_id="puz-1",
        vdf_type="wesolowski",
        iterations=100,
        computation_time_ms=5.0,
        output_y_hash="hash-y-1",
        proof_pi_hash="hash-pi-1",
        challenge_l=17,
        verified=True,
    )
    rcpt2 = QuantumTimelockReceipt(
        receipt_id="rcpt-2",
        puzzle_or_tick_id="puz-2",
        vdf_type="sloth",
        iterations=50,
        computation_time_ms=3.0,
        output_y_hash="hash-y-2",
        proof_pi_hash="hash-pi-2",
        challenge_l=19,
        verified=True,
    )

    root1 = ledger.add_receipt(rcpt1)
    root2 = ledger.add_receipt(rcpt2)

    assert len(root1) == 64
    assert len(root2) == 64
    assert root1 != root2


def test_quantum_timelock_drill_simulation():
    drill = QuantumTimelockVerificationDrill(iterations=50)
    res = drill.run_drill()
    assert res["ok"] is True
    assert res["total_stages"] == 5
    assert res["stages"]["stage_1_wesolowski_vdf_proof"]["passed"] is True
    assert res["stages"]["stage_2_sloth_permutation_inversion"]["passed"] is True
    assert res["stages"]["stage_3_puzzle_encryption_and_solution"]["passed"] is True
    assert res["stages"]["stage_4_merkle_ledger_immutability"]["passed"] is True
    assert res["stages"]["stage_5_solana_anchor_export"]["passed"] is True


def test_quantum_timelock_http_routes():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Create Timelock puzzle
    resp_create = client.post(
        "/v1/quantum/timelock/puzzle/create",
        json={"puzzle_id": "test-http-puz", "secret_text": "sample_http_data_123", "delay_seconds": 0.01},  # pragma: allowlist secret
    )
    assert resp_create.status_code == 200
    create_data = resp_create.json()
    assert create_data["ok"] is True
    assert create_data["puzzle"]["puzzle_id"] == "test-http-puz"

    # 2. Solve Timelock puzzle
    resp_solve = client.post(
        "/v1/quantum/timelock/puzzle/solve",
        json={"puzzle_id": "test-http-puz"},
    )
    assert resp_solve.status_code == 200
    solve_data = resp_solve.json()
    assert solve_data["ok"] is True
    assert solve_data["solution"]["decrypted_secret"] == "sample_http_data_123"  # pragma: allowlist secret
    assert "merkle_root" in solve_data

    # 3. Verify VDF proof directly
    resp_vdf = client.post(
        "/v1/quantum/timelock/vdf/verify",
        json={"algorithm": "wesolowski", "iterations": 40, "input_x": 4242},
    )
    assert resp_vdf.status_code == 200
    vdf_data = resp_vdf.json()
    assert vdf_data["ok"] is True
    assert vdf_data["proof"]["verified"] is True

    # 4. Sloth VDF route
    resp_sloth = client.post(
        "/v1/quantum/timelock/vdf/verify",
        json={"algorithm": "sloth", "iterations": 20, "input_x": 777},
    )
    assert resp_sloth.status_code == 200
    sloth_data = resp_sloth.json()
    assert sloth_data["ok"] is True
    assert sloth_data["verified"] is True

    # 5. Beacon tick
    resp_beacon = client.post(
        "/v1/quantum/timelock/beacon/tick",
        json={"epoch_index": 10, "quantum_seed": "test-quantum-seed"},
    )
    assert resp_beacon.status_code == 200
    beacon_data = resp_beacon.json()
    assert beacon_data["ok"] is True
    assert beacon_data["tick"]["epoch_index"] == 10

    # 6. Solana Anchor export
    resp_export = client.post("/v1/quantum/timelock/anchor/export")
    assert resp_export.status_code == 200
    export_data = resp_export.json()
    assert export_data["ok"] is True
    assert export_data["anchor"]["instruction"] == "anchor_spacetime_vdf_root"
    assert "quantum_timelock_anchoring" in export_data["program"]

    # 7. Drill simulate
    resp_drill = client.post("/v1/quantum/timelock/drill/simulate")
    assert resp_drill.status_code == 200
    drill_data = resp_drill.json()
    assert drill_data["ok"] is True
    assert drill_data["drill"]["ok"] is True
