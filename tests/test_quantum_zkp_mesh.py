"""Unit and integration tests for Quantum Zero-Knowledge Proofs & Witness Verification (Phase 82)."""

import pytest

from desk_gateway.quantum_zkp_mesh import (
    PauliBasis,
    QZKPProofResponse,
    QuantumWitnessState,
    QuantumZKPEngine,
)


def test_quantum_witness_commitment_hash():
    witness = QuantumWitnessState(
        witness_id="witness-1",
        qubits_count=2,
        stabilizers=["+XX", "+ZZ"],
        phase_angles=[0.0, 1.570796],
        fidelity=0.99,
    )
    h1 = witness.compute_commitment_hash("nonce-a")
    h2 = witness.compute_commitment_hash("nonce-b")
    assert len(h1) == 64
    assert len(h2) == 64
    assert h1 != h2


def test_quantum_zkp_interactive_session():
    engine = QuantumZKPEngine()
    witness = QuantumWitnessState(
        witness_id="witness-bell-0",
        qubits_count=2,
        stabilizers=["+XX", "-ZZ"],
        phase_angles=[0.0, 0.0],
        fidelity=0.98,
    )

    # 1. Prover initializes session
    session_info = engine.init_proof_session("prover-node", "verifier-node", witness)
    session_id = session_info["session_id"]
    assert session_info["status"] == "COMMITMENT_EXCHANGED"

    # 2. Verifier issues random challenge
    challenge = engine.generate_verifier_challenge(session_id)
    assert challenge in (PauliBasis.X, PauliBasis.Y, PauliBasis.Z)

    # 3. Prover responds to challenge
    response = engine.evaluate_prover_response(session_id, challenge)
    assert response.session_id == session_id
    assert response.verified is True
    assert response.projector_expectation >= 0.90
    assert len(response.response_proof) == 64
