"""Multi-tenant isolation engine enforcing organization and team namespaces across gateway operations."""

from __future__ import annotations

import contextvars
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
DEFAULT_TENANT_ID = "default"
DEFAULT_ORG_ID = "org-default"
DEFAULT_TEAM_ID = "team-default"
DEFAULT_ENVIRONMENT = "prod"


class TenantIsolationError(Exception):
    """Raised when tenant boundary isolation is violated."""


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str = DEFAULT_TENANT_ID
    org_id: str = DEFAULT_ORG_ID
    team_id: str = DEFAULT_TEAM_ID
    environment: str = DEFAULT_ENVIRONMENT
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not TENANT_ID_PATTERN.match(self.tenant_id):
            raise TenantIsolationError(f"Invalid tenant_id format: '{self.tenant_id}'")
        if not TENANT_ID_PATTERN.match(self.org_id):
            raise TenantIsolationError(f"Invalid org_id format: '{self.org_id}'")
        if not TENANT_ID_PATTERN.match(self.team_id):
            raise TenantIsolationError(f"Invalid team_id format: '{self.team_id}'")

    @property
    def namespace(self) -> str:
        """Fully qualified tenant namespace."""
        return f"{self.org_id}:{self.team_id}:{self.tenant_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "org_id": self.org_id,
            "team_id": self.team_id,
            "environment": self.environment,
            "namespace": self.namespace,
            "metadata": dict(self.metadata),
        }


current_tenant: contextvars.ContextVar[TenantContext] = contextvars.ContextVar(
    "current_tenant", default=TenantContext()
)


class TenantIsolationEngine:
    """Manages tenant isolation policies, namespace partitioning, and cross-tenant checks."""

    def __init__(self, default_tenant: TenantContext | None = None) -> None:
        self.default_tenant = default_tenant or TenantContext()
        self._registered_tenants: dict[str, TenantContext] = {
            self.default_tenant.tenant_id: self.default_tenant
        }

    def register_tenant(self, tenant: TenantContext) -> None:
        self._registered_tenants[tenant.tenant_id] = tenant

    def get_tenant(self, tenant_id: str) -> TenantContext | None:
        return self._registered_tenants.get(tenant_id)

    def extract_from_headers(self, headers: Mapping[str, str]) -> TenantContext:
        """Extract tenant context from incoming HTTP headers."""
        tenant_id = headers.get("x-tenant-id") or headers.get("X-Tenant-Id")
        org_id = headers.get("x-org-id") or headers.get("X-Org-Id")
        team_id = headers.get("x-team-id") or headers.get("X-Team-Id")
        env = headers.get("x-environment") or headers.get("X-Environment") or DEFAULT_ENVIRONMENT

        if not tenant_id:
            return self.default_tenant

        clean_tenant = tenant_id.strip().lower()
        clean_org = (org_id or f"org-{clean_tenant}").strip().lower()
        clean_team = (team_id or f"team-{clean_tenant}").strip().lower()
        clean_env = env.strip().lower()

        try:
            return TenantContext(
                tenant_id=clean_tenant,
                org_id=clean_org,
                team_id=clean_team,
                environment=clean_env,
            )
        except TenantIsolationError as exc:
            raise TenantIsolationError(f"Malformed tenant headers: {exc}") from exc

    def assert_same_tenant(
        self,
        caller_tenant: TenantContext,
        target_tenant_id: str,
        resource_name: str = "resource",
    ) -> None:
        """Assert that caller belongs to the target tenant, raising TenantIsolationError if mismatched."""
        if caller_tenant.tenant_id != target_tenant_id:
            raise TenantIsolationError(
                f"Cross-tenant access forbidden: caller '{caller_tenant.tenant_id}' cannot access "
                f"{resource_name} owned by '{target_tenant_id}' (namespace {caller_tenant.namespace})"
            )

    def partition_key(self, tenant: TenantContext, key: str) -> str:
        """Prefix a key or resource name with the tenant's isolated namespace."""
        return f"{tenant.namespace}::{key}"

    def unpartition_key(self, tenant: TenantContext, partitioned_key: str) -> str:
        """Strip tenant namespace prefix, verifying boundary ownership."""
        prefix = f"{tenant.namespace}::"
        if not partitioned_key.startswith(prefix):
            raise TenantIsolationError(
                f"Partition mismatch: key '{partitioned_key}' does not belong to namespace '{tenant.namespace}'"
            )
        return partitioned_key[len(prefix) :]

    def tenant_bank_name(self, tenant: TenantContext, seat: str) -> str:
        """Partition Hindsight memory bank name per tenant and seat (REQ-TENANT-003)."""
        clean_seat = seat.strip().lower()
        return f"{tenant.org_id}-{tenant.tenant_id}-pd-{clean_seat}"

    def parse_tenant_bank_name(self, bank_name: str) -> tuple[str, str, str]:
        """Parse tenant bank name into (org_id, tenant_id, seat)."""
        # Format: {org_id}-{tenant_id}-pd-{seat}
        parts = bank_name.split("-pd-")
        if len(parts) != 2:
            raise TenantIsolationError(f"Malformed tenant memory bank name: '{bank_name}'")
        org_and_tenant, seat = parts[0], parts[1]
        org_tenant_parts = org_and_tenant.split("-", 1)
        if len(org_tenant_parts) != 2:
            raise TenantIsolationError(f"Malformed tenant prefix in bank name: '{bank_name}'")
        return org_tenant_parts[0], org_tenant_parts[1], seat

    def create_dataset_token(self, tenant: TenantContext, dataset_id: str, secret: str = "tenant-ragflow-boundary") -> str:
        """Generate HMAC-SHA256 authenticated tenant boundary token for RAGFlow dataset access (REQ-TENANT-003)."""
        import hmac
        import hashlib
        msg = f"{tenant.namespace}::{dataset_id}".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return f"{tenant.namespace}::{dataset_id}::{sig}"

    def verify_dataset_token(self, tenant: TenantContext, dataset_id: str, token: str, secret: str = "tenant-ragflow-boundary") -> bool:
        """Verify HMAC-SHA256 authenticated tenant boundary token for RAGFlow dataset isolation (REQ-TENANT-003)."""
        import hmac
        import hashlib
        expected_prefix = f"{tenant.namespace}::{dataset_id}::"
        if not token.startswith(expected_prefix):
            return False
        sig = token[len(expected_prefix) :]
        msg = f"{tenant.namespace}::{dataset_id}".encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)

