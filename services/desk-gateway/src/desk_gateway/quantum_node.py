"""Authenticated worker node for the faithful distributed simulator (phase 68-02).

Each distinct simulator-node process owns its qubit leases and private
single-qubit conditional state. The central coordinator (pool / mesh /
protocol in :mod:`desk_gateway.quantum_teleportation`) keeps the correlated
joint density for 2-4 qubit evolutions, but it can only touch worker leases
through the fixed command set below, with per-operation node / instance /
session / lease scope and replay protection.

Fixed commands: ``reserve`` / ``apply_circuit`` / ``measure`` /
``stage_conditional_state`` / ``correct`` / ``transfer`` / ``release`` /
``inspect``. Later phase-69 QKD actions extend this module; the command
table stays fixed otherwise.

Security boundaries (ASVS 5.0 V4/V6/V7/V8):

- The worker credential is read from the ``QUANTUM_NODE_TOKEN`` environment
  variable only. It is never accepted via CLI argv, never echoed in errors,
  logs, or inspect output.
- Every mutating command binds ``node`` (must equal this worker's identity),
  ``instance`` (must equal this process instance; stale instances fail
  closed so a restart never resurrects leases), and the exact owned leases.
- ``operation_id`` is at-most-once: a repeated ID with a byte-identical
  payload returns the stored result without re-applying effects; a repeated
  ID with a *different* payload is rejected (409).
- ``correct`` is additionally one-shot per ``(session_id, lease_id)``: a
  duplicate correction returns the stored outcome instead of re-applying
  X/Z, and conflicting bits are rejected.
- ``inspect`` exposes allocation / lifecycle metadata only. Density
  matrices, keys, and QKD outcomes are never serialized.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .quantum_key import (
    ReconciliationFailed,
    bb84_state,
    correct_blocks,
    node_commitment,
    random_bytes,
    syndrome_blocks,
    toeplitz_extract,
    toeplitz_hash,
)
from .quantum_state import (
    QuantumDensityMatrix,
    H,
    S,
    X,
    Z,
)

__all__ = [
    "MAX_BODY_BYTES",
    "MAX_CIRCUIT_OPS",
    "MAX_ID_LEN",
    "MAX_LEASES_PER_OP",
    "MAX_NODE_LEN",
    "NODE_ACTIONS",
    "QuantumNodeError",
    "QuantumNodeLease",
    "QuantumNodeWorker",
    "build_node_parser",
    "create_node_app",
    "main",
    "parse_bearer",
    "worker_token_from_env",
]

#: Request/response body cap (bytes) for worker HTTP endpoints.
MAX_BODY_BYTES = 64 * 1024
#: Maximum qubit leases touched by one worker command.
MAX_LEASES_PER_OP = 4
#: Maximum gate operations in one ``apply_circuit`` command.
MAX_CIRCUIT_OPS = 8
#: Maximum length for operation / resource / session / lease IDs.
MAX_ID_LEN = 128
#: Maximum length for node IDs.
MAX_NODE_LEN = 64
#: Fixed worker command paths, resolved server-side only.
NODE_ACTIONS = (
    "reserve",
    "apply_circuit",
    "measure",
    "stage_conditional_state",
    "correct",
    "transfer",
    "release",
    "inspect",
)

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SEEN_OPS_CAP = 2048

_GATES = {"H": H, "X": X, "Z": Z, "S": S}


class QuantumNodeError(Exception):
    """Typed worker failure with an HTTP status, stable code, and safe detail."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": self.code, "detail": self.detail}


def _check_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise QuantumNodeError(400, "invalid_id", f"{name} must match [A-Za-z0-9._:-]{{1,128}}")
    return value


def _check_node(value: object, name: str = "node_id") -> str:
    if not isinstance(value, str) or not _NODE_RE.fullmatch(value):
        raise QuantumNodeError(400, "invalid_node", f"{name} must match [A-Za-z0-9._-]{{1,64}}")
    return value


def _check_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QuantumNodeError(400, "invalid_count", "count must be an integer in 1..4")
    if not 1 <= value <= MAX_LEASES_PER_OP:
        raise QuantumNodeError(400, "invalid_count", "count must be an integer in 1..4")
    return value


