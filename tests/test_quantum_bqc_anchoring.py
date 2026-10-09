"""Unit and integration tests for Verifiable Blind Quantum Verification, QSS & Solana Anchoring (Phase 73)."""

import math
import pytest

from desk_gateway.quantum_bqc_anchoring import (
    BQCAnchorExporter,
    BQCDrillSimulator,
    BQCLedger,
    QuantumSecretSharing,
    TrapQubitVerifier,
)


def test_trap_qubit_verifier():
    verifier = TrapQubitVerifier(trap_ratio=0.3)
    traps = verifier.designate_traps(total_qubits=10)

    assert len(traps) >= 3

    # Pass expected outcome
    for q in traps:
        expected = verifier.traps[q].expected_outcome
        assert verifier.verify_measurement(q, expected) is True

    assert verifier.all_traps_passed() is True

    # Intentionally corrupt one trap to simulate malicious server tampering
    q0 = traps[0]
    tampered_outcome = 1 - verifier.traps[q0].expected_outcome
    assert verifier.verify_measurement(q0, tampered_outcome) is False
    assert verifier.all_traps_passed() is False


def test_quantum_secret_sharing_shamir_threshold():
    secret_angle_code = 1337
    shares = QuantumSecretSharing.split_secret(secret_angle_code, threshold_t=3, num_shares_n=5)

    assert len(shares) == 5

    # Any subset of 3 shares reconstructs the exact secret
    subset_1 = [shares[0], shares[1], shares[2]]
    subset_2 = [shares[1], shares[3], shares[4]]
    assert QuantumSecretSharing.reconstruct_secret(subset_1) == secret_angle_code
    assert QuantumSecretSharing.reconstruct_secret(subset_2) == secret_angle_code


def test_bqc_merkle_ledger_and_anchor():
    ledger = BQCLedger()
    assert len(ledger.calculate_merkle_root()) == 64

    r1 = ledger.append_event("BQC_INIT", "sess-1", ["node-a"], 1.0, {"nodes": 12})
    root1 = ledger.calculate_merkle_root()
    assert r1.merkle_root == root1

    r2 = ledger.append_event("BQC_MEASURE", "sess-1", ["node-a"], 1.0, {"q": 0, "s": 1})
    root2 = ledger.calculate_merkle_root()
    assert root2 != root1
    assert len(ledger.receipts) == 2

    exporter = BQCAnchorExporter()
    anchor = exporter.export_commitment(ledger)
    assert anchor["status"] == "confirmed"
    assert anchor["merkle_root"] == root2
    assert anchor["slot"] >= 298695000


def test_bqc_drill_simulator():
    drill = BQCDrillSimulator.run_drill()
    assert drill["all_passed"] is True
    assert drill["step1_cluster_init"] is True
    assert drill["step2_trap_designation"] is True
    assert drill["step3_blind_measurements"] is True
    assert drill["step4_qss_threshold_reconstruction"] is True
    assert drill["step5_solana_anchoring"] is True
    assert len(drill["final_merkle_root"]) == 64
