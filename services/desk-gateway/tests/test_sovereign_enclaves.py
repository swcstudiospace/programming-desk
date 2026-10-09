import pytest
from desk_gateway.sovereign_enclaves import (
    AttestedDataFencingEngine,
    EnclaveBreachSimulator,
    SovereignEnclaveManager,
    TenancyTier,
    TenantKeyEncapsulationMesh,
    TenantSovereigntyProfile,
    ZKTokenMasker,
)


def test_zk_token_masker_pii_redaction():
    masker = ZKTokenMasker()
    session_id = "test-session-123"
    raw_text = "User admin@corp.example accessed server at 192.168.1.50 using key sk-abcdef1234567890abcdef."

    masked = masker.mask_payload(session_id, raw_text)
    assert "admin@corp.example" not in masked
    assert "192.168.1.50" not in masked
    assert "sk-abcdef1234567890abcdef" not in masked
    assert "<ZK_MASK:EMAIL:" in masked
    assert "<ZK_MASK:IP:" in masked
    assert "<ZK_MASK:API_KEY:" in masked

    unmasked = masker.unmask_payload(session_id, masked)
    assert unmasked == raw_text


def test_tenant_key_encapsulation_and_rotation():
    kem = TenantKeyEncapsulationMesh(master_seed="test-kem-seed")
    tenant_id = "tenant-acme"

    v1, k1 = kem.get_or_create_key(tenant_id)
    assert v1 == 1

    sig = kem.sign_for_tenant(tenant_id, "important-contract-data")
    assert sig.startswith("v1:")
    assert kem.verify_tenant_signature(tenant_id, "important-contract-data", sig) is True

    # Rotate key
    v2, k2 = kem.rotate_key(tenant_id)
    assert v2 == 2
    assert k1 != k2

    sig2 = kem.sign_for_tenant(tenant_id, "important-contract-data")
    assert sig2.startswith("v2:")
    assert kem.verify_tenant_signature(tenant_id, "important-contract-data", sig2) is True
    # Prior signature can still be verified with historical version
    assert kem.verify_tenant_signature(tenant_id, "important-contract-data", sig) is True


def test_attested_data_fencing_residency_and_tools():
    kem = TenantKeyEncapsulationMesh()
    fencing = AttestedDataFencingEngine(kem)

    profile = TenantSovereigntyProfile(
        tenant_id="tenant-eu-bank",
        tier=TenancyTier.ISOLATED,
        allowed_residency_regions=["eu-central-1", "eu-west-1"],
        allowed_desks=["desk-frankfurt-01"],
        allowed_tools=["sql_readonly"],
    )

    # Valid egress
    ok_receipt = fencing.evaluate_boundary(
        profile=profile,
        action="dispatch_job",
        destination_region="eu-central-1",
        destination_desk="desk-frankfurt-01",
        tools_requested=["sql_readonly"],
    )
    assert ok_receipt.is_allowed is True
    assert ok_receipt.violation_reason is None
    assert kem.verify_tenant_signature(
        profile.tenant_id,
        f"{ok_receipt.receipt_id}:{profile.tenant_id}:dispatch_job:eu-central-1:desk-frankfurt-01:True",
        ok_receipt.signature,
    )

    # Residency violation
    bad_res_receipt = fencing.evaluate_boundary(
        profile=profile,
        action="dispatch_job",
        destination_region="us-east-1",
        destination_desk="desk-frankfurt-01",
    )
    assert bad_res_receipt.is_allowed is False
    assert "Data residency violation" in bad_res_receipt.violation_reason

    # Tool violation
    bad_tool_receipt = fencing.evaluate_boundary(
        profile=profile,
        action="dispatch_job",
        destination_region="eu-central-1",
        destination_desk="desk-frankfurt-01",
        tools_requested=["sql_readonly", "bash_exec"],
    )
    assert bad_tool_receipt.is_allowed is False
    assert "Tool fence violation" in bad_tool_receipt.violation_reason


def test_sovereign_enclave_memory_isolation_and_breach():
    manager = SovereignEnclaveManager()
    p1 = TenantSovereigntyProfile(
        tenant_id="tenant-alpha",
        tier=TenancyTier.SOVEREIGN_AIRGAPPED,
        allowed_residency_regions=["us-east-1"],
        allowed_desks=["desk-alpha"],
        allowed_tools=[],
    )
    manager.register_tenant(p1)

    manager.store_tenant_data("tenant-alpha", "vault_key", "secret123", requesting_tenant="tenant-alpha")
    assert manager.read_tenant_data("tenant-alpha", "vault_key", requesting_tenant="tenant-alpha") == "secret123"

    # Unauthorized read attempt
    with pytest.raises(PermissionError):
        manager.read_tenant_data("tenant-alpha", "vault_key", requesting_tenant="tenant-attacker")

    # Unauthorized write attempt
    with pytest.raises(PermissionError):
        manager.store_tenant_data("tenant-alpha", "vault_key", "corrupted", requesting_tenant="tenant-attacker")

    assert len(manager.breach_log) == 2


def test_enclave_breach_benchmark_simulation():
    manager = SovereignEnclaveManager()
    res = EnclaveBreachSimulator.run_benchmark(manager)
    assert res["all_passed"] is True
    assert res["memory_breach_blocked"] is True
    assert res["fencing_breach_blocked"] is True
    assert res["tool_breach_blocked"] is True
    assert res["keys_disjoint"] is True
    assert res["logged_breaches_count"] >= 1
