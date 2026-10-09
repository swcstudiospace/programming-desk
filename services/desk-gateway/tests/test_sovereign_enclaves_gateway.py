import pytest
from starlette.testclient import TestClient
from desk_gateway.server import build_app


@pytest.fixture
def test_client():
    app, _ = build_app()
    return TestClient(app)


def test_enclave_gateway_register_and_mask_unmask(test_client):
    reg_resp = test_client.post(
        "/v1/enclaves/tenant/register",
        json={
            "tenant_id": "tenant-gateway-01",
            "tier": "ISOLATED",
            "allowed_residency_regions": ["us-east-1"],
            "allowed_desks": ["desk-test-alpha"],
            "allowed_tools": ["sql_exec"],
        },
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["ok"] is True
    assert reg_resp.json()["tier"] == "ISOLATED"

    # Mask text
    mask_resp = test_client.post(
        "/v1/enclaves/mask",
        json={
            "session_id": "sess-gw-1",
            "text": "Call john@example.com with key sk-123456789012345678901234",
        },
    )
    assert mask_resp.status_code == 200
    masked_text = mask_resp.json()["masked_text"]
    assert "john@example.com" not in masked_text
    assert "<ZK_MASK:" in masked_text

    # Unmask text
    unmask_resp = test_client.post(
        "/v1/enclaves/unmask",
        json={
            "session_id": "sess-gw-1",
            "masked_text": masked_text,
        },
    )
    assert unmask_resp.status_code == 200
    assert unmask_resp.json()["unmasked_text"] == "Call john@example.com with key sk-123456789012345678901234"


def test_enclave_gateway_fencing_evaluation(test_client):
    test_client.post(
        "/v1/enclaves/tenant/register",
        json={
            "tenant_id": "tenant-fence-test",
            "tier": "ISOLATED",
            "allowed_residency_regions": ["eu-central-1"],
            "allowed_desks": ["desk-eu"],
            "allowed_tools": ["search_tool"],
        },
    )

    # Allowed evaluation
    ok_resp = test_client.post(
        "/v1/enclaves/fencing/evaluate",
        json={
            "tenant_id": "tenant-fence-test",
            "destination_region": "eu-central-1",
            "destination_desk": "desk-eu",
            "tools_requested": ["search_tool"],
        },
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["fencing_decision"]["is_allowed"] is True

    # Blocked evaluation (wrong region)
    blocked_resp = test_client.post(
        "/v1/enclaves/fencing/evaluate",
        json={
            "tenant_id": "tenant-fence-test",
            "destination_region": "ap-southeast-1",
            "destination_desk": "desk-eu",
        },
    )
    assert blocked_resp.status_code == 200
    assert blocked_resp.json()["fencing_decision"]["is_allowed"] is False
    assert "Data residency violation" in blocked_resp.json()["fencing_decision"]["violation_reason"]


def test_enclave_gateway_key_rotate_and_breach_benchmark(test_client):
    test_client.post(
        "/v1/enclaves/tenant/register",
        json={"tenant_id": "tenant-rot-01", "tier": "STANDARD"},
    )

    rot_resp = test_client.post("/v1/enclaves/key/rotate", json={"tenant_id": "tenant-rot-01"})
    assert rot_resp.status_code == 200
    assert rot_resp.json()["active_key_version"] == 2

    bench_resp = test_client.post("/v1/enclaves/breach-test/run", json={})
    assert bench_resp.status_code == 200
    assert bench_resp.json()["benchmark"]["all_passed"] is True
