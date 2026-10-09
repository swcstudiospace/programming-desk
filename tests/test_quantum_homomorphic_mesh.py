"""Unit and integration tests for Quantum Homomorphic Encryption (Phase 84)."""

import pytest

from desk_gateway.quantum_homomorphic_mesh import (
    QHEExecutionEngine,
    QHEGateType,
    QHEQubitState,
)


def test_qhe_qubit_encryption_and_decryption():
    engine = QHEExecutionEngine()
    q = engine.encrypt_qubit(0, alpha=complex(1.0, 0.0), beta=complex(0.0, 0.0))

    assert q.qubit_index == 0
    assert q.otp_key_a in (0, 1)
    assert q.otp_key_b in (0, 1)

    # Measured outcome for pure |0> should be 0
    outcome = engine.decrypt_and_measure(0)
    assert outcome == 0


def test_qhe_clifford_hadamard_propagation():
    engine = QHEExecutionEngine()
    q = engine.encrypt_qubit(0, alpha=complex(1.0, 0.0), beta=complex(0.0, 0.0))
    orig_a, orig_b = q.otp_key_a, q.otp_key_b

    # H updates (a, b) -> (b, a)
    _, new_a, new_b = engine.apply_hadamard(0)
    assert new_a == orig_b
    assert new_b == orig_a


def test_qhe_clifford_phase_s_propagation():
    engine = QHEExecutionEngine()
    q = engine.encrypt_qubit(0, alpha=complex(0.6, 0.0), beta=complex(0.8, 0.0))
    orig_a, orig_b = q.otp_key_a, q.otp_key_b

    # S updates (a, b) -> (a, a ^ b)
    _, new_a, new_b = engine.apply_phase_s(0)
    assert new_a == orig_a
    assert new_b == orig_a ^ orig_b


def test_qhe_cnot_propagation():
    engine = QHEExecutionEngine()
    q0 = engine.encrypt_qubit(0, alpha=complex(1.0, 0.0), beta=complex(0.0, 0.0))
    q1 = engine.encrypt_qubit(1, alpha=complex(0.0, 0.0), beta=complex(1.0, 0.0))

    a1, b1 = q0.otp_key_a, q0.otp_key_b
    a2, b2 = q1.otp_key_a, q1.otp_key_b

    ca, cb, ta, tb = engine.apply_cnot(0, 1)
    assert ca == a1
    assert cb == b1 ^ b2
    assert ta == a1 ^ a2
    assert tb == b2


def test_qhe_t_gate_propagation():
    engine = QHEExecutionEngine()
    q = engine.encrypt_qubit(0, alpha=complex(0.6, 0.0), beta=complex(0.8, 0.0))
    _, a, b, corr = engine.apply_t_gate(0)

    assert a in (0, 1)
    assert b in (0, 1)
    assert corr in ("PHASE_GADGET_CORRECTION", "NO_CORRECTION")
