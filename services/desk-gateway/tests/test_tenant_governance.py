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
