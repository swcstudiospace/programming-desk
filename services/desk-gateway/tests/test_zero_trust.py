"""Tests for Ephemeral Seat Enclave Credentials & Dynamic Mutual TLS (Milestone v3.0 - Phase 26).

Covers:
- REQ-ZERO-001: Ephemeral per-seat session credential issuer with micro-TTL token expiry.
- REQ-ZERO-002: Dynamic mutual TLS (mTLS) certificate authority for inter-seat communication.
- REQ-ZERO-003: Hardware/enclave attestation evidence verifier evaluating cryptographic measurement claims.
- REQ-ZERO-004: Zero-trust continuous authentication policy engine re-verifying seat posture on sensitive tool calls.
- REQ-ZERO-005: Instantaneous session revocation & certificate revocation list (CRL) distribution across edge nodes.
- Starlette HTTP API routes in server.py.
"""

from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.zero_trust import (
    AttestationReport,
    EnclavePosture,
    EphemeralCredential,
    SeatCertificate,
    ZeroTrustEnclaveManager,
)


@pytest.fixture
def zt_mgr() -> ZeroTrustEnclaveManager:
    return ZeroTrustEnclaveManager(default_micro_ttl_s=2.0, cert_validity_s=10.0)


@pytest.fixture
def client() -> TestClient:
    app, _ = build_app()
    return TestClient(app)


def test_ephemeral_token_issuance_and_micro_ttl_expiry(zt_mgr: ZeroTrustEnclaveManager):
    """REQ-ZERO-001: Ephemeral micro-TTL credentials and validation."""
    tok = zt_mgr.issue_ephemeral_token(seat_id="lead", ttl_seconds=1.0)
    assert tok.seat_id == "lead"
    assert tok.is_expired is False

    # Valid immediately
    valid, msg = zt_mgr.validate_ephemeral_token(tok.token_id, "lead")
    assert valid is True

    # Mismatched seat ID
    valid_seat, seat_msg = zt_mgr.validate_ephemeral_token(tok.token_id, "systems")
    assert valid_seat is False
    assert "mismatch" in seat_msg

    # Simulate expiry
    tok.expires_at = time.time() - 1.0
    valid_exp, exp_msg = zt_mgr.validate_ephemeral_token(tok.token_id, "lead")
    assert valid_exp is False
    assert "expired" in exp_msg


def test_dynamic_mtls_cert_issuance_and_validation(zt_mgr: ZeroTrustEnclaveManager):
    """REQ-ZERO-002: Dynamic mTLS seat certificate generation and tamper check."""
    pk = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A\n-----END PUBLIC KEY-----"
    cert = zt_mgr.issue_seat_cert(seat_id="systems", public_key_pem=pk)
    assert cert.seat_id == "systems"
    assert cert.serial_number.startswith("cert-")
    assert len(cert.public_key_hash) == 64

    # Validate valid cert
    valid, _ = zt_mgr.validate_cert(cert.serial_number)
    assert valid is True

    # Tamper with fingerprint
    cert.fingerprint = "tampered_sig_12345"
    valid_tamper, tamper_msg = zt_mgr.validate_cert(cert.serial_number)
    assert valid_tamper is False
    assert "tamper" in tamper_msg


def test_hardware_enclave_attestation_verification(zt_mgr: ZeroTrustEnclaveManager):
    """REQ-ZERO-003: Golden measurement comparison and compromise posture."""
    golden_lead = zt_mgr.golden_measurements["lead"]

    # Valid report
    rep_ok = AttestationReport(
        enclave_id="lead",
        measurement_hash=golden_lead,
        platform_nonce="nonce-9988",
        timestamp=time.time(),
        signature="sig-ok",
    )
    valid, msg = zt_mgr.verify_attestation_report(rep_ok)
    assert valid is True
    assert zt_mgr.seat_postures["lead"] == EnclavePosture.HEALTHY

    # Tampered / compromised measurement
    rep_bad = AttestationReport(
        enclave_id="lead",
        measurement_hash="deadbeef" * 8,
        platform_nonce="nonce-9988",
        timestamp=time.time(),
        signature="sig-bad",
    )
    valid_bad, bad_msg = zt_mgr.verify_attestation_report(rep_bad)
    assert valid_bad is False
    assert "compromise" in bad_msg
    assert zt_mgr.seat_postures["lead"] == EnclavePosture.COMPROMISED


