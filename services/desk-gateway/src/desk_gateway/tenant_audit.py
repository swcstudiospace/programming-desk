"""Tenant audit trail verification with immutable per-tenant cryptographic event hashing and tamper detection (REQ-TENANT-005)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from desk_gateway.tenant import TenantContext


GENESIS_HASH = "0" * 64


class AuditTamperError(Exception):
    """Raised when tamper detection discovers an invalid hash chain or altered record."""


@dataclass(frozen=True)
class TenantAuditEvent:
    event_id: str
    tenant_id: str
    org_id: str
    action: str
    seat: str
    actor: str
    timestamp: float
    prev_hash: str
    payload_hash: str
    event_hash: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TenantAuditLogger:
    """Maintains an append-only, per-tenant SHA-256 hash-chained audit ledger."""

    def __init__(self) -> None:
        # Map: tenant_id -> list of TenantAuditEvent
        self._chains: dict[str, list[TenantAuditEvent]] = {}

    @staticmethod
    def _compute_payload_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _compute_event_hash(
        tenant_id: str,
        org_id: str,
        action: str,
        seat: str,
        actor: str,
        timestamp: float,
        prev_hash: str,
        payload_hash: str,
    ) -> str:
        chain_string = f"{tenant_id}|{org_id}|{action}|{seat}|{actor}|{timestamp:.6f}|{prev_hash}|{payload_hash}"
        return hashlib.sha256(chain_string.encode("utf-8")).hexdigest()

    def record_event(
        self,
        tenant: TenantContext,
        action: str,
        seat: str,
        actor: str,
        details: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> TenantAuditEvent:
        """Append a cryptographically chained audit event to the tenant's ledger."""
        ts = timestamp if timestamp is not None else time.time()
        chain = self._chains.setdefault(tenant.tenant_id, [])
        prev_hash = chain[-1].event_hash if chain else GENESIS_HASH

        details_dict = details or {}
        payload_hash = self._compute_payload_hash(details_dict)
        event_hash = self._compute_event_hash(
            tenant_id=tenant.tenant_id,
            org_id=tenant.org_id,
            action=action,
            seat=seat,
            actor=actor,
            timestamp=ts,
            prev_hash=prev_hash,
            payload_hash=payload_hash,
        )

        event = TenantAuditEvent(
            event_id=f"audit-{tenant.tenant_id}-{len(chain) + 1}",
            tenant_id=tenant.tenant_id,
            org_id=tenant.org_id,
            action=action,
            seat=seat,
            actor=actor,
            timestamp=ts,
            prev_hash=prev_hash,
            payload_hash=payload_hash,
            event_hash=event_hash,
            details=details_dict,
        )
        chain.append(event)
        return event

    def get_audit_trail(self, tenant: TenantContext) -> list[TenantAuditEvent]:
        """Return the event chain for a tenant."""
        return list(self._chains.get(tenant.tenant_id, []))

    def verify_chain(self, tenant: TenantContext) -> dict[str, Any]:
        """Verify the integrity of a tenant's cryptographic event chain, detecting tampering."""
        chain = self._chains.get(tenant.tenant_id, [])
        if not chain:
            return {"valid": True, "count": 0, "root_hash": GENESIS_HASH}

        expected_prev = GENESIS_HASH
        for idx, event in enumerate(chain):
            # 1. Verify prev_hash matches prior event
            if event.prev_hash != expected_prev:
                raise AuditTamperError(
                    f"Chain broken at index {idx} (event {event.event_id}): "
                    f"prev_hash '{event.prev_hash}' != expected '{expected_prev}'"
                )

            # 2. Verify payload hash matches details
            calc_payload_hash = self._compute_payload_hash(event.details)
            if calc_payload_hash != event.payload_hash:
                raise AuditTamperError(
                    f"Payload tampering detected at index {idx} (event {event.event_id}): "
                    f"payload_hash '{event.payload_hash}' != computed '{calc_payload_hash}'"
                )

            # 3. Verify event hash computation
            calc_event_hash = self._compute_event_hash(
                tenant_id=event.tenant_id,
                org_id=event.org_id,
                action=event.action,
                seat=event.seat,
                actor=event.actor,
                timestamp=event.timestamp,
                prev_hash=event.prev_hash,
                payload_hash=event.payload_hash,
            )
            if calc_event_hash != event.event_hash:
                raise AuditTamperError(
                    f"Event hash tampering detected at index {idx} (event {event.event_id}): "
                    f"event_hash '{event.event_hash}' != computed '{calc_event_hash}'"
                )

            expected_prev = event.event_hash

        return {
            "valid": True,
            "count": len(chain),
            "latest_event_id": chain[-1].event_id,
            "root_hash": chain[-1].event_hash,
        }
