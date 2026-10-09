"""Inter-Desk Agent Mesh & Distributed Work Distribution (REQ-MESH-001 to REQ-MESH-005).

Provides:
- MeshDiscoveryRegistry: Tailnet-based service discovery for autonomous desk instances (REQ-MESH-001).
- AgentBusRPC: Asynchronous inter-desk task handoff and progress tracking (REQ-MESH-002).
- ReceiptCoSigner: Dual-party cryptographic receipt co-signing protocol (REQ-MESH-003).
- DelegatedTaskStateMachine: Decentralized task delegation state machine with timeout negotiation and automated recall (REQ-MESH-004).
"""

from __future__ import annotations

import copy
import enum
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("desk_gateway.mesh")


class MeshError(Exception):
    """Base exception for inter-desk mesh operations."""

    def __init__(self, message: str, code: str = "mesh_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class DeskNotFoundError(MeshError):
    def __init__(self, desk_id: str) -> None:
        super().__init__(f"Mesh desk '{desk_id}' not found", code="desk_not_found", status_code=404)


class CoSignVerificationError(MeshError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="cosign_verification_failed", status_code=401)


class InvalidDelegationTransitionError(MeshError):
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Invalid delegation state transition: '{from_state}' -> '{to_state}'",
            code="invalid_delegation_transition",
            status_code=409,
        )


class DeskType(str, enum.Enum):
    PROGRAMMING = "programming"
    RECRUITMENT = "recruitment"
    TRADING = "trading"
    CUSTOM = "custom"


@dataclass
class MeshDeskNode:
    desk_id: str
    desk_type: DeskType
    tailnet_ip: str
    port: int = 8791
    capabilities: list[str] = field(default_factory=list)
    public_key: str = ""
    status: str = "active"
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://{self.tailnet_ip}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_id": self.desk_id,
            "desk_type": self.desk_type.value,
            "tailnet_ip": self.tailnet_ip,
            "port": self.port,
            "capabilities": self.capabilities,
            "public_key": self.public_key,
            "status": self.status,
            "last_heartbeat": self.last_heartbeat,
            "metadata": self.metadata,
        }