def _check_bit(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise QuantumNodeError(400, "invalid_bit", f"{name} must be 0 or 1")
    return value


def parse_bearer(header: object) -> str:
    """Extract a bearer token from an Authorization header value (never logged)."""
    if not isinstance(header, str):
        return ""
    if not header[:7].lower() == "bearer ":
        return ""
    return header[7:].strip()


def worker_token_from_env() -> str:
    """Read this worker's credential from ``QUANTUM_NODE_TOKEN`` only."""
    return os.environ.get("QUANTUM_NODE_TOKEN", "").strip()


@dataclass
class QuantumNodeLease:
    """Private per-qubit lease record. Never serialized wholesale."""

    lease_id: str
    resource_id: str
    session_id: str | None = None
    state: str = "active"
    rho: QuantumDensityMatrix | None = None

    def public(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "resource_id": self.resource_id,
            "session_id": self.session_id,
            "state": self.state,
        }


@dataclass
class _QKDRecord:
    """Node-private QKD session vault: candidates, key, capability, use state.

    Never serialized wholesale: ``inspect`` exposes leases only, pool events
    carry no key-round bits, and ``repr`` is redacted to class + session.
    """

    session_id: str
    role: str
    peer: str
    owner: str
    steps: list = field(default_factory=list)
    candidate_count: int = 0
    test_count: int = 0
    error_count: int = 0
    syndrome_len: int = 0
    corrections: int = 0
    tag_ok: bool = False
    raw_bits: list = field(default_factory=list)
    raw_bases: list = field(default_factory=list)
    key_bits: list = field(default_factory=list)
    phase_bits: list = field(default_factory=list)
    key: bytes | None = None
    blinding: bytes | None = None
    capability: str | None = None
    commitment_hex: str | None = None
    available: bool = False
    used: bool = False

    def __repr__(self) -> str:
        return f"_QKDRecord(session={self.session_id!r})"


def _public_matrix_to_rows(matrix: object) -> tuple[tuple[complex, ...], ...]:
    """Validate a 2x2 ``to_public_matrix`` payload and return complex rows."""
    if not isinstance(matrix, (list, tuple)) or len(matrix) != 2:
        raise QuantumNodeError(400, "invalid_state", "conditional state must be a 2x2 matrix")
    rows: list[tuple[complex, ...]] = []
    for i, row in enumerate(matrix):
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise QuantumNodeError(400, "invalid_state", "conditional state must be a 2x2 matrix")
        cells: list[complex] = []
        for j, cell in enumerate(row):
            if (
                not isinstance(cell, (list, tuple))
                or len(cell) != 2
                or any(isinstance(v, bool) for v in cell)
                or not all(isinstance(v, (int, float)) for v in cell)
            ):
                raise QuantumNodeError(400, "invalid_state", f"cell [{i}][{j}] must be [real, imag]")
            real, imag = float(cell[0]), float(cell[1])
            if not math.isfinite(real) or not math.isfinite(imag):
                raise QuantumNodeError(400, "invalid_state", f"cell [{i}][{j}] must be finite")
            cells.append(complex(real, imag))
        rows.append(tuple(cells))
    try:
        rho = QuantumDensityMatrix(tuple(rows))
    except (TypeError, ValueError) as exc:
        raise QuantumNodeError(400, "invalid_state", f"conditional state rejected: {exc}") from exc
    if rho.qubits != 1:
        raise QuantumNodeError(400, "invalid_state", "conditional state must be one qubit")
    return rho.rows


class QuantumNodeWorker:
    """One simulator-node process: fixed identity, capacity, and lease ownership."""

    def __init__(
        self,
        node_id: str,
        *,
        capacity: int = 16,
        token: str | None = None,
        rng: Any | None = None,
    ) -> None:
        self.node_id = _check_node(node_id)
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1 or capacity > 1024:
            raise QuantumNodeError(400, "invalid_capacity", "capacity must be an integer in 1..1024")
        credential = token if token is not None else worker_token_from_env()
        if not credential:
            raise QuantumNodeError(401, "missing_credential", "worker credential is not configured")
        self._token = credential
        self.capacity = capacity
        self.instance_id = secrets.token_hex(8)
        self._leases: dict[str, QuantumNodeLease] = {}
        self._qkd: dict[str, _QKDRecord] = {}
        self._lock = asyncio.Lock()
        self._seen_ops: dict[str, tuple[str, dict[str, Any]]] = {}
        self._corrections: dict[tuple[str, str], dict[str, Any]] = {}
        self._rng = rng if rng is not None else secrets.SystemRandom()

    def __repr__(self) -> str:
        # Redacted: identity only, never credential, lease, or key material.
        return f"QuantumNodeWorker(node_id={self.node_id!r})"

    # -- internal guards -------------------------------------------------

    def _auth(self, token: object, node: object, instance: object) -> None:
        presented = token if isinstance(token, str) else ""
        if not presented or not hmac.compare_digest(presented.encode(), self._token.encode()):
            raise QuantumNodeError(401, "unauthenticated", "invalid worker credential")
        if node != self.node_id:
            raise QuantumNodeError(403, "wrong_node", "command is not scoped to this node")
        if instance != self.instance_id:
            raise QuantumNodeError(409, "stale_instance", "command targets a stale worker instance")

    def _active_count(self) -> int:
        return sum(1 for lease in self._leases.values() if lease.state in ("active", "staged", "corrected"))

    def _idempotency(self, operation_id: str, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        seen = self._seen_ops.get(operation_id)
        if seen is not None:
            if seen[0] != digest:
                raise QuantumNodeError(409, "operation_conflict", "operation_id reused with a different payload")
            return dict(seen[1])
        return None

    def _remember(self, operation_id: str, payload: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self._seen_ops[operation_id] = (digest, dict(response))
        while len(self._seen_ops) > _SEEN_OPS_CAP:
            self._seen_ops.pop(next(iter(self._seen_ops)))

    def _owned(self, lease_id: str) -> QuantumNodeLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise QuantumNodeError(404, "unknown_lease", "lease is not owned by this worker")
        return lease

    # -- fixed commands --------------------------------------------------

    async def reserve(
        self,
        *,
        operation_id: str,
        resource_id: str,
        count: int,
        session_id: str | None = None,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        resource_id = _check_id(resource_id, "resource_id")
        if session_id is not None:
            _check_id(session_id, "session_id")
        count = _check_count(count)
        self._auth(token, node, instance)
        payload = {"action": "reserve", "resource_id": resource_id, "count": count, "session_id": session_id}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            if self._active_count() + count > self.capacity:
                raise QuantumNodeError(409, "capacity_exhausted", "worker capacity exhausted")
            leases: list[str] = []
            for _ in range(count):
                lease_id = f"{resource_id}:q-{secrets.token_hex(4)}"
                self._leases[lease_id] = QuantumNodeLease(
                    lease_id=lease_id, resource_id=resource_id, session_id=session_id
                )
                leases.append(lease_id)
            response = {"ok": True, "leases": leases, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def apply_circuit(
        self,
        *,
        operation_id: str,
        lease_ids: Sequence[str],
        operations: Sequence[Mapping[str, Any]],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        if not isinstance(lease_ids, (list, tuple)) or not 1 <= len(lease_ids) <= MAX_LEASES_PER_OP:
            raise QuantumNodeError(400, "invalid_leases", "lease_ids must list 1..4 lease IDs")
        for lease_id in lease_ids:
            _check_id(lease_id, "lease_id")
        if not isinstance(operations, (list, tuple)) or not 1 <= len(operations) <= MAX_CIRCUIT_OPS:
            raise QuantumNodeError(400, "invalid_circuit", "operations must list 1..8 gate operations")
        transcript: list[dict[str, Any]] = []
        for pos, op in enumerate(operations):
            if not isinstance(op, Mapping):
                raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}] must be an object")
            gate = op.get("gate")
            if gate == "CNOT":
                control, target = op.get("control"), op.get("target")
                for label, value in (("control", control), ("target", target)):
                    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < len(lease_ids):
                        raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}].{label} out of range")
                if control == target:
                    raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}] control/target must differ")
                transcript.append({"gate": "CNOT", "control": control, "target": target})
            elif gate in _GATES:
                target = op.get("target")
                if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < len(lease_ids):
                    raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}].target out of range")
                transcript.append({"gate": gate, "target": target})
            else:
                raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}].gate is not allowlisted")
            if set(op.keys()) - {"gate", "target", "control"}:
                raise QuantumNodeError(400, "invalid_circuit", f"operations[{pos}] carries unknown fields")
        self._auth(token, node, instance)
        payload = {"action": "apply_circuit", "lease_ids": list(lease_ids), "operations": transcript}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            leases = [self._owned(lease_id) for lease_id in lease_ids]
            for lease in leases:
                if lease.state not in ("active", "staged", "corrected"):
                    raise QuantumNodeError(409, "lease_unavailable", "lease is not available for gates")
            applied = False
            if len(leases) == 1 and leases[0].rho is not None:
                rho = leases[0].rho
                for entry in transcript:
                    if entry["gate"] == "CNOT":
                        raise QuantumNodeError(400, "invalid_circuit", "CNOT needs two staged leases")
                    rho = rho.apply_single(_GATES[entry["gate"]], 0)
                leases[0].rho = rho
                applied = True
            response = {"ok": True, "applied": applied, "transcript": transcript, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def measure(
        self,
        *,
        operation_id: str,
        lease_ids: Sequence[str] = (),
        token: str,
        node: str,
        instance: str,
        branch_probabilities: Sequence[object] | None = None,
        branch_bits: Sequence[Sequence[object]] | None = None,
        session_id: str | None = None,
        outcome_count: int | None = None,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        if session_id is not None:
            # QKD step branch: the engine samples through the kernel itself;
            # the worker binds the step to the session vault (counts only).
            session_id = _check_id(session_id, "session_id")
            if not isinstance(lease_ids, (list, tuple)) or len(lease_ids) != 0:
                raise QuantumNodeError(400, "invalid_leases", "QKD measure takes no lease IDs")
            if isinstance(outcome_count, bool) or not isinstance(outcome_count, int) or outcome_count < 0:
                raise QuantumNodeError(400, "invalid_count", "outcome_count must be a non-negative integer")
            self._auth(token, node, instance)
            payload = {"action": "measure", "session_id": session_id, "outcome_count": outcome_count}
            async with self._lock:
                replay = self._idempotency(operation_id, payload)
                if replay is not None:
                    return replay
                record = self._qkd_session(session_id)
                record.steps.append("measure")
                response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
                self._remember(operation_id, payload, response)
                return response
        if not isinstance(lease_ids, (list, tuple)) or not 1 <= len(lease_ids) <= MAX_LEASES_PER_OP:
            raise QuantumNodeError(400, "invalid_leases", "lease_ids must list 1..4 lease IDs")
        for lease_id in lease_ids:
            _check_id(lease_id, "lease_id")
        bits_out: list[int] | None = None
        probability: float | None = None
        if branch_probabilities is not None or branch_bits is not None:
            if branch_probabilities is None or branch_bits is None:
                raise QuantumNodeError(400, "invalid_branches", "branch probabilities and bits must be given together")
            if not isinstance(branch_probabilities, (list, tuple)) or not 1 <= len(branch_probabilities) <= 16:
                raise QuantumNodeError(400, "invalid_branches", "branch_probabilities must list 1..16 entries")
            if not isinstance(branch_bits, (list, tuple)) or len(branch_bits) != len(branch_probabilities):
                raise QuantumNodeError(400, "invalid_branches", "branch_bits must match probabilities")
            probs: list[float] = []
            for pos, value in enumerate(branch_probabilities):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be finite")
                if float(value) <= 0.0:
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be positive")
                probs.append(float(value))
            total = math.fsum(probs)
            if not math.isfinite(total) or total <= 0.0:
                raise QuantumNodeError(400, "invalid_branches", "branch probabilities must sum positive")
            parsed_bits: list[tuple[int, ...]] = []
            for pos, entry in enumerate(branch_bits):
                if not isinstance(entry, (list, tuple)) or not entry:
                    raise QuantumNodeError(400, "invalid_branches", f"branch_bits[{pos}] must be non-empty")
                bits: list[int] = []
                for bit in entry:
                    if isinstance(bit, bool) or bit not in (0, 1):
                        raise QuantumNodeError(400, "invalid_branches", f"branch_bits[{pos}] must hold 0/1")
                    bits.append(int(bit))
                parsed_bits.append(tuple(bits))
            drawn = self._rng.random()
            if isinstance(drawn, bool) or not isinstance(drawn, (int, float)) or not 0.0 <= float(drawn) < 1.0:
                raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw")
            cutoff = float(drawn) * total
            cumulative = 0.0
            chosen = len(probs) - 1
            for index, value in enumerate(probs):
                cumulative += value
                if cutoff < cumulative:
                    chosen = index
                    break
            bits_out = list(parsed_bits[chosen])
            probability = probs[chosen] / total
        self._auth(token, node, instance)
        payload = {
            "action": "measure",
            "lease_ids": list(lease_ids),
            "branch_probabilities": list(branch_probabilities) if branch_probabilities is not None else None,
            "branch_bits": [list(entry) for entry in branch_bits] if branch_bits is not None else None,
        }
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            for lease_id in lease_ids:
                lease = self._owned(lease_id)
                if lease.state not in ("active", "staged", "corrected"):
                    raise QuantumNodeError(409, "lease_unavailable", "lease is not available for measurement")
            for lease_id in lease_ids:
                lease = self._leases[lease_id]
                lease.state = "measured"
                lease.rho = None
            response = {
                "ok": True,
                "acknowledgement": f"ack-{operation_id}",
                "bits": bits_out,
                "probability": probability,
                "active_count": self._active_count(),
            }
            self._remember(operation_id, payload, response)
            return response

    async def stage_conditional_state(
        self,
        *,
        operation_id: str,
        lease_id: str,
        session_id: str,
        rho_matrix: object,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        lease_id = _check_id(lease_id, "lease_id")
        session_id = _check_id(session_id, "session_id")
        rows = _public_matrix_to_rows(rho_matrix)
        self._auth(token, node, instance)
        payload = {"action": "stage_conditional_state", "lease_id": lease_id, "session_id": session_id}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            lease = self._owned(lease_id)
            if lease.state != "active":
                raise QuantumNodeError(409, "lease_unavailable", "conditional state needs an active lease")
            lease.rho = QuantumDensityMatrix(rows)
            lease.state = "staged"
            lease.session_id = session_id
            response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def correct(
        self,
        *,
        operation_id: str,
        lease_id: str,
        session_id: str,
        bsm_x: int,
        bsm_z: int,
        frame_x: int,
        frame_z: int,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        lease_id = _check_id(lease_id, "lease_id")
        session_id = _check_id(session_id, "session_id")
        bsm_x = _check_bit(bsm_x, "bsm_x")
        bsm_z = _check_bit(bsm_z, "bsm_z")
        frame_x = _check_bit(frame_x, "frame_x")
        frame_z = _check_bit(frame_z, "frame_z")
        self._auth(token, node, instance)
        payload = {
            "action": "correct",
            "lease_id": lease_id,
            "session_id": session_id,
            "bsm_x": bsm_x,
            "bsm_z": bsm_z,
            "frame_x": frame_x,
            "frame_z": frame_z,
        }
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            key = (session_id, lease_id)
            stored = self._corrections.get(key)
            if stored is not None:
                if (
                    stored["bsm_x"] != bsm_x
                    or stored["bsm_z"] != bsm_z
                    or stored["frame_x"] != frame_x
                    or stored["frame_z"] != frame_z
                ):
                    raise QuantumNodeError(409, "correction_conflict", "correction already applied for this session")
                return dict(stored["response"])
            lease = self._owned(lease_id)
            if lease.state != "staged" or lease.session_id != session_id or lease.rho is None:
                raise QuantumNodeError(409, "no_staged_state", "no staged conditional state for this session")
            correction_x = bsm_x ^ frame_x
            correction_z = bsm_z ^ frame_z
            rho = lease.rho
            gate_x = bool(correction_x)
            gate_z = bool(correction_z)
            if gate_x:
                rho = rho.apply_single(X, 0)
            if gate_z:
                rho = rho.apply_single(Z, 0)
            lease.rho = rho
            lease.state = "corrected"
            response = {
                "ok": True,
                "acknowledgement": f"ack-{operation_id}",
                "correction_x": correction_x,
                "correction_z": correction_z,
                "gate_x": gate_x,
                "gate_z": gate_z,
                "correction_applied": True,
                "rho_matrix": rho.to_public_matrix(),
                "active_count": self._active_count(),
            }
            self._corrections[key] = {
                "bsm_x": bsm_x,
                "bsm_z": bsm_z,
                "frame_x": frame_x,
                "frame_z": frame_z,
                "response": dict(response),
            }
            self._remember(operation_id, payload, response)
            return response

    async def transfer(
        self,
        *,
        operation_id: str,
        lease_ids: Sequence[str],
        from_resource: str,
        to_resource: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        from_resource = _check_id(from_resource, "from_resource")
        to_resource = _check_id(to_resource, "to_resource")
        if not isinstance(lease_ids, (list, tuple)) or not 1 <= len(lease_ids) <= MAX_LEASES_PER_OP:
            raise QuantumNodeError(400, "invalid_leases", "lease_ids must list 1..4 lease IDs")
        for lease_id in lease_ids:
            _check_id(lease_id, "lease_id")
        if from_resource == to_resource:
            raise QuantumNodeError(400, "invalid_transfer", "transfer needs distinct resources")
        self._auth(token, node, instance)
        payload = {
            "action": "transfer",
            "lease_ids": list(lease_ids),
            "from_resource": from_resource,
            "to_resource": to_resource,
        }
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            for lease_id in lease_ids:
                lease = self._owned(lease_id)
                if lease.resource_id != from_resource:
                    raise QuantumNodeError(409, "lease_unavailable", "lease is not bound to from_resource")
                if lease.state not in ("active", "staged", "corrected", "measured"):
                    raise QuantumNodeError(409, "lease_unavailable", "lease is not transferable")
            for lease_id in lease_ids:
                self._leases[lease_id].resource_id = to_resource
            response = {"ok": True, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def release(
        self,
        *,
        operation_id: str,
        lease_ids: Sequence[str],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        if not isinstance(lease_ids, (list, tuple)) or not 1 <= len(lease_ids) <= MAX_LEASES_PER_OP:
            raise QuantumNodeError(400, "invalid_leases", "lease_ids must list 1..4 lease IDs")
        for lease_id in lease_ids:
            _check_id(lease_id, "lease_id")
        self._auth(token, node, instance)
        payload = {"action": "release", "lease_ids": list(lease_ids)}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            for lease_id in lease_ids:
                lease = self._owned(lease_id)
                if lease.state == "released":
                    raise QuantumNodeError(409, "already_released", "lease was already released")
            for lease_id in lease_ids:
                lease = self._leases[lease_id]
                lease.state = "released"
                lease.rho = None
            response = {"ok": True, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    # -- QKD session commands (node-private vault; same auth/replay/errors) --

    def _qkd_session(self, session_id: str) -> _QKDRecord:
        record = self._qkd.get(session_id)
        if record is None:
            raise QuantumNodeError(404, "unknown_session", "no QKD session bound on this worker")
        return record

    async def begin_qkd(
        self,
        *,
        operation_id: str,
        session_id: str,
        role: str,
        peer: str,
        owner: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Bind role/session/ownership to this worker's own node. No URL selection."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if role not in ("alice", "bob"):
            raise QuantumNodeError(400, "invalid_role", "role must be alice or bob")
        peer = _check_node(peer, "peer")
        owner = _check_id(owner, "owner")
        self._auth(token, node, instance)
        payload = {"action": "begin_qkd", "session_id": session_id, "role": role, "peer": peer, "owner": owner}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            existing = self._qkd.get(session_id)
            if existing is not None:
                if (existing.role, existing.peer, existing.owner) != (role, peer, owner):
                    raise QuantumNodeError(409, "session_conflict", "QKD session already bound with different ownership")
                return {"ok": True, "session_id": session_id}
            self._qkd[session_id] = _QKDRecord(session_id=session_id, role=role, peer=peer, owner=owner, steps=["begin"])
            response = {"ok": True, "session_id": session_id}
            self._remember(operation_id, payload, response)
            return response

    async def prepare(
        self,
        *,
        operation_id: str,
        session_id: str,
        count: int,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise QuantumNodeError(400, "invalid_count", "count must be a non-negative integer")
        self._auth(token, node, instance)
        payload = {"action": "prepare", "session_id": session_id, "count": count}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.candidate_count = count
            record.steps.append("prepare")
            response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def disclose_sample(
        self,
        *,
        operation_id: str,
        session_id: str,
        test_count: int,
        error_count: int,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        for label, value in (("test_count", test_count), ("error_count", error_count)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise QuantumNodeError(400, "invalid_count", f"{label} must be a non-negative integer")
        if error_count > test_count:
            raise QuantumNodeError(400, "invalid_sample", "error_count must not exceed test_count")
        self._auth(token, node, instance)
        payload = {"action": "disclose_sample", "session_id": session_id, "test_count": test_count, "error_count": error_count}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.test_count = test_count
            record.error_count = error_count
            record.steps.append("disclose_sample")
            response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def syndrome(
        self,
        *,
        operation_id: str,
        session_id: str,
        syndrome_bits_count: int,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if isinstance(syndrome_bits_count, bool) or not isinstance(syndrome_bits_count, int) or syndrome_bits_count < 0:
            raise QuantumNodeError(400, "invalid_count", "syndrome_bits_count must be a non-negative integer")
        self._auth(token, node, instance)
        payload = {"action": "syndrome", "session_id": session_id, "syndrome_bits_count": syndrome_bits_count}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.syndrome_len = syndrome_bits_count
            record.steps.append("syndrome")
            response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def reconcile(
        self,
        *,
        operation_id: str,
        session_id: str,
        corrected_count: int,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if isinstance(corrected_count, bool) or not isinstance(corrected_count, int) or corrected_count < 0:
            raise QuantumNodeError(400, "invalid_count", "corrected_count must be a non-negative integer")
        self._auth(token, node, instance)
        payload = {"action": "reconcile", "session_id": session_id, "corrected_count": corrected_count}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.corrections = corrected_count
            record.steps.append("reconcile")
            response = {"ok": True, "acknowledgement": f"ack-{operation_id}", "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def verify_tag(
        self,
        *,
        operation_id: str,
        session_id: str,
        tag_ok: bool,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if not isinstance(tag_ok, bool):
            raise QuantumNodeError(400, "invalid_tag", "tag_ok must be a boolean")
        self._auth(token, node, instance)
        payload = {"action": "verify_tag", "session_id": session_id, "tag_ok": tag_ok}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.tag_ok = tag_ok
            record.steps.append("verify_tag")
            response = {"ok": True, "verified": tag_ok, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    def _qkd_indices(self, values: object, limit: int, name: str) -> list[int]:
        if not isinstance(values, (list, tuple)):
            raise QuantumNodeError(400, "invalid_index", f"{name} must be a list of indices")
        chosen: list[int] = []
        seen: set[int] = set()
        for pos, item in enumerate(values):
            if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < limit or item in seen:
                raise QuantumNodeError(400, "invalid_index", f"{name}[{pos}] is not a unique in-range index")
            seen.add(item)
            chosen.append(item)
        return chosen

    async def qkd_prepare_bb84(
        self,
        *,
        operation_id: str,
        session_id: str,
        count: int,
        rng: Any,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Draw Alice's signals. Bases are public; the state list is the channel.

        The bit string stays in this vault. Returned states are not written to
        the replay log. A second prepare on the same session is 409.
        """
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20000:
            raise QuantumNodeError(400, "invalid_count", "count must be an integer in 1..20000")
        if rng is None or not hasattr(rng, "random") or not hasattr(rng, "choice"):
            raise QuantumNodeError(400, "invalid_rng", "rng must provide random() and choice()")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if record.role != "alice":
                raise QuantumNodeError(403, "wrong_role", "only the sending node prepares BB84 signals")
            if "prepare" in record.steps:
                raise QuantumNodeError(409, "session_step", "BB84 signals were already prepared")
            raw_bits: list[int] = []
            raw_bases: list[str] = []
            states: list[Any] = []
            for _ in range(count):
                draw = rng.random()
                if isinstance(draw, bool) or not isinstance(draw, (int, float)) or not 0.0 <= float(draw) < 1.0:
                    raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw")
                bit = 1 if float(draw) < 0.5 else 0
                basis = rng.choice(("+", "x"))
                if basis not in ("+", "x"):
                    raise QuantumNodeError(503, "rng_failure", "worker RNG produced an unknown basis")
                raw_bits.append(bit)
                raw_bases.append(basis)
                states.append(bb84_state(bit, basis))
            record.raw_bits = raw_bits
            record.raw_bases = raw_bases
            record.candidate_count = count
            record.steps.append("prepare")
            return {"ok": True, "bases": list(raw_bases), "states": states}

    async def qkd_measure_bb84(
        self,
        *,
        operation_id: str,
        session_id: str,
        states: Sequence[Any],
        bases: Sequence[object],
        rng: Any,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Measure the channel states in Bob's bases and keep only his bits."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if not isinstance(states, (list, tuple)) or not isinstance(bases, (list, tuple)):
            raise QuantumNodeError(400, "invalid_signal", "states and bases must be sequences")
        if len(states) != len(bases) or not 1 <= len(states) <= 20000:
            raise QuantumNodeError(400, "invalid_signal", "states and bases must share a length in 1..20000")
        if rng is None or not hasattr(rng, "random"):
            raise QuantumNodeError(400, "invalid_rng", "rng must provide random()")
        self._auth(token, node, instance)
        measured: list[int] = []
        chosen: list[str] = []
        for state, basis in zip(states, bases):
            if basis not in ("+", "x"):
                raise QuantumNodeError(400, "invalid_basis", "basis must be + or x")
            vec = state.apply_single(H, 0) if basis == "x" else state
            try:
                bit = int(vec.density().measure_z((0,), rng).bits[0])
            except (AttributeError, TypeError, ValueError) as exc:
                raise QuantumNodeError(400, "invalid_signal", "signal is not a one-qubit state") from exc
            if bit not in (0, 1):
                raise QuantumNodeError(400, "invalid_signal", "measurement did not yield a bit")
            measured.append(bit)
            chosen.append(str(basis))
        async with self._lock:
            record = self._qkd_session(session_id)
            if record.role != "bob":
                raise QuantumNodeError(403, "wrong_role", "only the receiving node measures BB84 signals")
            if "measure" in record.steps:
                raise QuantumNodeError(409, "session_step", "BB84 signals were already measured")
            record.raw_bits = measured
            record.raw_bases = chosen
            record.candidate_count = len(measured)
            record.steps.append("measure")
            return {"ok": True, "count": len(measured)}

    async def qkd_adopt_indices(
        self,
        *,
        operation_id: str,
        session_id: str,
        key_indices: Sequence[int],
        phase_indices: Sequence[int],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Split raw bits into a private key string and a public phase sample."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if "sift" in record.steps:
                raise QuantumNodeError(409, "session_step", "this session was already sifted")
            keys = self._qkd_indices(key_indices, len(record.raw_bits), "key_indices")
            phase = self._qkd_indices(phase_indices, len(record.raw_bits), "phase_indices")
            if set(keys) & set(phase):
                raise QuantumNodeError(400, "invalid_index", "key and phase indices must be disjoint")
            record.key_bits = [record.raw_bits[i] for i in keys]
            record.phase_bits = [record.raw_bits[i] for i in phase]
            disclosed = list(record.phase_bits)
            record.raw_bits = []
            record.steps.append("sift")
            return {"ok": True, "key_len": len(record.key_bits), "phase_bits": disclosed}

    async def qkd_lengths(
        self,
        *,
        operation_id: str,
        session_id: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            return {
                "ok": True,
                "key_len": len(record.key_bits),
                "phase_len": len(record.phase_bits),
            }

    async def qkd_accept_bit(
        self,
        *,
        operation_id: str,
        session_id: str,
        bit: int,
        bucket: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Store one locally owned outcome. The response carries a count only."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if isinstance(bit, bool) or bit not in (0, 1):
            raise QuantumNodeError(400, "invalid_bit", "bit must be 0 or 1")
        if bucket not in ("key", "phase"):
            raise QuantumNodeError(400, "invalid_bucket", "bucket must be key or phase")
        self._auth(token, node, instance)
        payload = {
            "action": "qkd_accept_bit",
            "session_id": session_id,
            "bucket": bucket,
            "bit": int(bit),
        }
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            target = record.key_bits if bucket == "key" else record.phase_bits
            target.append(int(bit))
            response = {"ok": True, "count": len(target)}
            self._remember(operation_id, payload, response)
            return response

    async def qkd_syndrome(
        self,
        *,
        operation_id: str,
        session_id: str,
        order: Sequence[int],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Return public parity checks of this node's key string. Not the bits."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if record.role != "alice":
                raise QuantumNodeError(403, "wrong_role", "only the sending node announces the syndrome")
            if "syndrome" in record.steps:
                raise QuantumNodeError(409, "session_step", "syndrome was already announced")
            try:
                syndromes, total = syndrome_blocks(record.key_bits, order)
            except (ReconciliationFailed, ValueError) as exc:
                raise QuantumNodeError(400, "invalid_syndrome", "syndrome inputs were rejected") from exc
            record.syndrome_len = total
            record.steps.append("syndrome")
            return {"ok": True, "syndromes": list(syndromes), "syndrome_bits": total}

    async def qkd_correct(
        self,
        *,
        operation_id: str,
        session_id: str,
        order: Sequence[int],
        syndromes: Sequence[int],
        flip_positions: Sequence[int] = (),
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Correct this node's own key string. The corrected bits stay here."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if record.role != "bob":
                raise QuantumNodeError(403, "wrong_role", "only the receiving node applies the syndrome")
            if "correct" in record.steps:
                raise QuantumNodeError(409, "session_step", "syndrome was already applied")
            try:
                corrected, corrections = correct_blocks(
                    record.key_bits, order, syndromes, flip_positions=flip_positions
                )
            except (ReconciliationFailed, ValueError) as exc:
                raise QuantumNodeError(400, "invalid_syndrome", "syndrome inputs were rejected") from exc
            record.key_bits = list(corrected)
            record.corrections = corrections
            record.steps.append("correct")
            return {"ok": True, "corrections": corrections}

    async def qkd_tag(
        self,
        *,
        operation_id: str,
        session_id: str,
        seed: Sequence[int],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """32-bit Toeplitz tag of this node's key string. The tag is public."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if "verify_tag" in record.steps:
                raise QuantumNodeError(409, "session_step", "verification tag was already produced")
            try:
                tag = toeplitz_hash(seed, record.key_bits, 32)
            except ValueError as exc:
                raise QuantumNodeError(400, "invalid_tag", "verification seed was rejected") from exc
            record.steps.append("verify_tag")
            return {"ok": True, "tag": list(tag)}

    async def qkd_extract(
        self,
        *,
        operation_id: str,
        session_id: str,
        seed: Sequence[int],
        rng: Any,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Extract locally. Returns the commitment and length, never the key."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        if rng is None or not hasattr(rng, "random"):
            raise QuantumNodeError(400, "invalid_rng", "rng must provide random()")
        self._auth(token, node, instance)
        async with self._lock:
            record = self._qkd_session(session_id)
            if record.key is not None or "extract" in record.steps:
                raise QuantumNodeError(409, "session_step", "key was already extracted")
            try:
                key = toeplitz_extract(seed, record.key_bits)
                blinding = random_bytes(rng, 32)
                commitment = node_commitment(self.node_id, session_id, blinding, key)
            except ValueError as exc:
                raise QuantumNodeError(400, "invalid_extract", "extraction seed was rejected") from exc
            record.key = key
            record.blinding = blinding
            record.capability = secrets.token_hex(16)
            record.commitment_hex = commitment
            record.available = True
            record.used = False
            record.key_bits = []
            record.raw_bits = []
            record.phase_bits = []
            record.steps.append("extract")
            return {"ok": True, "key_length": len(key) * 8, "commitment_hex": commitment}

    async def use_key(
        self,
        *,
        operation_id: str,
        owner: str,
        session: str,
        capability: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """One-shot key use: success returns no bytes; second use is 409."""
        operation_id = _check_id(operation_id, "operation_id")
        owner = _check_id(owner, "owner")
        session = _check_id(session, "session")
        self._auth(token, node, instance)
        presented = capability if isinstance(capability, str) else ""
        payload = {"action": "use_key", "owner": owner, "session": session}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd.get(session)
            if record is None or record.owner != owner:
                raise QuantumNodeError(403, "wrong_owner_or_session", "use_key is not owned by this claimant for this session")
            if not record.available or record.key is None:
                raise QuantumNodeError(409, "key_unavailable", "no agreed key is available for this session")
            if record.used:
                raise QuantumNodeError(409, "already_used", "key capability was already consumed")
            if not presented or record.capability is None or not hmac.compare_digest(presented.encode(), record.capability.encode()):
                raise QuantumNodeError(403, "wrong_capability", "key capability does not match")
            record.used = True
            response = {"ok": True, "outcome": "accepted"}
            self._remember(operation_id, payload, response)
            return response

    async def abort(
        self,
        *,
        operation_id: str,
        session_id: str,
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Destroy key availability for a session; restart loses everything."""
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        payload = {"action": "abort", "session_id": session_id}
        async with self._lock:
            replay = self._idempotency(operation_id, payload)
            if replay is not None:
                return replay
            record = self._qkd_session(session_id)
            record.key = None
            record.blinding = None
            record.capability = None
            record.commitment_hex = None
            record.available = False
            record.raw_bits = []
            record.raw_bases = []
            record.key_bits = []
            record.phase_bits = []
            record.steps.append("abort")
            response = {"ok": True, "session_id": session_id}
            self._remember(operation_id, payload, response)
            return response

    async def inspect(self, *, token: str, node: str, instance: str | None = None) -> dict[str, Any]:
        # Read-only discovery: an empty instance returns this process identity
        # (token + node still enforced) so remotes can bind later commands.
        self._auth(token, node, instance if instance else self.instance_id)
        async with self._lock:
            return {
                "ok": True,
                "node_id": self.node_id,
                "instance_id": self.instance_id,
                "capacity": self.capacity,
                "active_count": self._active_count(),
                "leases": [lease.public() for lease in self._leases.values() if lease.state != "released"],
            }


async def deposit_correlated_key_bits(
    alice: QuantumNodeWorker,
    bob: QuantumNodeWorker,
    rho: Any,
    session_id: str,
    rng: Any,
    operation_prefix: str,
    alice_auth: Mapping[str, str],
    bob_auth: Mapping[str, str],
) -> None:
    """Sample one shared Z round and hand each click only to its owner.

    The outcomes are not returned. Callers that need a public sample (phase
    error, CHSH) must use a disclosing measurement instead.
    """
    branch = rho.measure_z((0, 1), rng)
    await alice.qkd_accept_bit(
        operation_id=f"{operation_prefix}-a",
        session_id=session_id,
        bit=int(branch.bits[0]),
        bucket="key",
        token=alice_auth["token"],
        node=alice_auth["node"],
        instance=alice_auth["instance"],
    )
    await bob.qkd_accept_bit(
        operation_id=f"{operation_prefix}-b",
        session_id=session_id,
        bit=int(branch.bits[1]),
        bucket="key",
        token=bob_auth["token"],
        node=bob_auth["node"],
        instance=bob_auth["instance"],
    )


# -- Starlette worker app --------------------------------------------------

def create_node_app(worker: QuantumNodeWorker):  # type: ignore[no-untyped-def]
    """Build the fixed-path Starlette app serving one worker's command set."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _body(request: Request) -> Any:
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            raise QuantumNodeError(413, "body_too_large", "request body exceeds 64 KiB")
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise QuantumNodeError(400, "invalid_json", "request body is not valid JSON") from exc
    def _creds(request: Request) -> str:
        return parse_bearer(request.headers.get("authorization", ""))


    def _handler(action: str):  # type: ignore[no-untyped-def]
        async def handle(request: Request):  # type: ignore[no-untyped-def]
            try:
                body = await _body(request)
                if not isinstance(body, dict):
                    raise QuantumNodeError(400, "invalid_json", "request body must be a JSON object")
                token = _creds(request)
                node = body.get("node")
                instance = body.get("instance")
                operation_id = body.get("operation_id", "")
                if action == "reserve":
                    result = await worker.reserve(
                        operation_id=operation_id,
                        resource_id=body.get("resource_id", ""),
                        count=body.get("count", 0),
                        session_id=body.get("session_id"),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "apply_circuit":
                    result = await worker.apply_circuit(
                        operation_id=operation_id,
                        lease_ids=body.get("lease_ids", []),
                        operations=body.get("operations", []),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "measure":
                    result = await worker.measure(
                        operation_id=operation_id,
                        lease_ids=body.get("lease_ids", []),
                        token=token,
                        node=node,
                        instance=instance,
                        branch_probabilities=body.get("branch_probabilities"),
                        branch_bits=body.get("branch_bits"),
                    )
                elif action == "stage_conditional_state":
                    result = await worker.stage_conditional_state(
                        operation_id=operation_id,
                        lease_id=body.get("lease_id", ""),
                        session_id=body.get("session_id", ""),
                        rho_matrix=body.get("rho_matrix"),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "correct":
                    result = await worker.correct(
                        operation_id=operation_id,
                        lease_id=body.get("lease_id", ""),
                        session_id=body.get("session_id", ""),
                        bsm_x=body.get("bsm_x", -1),
                        bsm_z=body.get("bsm_z", -1),
                        frame_x=body.get("frame_x", -1),
                        frame_z=body.get("frame_z", -1),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "transfer":
                    result = await worker.transfer(
                        operation_id=operation_id,
                        lease_ids=body.get("lease_ids", []),
                        from_resource=body.get("from_resource", ""),
                        to_resource=body.get("to_resource", ""),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "release":
                    result = await worker.release(
                        operation_id=operation_id,
                        lease_ids=body.get("lease_ids", []),
                        token=token,
                        node=node,
                        instance=instance,
                    )
                elif action == "inspect":
                    result = await worker.inspect(token=token, node=node, instance=instance)
                else:  # pragma: no cover - fixed action table
                    raise QuantumNodeError(404, "unknown_action", "unknown worker action")
                return JSONResponse(result)
            except QuantumNodeError as exc:
                return JSONResponse(
                    exc.to_dict(),
                    status_code=exc.status,
                    headers={"Content-Type": "application/problem+json"},
                )

        return handle

    routes = [Route(f"/v1/node/{action}", _handler(action), methods=["POST"]) for action in NODE_ACTIONS]
    from starlette.applications import Starlette

    return Starlette(routes=routes)


def build_node_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one authenticated quantum simulator node worker.")
    parser.add_argument("--node", required=True, help="Worker node identity (1..64 chars).")
    parser.add_argument("--capacity", type=int, default=16, help="Fixed qubit capacity (1..1024).")
    parser.add_argument("--port", type=int, default=8891, help="Local TCP port to serve.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry: node / capacity / port only. Credential comes from the environment."""
    parser = build_node_parser()
    args = parser.parse_args(argv)
    token = worker_token_from_env()
    if not token:
        parser.error("QUANTUM_NODE_TOKEN is not set")
    worker = QuantumNodeWorker(args.node, capacity=args.capacity, token=token)
    app = create_node_app(worker)
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
