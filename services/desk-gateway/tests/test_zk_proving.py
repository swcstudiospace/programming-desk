"""Tests for Zero-Knowledge Proof Synthesis & Circuit Verification (Milestone v4.4 - Phase 54)."""

import pytest

from desk_gateway.zk_proving import (
    ZKCircuit,
    ZKConstraint,
    ZKProofGenerator,
    ZKProofVerifier,
    ZKStateTransitionProver,
)


def test_zk_constraint_evaluation():
    # Constraint: (x + y) * 2 == z
    # A: x: 1, y: 1
    # B: two: 1 (so sum_b = 1 * witness["two"] = 2.0)
    # C: z: 1
    c = ZKConstraint(
        constraint_id="c_test_01",
        a_coefficients={"x": 1.0, "y": 1.0},
        b_coefficients={"two": 1.0},
        c_coefficients={"z": 1.0},
    )

    valid_witness = {"x": 3.0, "y": 4.0, "two": 2.0, "z": 14.0}
    invalid_witness = {"x": 3.0, "y": 4.0, "two": 2.0, "z": 15.0}

    assert c.evaluate(valid_witness) is True
    assert c.evaluate(invalid_witness) is False


def test_zk_circuit_satisfiability():
    circuit = ZKCircuit(
        circuit_id="circuit-mul",
        name="MultiplicationCircuit",
        public_wire_names=["one", "x", "result"],
        private_wire_names=["secret_factor"],
    )
    # (x) * (secret_factor) == result
    c = ZKConstraint(
        constraint_id="c_mul",
        a_coefficients={"x": 1.0},
        b_coefficients={"secret_factor": 1.0},
        c_coefficients={"result": 1.0},
    )
    circuit.add_constraint(c)

    sat_witness = {"one": 1.0, "x": 6.0, "secret_factor": 7.0, "result": 42.0}
    unsat_witness = {"one": 1.0, "x": 6.0, "secret_factor": 8.0, "result": 42.0}

    assert circuit.is_satisfied(sat_witness) is True
    assert circuit.is_satisfied(unsat_witness) is False


def test_zk_proof_generation_and_verification():
    generator = ZKProofGenerator(proving_key_secret="test-secret-key")
    verifier = ZKProofVerifier(proving_key_secret="test-secret-key")

    circuit = ZKCircuit(
        circuit_id="test-circuit",
        name="TestCircuit",
        public_wire_names=["one", "x", "y"],
        private_wire_names=["secret"],
    )
    circuit.add_constraint(
        ZKConstraint(
            constraint_id="c_add",
            a_coefficients={"x": 1.0, "secret": 1.0},
            b_coefficients={"one": 1.0},
            c_coefficients={"y": 1.0},
        )
    )

    public_inputs = {"x": 10.0, "y": 25.0}
    private_witness = {"secret": 15.0}

    proof = generator.generate_proof(circuit, public_inputs, private_witness)
    assert proof.proof_id.startswith("zkp-")
    assert proof.circuit_id == "test-circuit"

    receipt = verifier.verify_proof(circuit, proof)
    assert receipt.is_valid is True
    assert receipt.proof_id == proof.proof_id


def test_zk_proof_tamper_rejection():
    generator = ZKProofGenerator(proving_key_secret="test-secret-key")
    verifier = ZKProofVerifier(proving_key_secret="test-secret-key")

    circuit = ZKCircuit(
        circuit_id="test-circuit",
        name="TestCircuit",
        public_wire_names=["one", "a", "b"],
        private_wire_names=["w"],
    )
    circuit.add_constraint(
        ZKConstraint(
            constraint_id="c1",
            a_coefficients={"a": 1.0},
            b_coefficients={"w": 1.0},
            c_coefficients={"b": 1.0},
        )
    )

    proof = generator.generate_proof(circuit, {"a": 2.0, "b": 6.0}, {"w": 3.0})

    # Tamper with circuit ID
    other_circuit = ZKCircuit(
        circuit_id="different-circuit",
        name="Other",
        public_wire_names=["one"],
        private_wire_names=[],
    )
    tamper_receipt = verifier.verify_proof(other_circuit, proof)
    assert tamper_receipt.is_valid is False


def test_zk_state_transition_prover():
    state_prover = ZKStateTransitionProver()
    proof, receipt = state_prover.prove_state_transition(
        initial_state=500.0,
        delta=120.0,
        secret_auth_code=4321.0,
    )

    assert receipt.is_valid is True
    assert receipt.public_inputs["final_state"] == 620.0
