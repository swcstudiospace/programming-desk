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

from desk_gateway.quantum_state import (
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
        self._lock = asyncio.Lock()
        self._seen_ops: dict[str, tuple[str, dict[str, Any]]] = {}
        self._corrections: dict[tuple[str, str], dict[str, Any]] = {}
        self._rng = rng if rng is not None else secrets.SystemRandom()

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
        lease_ids: Sequence[str],
        token: str,
        node: str,
        instance: str,
        branch_probabilities: Sequence[object] | None = None,
        branch_bits: Sequence[Sequence[object]] | None = None,
    ) -> dict[str, Any]:
        operation_id = _check_id(operation_id, "operation_id")
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