def test_continuous_zero_trust_posture_evaluation(zt_mgr: ZeroTrustEnclaveManager):
    """REQ-ZERO-004: Posture evaluation and sensitive action step-up."""
    # Healthy posture allows standard & sensitive
    zt_mgr.seat_postures["infra"] = EnclavePosture.HEALTHY
    ok_std, _ = zt_mgr.evaluate_tool_invocation_posture("infra", "read_logs", is_sensitive=False)
    assert ok_std is True
    ok_sens, _ = zt_mgr.evaluate_tool_invocation_posture("infra", "deploy_prod", is_sensitive=True)
    assert ok_sens is True

    # Degraded posture allows standard but blocks sensitive
    zt_mgr.seat_postures["infra"] = EnclavePosture.DEGRADED
    ok_std2, _ = zt_mgr.evaluate_tool_invocation_posture("infra", "read_logs", is_sensitive=False)
    assert ok_std2 is True
    ok_sens2, sens_msg = zt_mgr.evaluate_tool_invocation_posture("infra", "deploy_prod", is_sensitive=True)
    assert ok_sens2 is False
    assert "step-up" in sens_msg

    # Compromised blocks all
    zt_mgr.seat_postures["infra"] = EnclavePosture.COMPROMISED
    ok_all, comp_msg = zt_mgr.evaluate_tool_invocation_posture("infra", "read_logs", is_sensitive=False)
    assert ok_all is False
    assert "compromised" in comp_msg


def test_crl_revocation_and_instant_denial(zt_mgr: ZeroTrustEnclaveManager):
    """REQ-ZERO-005: Token and cert revocation with CRL distribution."""
    tok = zt_mgr.issue_ephemeral_token(seat_id="web")
    cert = zt_mgr.issue_seat_cert(seat_id="web", public_key_pem="PUB_KEY")

    # Revoke both
    zt_mgr.revoke_token(tok.token_id, reason="anomaly")
    zt_mgr.revoke_cert(cert.serial_number, reason="key_leak")

    # Validate denial
    v_tok, tok_msg = zt_mgr.validate_ephemeral_token(tok.token_id, "web")
    assert v_tok is False
    assert "revoked" in tok_msg

    v_cert, cert_msg = zt_mgr.validate_cert(cert.serial_number)
    assert v_cert is False
    assert "revoked" in cert_msg

    # CRL distribution inspect
    crl = zt_mgr.get_crl()
    assert tok.token_id in crl["revoked_tokens"]
    assert cert.serial_number in crl["revoked_serials"]
    assert crl["total_revocations"] == 2


def test_zero_trust_gateway_endpoints(client: TestClient):
    """Starlette API integration tests for Zero-Trust endpoints."""
    # 1. Issue & Validate Token
    r_iss = client.post("/v1/zero-trust/claim/issue", json={"seat_id": "lead", "ttl_seconds": 60})
    assert r_iss.status_code == 200
    issued_id = r_iss.json()["token_id"]

    chk_res = client.post("/v1/zero-trust/claim/validate", json={"claim_id": issued_id, "seat_id": "lead"}) # pragma: allowlist secret
    assert chk_res.status_code == 200
    assert chk_res.json()["valid"] is True

    # 2. Issue Cert
    r_cert = client.post("/v1/zero-trust/cert/issue", json={"seat_id": "systems", "public_key_pem": "KEY_123"})
    assert r_cert.status_code == 200
    serial = r_cert.json()["serial_number"]

    # 3. Attestation Report
    r_att = client.post("/v1/zero-trust/attestation/verify", json={
        "enclave_id": "systems",
        "measurement_hash": "3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b",
    })
    assert r_att.status_code == 200
    assert r_att.json()["valid"] is True

    # 4. Posture Evaluation
    r_post = client.post("/v1/zero-trust/posture/evaluate", json={
        "seat_id": "systems",
        "tool_name": "database_write",
        "is_sensitive": True,
    })
    assert r_post.status_code == 200
    assert r_post.json()["valid"] is True

    # 5. Revocation & CRL
    r_rev = client.post("/v1/zero-trust/revoke", json={"serial_number": serial})
    assert r_rev.status_code == 200
    assert serial in r_rev.json()["crl"]["revoked_serials"]

    r_crl = client.get("/v1/zero-trust/crl")
    assert r_crl.status_code == 200
    assert serial in r_crl.json()["revoked_serials"]
