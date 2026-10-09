"""Gateway REST integration tests for Phase 44 & Phase 45."""

import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def client(tmp_path):
    app, _ = build_app()
    return TestClient(app)


def test_pqc_cryptography_gateway_routes(client):
    # 1. Generate keypair
    key_resp = client.post("/v1/pqc/keys/generate", json={"key_id": "api-seat-kem"})
    assert key_resp.status_code == 200
    assert key_resp.json()["ok"] is True
    assert key_resp.json()["bundle"]["key_id"] == "api-seat-kem"

    # 2. Encapsulate
    encap_resp = client.post("/v1/pqc/kem/encapsulate", json={"key_id": "api-seat-kem"})
    assert encap_resp.status_code == 200
    assert encap_resp.json()["ok"] is True
    assert "classical_ciphertext" in encap_resp.json()["receipt"]

    # 3. Sign & verify
    sign_resp = client.post("/v1/pqc/signature/sign", json={"message": "Deploy smart contract", "key_id": "api-seat"})
    assert sign_resp.status_code == 200
    assert sign_resp.json()["ok"] is True
    sig = sign_resp.json()["signature"]

    verify_resp = client.post("/v1/pqc/signature/verify", json={"message": "Deploy smart contract", "signature": sig})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True

    # 4. Audit negotiation
    nego_resp = client.post(
        "/v1/pqc/audit/negotiate",
        json={
            "client_suites": ["X25519+ML-KEM-768", "X25519"],
            "server_suites": ["X25519+ML-KEM-768"],
            "agreed_suite": "X25519+ML-KEM-768",
        },
    )
    assert nego_resp.status_code == 200
    assert nego_resp.json()["negotiation"]["status"] == "APPROVED"


def test_pqc_lattice_ledger_and_passport_gateway_routes(client):
    # 1. Issue passport
    pass_resp = client.post("/v1/pqc/identity/passport/issue", json={"seat_id": "lead", "roles": ["ADMIN"]})
    assert pass_resp.status_code == 200
    passport = pass_resp.json()["passport"]
    assert passport["seat_id"] == "lead"

    # 2. Verify passport
    vpass_resp = client.post("/v1/pqc/identity/passport/verify", json={"passport": passport})
    assert vpass_resp.status_code == 200
    assert vpass_resp.json()["verification"]["verified"] is True

    # 3. Append ledger entry
    entry_resp = client.post(
        "/v1/pqc/ledger/append",
        json={"action": "test_quantum_receipt", "payload": {"status": "ok"}},
    )
    assert entry_resp.status_code == 200
    assert entry_resp.json()["ok"] is True
    assert "merkle_root" in entry_resp.json()

    # 4. Export anchor
    anchor_resp = client.post("/v1/pqc/ledger/anchor/export", json={})
    assert anchor_resp.status_code == 200
    assert anchor_resp.json()["anchor"]["status"] == "CONFIRMED"

    # 5. Run quantum attack drill
    drill_resp = client.post("/v1/pqc/drill/simulate", json={})
    assert drill_resp.status_code == 200
    assert drill_resp.json()["drill"]["status"] == "PASS"
