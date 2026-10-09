"""Unit tests for Topological Qubit Surface Code & Quantum State Anchoring (Milestone v5.0 - Phase 67)."""

import pytest

from desk_gateway.quantum_topological_mesh import (
    CorrectionOperator,
    MWPMDecoder,
    QuantumAnchorExporter,
    QuantumStateReceiptLedger,
    QuantumTopologicalDrillSimulator,
    QubitType,
    StabilizerMeasurement,
    SurfaceCodeLattice,
    SyndromeExtractor,
)


def test_surface_code_lattice_initialization():
    lattice = SurfaceCodeLattice(distance=3)
    assert lattice.distance == 3
    # Distance 3 rotated code has 3x3 = 9 data qubits
    assert len(lattice.data_qubits) == 9
    assert len(lattice.measure_qubits) > 0
    d_dict = lattice.to_dict()
    assert d_dict["data_qubit_count"] == 9
    assert len(d_dict["active_errors"]) == 0


def test_syndrome_extraction_no_errors():
    lattice = SurfaceCodeLattice(distance=3)
    extractor = SyndromeExtractor(lattice)
    syndromes = extractor.extract_syndrome()
    assert len(syndromes) > 0
    # No physical errors, all syndromes must be +1
    for s in syndromes:
        assert s.syndrome_bit == 1


def test_physical_error_injection_and_syndrome_defect():
    lattice = SurfaceCodeLattice(distance=3)
    # Inject bit-flip error X onto data qubit at (1, 1)
    lattice.inject_physical_error(1, 1, "X")
    d_dict = lattice.to_dict()
    assert len(d_dict["active_errors"]) == 1
    assert d_dict["active_errors"][0]["error_state"] == "X"

    extractor = SyndromeExtractor(lattice)
    syndromes = extractor.extract_syndrome()
    defects = [s for s in syndromes if s.syndrome_bit == -1]
    # Injected error must flip at least one stabilizer measurement
    assert len(defects) > 0


def test_mwpm_decoder_and_error_recovery():
    lattice = SurfaceCodeLattice(distance=3)
    lattice.inject_physical_error(1, 1, "X")

    extractor = SyndromeExtractor(lattice)
    syndromes = extractor.extract_syndrome()

    decoder = MWPMDecoder(lattice)
    corrections = decoder.decode_syndromes(syndromes)
    assert len(corrections) > 0
    assert corrections[0].pauli_correction == "X"

    # Post-decoding verify that errors are resolved
    post_syndromes = extractor.extract_syndrome()
    assert all(s.syndrome_bit == 1 for s in post_syndromes)


def test_quantum_state_receipt_ledger_merkle_root():
    ledger = QuantumStateReceiptLedger()
    rcpt1 = ledger.append_event("TEST_EVENT_1", "state_digest_alpha", 0, 0)
    assert rcpt1.receipt_id.startswith("qrcpt-")
    assert len(rcpt1.signature) == 64

    rcpt2 = ledger.append_event("TEST_EVENT_2", "state_digest_beta", 2, 1)
    assert len(ledger.receipts) == 2

    root = ledger.compute_merkle_root()
    assert len(root) == 64


def test_quantum_anchor_exporter():
    ledger = QuantumStateReceiptLedger()
    ledger.append_event("LOGICAL_STATE_INIT", "state_digest_00", 0, 0)
    exporter = QuantumAnchorExporter()
    commitment = exporter.export_commitment(ledger)

    assert commitment["status"] == "CONFIRMED_ON_SOLANA_DEVNET"
    assert commitment["receipts_count"] == 1
    assert "solana_tx" in commitment


def test_quantum_topological_drill_simulator():
    results = QuantumTopologicalDrillSimulator.run_drill()
    assert results["drill_status"] == "ALL_CHECKS_PASSED"
    assert results["bell_state_fidelity"] is True
    assert results["vqe_convergence"] is True
    assert results["qaoa_partitioning"] is True
    assert results["syndrome_defects_detected"] is True
    assert results["mwpm_corrections_applied"] is True
    assert results["syndromes_resolved"] is True
    assert results["solana_anchoring"] is True
