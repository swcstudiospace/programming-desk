"""Multi-tenant quota and rate limiting policer with burst ceilings and fair-share scheduling (REQ-TENANT-004)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from desk_gateway.tenant import TenantContext


class QuotaExceededError(Exception):
    """Raised when tenant exceeds request rate, burst ceiling, or concurrency limits."""

    def __init__(self, tenant_id: str, metric: str, limit: float, current: float, retry_after: float = 1.0) -> None:
        super().__init__(
            f"Tenant '{tenant_id}' exceeded {metric} limit: {current:.1f}/{limit:.1f} (retry after {retry_after:.1f}s)"
        )
        self.tenant_id = tenant_id
        self.metric = metric
        self.limit = limit
        self.current = current
        self.retry_after = retry_after


@dataclass
class TenantQuotaLimits:
    """Configured quota thresholds for a tenant tier."""
    max_requests_per_minute: float = 120.0  # Steady state rate: 2 req/sec
    burst_ceiling: float = 30.0             # Max tokens in burst bucket
    max_concurrent_operations: int = 10     # Max active concurrency
    fair_share_weight: float = 1.0          # Multiplier for fair-share distribution


@dataclass
class TenantBucketState:
    """State of token bucket and concurrency for a tenant."""
    tokens: float
    last_leak_timestamp: float
    active_concurrent: int = 0
    total_requests: int = 0
    throttled_requests: int = 0


class TenantQuotaPolicer:
    """Enforces multi-tenant fair-share token-bucket quotas and burst ceilings."""

    def __init__(
        self,
        default_limits: TenantQuotaLimits | None = None,
        custom_limits: dict[str, TenantQuotaLimits] | None = None,
    ) -> None:
        self.default_limits = default_limits or TenantQuotaLimits()
        self.custom_limits: dict[str, TenantQuotaLimits] = custom_limits or {}
        self._states: dict[str, TenantBucketState] = {}

    def get_limits(self, tenant: TenantContext) -> TenantQuotaLimits:
        return self.custom_limits.get(tenant.tenant_id, self.default_limits)

    def set_tenant_limits(self, tenant_id: str, limits: TenantQuotaLimits) -> None:
        self.custom_limits[tenant_id] = limits

    def _get_or_create_state(self, tenant: TenantContext, now: float) -> TenantBucketState:
        limits = self.get_limits(tenant)
        if tenant.tenant_id not in self._states:
            self._states[tenant.tenant_id] = TenantBucketState(
                tokens=limits.burst_ceiling,
                last_leak_timestamp=now,
            )
        return self._states[tenant.tenant_id]

    def acquire(
        self,
        tenant: TenantContext,
        cost: float = 1.0,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Check and consume rate limit quota, raising QuotaExceededError if limit breached."""
        now = now if now is not None else time.time()
        limits = self.get_limits(tenant)
        state = self._get_or_create_state(tenant, now)

        # 1. Check concurrent operations
        if state.active_concurrent >= limits.max_concurrent_operations:
            state.throttled_requests += 1
            raise QuotaExceededError(
                tenant_id=tenant.tenant_id,
                metric="concurrency",
                limit=float(limits.max_concurrent_operations),
                current=float(state.active_concurrent),
                retry_after=0.5,
            )

        # 2. Refill tokens based on elapsed time and fill rate (requests per sec * fair_share_weight)
        fill_rate = (limits.max_requests_per_minute / 60.0) * limits.fair_share_weight
        elapsed = max(0.0, now - state.last_leak_timestamp)
        state.tokens = min(limits.burst_ceiling, state.tokens + elapsed * fill_rate)
        state.last_leak_timestamp = now

        # 3. Check burst ceiling and available tokens
        if state.tokens < cost:
            state.throttled_requests += 1
            deficit = cost - state.tokens
            retry_after = deficit / fill_rate if fill_rate > 0 else 1.0
            raise QuotaExceededError(
                tenant_id=tenant.tenant_id,
                metric="rate_burst",
                limit=limits.burst_ceiling,
                current=state.tokens,
                retry_after=max(0.1, retry_after),
            )

        # 4. Deduct tokens and track active concurrency
        state.tokens -= cost
        state.active_concurrent += 1
        state.total_requests += 1

        return {
            "allowed": True,
            "tenant_id": tenant.tenant_id,
            "remaining_tokens": round(state.tokens, 2),
            "burst_ceiling": limits.burst_ceiling,
            "active_concurrent": state.active_concurrent,
            "fill_rate_rps": round(fill_rate, 2),
        }

    def release(self, tenant: TenantContext) -> None:
        """Release active concurrency after operation completion."""
        state = self._states.get(tenant.tenant_id)
        if state and state.active_concurrent > 0:
            state.active_concurrent -= 1

    def get_quota_status(self, tenant: TenantContext, now: float | None = None) -> dict[str, Any]:
        """Inspect current quota state and limits for a tenant."""
        now = now if now is not None else time.time()
        limits = self.get_limits(tenant)
        state = self._get_or_create_state(tenant, now)

        fill_rate = (limits.max_requests_per_minute / 60.0) * limits.fair_share_weight
        elapsed = max(0.0, now - state.last_leak_timestamp)
        current_tokens = min(limits.burst_ceiling, state.tokens + elapsed * fill_rate)

        return {
            "tenant_id": tenant.tenant_id,
            "org_id": tenant.org_id,
            "remaining_tokens": round(current_tokens, 2),
            "burst_ceiling": limits.burst_ceiling,
            "max_requests_per_minute": limits.max_requests_per_minute,
            "active_concurrent": state.active_concurrent,
            "max_concurrent": limits.max_concurrent_operations,
            "fair_share_weight": limits.fair_share_weight,
            "total_requests": state.total_requests,
            "throttled_requests": state.throttled_requests,
        }