class MeshDiscoveryRegistry:
    """Inter-desk agent service discovery protocol registering autonomous desk instances (REQ-MESH-001)."""

    def __init__(self, heartbeat_timeout_sec: float = 60.0) -> None:
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self._desks: dict[str, MeshDeskNode] = {}

    def register_desk(
        self,
        desk_id: str,
        desk_type: DeskType | str,
        tailnet_ip: str,
        port: int = 8791,
        capabilities: list[str] | None = None,
        public_key: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> MeshDeskNode:
        if isinstance(desk_type, str):
            try:
                desk_type = DeskType(desk_type.lower())
            except ValueError:
                desk_type = DeskType.CUSTOM

        node = MeshDeskNode(
            desk_id=desk_id,
            desk_type=desk_type,
            tailnet_ip=tailnet_ip,
            port=port,
            capabilities=capabilities or [],
            public_key=public_key,
            last_heartbeat=time.time(),
            metadata=metadata or {},
        )
        self._desks[desk_id] = node
        logger.info("Registered mesh desk '%s' (type=%s, tailnet_ip=%s)", desk_id, desk_type.value, tailnet_ip)
        return node

    def heartbeat(self, desk_id: str) -> MeshDeskNode:
        desk = self.get_desk(desk_id)
        desk.last_heartbeat = time.time()
        desk.status = "active"
        return desk

    def get_desk(self, desk_id: str) -> MeshDeskNode:
        desk = self._desks.get(desk_id)
        if not desk:
            raise DeskNotFoundError(desk_id)
        return desk

    def list_desks(self, desk_type: DeskType | str | None = None, capability: str | None = None) -> list[MeshDeskNode]:
        now = time.time()
        out = []
        filter_type = DeskType(desk_type.lower()) if isinstance(desk_type, str) else desk_type

        for desk in self._desks.values():
            if now - desk.last_heartbeat > self.heartbeat_timeout_sec:
                desk.status = "unreachable"

            if filter_type and desk.desk_type != filter_type:
                continue
            if capability and capability not in desk.capabilities:
                continue
            out.append(desk)
        return out


@dataclass
class AgentBusMessage:
    message_id: str
    source_desk: str
    target_desk: str
    task_id: str
    method: str
    payload: dict[str, Any]
    correlation_id: str
    status: str = "pending"  # pending, in_progress, completed, failed
    progress_pct: float = 0.0
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source_desk": self.source_desk,
            "target_desk": self.target_desk,
            "task_id": self.task_id,
            "method": self.method,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "progress_pct": self.progress_pct,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentBusRPC:
    """Asynchronous inter-desk RPC protocol via VPS Agent Bus enabling task handoffs and progress tracking (REQ-MESH-002)."""

    def __init__(self, registry: MeshDiscoveryRegistry) -> None:
        self.registry = registry
        self._messages: dict[str, AgentBusMessage] = {}  # message_id -> message
        self._handlers: dict[str, Callable[[AgentBusMessage], Any]] = {}

    def register_method_handler(self, method: str, handler: Callable[[AgentBusMessage], Any]) -> None:
        self._handlers[method] = handler

    def dispatch_task(
        self,
        source_desk: str,
        target_desk: str,
        task_id: str,
        method: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> AgentBusMessage:
        # Verify target desk exists
        self.registry.get_desk(target_desk)

        msg_id = f"rpc-{int(time.time()*1000)}-{hashlib.sha256(f'{task_id}:{method}'.encode()).hexdigest()[:8]}"
        corr_id = correlation_id or f"corr-{hashlib.sha256(msg_id.encode()).hexdigest()[:12]}"

        msg = AgentBusMessage(
            message_id=msg_id,
            source_desk=source_desk,
            target_desk=target_desk,
            task_id=task_id,
            method=method,
            payload=payload,
            correlation_id=corr_id,
        )
        self._messages[msg_id] = msg
        logger.info("Dispatched RPC message %s: %s -> %s (task=%s, method=%s)", msg_id, source_desk, target_desk, task_id, method)
        return msg

    def update_progress(
        self,
        message_id: str,
        progress_pct: float,
        status: str = "in_progress",
        result: dict[str, Any] | None = None,
    ) -> AgentBusMessage:
        msg = self._messages.get(message_id)
        if not msg:
            raise MeshError(f"RPC message '{message_id}' not found", code="message_not_found", status_code=404)

        msg.progress_pct = max(0.0, min(100.0, progress_pct))
        msg.status = status
        if result is not None:
            msg.result = result
        msg.updated_at = time.time()
        return msg

    def get_message(self, message_id: str) -> AgentBusMessage | None:
        return self._messages.get(message_id)

    def get_by_correlation_id(self, correlation_id: str) -> list[AgentBusMessage]:
        return [m for m in self._messages.values() if m.correlation_id == correlation_id]

    def get_by_task_id(self, task_id: str) -> list[AgentBusMessage]:
        return [m for m in self._messages.values() if m.task_id == task_id]


@dataclass
class CoSignedReceipt:
    receipt_id: str
    task_id: str
    source_desk: str
    target_desk: str
    payload_hash: str
    timestamp: float
    source_signature: str
    target_signature: str
    status: str = "verified"  # pending, verified, rejected

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "task_id": self.task_id,
            "source_desk": self.source_desk,
            "target_desk": self.target_desk,
            "payload_hash": self.payload_hash,
            "timestamp": self.timestamp,
            "source_signature": self.source_signature,
            "target_signature": self.target_signature,
            "status": self.status,
        }


class ReceiptCoSigner:
    """Cross-organization receipt co-signing protocol with dual-party cryptographic attestation (REQ-MESH-003)."""

    def __init__(self, local_desk_id: str, signing_secret: str, max_drift_sec: float = 300.0) -> None:
        self.local_desk_id = local_desk_id
        self.signing_secret = signing_secret.encode("utf-8") if isinstance(signing_secret, str) else signing_secret
        self.max_drift_sec = max_drift_sec
        self._shared_secrets: dict[str, bytes] = {}

    def register_peer_secret(self, peer_desk_id: str, secret: str) -> None:
        self._shared_secrets[peer_desk_id] = secret.encode("utf-8") if isinstance(secret, str) else secret

    @staticmethod
    def compute_payload_hash(data: dict[str, Any]) -> str:
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _sign(self, desk_id: str, receipt_id: str, task_id: str, payload_hash: str, timestamp: float, secret: bytes) -> str:
        message = f"{desk_id}:{receipt_id}:{task_id}:{payload_hash}:{timestamp}".encode("utf-8")
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def sign_source(self, task_id: str, target_desk: str, task_result: dict[str, Any]) -> dict[str, Any]:
        """Originating desk generates receipt and first signature."""
        receipt_id = f"rcpt-{int(time.time()*1000)}-{secrets_token()}"
        ts = time.time()
        p_hash = self.compute_payload_hash(task_result)
        source_sig = self._sign(self.local_desk_id, receipt_id, task_id, p_hash, ts, self.signing_secret)

        return {
            "receipt_id": receipt_id,
            "task_id": task_id,
            "source_desk": self.local_desk_id,
            "target_desk": target_desk,
            "payload_hash": p_hash,
            "timestamp": ts,
            "source_signature": source_sig,
        }

    def cosign_target(self, receipt_proposal: dict[str, Any], task_result: dict[str, Any]) -> CoSignedReceipt:
        """Target desk validates source signature and appends second signature."""
        receipt_id = receipt_proposal["receipt_id"]
        task_id = receipt_proposal["task_id"]
        source_desk = receipt_proposal["source_desk"]
        target_desk = receipt_proposal["target_desk"]
        claimed_hash = receipt_proposal["payload_hash"]
        ts = float(receipt_proposal["timestamp"])
        source_sig = receipt_proposal["source_signature"]

        # 1. Verify drift
        now = time.time()
        if abs(now - ts) > self.max_drift_sec:
            raise CoSignVerificationError(f"Receipt timestamp skew ({abs(now - ts):.1f}s) exceeded {self.max_drift_sec}s")

        # 2. Verify payload hash match
        actual_hash = self.compute_payload_hash(task_result)
        if not hmac.compare_digest(claimed_hash, actual_hash):
            raise CoSignVerificationError("Payload hash does not match task result")

        # 3. Verify source signature
        source_secret = self._shared_secrets.get(source_desk, self.signing_secret)
        expected_source_sig = self._sign(source_desk, receipt_id, task_id, claimed_hash, ts, source_secret)
        if not hmac.compare_digest(source_sig, expected_source_sig):
            raise CoSignVerificationError("Invalid source signature on proposal")

        # 4. Generate target co-signature
        target_sig = self._sign(target_desk, receipt_id, task_id, claimed_hash, ts, self.signing_secret)

        return CoSignedReceipt(
            receipt_id=receipt_id,
            task_id=task_id,
            source_desk=source_desk,
            target_desk=target_desk,
            payload_hash=claimed_hash,
            timestamp=ts,
            source_signature=source_sig,
            target_signature=target_sig,
            status="verified",
        )

    def verify_cosigned_receipt(self, receipt: CoSignedReceipt) -> bool:
        """Verify dual signatures on a co-signed receipt."""
        source_secret = self._shared_secrets.get(receipt.source_desk, self.signing_secret)
        target_secret = self._shared_secrets.get(receipt.target_desk, self.signing_secret)

        expected_source = self._sign(
            receipt.source_desk, receipt.receipt_id, receipt.task_id, receipt.payload_hash, receipt.timestamp, source_secret
        )
        expected_target = self._sign(
            receipt.target_desk, receipt.receipt_id, receipt.task_id, receipt.payload_hash, receipt.timestamp, target_secret
        )

        source_valid = hmac.compare_digest(receipt.source_signature, expected_source)
        target_valid = hmac.compare_digest(receipt.target_signature, expected_target)

        if not source_valid:
            raise CoSignVerificationError("Source signature invalid on co-signed receipt")
        if not target_valid:
            raise CoSignVerificationError("Target signature invalid on co-signed receipt")

        return True


def secrets_token() -> str:
    import secrets
    return secrets.token_hex(6)


class DelegationState(str, enum.Enum):
    INITIATED = "initiated"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    RECALLED = "recalled"
    COMPLETED = "completed"


@dataclass
class DelegatedTask:
    delegation_id: str
    task_id: str
    originating_desk: str
    assigned_desk: str
    state: DelegationState = DelegationState.INITIATED
    timeout_sec: float = 300.0
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "task_id": self.task_id,
            "originating_desk": self.originating_desk,
            "assigned_desk": self.assigned_desk,
            "state": self.state.value,
            "timeout_sec": self.timeout_sec,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": self.history,
        }


