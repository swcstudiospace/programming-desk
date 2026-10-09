import hashlib
import hmac
import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app

@pytest.fixture
def client():
    app, _ = build_app()
    return TestClient(app)

def test_bridge_routes_e2e(client):
    # 1. Relay Genesis EVM header
    h0_payload = {
        "chain_type": "EVM",
        "height": 0,
        "block_hash": "0xgenesis",
        "parent_hash": "0x0",
        "state_root": "0xstateroot0",
        "receipts_root": "0x0",
        "relayer_id": "relayer-primary",
    }
    resp = client.post("/v1/bridge/relay/header", json=h0_payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 2. Relay next header
    h1_payload = {
        "chain_type": "EVM",
        "height": 1,
        "block_hash": "0xblock1",
        "parent_hash": "0xgenesis",
        "state_root": "0xstateroot1",
        "receipts_root": "0x1",
        "relayer_id": "relayer-primary",
    }
    resp = client.post("/v1/bridge/relay/header", json=h1_payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 3. Dispatch cross-chain message
    signing_secret = b"cross-chain-relay-secret"
    sig_payload = "msg-100:EVM:SOLANA:1".encode("utf-8")
    sig = hmac.new(signing_secret, sig_payload, hashlib.sha256).hexdigest()

    dispatch_payload = {
        "message_id": "msg-100",
        "source_chain": "EVM",
        "target_chain": "SOLANA",
        "sender_address": "0xUserEVM",
        "recipient_address": "SolanaPubkey111",
        "payload": {"action": "mint_asset", "symbol": "DESK", "amount": 100},
        "nonce": 1,
        "proof": "dummy-proof",
        "signature": sig,
        "relayer_id": "relayer-primary",
    }
    resp = client.post("/v1/bridge/message/dispatch", json=dispatch_payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["dispatch"]["status"] == "DISPATCHED"

    # Replay same message -> fails
    resp_replay = client.post("/v1/bridge/message/dispatch", json=dispatch_payload)
    assert resp_replay.status_code == 400
    assert resp_replay.json()["ok"] is False


def test_oracle_routes_e2e(client):
    # Ingest multiple oracle reports
    for seat, val in [("lead", 150.0), ("reviewer", 152.0), ("operator", 149.0), ("adversary", 999.0)]:
        resp = client.post("/v1/oracle/reports/ingest", json={
            "feed_name": "SOL-USD",
            "source_id": seat,
            "value": val,
            "signature": f"sig-{seat}",
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    # Finalize feed
    resp = client.post("/v1/oracle/feeds/SOL-USD/finalize", json={"min_reports": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert 149.0 <= data["feed"]["median_value"] <= 152.0
    assert "anchor" in data
    assert data["anchor"]["feed_name"] == "SOL-USD"

    # Get latest feed
    resp = client.get("/v1/oracle/feeds/SOL-USD")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["feed"]["feed_name"] == "SOL-USD"


def test_bridge_drill_simulate_e2e(client):
    resp = client.post("/v1/bridge/drill/simulate")
    assert resp.status_code == 200
    drill = resp.json()["drill"]
    assert drill["status"] == "PASS"
