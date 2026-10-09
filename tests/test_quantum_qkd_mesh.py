"""Unit and integration tests for QKD, Entanglement State Ledger & Solana Anchoring (Phase 69)."""

import pytest

from desk_gateway.quantum_qkd_mesh import (
    EavesdropDetector,
    QKDKeyExchangeSession,
    QKDProtocolEngine,
    QuantumTeleportationAnchorExporter,
    QuantumTeleportationDrillSimulator,
    QuantumTeleportationReceiptLedger,
)
from desk_gateway.quantum_teleportation import (
    BellPairPool,
    QuantumRepeaterMesh,
)


def test_qkd_bb84_clean_exchange():
    engine = QKDProtocolEngine()
    session = engine.run_bb84_exchange("desk-alpha", "desk-beta", bit_length=128, intercept_ratio=0.0)

    assert session.session_id.startswith("qkd-bb84-")
    assert session.raw_bits_count == 128
    assert session.sifted_bits_count > 0
    assert session.qber == 0.0
    assert session.eavesdropping_detected is False
    assert len(session.final_shared_key_hex) == 64  # SHA-256 hex digest


def test_qkd_bb84_eavesdropping_abort():
    engine = QKDProtocolEngine()
    # High interception ratio should cause QBER > 11% and trigger abort
    session = engine.run_bb84_exchange("desk-alpha", "desk-beta", bit_length=256, intercept_ratio=0.90)

    assert session.qber > 0.10
    assert session.eavesdropping_detected is True
    assert session.final_shared_key_hex == ""  # Aborted


def test_qkd_e91_exchange():
    engine = QKDProtocolEngine()
    session = engine.run_e91_exchange("desk-alpha", "desk-beta", pair_count=120, noise_level=0.0)

    assert session.session_id.startswith("qkd-e91-")
    assert session.qber == 0.0
    assert session.eavesdropping_detected is False
    assert len(session.final_shared_key_hex) == 64


def test_quantum_teleportation_receipt_ledger_merkle():
    ledger = QuantumTeleportationReceiptLedger()
    root_empty = ledger.calculate_merkle_root()
    assert len(root_empty) == 64

    rcpt1 = ledger.append_event(
        "TELEPORT_SUCCESS",
        ["desk-alpha", "desk-beta"],
        "session-1",
        0.985,
        {"qubit": "plus"},
    )
    rcpt2 = ledger.append_event(
        "QKD_KEY_ESTABLISHED",
        ["desk-alpha", "desk-beta"],
        "session-2",
        0.015,
        {"key_id": "k1"},
    )

    root_two = ledger.calculate_merkle_root()
    assert len(root_two) == 64
    assert root_two != root_empty
    assert len(ledger.receipts) == 2
    assert rcpt2.merkle_root == root_two


def test_quantum_teleportation_anchor_exporter():
    ledger = QuantumTeleportationReceiptLedger()
    ledger.append_event(
        "TELEPORT_SUCCESS",
        ["desk-alpha", "desk-gamma"],
        "sess-100",
        0.99,
        {"data": "superposition"},
    )
    exporter = QuantumTeleportationAnchorExporter()
    commitment = exporter.export_commitment(ledger)

    assert commitment["status"] == "confirmed"
    assert len(commitment["commitment_tx"]) == 64
    assert len(commitment["merkle_root"]) == 64
    assert commitment["event_count"] == 1


def test_quantum_teleportation_drill_simulator():
    drill_results = QuantumTeleportationDrillSimulator.run_drill()
    assert drill_results["all_passed"] is True
    assert drill_results["purify_step"]["success"] is True
    assert drill_results["repeater_step"]["success"] is True
    assert drill_results["teleport_step"]["success"] is True
    assert drill_results["qkd_step"]["clean_success"] is True
    assert drill_results["qkd_step"]["eavesdropped_detected"] is True
    assert drill_results["anchor_step"]["success"] is True
    assert drill_results["ledger_receipts_count"] >= 3
