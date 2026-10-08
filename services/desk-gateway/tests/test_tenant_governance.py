"""Tests for multi-tenant governance and RBAC policy enforcement (REQ-TENANT-001, REQ-TENANT-002)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.rbac import (
    AccessDecision,
    PolicyRule,
    RBACPolicyEngine,
    Role,
)
from desk_gateway.server import build_app
from desk_gateway.tenant import (
    TenantContext,
    TenantIsolationEngine,
    TenantIsolationError,
    current_tenant,
)


def test_tenant_context_validation() -> None:
    # Valid tenant context
    ctx = TenantContext(tenant_id="acme", org_id="org-acme", team_id="team-alpha", environment="staging")
    assert ctx.tenant_id == "acme"
    assert ctx.namespace == "org-acme:team-alpha:acme"
    assert ctx.to_dict()["namespace"] == "org-acme:team-alpha:acme"

    # Invalid characters in tenant_id should raise TenantIsolationError
    with pytest.raises(TenantIsolationError):
        TenantContext(tenant_id="invalid/tenant!@#")

    with pytest.raises(TenantIsolationError):
        TenantContext(org_id="")


def test_tenant_isolation_partition_keys() -> None:
    engine = TenantIsolationEngine()
    tenant_a = TenantContext(tenant_id="tenant-a", org_id="org-1", team_id="team-1")
    tenant_b = TenantContext(tenant_id="tenant-b", org_id="org-2", team_id="team-2")

    key = "dataset-vector-index"
    partitioned = engine.partition_key(tenant_a, key)
    assert partitioned == f"{tenant_a.namespace}::{key}"

    # Unpartitioning with owner succeeds
    assert engine.unpartition_key(tenant_a, partitioned) == key

    # Unpartitioning with different tenant fails
    with pytest.raises(TenantIsolationError):
        engine.unpartition_key(tenant_b, partitioned)

    # Cross-tenant assertion check
    with pytest.raises(TenantIsolationError):
        engine.assert_same_tenant(tenant_a, "tenant-b", resource_name="memory_partition")


def test_tenant_header_extraction() -> None:
    engine = TenantIsolationEngine()

    # Empty headers fallback to default
    ctx_default = engine.extract_from_headers({})
    assert ctx_default.tenant_id == "default"

    # Provided headers
    headers = {
        "x-tenant-id": "client-corp",
        "x-org-id": "org-corp",
        "x-team-id": "team-eng",
        "x-environment": "prod",
    }
    extracted = engine.extract_from_headers(headers)
    assert extracted.tenant_id == "client-corp"
    assert extracted.org_id == "org-corp"
    assert extracted.team_id == "team-eng"
    assert extracted.environment == "prod"


def test_rbac_policy_engine_evaluation() -> None:
    rbac = RBACPolicyEngine(strict_gates=["g5", "g6"])
    tenant = TenantContext(tenant_id="corp", environment="prod")

    # Admin has unrestricted access
    res_admin = rbac.evaluate(tenant, Role.ADMIN, seat="lead", action="tool:any_tool")
    assert res_admin.decision == AccessDecision.ALLOW

    # Lead has access across seats
    res_lead = rbac.evaluate(tenant, Role.LEAD, seat="lead", action="tool:desk_brief")
    assert res_lead.decision == AccessDecision.ALLOW

    # Gate 5 requires approval and rollback plan
    res_g5_unapproved = rbac.evaluate(
        tenant,
        Role.DEVELOPER,
        seat="systems",
        action="tool:modify_config",
        gates=["g5"],
        has_approval=False,
        has_rollback_plan=False,
    )
    assert res_g5_unapproved.decision == AccessDecision.DENY
    assert "Gate 5" in res_g5_unapproved.reason

    # Gate 5 approved
    res_g5_approved = rbac.evaluate(
        tenant,
        Role.DEVELOPER,
        seat="systems",
        action="tool:modify_config",
        gates=["g5"],
        has_approval=True,
        has_rollback_plan=True,
    )
    assert res_g5_approved.decision == AccessDecision.ALLOW

    # Gate 6 requires approval
    res_g6_unapproved = rbac.evaluate(
        tenant,
        Role.OPERATOR,
        seat="infra",
        action="tool:destroy_cluster",
        gates=["g6"],
        has_approval=False,
    )
    assert res_g6_unapproved.decision == AccessDecision.DENY

    # Auditor cannot perform write actions
    res_auditor = rbac.evaluate(tenant, Role.AUDITOR, seat="lead", action="tool:write_data")
    assert res_auditor.decision == AccessDecision.DENY

    # Unknown role denied
    res_unknown = rbac.evaluate(tenant, "hacker_role", seat="lead", action="tool:desk_brief")
    assert res_unknown.decision == AccessDecision.DENY


def test_tenant_api_endpoints() -> None:
    app, _ = build_app()
    client = TestClient(app)

    # 1. GET /v1/tenant/current with default tenant
    resp = client.get("/v1/tenant/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["tenant"]["tenant_id"] == "default"

    # 2. GET /v1/tenant/current with custom headers
    resp = client.get(
        "/v1/tenant/current",
        headers={
            "X-Tenant-Id": "acme-corp",
            "X-Org-Id": "acme-org",
            "X-Team-Id": "acme-infra",
            "X-Environment": "staging",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant"]["tenant_id"] == "acme-corp"
    assert data["tenant"]["org_id"] == "acme-org"
    assert data["tenant"]["namespace"] == "acme-org:acme-infra:acme-corp"

    # 3. GET /v1/tenant/policies
    resp = client.get("/v1/tenant/policies")
    assert resp.status_code == 200
    policies_data = resp.json()
    assert policies_data["ok"] is True
    assert policies_data["count"] > 0

    # 4. POST /v1/tenant/policies/evaluate
    eval_payload = {
        "role": "developer",
        "seat": "systems",
        "action": "tool:desk_brief",
    }
    resp = client.post("/v1/tenant/policies/evaluate", json=eval_payload)
    assert resp.status_code == 200
    eval_res = resp.json()
    assert eval_res["ok"] is True
    assert eval_res["decision"] == "allow"

    # 5. POST /v1/tenant/policies/evaluate with unrecognized role
    eval_unknown_payload = {
        "role": "unauthorized_role",
        "seat": "systems",
        "action": "tool:desk_brief",
    }
    resp = client.post("/v1/tenant/policies/evaluate", json=eval_unknown_payload)
    assert resp.status_code == 200
    eval_res = resp.json()
    assert eval_res["ok"] is False
    assert eval_res["decision"] == "deny"


def test_tenant_memory_bank_and_dataset_isolation() -> None:
    engine = TenantIsolationEngine()
    tenant_corp = TenantContext(tenant_id="corp", org_id="org-acme")
    tenant_fin = TenantContext(tenant_id="fin", org_id="org-acme")

    # Bank name partition
    bank_name = engine.tenant_bank_name(tenant_corp, "lead")
    assert bank_name == "org-acme-corp-pd-lead"

    org_id, tenant_id, seat = engine.parse_tenant_bank_name(bank_name)
    assert org_id == "org"
    assert tenant_id == "acme-corp"
    assert seat == "lead"

    # Dataset boundary token authentication
    token = engine.create_dataset_token(tenant_corp, "knowledge-base-v1")
    assert engine.verify_dataset_token(tenant_corp, "knowledge-base-v1", token) is True
    # Fails for different tenant
    assert engine.verify_dataset_token(tenant_fin, "knowledge-base-v1", token) is False
    # Fails for altered dataset_id
    assert engine.verify_dataset_token(tenant_corp, "other-dataset", token) is False


def test_tenant_quota_policer() -> None:
    from desk_gateway.tenant_quota import (
        QuotaExceededError,
        TenantQuotaLimits,
        TenantQuotaPolicer,
    )

    limits = TenantQuotaLimits(
        max_requests_per_minute=60.0,  # 1 req/sec
        burst_ceiling=3.0,
        max_concurrent_operations=2,
    )
    policer = TenantQuotaPolicer(default_limits=limits)
    tenant = TenantContext(tenant_id="tenant-burst")

    # Burst tokens acquisition: ceiling is 3.0
    res1 = policer.acquire(tenant, cost=1.0, now=100.0)
    assert res1["allowed"] is True
    assert res1["remaining_tokens"] == 2.0

    res2 = policer.acquire(tenant, cost=1.0, now=100.0)
    assert res2["allowed"] is True

    # Max concurrency check: active is now 2, limit is 2
    with pytest.raises(QuotaExceededError) as exc_info:
        policer.acquire(tenant, cost=1.0, now=100.0)
    assert "concurrency" in str(exc_info.value)

    # Release 1 concurrent operation
    policer.release(tenant)

    # Token bucket exhaustion: tokens remaining was 1.0, cost 1.0 -> 0.0 tokens left
    res3 = policer.acquire(tenant, cost=1.0, now=100.0)
    assert res3["allowed"] is True

    # Release concurrent operation to test burst rate exhaustion without concurrency block
    policer.release(tenant)

    # Next immediate request exhausts burst tokens
    with pytest.raises(QuotaExceededError) as exc_info:
        policer.acquire(tenant, cost=1.0, now=100.0)
    assert "rate_burst" in str(exc_info.value)

    # After 2 seconds, refilled 2 tokens (1 req/sec)
    res4 = policer.acquire(tenant, cost=1.0, now=102.0)
    assert res4["allowed"] is True


def test_tenant_audit_logger_cryptographic_chain() -> None:
    from desk_gateway.tenant_audit import (
        AuditTamperError,
        GENESIS_HASH,
        TenantAuditLogger,
    )

    logger = TenantAuditLogger()
    tenant = TenantContext(tenant_id="audit-tenant", org_id="org-audit")

    # Empty chain verification
    v0 = logger.verify_chain(tenant)
    assert v0["valid"] is True
    assert v0["count"] == 0

    # Record event 1
    evt1 = logger.record_event(
        tenant=tenant,
        action="model_query",
        seat="systems",
        actor="dev-user",
        details={"prompt_tokens": 120},
        timestamp=1000.0,
    )
    assert evt1.prev_hash == GENESIS_HASH

    # Record event 2
    evt2 = logger.record_event(
        tenant=tenant,
        action="execute_plan",
        seat="lead",
        actor="orchestrator",
        details={"plan_id": "16-02"},
        timestamp=1001.0,
    )
    assert evt2.prev_hash == evt1.event_hash

    # Verify chain
    v2 = logger.verify_chain(tenant)
    assert v2["valid"] is True
    assert v2["count"] == 2
    assert v2["root_hash"] == evt2.event_hash

    # Tamper with event 1 details
    evt1.details["prompt_tokens"] = 99999
    with pytest.raises(AuditTamperError) as exc_info:
        logger.verify_chain(tenant)
    assert "Payload tampering detected" in str(exc_info.value)


def test_tenant_quota_and_audit_api_routes() -> None:
    app, _ = build_app()
    client = TestClient(app)
    headers = {"X-Tenant-Id": "api-tenant", "X-Org-Id": "org-api"}

    # 1. GET /v1/tenant/quota
    resp = client.get("/v1/tenant/quota", headers=headers)
    assert resp.status_code == 200
    q_data = resp.json()
    assert q_data["ok"] is True
    assert q_data["quota"]["tenant_id"] == "api-tenant"

    # 2. POST /v1/tenant/quota/acquire
    resp = client.post("/v1/tenant/quota/acquire", headers=headers, json={"cost": 1.0})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 3. POST /v1/tenant/quota/release
    resp = client.post("/v1/tenant/quota/release", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 4. POST /v1/tenant/audit/record
    resp = client.post(
        "/v1/tenant/audit/record",
        headers=headers,
        json={
            "action": "dataset_ingest",
            "seat": "data",
            "actor": "admin",
            "details": {"chunks": 50},
        },
    )
    assert resp.status_code == 200
    event_data = resp.json()
    assert event_data["ok"] is True
    assert event_data["event"]["action"] == "dataset_ingest"

    # 5. GET /v1/tenant/audit
    resp = client.get("/v1/tenant/audit", headers=headers)
    assert resp.status_code == 200
    trail = resp.json()
    assert trail["ok"] is True
    assert trail["count"] >= 1

    # 6. POST /v1/tenant/audit/verify
    resp = client.post("/v1/tenant/audit/verify", headers=headers)
    assert resp.status_code == 200
    v_res = resp.json()
    assert v_res["ok"] is True
    assert v_res["tamper_detected"] is False