class DelegatedTaskStateMachine:
    """Decentralized task delegation state machine handling timeout negotiation, rejection, and automated recall (REQ-MESH-004)."""

    VALID_TRANSITIONS: dict[DelegationState, set[DelegationState]] = {
        DelegationState.INITIATED: {DelegationState.ACCEPTED, DelegationState.REJECTED, DelegationState.TIMED_OUT, DelegationState.RECALLED},
        DelegationState.ACCEPTED: {DelegationState.IN_PROGRESS, DelegationState.RECALLED, DelegationState.TIMED_OUT},
        DelegationState.IN_PROGRESS: {DelegationState.COMPLETED, DelegationState.RECALLED, DelegationState.TIMED_OUT},
        DelegationState.REJECTED: {DelegationState.RECALLED},
        DelegationState.TIMED_OUT: {DelegationState.RECALLED},
        DelegationState.RECALLED: set(),
        DelegationState.COMPLETED: set(),
    }

    def __init__(self) -> None:
        self._delegations: dict[str, DelegatedTask] = {}

    def initiate_delegation(
        self,
        task_id: str,
        originating_desk: str,
        assigned_desk: str,
        timeout_sec: float = 300.0,
    ) -> DelegatedTask:
        d_id = f"del-{int(time.time()*1000)}-{secrets_token()}"
        task = DelegatedTask(
            delegation_id=d_id,
            task_id=task_id,
            originating_desk=originating_desk,
            assigned_desk=assigned_desk,
            timeout_sec=timeout_sec,
            history=[{"state": DelegationState.INITIATED.value, "timestamp": time.time(), "reason": "initiated"}],
        )
        self._delegations[d_id] = task
        logger.info("Initiated delegation %s: task %s from %s to %s (timeout=%.1fs)", d_id, task_id, originating_desk, assigned_desk, timeout_sec)
        return task

    def get_delegation(self, delegation_id: str) -> DelegatedTask:
        task = self._delegations.get(delegation_id)
        if not task:
            raise MeshError(f"Delegation '{delegation_id}' not found", code="delegation_not_found", status_code=404)
        return task

    def check_timeouts(self) -> list[DelegatedTask]:
        """Evaluate delegations against their negotiated timeout and transition expired ones."""
        now = time.time()
        timed_out = []
        for task in self._delegations.values():
            if task.state in {DelegationState.INITIATED, DelegationState.ACCEPTED, DelegationState.IN_PROGRESS}:
                if now - task.created_at > task.timeout_sec:
                    self._transition(task, DelegationState.TIMED_OUT, reason=f"Operation exceeded negotiated timeout of {task.timeout_sec}s")
                    timed_out.append(task)
        return timed_out

    def advance_state(
        self,
        delegation_id: str,
        new_state: DelegationState | str,
        reason: str = "",
    ) -> DelegatedTask:
        task = self.get_delegation(delegation_id)
        target = DelegationState(new_state.lower()) if isinstance(new_state, str) else new_state
        return self._transition(task, target, reason)

    def reject_delegation(self, delegation_id: str, reason: str = "Capacity unavailable") -> DelegatedTask:
        """Assigned desk rejects delegation proposal."""
        return self.advance_state(delegation_id, DelegationState.REJECTED, reason=reason)

    def recall_to_origin(self, delegation_id: str, reason: str = "Automated recall to originating desk") -> DelegatedTask:
        """Automated recall back to originating desk when rejected, timed out, or manually preempted."""
        task = self.get_delegation(delegation_id)
        # Check if already timed out or needs check
        self.check_timeouts()
        return self._transition(task, DelegationState.RECALLED, reason=reason)

    def _transition(self, task: DelegatedTask, target: DelegationState, reason: str = "") -> DelegatedTask:
        allowed = self.VALID_TRANSITIONS.get(task.state, set())
        if target not in allowed:
            raise InvalidDelegationTransitionError(task.state.value, target.value)

        task.state = target
        task.reason = reason
        task.updated_at = time.time()
        task.history.append({"state": target.value, "timestamp": time.time(), "reason": reason})
        logger.info("Delegation %s transitioned to %s (reason: %s)", task.delegation_id, target.value, reason)
        return task
