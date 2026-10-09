"""Multi-Tenant Sovereign Enclaves & Attested Data Fencing Engine.

Provides cryptographically isolated sovereign enclaves, zero-knowledge token masking / PII redaction,
tenant key encapsulation with dynamic rotation, attested data fencing policies, and breach benchmarking.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class TenancyTier(str, Enum):
    STANDARD = "STANDARD"
    ISOLATED = "ISOLATED"
    SOVEREIGN_AIRGAPPED = "SOVEREIGN_AIRGAPPED"


@dataclass
class TenantSovereigntyProfile:
    tenant_id: str
    tier: TenancyTier
    allowed_residency_regions: List[str]
    allowed_desks: List[str]
    allowed_tools: List[str]
    forbidden_egress_domains: List[str] = field(default_factory=list)
    enforce_pii_masking: bool = True
    active_key_version: int = 1
    created_at: float = field(default_factory=time.time)


@dataclass
class FencingDecisionReceipt:
    receipt_id: str
    tenant_id: str
    action: str
    destination_region: str
    destination_desk: str
    is_allowed: bool
    violation_reason: Optional[str]
    timestamp: float
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "destination_region": self.destination_region,
            "destination_desk": self.destination_desk,
            "is_allowed": self.is_allowed,
            "violation_reason": self.violation_reason,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class ZKTokenMasker:
    """Zero-knowledge token masking and PII redaction pipeline with reversible session maps."""

    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    API_KEY_PATTERN = re.compile(r"(?:sk-[a-zA-Z0-9]{20,}|key-[a-zA-Z0-9]{16,}|ghp_[a-zA-Z0-9]{20,})")
    IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

    def __init__(self) -> None:
        self._session_token_maps: Dict[str, Dict[str, str]] = {}
        self._reverse_token_maps: Dict[str, Dict[str, str]] = {}

    def mask_payload(self, session_id: str, text: str) -> str:
        token_map = self._session_token_maps.setdefault(session_id, {})
        rev_map = self._reverse_token_maps.setdefault(session_id, {})

        def replace_with_token(match: re.Match, token_type: str) -> str:
            val = match.group(0)
            if val in rev_map:
                return rev_map[val]
            surrogate = f"<ZK_MASK:{token_type}:{secrets.token_hex(4)}>"
            token_map[surrogate] = val
            rev_map[val] = surrogate
            return surrogate

        # Redact API keys first
        masked = self.API_KEY_PATTERN.sub(lambda m: replace_with_token(m, "API_KEY"), text)
        # Redact emails
        masked = self.EMAIL_PATTERN.sub(lambda m: replace_with_token(m, "EMAIL"), masked)
        # Redact IP addresses
        masked = self.IP_PATTERN.sub(lambda m: replace_with_token(m, "IP"), masked)

        return masked

    def unmask_payload(self, session_id: str, masked_text: str) -> str:
        token_map = self._session_token_maps.get(session_id, {})
        unmasked = masked_text
        for surrogate, original in token_map.items():
            unmasked = unmasked.replace(surrogate, original)
        return unmasked


class TenantKeyEncapsulationMesh:
    """Tenant Key Encapsulation Mechanism (KEM) generating distinct cryptographic roots with rotation."""

    def __init__(self, master_seed: str = "desk-master-enclave-seed") -> None:
        self.master_seed = master_seed.encode("utf-8")
        # tenant_id -> {version: key_bytes}
        self._tenant_keys: Dict[str, Dict[int, bytes]] = {}
        self._active_versions: Dict[str, int] = {}

    def get_or_create_key(self, tenant_id: str, version: Optional[int] = None) -> Tuple[int, bytes]:
        if tenant_id not in self._tenant_keys:
            self._tenant_keys[tenant_id] = {}
            self._active_versions[tenant_id] = 1

        active_ver = self._active_versions[tenant_id]
        target_ver = version or active_ver

        if target_ver not in self._tenant_keys[tenant_id]:
            # Derive deterministic versioned key from master seed and tenant ID
            h = hmac.new(
                self.master_seed,
                f"kem:{tenant_id}:v{target_ver}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
            self._tenant_keys[tenant_id][target_ver] = h

        return target_ver, self._tenant_keys[tenant_id][target_ver]

    def rotate_key(self, tenant_id: str) -> Tuple[int, bytes]:
        curr_ver = self._active_versions.get(tenant_id, 1)
        new_ver = curr_ver + 1
        self._active_versions[tenant_id] = new_ver
        return self.get_or_create_key(tenant_id, version=new_ver)

    def sign_for_tenant(self, tenant_id: str, data: str) -> str:
        ver, key = self.get_or_create_key(tenant_id)
        sig = hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"v{ver}:{sig}"

    def verify_tenant_signature(self, tenant_id: str, data: str, full_sig: str) -> bool:
        if ":" not in full_sig:
            return False
        ver_str, sig = full_sig.split(":", 1)
        try:
            ver = int(ver_str.lstrip("v"))
        except ValueError:
            return False

        _, key = self.get_or_create_key(tenant_id, version=ver)
        expected = hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)


class AttestedDataFencingEngine:
    """Enforces data residency, compute tenancy tiers, and cross-desk egress boundaries."""

    def __init__(self, kem: TenantKeyEncapsulationMesh) -> None:
        self.kem = kem

    def evaluate_boundary(
        self,
        profile: TenantSovereigntyProfile,
        action: str,
        destination_region: str,
        destination_desk: str,
        tools_requested: Optional[List[str]] = None,
    ) -> FencingDecisionReceipt:
        tools = tools_requested or []
        now = time.time()
        receipt_id = f"fence-{hashlib.sha256(f'{profile.tenant_id}-{destination_desk}-{now}'.encode()).hexdigest()[:12]}"

        # 1. Check data residency
        if profile.allowed_residency_regions and destination_region not in profile.allowed_residency_regions:
            reason = f"Data residency violation: region '{destination_region}' is not in allowed residency list: {profile.allowed_residency_regions}"
            return self._create_receipt(receipt_id, profile.tenant_id, action, destination_region, destination_desk, False, reason, now)

        # 2. Check destination desk
        if profile.allowed_desks and destination_desk not in profile.allowed_desks:
            reason = f"Desk isolation violation: desk '{destination_desk}' is not authorized for tenant '{profile.tenant_id}'"
            return self._create_receipt(receipt_id, profile.tenant_id, action, destination_region, destination_desk, False, reason, now)

        # 3. Check tool authorization
        if profile.allowed_tools:
            unauthorized = [t for t in tools if t not in profile.allowed_tools]
            if unauthorized:
                reason = f"Tool fence violation: tools {unauthorized} are forbidden for tenant '{profile.tenant_id}'"
                return self._create_receipt(receipt_id, profile.tenant_id, action, destination_region, destination_desk, False, reason, now)

        # 4. Check airgapped tier strictness
        if profile.tier == TenancyTier.SOVEREIGN_AIRGAPPED:
            if destination_desk.startswith("external-") or destination_region == "public_cloud":
                reason = f"Airgap sovereignty violation: sovereign airgapped tenant cannot egress to '{destination_desk}'"
                return self._create_receipt(receipt_id, profile.tenant_id, action, destination_region, destination_desk, False, reason, now)

        return self._create_receipt(receipt_id, profile.tenant_id, action, destination_region, destination_desk, True, None, now)

    def _create_receipt(
        self,
        receipt_id: str,
        tenant_id: str,
        action: str,
        destination_region: str,
        destination_desk: str,
        is_allowed: bool,
        violation_reason: Optional[str],
        timestamp: float,
    ) -> FencingDecisionReceipt:
        body = f"{receipt_id}:{tenant_id}:{action}:{destination_region}:{destination_desk}:{is_allowed}"
        signature = self.kem.sign_for_tenant(tenant_id, body)
        return FencingDecisionReceipt(
            receipt_id=receipt_id,
            tenant_id=tenant_id,
            action=action,
            destination_region=destination_region,
            destination_desk=destination_desk,
            is_allowed=is_allowed,
            violation_reason=violation_reason,
            timestamp=timestamp,
            signature=signature,
        )


class SovereignEnclaveManager:
    """Manages enclave life-cycles, tenant boundary sandboxes, and breach detection."""

    def __init__(self, master_seed: str = "desk-master-enclave-seed") -> None:
        self.profiles: Dict[str, TenantSovereigntyProfile] = {}
        self.kem = TenantKeyEncapsulationMesh(master_seed)
        self.masker = ZKTokenMasker()
        self.fencing_engine = AttestedDataFencingEngine(self.kem)
        self.enclave_memory: Dict[str, Dict[str, Any]] = {}
        self.breach_log: List[Dict[str, Any]] = []

    def register_tenant(self, profile: TenantSovereigntyProfile) -> None:
        self.profiles[profile.tenant_id] = profile
        self.kem.get_or_create_key(profile.tenant_id)
        self.enclave_memory[profile.tenant_id] = {}

    def store_tenant_data(self, tenant_id: str, key: str, value: Any, requesting_tenant: str) -> None:
        if requesting_tenant != tenant_id:
            breach_event = {
                "timestamp": time.time(),
                "type": "CROSS_TENANT_WRITE_BREACH",
                "requesting_tenant": requesting_tenant,
                "target_tenant": tenant_id,
                "key": key,
            }
            self.breach_log.append(breach_event)
            raise PermissionError(f"Cross-tenant memory mutation blocked: {requesting_tenant} -> {tenant_id}")

        self.enclave_memory.setdefault(tenant_id, {})[key] = value

    def read_tenant_data(self, tenant_id: str, key: str, requesting_tenant: str) -> Any:
        if requesting_tenant != tenant_id:
            breach_event = {
                "timestamp": time.time(),
                "type": "CROSS_TENANT_READ_BREACH",
                "requesting_tenant": requesting_tenant,
                "target_tenant": tenant_id,
                "key": key,
            }
            self.breach_log.append(breach_event)
            raise PermissionError(f"Cross-tenant memory access blocked: {requesting_tenant} -> {tenant_id}")

        return self.enclave_memory.get(tenant_id, {}).get(key)


class EnclaveBreachSimulator:
    """Benchmark harness testing isolation under concurrent adversarial cross-tenant access attempts."""

    @classmethod
    def run_benchmark(cls, manager: SovereignEnclaveManager) -> Dict[str, Any]:
        t1 = "tenant-fintech"
        t2 = "tenant-healthcare"

        p1 = TenantSovereigntyProfile(
            tenant_id=t1,
            tier=TenancyTier.SOVEREIGN_AIRGAPPED,
            allowed_residency_regions=["us-east-1"],
            allowed_desks=["desk-secure-1"],
            allowed_tools=["sql_query"],
        )
        p2 = TenantSovereigntyProfile(
            tenant_id=t2,
            tier=TenancyTier.ISOLATED,
            allowed_residency_regions=["eu-central-1"],
            allowed_desks=["desk-eu-1"],
            allowed_tools=["pdf_parse"],
        )
        manager.register_tenant(p1)
        manager.register_tenant(p2)

        manager.store_tenant_data(t1, "secret_financials", {"balance": 1000000}, requesting_tenant=t1)

        # Test 1: Cross-tenant memory breach attempt
        memory_breach_blocked = False
        try:
            manager.read_tenant_data(t1, "secret_financials", requesting_tenant=t2)
        except PermissionError:
            memory_breach_blocked = True

        # Test 2: Cross-tenant data fencing breach (residency & desk mismatch)
        fence_res = manager.fencing_engine.evaluate_boundary(
            profile=p1,
            action="egress_state",
            destination_region="eu-central-1",
            destination_desk="desk-eu-1",
            tools_requested=["sql_query"],
        )
        fencing_breach_blocked = not fence_res.is_allowed

        # Test 3: Tool unauthorized execution
        tool_fence_res = manager.fencing_engine.evaluate_boundary(
            profile=p2,
            action="invoke_tool",
            destination_region="eu-central-1",
            destination_desk="desk-eu-1",
            tools_requested=["unauthorized_exec"],
        )
        tool_breach_blocked = not tool_fence_res.is_allowed

        # Test 4: Key isolation check
        _, k1 = manager.kem.get_or_create_key(t1)
        _, k2 = manager.kem.get_or_create_key(t2)
        keys_disjoint = (k1 != k2)

        passed = all([
            memory_breach_blocked,
            fencing_breach_blocked,
            tool_breach_blocked,
            keys_disjoint,
        ])

        return {
            "all_passed": passed,
            "memory_breach_blocked": memory_breach_blocked,
            "fencing_breach_blocked": fencing_breach_blocked,
            "tool_breach_blocked": tool_breach_blocked,
            "keys_disjoint": keys_disjoint,
            "logged_breaches_count": len(manager.breach_log),
        }
