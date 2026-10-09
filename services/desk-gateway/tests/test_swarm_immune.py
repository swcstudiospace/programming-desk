"""Unit and integration tests for Swarm Immune Defense & Seat Quarantine (Milestone v3.4 - Phase 34)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.server import build_app
from desk_gateway.swarm_immune import (
    BehavioralProfile,
    SeatContainmentState,
    ShadowExecutionSandbox,
    SwarmImmuneEngine,
    calculate_shannon_entropy,
)


def test_shannon_entropy():
    # Empty string entropy is 0
    assert calculate_shannon_entropy("") == 0.0
    # Single repeating character has zero entropy
    assert calculate_shannon_entropy("aaaaaaa") == 0.0
    # Diverse high-entropy string
    high_ent = calculate_shannon_entropy("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*")
    assert high_ent > 4.5


def test_behavioral_profile_and_anomaly_score():
    profile = BehavioralProfile(seat_id="seat-1", alpha=0.5)
    assert profile.state == SeatContainmentState.HEALTHY
    
    # Baseline update
    score1 = profile.update(latency_ms=50.0, entropy=3.0, is_error=False)
    assert score1 >= 0.0

    # Large latency and error spike
    score2 = profile.update(latency_ms=5000.0, entropy=7.5, is_error=True)
    assert score2 > score1
    assert score2 >= 1.0


def test_swarm_immune_engine_quarantine_transitions():
    engine = SwarmImmuneEngine(secret_key="test-key-3.4")

    # Record normal telemetry
    res1 = engine.record_telemetry(
        seat_id="seat-alpha",
        tool_name="git_status",
        payload="branch main up to date",
        latency_ms=45.0,
        is_error=False,
    )
    assert res1["state"] == SeatContainmentState.HEALTHY.value
    assert engine.is_capability_permitted("seat-alpha", "mcp_tool_execute") is True

    # High anomaly event -> quarantine
    res2 = engine.record_telemetry(
        seat_id="seat-alpha",
        tool_name="exec_script",
        payload="X" * 1000 + "randomPayload1239847129847!@#$!@#$",
        latency_ms=10000.0,
        is_error=True,
    )
    # The anomaly score crosses quarantine threshold
    assert res2["anomaly_score"] >= 1.0
    assert res2["state"] == SeatContainmentState.QUARANTINED.value

    # Check capabilities are pruned
    allowed = engine.get_allowed_capabilities("seat-alpha")
    assert "git_commit" not in allowed
    assert "file_mutate" not in allowed
    assert "read_telemetry" in allowed
    assert engine.is_capability_permitted("seat-alpha", "git_commit") is False

    # Check HMAC quarantine receipt
    assert len(engine.receipts) == 1
    receipt = engine.receipts[0]
    assert receipt["seat_id"] == "seat-alpha"
    assert receipt["action"] == "QUARANTINE"
    assert engine.verify_receipt(receipt) is True

    # Unquarantine seat
    unq = engine.unquarantine_seat("seat-alpha", reason="Audit cleared")
    assert unq["state"] == SeatContainmentState.HEALTHY.value
    assert engine.is_capability_permitted("seat-alpha", "git_commit") is True


def test_shadow_execution_sandbox():
    sandbox = ShadowExecutionSandbox()

    def normal_handler(args):
        return {"processed": args["val"] * 2}

    def failing_handler(args):
        raise ValueError("Invalid shadow instruction")

    res_ok = sandbox.execute_in_shadow("exec-1", "seat-beta", "calc", {"val": 21}, normal_handler)
    assert res_ok["status"] == "SAFE"
    assert res_ok["result"] == {"processed": 42}
    assert res_ok["sandboxed"] is True

    res_fail = sandbox.execute_in_shadow("exec-2", "seat-beta", "calc", {"val": 0}, failing_handler)
    assert res_fail["status"] == "SUSPICIOUS_FAIL"
    assert "Invalid shadow instruction" in res_fail["error"]


def test_quarantine_receipt_tamper_rejection():
    engine = SwarmImmuneEngine(secret_key="secret-salt")
    rec = engine._generate_receipt("seat-delta", "DRAIN", "Malicious actor detected")
    assert engine.verify_receipt(rec) is True

    # Tamper with receipt
    tampered_rec = dict(rec)
    tampered_rec["reason"] = "Tampered reason"
    assert engine.verify_receipt(tampered_rec) is False


def test_immune_rest_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Telemetry evaluation endpoint
    eval_resp = client.post(
        "/v1/immune/telemetry/evaluate",
        json={
            "seat_id": "seat-gamma",
            "tool_name": "fs_read",
            "payload": "normal harmless read payload",
            "latency_ms": 25.0,
            "is_error": False,
        },
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["ok"] is True
    assert eval_data["telemetry"]["state"] == "HEALTHY"

    # 2. Manual quarantine endpoint
    q_resp = client.post(
        "/v1/immune/seat/quarantine",
        json={"seat_id": "seat-gamma", "reason": "Operator command execution flag"},
    )
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert q_data["ok"] is True
    assert q_data["result"]["state"] == "QUARANTINED"
    assert "signature" in q_data["result"]["receipt"]

    # 3. Shadow execute endpoint
    shadow_resp = client.post(
        "/v1/immune/shadow/execute",
        json={
            "seat_id": "seat-gamma",
            "tool_name": "speculative_bash",
            "arguments": {"cmd": "ls -la"},
        },
    )
    assert shadow_resp.status_code == 200
    shadow_data = shadow_resp.json()
    assert shadow_data["ok"] is True
    assert shadow_data["execution"]["status"] == "SAFE"

    # 4. Status endpoint
    status_resp = client.get("/v1/immune/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["ok"] is True
    assert "seat-gamma" in status_data["status"]["seats"]
    assert status_data["status"]["seats"]["seat-gamma"]["state"] == "QUARANTINED"

    # 5. Unquarantine endpoint
    unq_resp = client.post(
        "/v1/immune/seat/unquarantine",
        json={"seat_id": "seat-gamma", "reason": "Passed security review"},
    )
    assert unq_resp.status_code == 200
    unq_data = unq_resp.json()
    assert unq_data["ok"] is True
    assert unq_data["result"]["state"] == "HEALTHY"
