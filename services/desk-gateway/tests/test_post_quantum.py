"""Unit tests for Phase 44: Post-Quantum Hybrid Cryptographic Primitives & Lattice KEM."""

import pytest
from desk_gateway.post_quantum import (
    HybridKEM,
    HybridKeyPair,
    EncapsulationReceipt,
    HybridSignatureEngine,
    HybridSignature,
    PQCChannelSession,
    QuantumAuditInspector,
)


def test_hybrid_kem_keygen_and_encapsulation():
    kem = HybridKEM()
    keypair = kem.generate_keypair("seat-kem-test")

    assert keypair.key_id == "seat-kem-test"
    assert "ML-KEM" in keypair.algorithm_suite
    assert len(keypair.classical_public_key) > 0
    assert len(keypair.lattice_public_key) > 0

    # Public bundle serialization
    bundle = keypair.public_bundle()
    assert bundle["algorithm_suite"] == "X25519+ML-KEM-768"

    # Encapsulate
    secret, receipt = kem.encapsulate(keypair)
    assert len(secret) == 32
    assert receipt.key_id == "seat-kem-test"
    assert len(receipt.classical_ciphertext) > 0
    assert len(receipt.lattice_ciphertext) > 0


def test_hybrid_signature_sign_and_verify():
    sig_engine = HybridSignatureEngine(signing_secret="quantum-desk-secret-key")
    message = b"Authorize deployment of tool lattice-attested-v1"

    sig = sig_engine.sign(message, key_id="seat-quality")
    assert sig.key_id == "seat-quality"
    assert "ML-DSA" in sig.algorithm_suite
    assert len(sig.classical_sig) > 0
    assert len(sig.lattice_sig) > 0

    # Verify signature passes
    assert sig_engine.verify(message, sig) is True

    # Tampered message fails
    assert sig_engine.verify(b"Authorize deployment of tool malicious-v1", sig) is False

    # Tampered classical sig fails
    tampered_c = HybridSignature(
        key_id=sig.key_id,
        classical_sig="tampered" + sig.classical_sig[8:],
        lattice_sig=sig.lattice_sig,
        algorithm_suite=sig.algorithm_suite,
        message_digest=sig.message_digest,
    )
    assert sig_engine.verify(message, tampered_c) is False

    # Tampered lattice sig fails
    tampered_l = HybridSignature(
        key_id=sig.key_id,
        classical_sig=sig.classical_sig,
        lattice_sig="tampered" + sig.lattice_sig[8:],
        algorithm_suite=sig.algorithm_suite,
        message_digest=sig.message_digest,
    )
    assert sig_engine.verify(message, tampered_l) is False


def test_pqc_channel_session_encryption_and_replay_protection():
    kem = HybridKEM()
    kp = kem.generate_keypair("session-node")
    shared_secret, _ = kem.encapsulate(kp)

    session = PQCChannelSession("chan-session-42", shared_secret)

    msg1 = session.encrypt("Payload alpha")
    msg2 = session.encrypt("Payload beta")

    assert msg1.counter == 1
    assert msg2.counter == 2

    # In-order decryption
    dec1 = session.decrypt(msg1)
    assert dec1 == "Payload alpha"

    dec2 = session.decrypt(msg2)
    assert dec2 == "Payload beta"

    # Replay attack fails
    with pytest.raises(ValueError, match="Replay attack detected"):
        session.decrypt(msg1)


def test_quantum_audit_inspector_downgrade_detection():
    inspector = QuantumAuditInspector()

    # Legitimate negotiation
    ok_res = inspector.evaluate_negotiation(
        client_suites=["X25519+ML-KEM-768", "X25519"],
        server_suites=["X25519+ML-KEM-768"],
        agreed_suite="X25519+ML-KEM-768",
    )
    assert ok_res["status"] == "APPROVED"
    assert ok_res["quantum_safe"] is True

    # Downgrade attack: both support PQC but classical negotiated
    down_res = inspector.evaluate_negotiation(
        client_suites=["X25519+ML-KEM-768", "X25519"],
        server_suites=["X25519+ML-KEM-768", "X25519"],
        agreed_suite="X25519",
    )
    assert down_res["status"] == "BLOCKED"
    assert down_res["quantum_safe"] is False
    assert len(inspector.alerts) >= 1
    assert inspector.alerts[-1].event_type == "DOWNGRADE_ATTACK_DETECTED"
