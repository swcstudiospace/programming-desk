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
import base64
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
    MAX_QKD_UNITS,
    ReconciliationFailed,
    bb84_state,
    correct_blocks,
    node_commitment,
    random_bits,
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
    "MAX_QKD_SESSIONS",
    "NODE_ACTIONS",
    "QKD_ABORT_REASONS",
    "QKD_OWNER_ACTIONS",
    "QKD_STEP_ACTIONS",
    "QKD_USE_OPERATIONS",
    "QuantumNodeError",
    "QuantumNodeLease",
    "QuantumNodeWorker",
    "build_node_parser",
    "create_node_app",
    "decode_bits",
    "decode_density",
    "decode_indices",
    "decode_signals",
    "encode_bits",
    "encode_density",
    "encode_indices",
    "encode_signals",
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
#: Fixed worker command paths, resolved server-side only. ``qkd_step``
#: carries coordinator protocol work; ``qkd_owner`` carries the private
#: owning-node capability path. The gateway never proxies ``qkd_owner``.
NODE_ACTIONS = (
    "reserve",
    "apply_circuit",
    "measure",
    "stage_conditional_state",
    "correct",
    "transfer",
    "release",
    "inspect",
    "qkd_step",
    "qkd_owner",
)

#: Fixed coordinator QKD actions under ``qkd_step`` (branch dispatch only).
QKD_STEP_ACTIONS = (
    "begin",
    "prepare_bb84",
    "measure_bb84",
    "adopt_indices",
    "measure_e91",
    "lengths",
    "syndrome",
    "correct",
    "tag",
    "extract",
    "abort",
)
#: Fixed private owner actions under ``qkd_owner`` (never on the gateway).
QKD_OWNER_ACTIONS = ("capability", "use")
#: Fixed abort reason codes accepted by ``qkd_step/abort``.
QKD_ABORT_REASONS = (
    "user_abort",
    "qber_exceeded",
    "witness_failed",
    "insufficient_sample",
    "insufficient_entropy",
    "reconciliation_failed",
    "resource_exhausted",
    "protocol_error",
)
#: Fixed consumer labels accepted by ``qkd_owner/use``.
QKD_USE_OPERATIONS = ("teleport_release", "drill_release", "qkd_test")
#: Maximum nonterminal QKD records per worker, including established but
#: unused keys. Terminal (used/aborted) compacts never count here and are
#: never evicted to make room; ``begin`` refuses past this bound.
MAX_QKD_SESSIONS = 64
#: Maximum ordered E91 rounds (and BB84 signals) per session. Toeplitz
#: seeds are NOT logical units: a maximum candidate needs ``n+31`` tag
#: seed bits and ``n+ell-1`` extraction seed bits (at most 20255 at
#: ``ell=256``), validated against that requirement, still far below 64KiB.
_MAX_E91_ROUNDS = 20000
#: Retained terminal (used/aborted) compact QKD records. Each holds counts
#: and terminal flags only, no private arrays; oldest compacts beyond this
#: bound are reclaimed.
_QKD_TERMINAL_CAP = 2048
#: Reconciliation block width shared with ``quantum_key`` Hamming helpers.
_QKD_SYNDROME_BLOCK = 63
#: Codec-level sanity caps (actual 64KiB admission is measured on the wire;
#: per-action exact lengths govern). Seeds up to 20255 bits must pass.
_MAX_CODEC_BITS = 131072
_MAX_CODEC_INDICES = 65535
_MAX_CODEC_SIGNALS = 131072

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
#: Full acknowledgement cache: last 2048 operation responses.
_SEEN_OPS_CAP = 2048
#: Exact at-most-once effect history: one digest tombstone per accepted
#: effect, never evicted. Bounds total effects per worker instance.
_MAX_EFFECT_HISTORY = 262144
#: History slots reserved for terminal cleanup (1024 leases + 64 QKD
#: records): release / abort / use_key consume these after the soft cap.
_RESERVED_CLEANUP_SLOTS = 1088
#: Soft admission ceiling for non-cleanup effects; cleanup-only above this.
_NON_CLEANUP_EFFECT_CAP = _MAX_EFFECT_HISTORY - _RESERVED_CLEANUP_SLOTS
#: Effect actions allowed into the reserved cleanup slots. Every other
#: action refuses at the soft ceiling. New effect methods MUST pass their
#: cleanup action explicitly; the default classifies as non-cleanup.
_CLEANUP_ACTIONS = frozenset({"release", "abort", "use_key"})

_GATES = {"H": H, "X": X, "Z": Z, "S": S}


def _payload_digest(payload: Mapping[str, Any]) -> str:
    """Canonical digest of one validated effect payload for replay comparison."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _mint_lease_id(resource_id: str) -> str:
    """Mint an independently bounded lease ID for a (possibly 128-char) resource.

    Short resources keep the readable ``{resource}:q-{rand}`` form. Long
    resources are truncated with a sha256 fingerprint so the lease ID stays
    within ``MAX_ID_LEN`` (every issued lease must pass ``release`` ID
    validation) while remaining unique per resource. The full resource ID is
    stored on the lease record; the lease ID itself is only an owner handle.
    """
    rand = secrets.token_hex(4)
    if len(resource_id) + 11 <= MAX_ID_LEN:
        return f"{resource_id}:q-{rand}"
    fingerprint = hashlib.sha256(resource_id.encode()).hexdigest()[:16]
    return f"{resource_id[:98]}:h-{fingerprint}:q-{rand}"


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

    Never serialized wholesale: ``inspect``/``lengths`` expose counts and
    terminal flags only, and ``repr`` is redacted to class + session. The
    owner is the bound node identity derived from the worker credential at
    ``begin`` (never a body-supplied owner). Terminal (used/aborted)
    records are compacted: private lists/bytes/capability cleared, counts
    snapshotted, replay history retained.
    """

    session_id: str
    protocol: str
    role: str
    peer: str
    owner: str
    bound_instance: str
    steps: list = field(default_factory=list)
    raw_bits: list = field(default_factory=list)
    raw_bases: list = field(default_factory=list)
    key_bits: list = field(default_factory=list)
    phase_bits: list = field(default_factory=list)
    e91_rounds: list = field(default_factory=list)
    e91_round_count: int = 0
    syndrome_len: int = 0
    corrections: int = 0
    key: bytes | None = None
    blinding: bytes | None = None
    capability: str | None = None
    commitment_hex: str | None = None
    available: bool = False
    used: bool = False
    aborted: bool = False
    abort_reason: str | None = None
    final_key_length: int = 0
    final_phase_length: int = 0

    @property
    def terminal(self) -> bool:
        """Used or aborted records hold compact replay only."""
        return self.used or self.aborted

    @property
    def state(self) -> str:
        """Public lifecycle label: active, established, used, or aborted."""
        if self.used:
            return "used"
        if self.aborted:
            return "aborted"
        if self.available:
            return "established"
        return "active"

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
            try:
                real, imag = float(cell[0]), float(cell[1])
            except OverflowError:
                raise QuantumNodeError(400, "invalid_state", f"cell [{i}][{j}] must be finite") from None
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


# -- QKD wire codecs (section 3: identical Local/Remote strict codecs) ----
#
# Compact DTOs; unknown fields, type confusion, and padding violations are
# all 400. Decode never normalizes: the exact validated bit/index/signal
# sequences round-trip bit-identically over both transports.

def _check_dto(dto: object, encoding: str, name: str) -> dict[str, Any]:
    if not isinstance(dto, dict):
        raise QuantumNodeError(400, "invalid_codec", f"{name} must be an object")
    if dto.get("encoding") != encoding:
        raise QuantumNodeError(400, "invalid_codec", f"{name} must use encoding {encoding}")
    return dto


def encode_bits(bits: Sequence[int]) -> dict[str, Any]:
    """Pack bits MSB-first: bit ``i`` sets byte ``i//8`` bit ``7-(i%8)``."""
    values = list(bits)
    for bit in values:
        if isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1):
            raise QuantumNodeError(400, "invalid_bits", "bits must hold integer 0/1")
    raw = bytearray((len(values) + 7) // 8)
    for pos, bit in enumerate(values):
        if bit:
            raw[pos // 8] |= 1 << (7 - (pos % 8))
    return {"encoding": "bits-msb-v1", "count": len(values), "data": base64.b64encode(bytes(raw)).decode()}


def decode_bits(dto: object, name: str, *, exact: int | None = None) -> tuple[int, ...]:
    """Strict ``bits-msb-v1`` decode with exact length and zero padding."""
    body = _check_dto(dto, "bits-msb-v1", name)
    if set(body) != {"encoding", "count", "data"}:
        raise QuantumNodeError(400, "invalid_codec", f"{name} carries unknown fields")
    count = body["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > _MAX_CODEC_BITS:
        raise QuantumNodeError(400, "invalid_bits", f"{name} count is out of range")
    if exact is not None and count != exact:
        raise QuantumNodeError(400, "invalid_bits", f"{name} must hold exactly {exact} bits")
    data = body["data"]
    if not isinstance(data, str):
        raise QuantumNodeError(400, "invalid_bits", f"{name} data must be base64")
    try:
        raw = base64.b64decode(data.encode(), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise QuantumNodeError(400, "invalid_bits", f"{name} data is not strict base64") from exc
    if len(raw) != (count + 7) // 8:
        raise QuantumNodeError(400, "invalid_bits", f"{name} must hold exactly ceil(count/8) bytes")
    out: list[int] = []
    for pos in range(count):
        out.append((raw[pos // 8] >> (7 - (pos % 8))) & 1)
    unused = len(raw) * 8 - count
    if unused and (raw[-1] & ((1 << unused) - 1)):
        raise QuantumNodeError(400, "invalid_bits", f"{name} has nonzero unused trailing bits")
    return tuple(out)


def encode_indices(values: Sequence[int]) -> dict[str, Any]:
    """Pack indices as concatenated u16BE, preserving list order."""
    items = list(values)
    raw = bytearray()
    for pos, value in enumerate(items):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 19999:
            raise QuantumNodeError(400, "invalid_index", f"index[{pos}] must be an integer in 0..19999")
        raw += int(value).to_bytes(2, "big")
    return {"encoding": "u16be-v1", "count": len(items), "data": base64.b64encode(bytes(raw)).decode()}


def decode_indices(dto: object, name: str) -> tuple[int, ...]:
    """Strict ``u16be-v1`` decode: exact 2n bytes, ordered, unique, 0..19999."""
    body = _check_dto(dto, "u16be-v1", name)
    if set(body) != {"encoding", "count", "data"}:
        raise QuantumNodeError(400, "invalid_codec", f"{name} carries unknown fields")
    count = body["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > _MAX_CODEC_INDICES:
        raise QuantumNodeError(400, "invalid_index", f"{name} count is out of range")
    data = body["data"]
    if not isinstance(data, str):
        raise QuantumNodeError(400, "invalid_index", f"{name} data must be base64")
    try:
        raw = base64.b64decode(data.encode(), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise QuantumNodeError(400, "invalid_index", f"{name} data is not strict base64") from exc
    if len(raw) != 2 * count:
        raise QuantumNodeError(400, "invalid_index", f"{name} must hold exactly 2n bytes")
    out: list[int] = []
    seen: set[int] = set()
    for pos in range(count):
        value = int.from_bytes(raw[2 * pos : 2 * pos + 2], "big")
        if value > 19999 or value in seen:
            raise QuantumNodeError(400, "invalid_index", f"{name}[{pos}] is not a unique in-range index")
        seen.add(value)
        out.append(value)
    return tuple(out)


def encode_signals(values: Sequence[int]) -> dict[str, Any]:
    """Pack BB84 signals two bits each: 0=|0>, 1=|1>, 2=|+>, 3=|->."""
    items = list(values)
    raw = bytearray((2 * len(items) + 7) // 8)
    for pos, value in enumerate(items):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
            raise QuantumNodeError(400, "invalid_signal", f"signal[{pos}] must be 0..3")
        shift = 6 - 2 * (pos % 4)
        raw[pos // 4] |= (int(value) & 3) << shift
    return {"encoding": "bb84-signals-v1", "count": len(items), "data": base64.b64encode(bytes(raw)).decode()}


def decode_signals(dto: object, name: str) -> tuple[int, ...]:
    """Strict ``bb84-signals-v1`` decode with exact byte count and padding."""
    body = _check_dto(dto, "bb84-signals-v1", name)
    if set(body) != {"encoding", "count", "data"}:
        raise QuantumNodeError(400, "invalid_codec", f"{name} carries unknown fields")
    count = body["count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > _MAX_CODEC_SIGNALS:
        raise QuantumNodeError(400, "invalid_signal", f"{name} count is out of range")
    data = body["data"]
    if not isinstance(data, str):
        raise QuantumNodeError(400, "invalid_signal", f"{name} data must be base64")
    try:
        raw = base64.b64decode(data.encode(), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise QuantumNodeError(400, "invalid_signal", f"{name} data is not strict base64") from exc
    if len(raw) != (2 * count + 7) // 8:
        raise QuantumNodeError(400, "invalid_signal", f"{name} must hold exactly ceil(2n/8) bytes")
    out: list[int] = []
    for pos in range(count):
        out.append((raw[pos // 4] >> (6 - 2 * (pos % 4))) & 3)
    unused_slots = len(raw) * 4 - count
    if unused_slots:
        mask = (1 << (2 * unused_slots)) - 1
        if raw[-1] & mask:
            raise QuantumNodeError(400, "invalid_signal", f"{name} has nonzero unused trailing bits")
    return tuple(out)


def encode_density(rho: Any) -> dict[str, Any]:
    """Encode a 1- or 2-qubit density as ``density-v1`` ``[[real, imag]]``."""
    rows = rho.rows
    dim = len(rows)
    qubits = {2: 1, 4: 2}.get(dim)
    if qubits is None:
        raise QuantumNodeError(400, "invalid_state", "density must be one or two qubits")
    return {
        "encoding": "density-v1",
        "qubits": qubits,
        "matrix": [[[float(entry.real), float(entry.imag)] for entry in row] for row in rows],
    }


def decode_density(dto: object, name: str, *, qubits: int) -> Any:
    """Strict ``density-v1`` decode with direct kernel validation.

    Exact dimensions, finite entries, and the kernel's own
    trace/Hermiticity/PSD checks apply; nothing is normalized or replaced.
    """
    body = _check_dto(dto, "density-v1", name)
    if set(body) != {"encoding", "qubits", "matrix"}:
        raise QuantumNodeError(400, "invalid_codec", f"{name} carries unknown fields")
    if isinstance(body["qubits"], bool) or body["qubits"] != qubits:
        raise QuantumNodeError(400, "invalid_state", f"{name} must be a {qubits}-qubit density")
    dim = 2**qubits
    matrix = body["matrix"]
    if not isinstance(matrix, (list, tuple)) or len(matrix) != dim:
        raise QuantumNodeError(400, "invalid_state", f"{name} must be a {dim}x{dim} matrix")
    rows: list[tuple[complex, ...]] = []
    for i, row in enumerate(matrix):
        if not isinstance(row, (list, tuple)) or len(row) != dim:
            raise QuantumNodeError(400, "invalid_state", f"{name} must be a {dim}x{dim} matrix")
        cells: list[complex] = []
        for j, cell in enumerate(row):
            if (
                not isinstance(cell, (list, tuple))
                or len(cell) != 2
                or any(isinstance(v, bool) for v in cell)
                or not all(isinstance(v, (int, float)) for v in cell)
            ):
                raise QuantumNodeError(400, "invalid_state", f"{name}[{i}][{j}] must be [real, imag]")
            try:
                real, imag = float(cell[0]), float(cell[1])
            except OverflowError:
                raise QuantumNodeError(400, "invalid_state", f"{name}[{i}][{j}] must be finite") from None
            if not math.isfinite(real) or not math.isfinite(imag):
                raise QuantumNodeError(400, "invalid_state", f"{name}[{i}][{j}] must be finite")
            cells.append(complex(real, imag))
        rows.append(tuple(cells))
    try:
        return QuantumDensityMatrix(tuple(rows))
    except (TypeError, ValueError) as exc:
        raise QuantumNodeError(400, "invalid_state", f"{name} rejected: {exc}") from exc


def _syndrome_widths(n: int) -> tuple[int, ...]:
    """Per-block parity widths mirroring the Hamming partition (blocks of 63)."""
    widths: list[int] = []
    for start in range(0, n, _QKD_SYNDROME_BLOCK):
        chunk = min(_QKD_SYNDROME_BLOCK, n - start)
        widths.append(math.ceil(math.log2(chunk + 1)))
    return tuple(widths)


def _syndrome_ints_to_bits(syndromes: Sequence[int], n: int) -> tuple[int, ...]:
    """Expand per-block syndrome integers to MSB-first parity bits."""
    bits: list[int] = []
    for value, width in zip(syndromes, _syndrome_widths(n)):
        for k in range(width):
            bits.append((int(value) >> (width - 1 - k)) & 1)
    return tuple(bits)


def _syndrome_bits_to_ints(bits: Sequence[int], n: int) -> tuple[int, ...]:
    """Fold MSB-first parity bits back to per-block syndrome integers."""
    widths = _syndrome_widths(n)
    if len(bits) != sum(widths):
        raise QuantumNodeError(400, "invalid_syndrome", "syndrome length does not match the candidate")
    out: list[int] = []
    pos = 0
    for width in widths:
        value = 0
        for k in range(width):
            value = (value << 1) | int(bits[pos + k])
        out.append(value)
        pos += width
    return tuple(out)

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
        # Compact at-most-once history: operation-ID digest tombstones for
        # every accepted effect, never evicted (see _idempotency).
        self._tombstones: dict[str, str] = {}
        # Released lease handles, kept only to report already_released for
        # known-finished leases; the full records are reclaimed on release.
        self._released_ids: set[str] = set()
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
        # Every unreleased handle needs a terminal cleanup effect, including
        # measured handles. Measurement destroys state, not owner liability.
        return len(self._leases)

    def _idempotency(
        self, operation_id: str, payload: Mapping[str, Any], action: str = "effect"
    ) -> dict[str, Any] | None:
        """At-most-once gate: cached replay, conflict, expiry, or admission.

        A repeated ID with a byte-identical payload returns the cached
        acknowledgement; with any changed field it conflicts (409). An ID
        whose acknowledgement left the 2048-entry cache but whose digest
        tombstone survives returns 409 ``operation_expired`` and never
        re-executes. Unseen non-cleanup effects refuse at 261056 before any
        effect or draw; terminal ``release`` / ``abort`` / ``use_key``
        cleanup may consume the 1088 reserved slots up to the 262144 hard
        cap. Read-only probes (``inspect``) never enter this gate.
        """
        digest = _payload_digest(payload)
        seen = self._seen_ops.get(operation_id)
        if seen is not None:
            if seen[0] != digest:
                raise QuantumNodeError(409, "operation_conflict", "operation_id reused with a different payload")
            return dict(seen[1])
        known = self._tombstones.get(operation_id)
        if known is not None:
            if known != digest:
                raise QuantumNodeError(409, "operation_conflict", "operation_id reused with a different payload")
            raise QuantumNodeError(409, "operation_expired", "operation acknowledgement expired; never re-executed")
        if len(self._tombstones) >= _MAX_EFFECT_HISTORY:
            raise QuantumNodeError(409, "history_exhausted", "worker effect history is saturated")
        if action not in _CLEANUP_ACTIONS and len(self._tombstones) >= _NON_CLEANUP_EFFECT_CAP:
            raise QuantumNodeError(
                409, "history_exhausted", "worker effect history is saturated; terminal cleanup only"
            )
        return None

    def _remember(self, operation_id: str, payload: Mapping[str, Any], response: Mapping[str, Any]) -> None:
        digest = _payload_digest(payload)
        self._seen_ops[operation_id] = (digest, dict(response))
        self._tombstones.setdefault(operation_id, digest)
        while len(self._seen_ops) > _SEEN_OPS_CAP:
            self._seen_ops.pop(next(iter(self._seen_ops)))

    def _owned(self, lease_id: str) -> QuantumNodeLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            if lease_id in self._released_ids:
                raise QuantumNodeError(409, "already_released", "lease was already released")
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
                lease_id = _mint_lease_id(resource_id)
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
            elif isinstance(gate, str) and gate in _GATES:
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
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be finite")
                try:
                    number = float(value)
                except OverflowError:
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be finite") from None
                if not math.isfinite(number):
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be finite")
                if number <= 0.0:
                    raise QuantumNodeError(400, "invalid_branches", f"branch_probabilities[{pos}] must be positive")
                probs.append(number)
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
            # Randomness is drawn here, after authentication, replay lookup,
            # and lease checks, so a replayed measurement returns the saved
            # acknowledgement without consuming another draw.
            if branch_probabilities is not None and branch_bits is not None:
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
        payload = {
            "action": "stage_conditional_state",
            "lease_id": lease_id,
            "session_id": session_id,
            "rho_matrix": [[[cell.real, cell.imag] for cell in row] for row in rows],
        }
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
                response = {**stored["response"], "acknowledgement": f"ack-{operation_id}"}
                self._remember(operation_id, payload, response)
                return response
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
            replay = self._idempotency(operation_id, payload, "release")
            if replay is not None:
                return replay
            for lease_id in lease_ids:
                # Raises unknown_lease (404) or already_released (409); the
                # released-ID set preserves the finished-lease signal after
                # the full record is reclaimed below.
                self._owned(lease_id)
            for lease_id in lease_ids:
                del self._leases[lease_id]
                self._released_ids.add(lease_id)
                for key in [key for key in self._corrections if key[1] == lease_id]:
                    del self._corrections[key]
            response = {"ok": True, "active_count": self._active_count()}
            self._remember(operation_id, payload, response)
            return response

    async def inspect(
        self, *, token: str, node: str, instance: str | None = None,
        lease_offset: int = 0, lease_limit: int = 64,
        resource_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Discover identity or inspect a bounded, optionally pinned lease page.

        Counts and offsets refer to the resource-filtered records. Pages are
        snapshots, not terminal proof that an in-flight reservation is absent.
        """
        self._auth(token, node, self.instance_id if instance in (None, "") else instance)
        if isinstance(lease_offset, bool) or not isinstance(lease_offset, int) or lease_offset < 0:
            raise QuantumNodeError(400, "invalid_offset", "lease_offset must be a nonnegative integer")
        if isinstance(lease_limit, bool) or not isinstance(lease_limit, int) or not 1 <= lease_limit <= 64:
            raise QuantumNodeError(400, "invalid_limit", "lease_limit must be an integer in 1..64")
        resources = None
        if resource_ids is not None:
            if not isinstance(resource_ids, list) or len(resource_ids) > MAX_LEASES_PER_OP:
                raise QuantumNodeError(400, "invalid_resources", "resource_ids must list at most 4 unique IDs")
            resources = {_check_id(value, "resource_id") for value in resource_ids}
            if len(resources) != len(resource_ids):
                raise QuantumNodeError(400, "invalid_resources", "resource_ids must be unique")
        async with self._lock:
            leases = []
            lease_count = 0
            for lease in self._leases.values():
                if resources is not None and lease.resource_id not in resources:
                    continue
                if lease_offset <= lease_count < lease_offset + lease_limit:
                    leases.append(lease.public())
                lease_count += 1
            next_offset = lease_offset + len(leases)
            return {
                "ok": True,
                "node_id": self.node_id,
                "instance_id": self.instance_id,
                "capacity": self.capacity,
                "active_count": self._active_count(),
                "leases": leases,
                "lease_count": lease_count,
                "lease_offset": lease_offset,
                "lease_limit": lease_limit,
                "next_offset": next_offset if next_offset < lease_count else None,
            }

    # -- QKD sessions (fixed qkd_step/qkd_owner contract; same auth/replay) --
    #
    # Eleven coordinator actions run under ``qkd_step`` with explicit branch
    # dispatch; two owner-private actions run under ``qkd_owner``. The owner
    # is the authenticated node identity bound at ``begin`` (never a body
    # field). Role, session, original-instance, stage, and replay checks all
    # precede worker-local RNG draws and record mutation inside the lock.
    # Private draws (bits, bases, outcomes, blinding, Toeplitz seeds for
    # Alice's own tag/extraction) use this worker's RNG only; the
    # coordinator never supplies a private draw and Alice's candidate is
    # never copied into Bob. Toeplitz seeds are public randomness: Alice
    # generates one fresh seed per tag/extraction operation and the engine
    # transports that SAME seed to Bob, who hashes his own candidate.

    def _qkd_session(self, session_id: str) -> _QKDRecord:
        record = self._qkd.get(session_id)
        if record is None:
            raise QuantumNodeError(404, "unknown_session", "no QKD session bound on this worker")
        return record

    def _qkd_nonterminal_count(self) -> int:
        return sum(1 for record in self._qkd.values() if not record.terminal)

    def _qkd_reap_terminals(self) -> None:
        """Reclaim oldest terminal compacts past the retention bound."""
        terminal = [key for key, record in self._qkd.items() if record.terminal]
        for key in terminal[: max(0, len(terminal) - _QKD_TERMINAL_CAP)]:
            del self._qkd[key]

    @staticmethod
    def _qkd_compact(record: _QKDRecord) -> None:
        """Reduce a terminal record to compact replay: counts and flags only."""
        record.final_key_length = len(record.key_bits)
        record.final_phase_length = len(record.phase_bits)
        record.e91_round_count = len(record.e91_rounds)
        record.raw_bits = []
        record.raw_bases = []
        record.key_bits = []
        record.phase_bits = []
        record.e91_rounds = []
        record.key = None
        record.blinding = None
        record.capability = None
        record.commitment_hex = None

    @staticmethod
    def _qkd_check_binding(record: _QKDRecord, node: str, instance: str) -> None:
        if record.owner != node:
            raise QuantumNodeError(403, "wrong_owner", "QKD session is not owned by this node")
        if record.bound_instance != instance:
            raise QuantumNodeError(409, "stale_instance", "QKD session is bound to another worker instance")

    @staticmethod
    def _qkd_exact_fields(payload: Mapping[str, Any], action: str, required: set[str], allowed: set[str]) -> None:
        keys = set(payload)
        if not required <= keys <= allowed:
            raise QuantumNodeError(400, "invalid_payload", f"{action} payload fields are not allowlisted")

    def _qkd_check_payload(self, action: str, payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate one qkd_step payload; return (replay digest, decoded ctx).

        Strict codecs only (section 3). The digest covers the raw validated
        DTOs so any changed field under a reused operation ID conflicts.
        """
        if action == "begin":
            self._qkd_exact_fields(payload, action, {"protocol", "role", "peer"}, {"protocol", "role", "peer"})
            protocol, role = payload["protocol"], payload["role"]
            if protocol not in ("BB84", "E91"):
                raise QuantumNodeError(400, "invalid_protocol", "protocol must be BB84 or E91")
            if role not in ("alice", "bob"):
                raise QuantumNodeError(400, "invalid_role", "role must be alice or bob")
            peer = _check_node(payload["peer"], "peer")
            digest = {"action": action, "protocol": protocol, "role": role, "peer": peer}
            return digest, {"protocol": protocol, "role": role, "peer": peer}
        if action == "prepare_bb84":
            self._qkd_exact_fields(payload, action, {"count"}, {"count"})
            count = payload["count"]
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_QKD_UNITS:
                raise QuantumNodeError(400, "invalid_count", "count must be an integer in 0..20000")
            return {"action": action, "count": count}, {"count": count}
        if action == "measure_bb84":
            self._qkd_exact_fields(payload, action, {"signals"}, {"signals", "channel_basis_policy"})
            signals = decode_signals(payload["signals"], "signals")
            if not 0 < len(signals) <= MAX_QKD_UNITS:
                raise QuantumNodeError(400, "invalid_signal", "signals must hold 1..20000 entries")
            policy = payload.get("channel_basis_policy")
            if policy is not None and policy != "Z/X-uniform":
                raise QuantumNodeError(400, "invalid_policy", "channel_basis_policy must be Z/X-uniform")
            digest = {"action": action, "signals": payload["signals"], "channel_basis_policy": policy}
            return digest, {"signals": signals, "policy": policy}
        if action == "adopt_indices":
            self._qkd_exact_fields(payload, action, {"keep", "phase"}, {"keep", "phase"})
            keep = decode_indices(payload["keep"], "keep")
            phase = decode_indices(payload["phase"], "phase")
            if set(keep) & set(phase):
                raise QuantumNodeError(400, "invalid_index", "keep and phase indices must be disjoint")
            if len(keep) + len(phase) > MAX_QKD_UNITS:
                raise QuantumNodeError(400, "invalid_index", "keep and phase hold at most 20000 indices")
            digest = {"action": action, "keep": payload["keep"], "phase": payload["phase"]}
            return digest, {"keep": keep, "phase": phase}
        if action == "measure_e91":
            self._qkd_exact_fields(
                payload, action,
                {"round_index", "pair_id", "lease_id", "setting", "state"},
                {"round_index", "pair_id", "lease_id", "setting", "state"},
            )
            round_index = payload["round_index"]
            if isinstance(round_index, bool) or not isinstance(round_index, int) or not 0 <= round_index < _MAX_E91_ROUNDS:
                raise QuantumNodeError(400, "invalid_round", "round_index must be an integer in 0..19999")
            pair_id = _check_id(payload["pair_id"], "pair_id")
            lease_id = _check_id(payload["lease_id"], "lease_id")
            setting = payload["setting"]
            if isinstance(setting, bool) or setting not in (0, 1):
                raise QuantumNodeError(400, "invalid_setting", "setting must be 0 (Z) or 1 (X)")
            state = payload["state"]
            if not isinstance(state, dict) or state.get("encoding") != "density-v1":
                raise QuantumNodeError(400, "invalid_codec", "state must use encoding density-v1")
            qubits = state.get("qubits")
            if isinstance(qubits, bool) or qubits not in (1, 2):
                raise QuantumNodeError(400, "invalid_state", "state must be a 1- or 2-qubit density")
            density = decode_density(state, "state", qubits=int(qubits))
            digest = {
                "action": action, "round_index": round_index, "pair_id": pair_id,
                "lease_id": lease_id, "setting": int(setting), "state": state,
            }
            return digest, {
                "round_index": round_index, "pair_id": pair_id, "lease_id": lease_id,
                "setting": int(setting), "density": density,
            }
        if action == "lengths":
            self._qkd_exact_fields(payload, action, set(), set())
            return {"action": action}, {}
        if action == "syndrome":
            self._qkd_exact_fields(payload, action, {"order"}, {"order"})
            order = decode_indices(payload["order"], "order")
            return {"action": action, "order": payload["order"]}, {"order": order}
        if action == "correct":
            self._qkd_exact_fields(payload, action, {"order", "syndrome"}, {"order", "syndrome"})
            order = decode_indices(payload["order"], "order")
            syndrome = decode_bits(payload["syndrome"], "syndrome")
            digest = {"action": action, "order": payload["order"], "syndrome": payload["syndrome"]}
            return digest, {"order": order, "syndrome": syndrome}
        if action == "tag":
            self._qkd_exact_fields(payload, action, {"seed"}, {"seed"})
            seed = payload["seed"]
            if seed is not None:
                seed = decode_bits(seed, "seed")
            return {"action": action, "seed": payload["seed"]}, {"seed": seed}
        if action == "extract":
            self._qkd_exact_fields(payload, action, {"output_length", "seed"}, {"output_length", "seed"})
            ell = payload["output_length"]
            if isinstance(ell, bool) or not isinstance(ell, int) or not 128 <= ell <= 256 or ell % 8:
                raise QuantumNodeError(400, "invalid_extract_length", "output_length must be byte-aligned in 128..256")
            seed = payload["seed"]
            if seed is not None:
                seed = decode_bits(seed, "seed")
            return {"action": action, "output_length": int(ell), "seed": payload["seed"]}, {
                "output_length": int(ell), "seed": seed,
            }
        if action == "abort":
            self._qkd_exact_fields(payload, action, {"reason"}, {"reason"})
            reason = payload["reason"]
            if reason not in QKD_ABORT_REASONS:
                raise QuantumNodeError(400, "invalid_reason", "abort reason is not allowlisted")
            return {"action": action, "reason": reason}, {"reason": reason}
        raise QuantumNodeError(400, "unknown_action", "qkd_step action is not allowlisted")

    async def qkd_step(
        self,
        *,
        operation_id: str,
        session_id: str,
        action: str,
        payload: Mapping[str, Any],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Fixed coordinator QKD dispatcher: allowlisted actions, auth first.

        Authentication and action/payload validation precede the worker lock;
        role/session/instance/stage/replay checks and one-shot guards precede
        every worker-local draw inside the lock. ``lengths`` is readonly
        (deadline semantics, never enters the replay gate).
        """
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        if not isinstance(action, str) or action not in QKD_STEP_ACTIONS:
            raise QuantumNodeError(400, "unknown_action", "qkd_step action is not allowlisted")
        if not isinstance(payload, dict):
            raise QuantumNodeError(400, "invalid_payload", "qkd_step payload must be an object")
        if action == "lengths":
            self._qkd_check_payload(action, payload)
            async with self._lock:
                record = self._qkd_session(session_id)
                self._qkd_check_binding(record, node, instance)
                key_length, phase_length = len(record.key_bits), len(record.phase_bits)
                return {
                    "ok": True,
                    "key_length": key_length,
                    "phase_length": phase_length,
                    "key_available": record.available and not record.terminal,
                    "state": record.state,
                }
        digest, ctx = self._qkd_check_payload(action, payload)
        digest = {"session_id": session_id, **digest}
        admission = "abort" if action == "abort" else "effect"
        async with self._lock:
            replay = self._idempotency(operation_id, digest, admission)
            if replay is not None:
                return replay
            if action == "begin":
                response = self._qkd_begin(session_id, ctx, node, instance)
            else:
                record = self._qkd_session(session_id)
                self._qkd_check_binding(record, node, instance)
                if action == "prepare_bb84":
                    response = self._qkd_prepare_bb84(record, ctx)
                elif action == "measure_bb84":
                    response = self._qkd_measure_bb84(record, ctx)
                elif action == "adopt_indices":
                    response = self._qkd_adopt_indices(record, ctx)
                elif action == "measure_e91":
                    response = self._qkd_measure_e91(record, ctx)
                elif action == "syndrome":
                    response = self._qkd_syndrome(record, ctx)
                elif action == "correct":
                    response = self._qkd_correct(record, ctx)
                elif action == "tag":
                    response = self._qkd_tag(record, ctx)
                elif action == "extract":
                    response = self._qkd_extract(record, ctx)
                elif action == "abort":
                    response = self._qkd_abort(record, ctx)
                else:  # pragma: no cover - allowlist exhaustive
                    raise QuantumNodeError(400, "unknown_action", "qkd_step action is not allowlisted")
            self._remember(operation_id, digest, response)
            return response

    def _qkd_begin(self, session_id: str, ctx: Mapping[str, Any], node: str, instance: str) -> dict[str, Any]:
        """Bind protocol/role/peer with the owner derived from the credential."""
        protocol, role, peer = ctx["protocol"], ctx["role"], ctx["peer"]
        existing = self._qkd.get(session_id)
        if existing is not None:
            if (
                existing.protocol, existing.role, existing.peer,
                existing.owner, existing.bound_instance,
            ) != (protocol, role, peer, node, instance):
                raise QuantumNodeError(409, "session_conflict", "QKD session already bound differently")
            return {"ok": True, "session_id": session_id}
        if self._qkd_nonterminal_count() >= MAX_QKD_SESSIONS:
            raise QuantumNodeError(409, "qkd_capacity", "worker holds 64 nonterminal QKD records")
        self._qkd[session_id] = _QKDRecord(
            session_id=session_id, protocol=protocol, role=role, peer=peer,
            owner=node, bound_instance=instance, steps=["begin"],
        )
        return {"ok": True, "session_id": session_id}

    @staticmethod
    def _qkd_require_live(record: _QKDRecord) -> None:
        if record.used:
            raise QuantumNodeError(409, "already_used", "key capability was already consumed")
        if record.aborted:
            raise QuantumNodeError(409, "already_aborted", "QKD session was already aborted")

    @staticmethod
    def _qkd_require_role(record: _QKDRecord, role: str, detail: str) -> None:
        if record.role != role:
            raise QuantumNodeError(403, "wrong_role", detail)

    @staticmethod
    def _qkd_require_protocol(record: _QKDRecord, protocol: str) -> None:
        if record.protocol != protocol:
            raise QuantumNodeError(409, "protocol_mismatch", f"QKD session runs {record.protocol}")

    @staticmethod
    def _qkd_require_once(record: _QKDRecord, marker: str, detail: str) -> None:
        if marker in record.steps:
            raise QuantumNodeError(409, "session_step", detail)

    @staticmethod
    def _qkd_draw(random_draw: object) -> float:
        if isinstance(random_draw, bool) or not isinstance(random_draw, (int, float)):
            raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw")
        try:
            value = float(random_draw)
        except (OverflowError, ValueError) as exc:
            raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw") from exc
        if not 0.0 <= value < 1.0:
            raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw")
        return value

    def _qkd_random(self) -> float:
        try:
            draw = self._rng.random()
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise QuantumNodeError(503, "rng_failure", "worker RNG failed to produce a draw") from exc
        return self._qkd_draw(draw)

    def _qkd_prepare_bb84(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Alice draws private bits/bases; signals and preparing bases reply."""
        self._qkd_require_live(record)
        self._qkd_require_role(record, "alice", "only the sending node prepares BB84 signals")
        self._qkd_require_protocol(record, "BB84")
        self._qkd_require_once(record, "prepare_bb84", "BB84 signals were already prepared")
        count = ctx["count"]
        raw_bits: list[int] = []
        raw_bases: list[str] = []
        signals: list[int] = []
        for _ in range(count):
            bit = 1 if self._qkd_random() < 0.5 else 0
            basis = "+" if self._qkd_random() < 0.5 else "x"
            raw_bits.append(bit)
            raw_bases.append(str(basis))
            signals.append(bit + (0 if basis == "+" else 2))
        record.raw_bits = raw_bits
        record.raw_bases = raw_bases
        record.steps.append("prepare_bb84")
        return {
            "ok": True,
            "signals": encode_signals(signals),
            "bases": encode_bits([0 if b == "+" else 1 for b in raw_bases]),
        }

    def _qkd_measure_bb84(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Bob draws private bases, measures the channel, keeps only outcomes."""
        self._qkd_require_live(record)
        self._qkd_require_role(record, "bob", "only the receiving node measures BB84 signals")
        self._qkd_require_protocol(record, "BB84")
        self._qkd_require_once(record, "measure_bb84", "BB84 signals were already measured")
        measured: list[int] = []
        measured_bases: list[str] = []
        for value in ctx["signals"]:
            bit, ensemble = value & 1, "+" if value < 2 else "x"
            basis = "+" if self._qkd_random() < 0.5 else "x"
            state = bb84_state(bit, ensemble)
            probed = state.apply_single(H, 0) if basis == "x" else state
            try:
                outcome = int(probed.density().measure_z((0,), self._rng).bits[0])
            except (TypeError, ValueError) as exc:
                raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw") from exc
            if outcome not in (0, 1):
                raise QuantumNodeError(503, "rng_failure", "measurement did not yield a bit")
            measured.append(outcome)
            measured_bases.append(str(basis))
        record.raw_bits = measured
        record.raw_bases = measured_bases
        record.steps.append("measure_bb84")
        return {
            "ok": True,
            "bases": encode_bits([0 if b == "+" else 1 for b in measured_bases]),
            "count": len(measured),
        }

    def _qkd_adopt_indices(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Split raw bits into a private candidate and a public phase sample.

        BB84 endpoints index their own raw draw; disclosed phase bits leave
        the candidate. E91 key rounds land directly in the candidate, so an
        E91 ``adopt`` carries empty lists and only finalizes candidacy.
        """
        self._qkd_require_live(record)
        self._qkd_require_once(record, "adopt_indices", "this session was already sifted")
        keep, phase = ctx["keep"], ctx["phase"]
        if record.protocol == "E91":
            if keep or phase:
                raise QuantumNodeError(400, "invalid_index", "E91 rounds need no raw-bit indices")
            if not record.e91_rounds:
                raise QuantumNodeError(409, "insufficient_sample", "no E91 key rounds recorded")
        else:
            marker = "prepare_bb84" if record.role == "alice" else "measure_bb84"
            if marker not in record.steps:
                raise QuantumNodeError(409, "session_step", "no raw BB84 draw to sift yet")
            bound = len(record.raw_bits)
            for name, indices in (("keep", keep), ("phase", phase)):
                for pos, value in enumerate(indices):
                    if value >= bound:
                        raise QuantumNodeError(400, "invalid_index", f"{name}[{pos}] is outside the raw draw")
            record.key_bits = [record.raw_bits[i] for i in keep]
            record.phase_bits = [record.raw_bits[i] for i in phase]
            record.raw_bits = []
            record.raw_bases = []
        disclosed = list(record.phase_bits)
        record.steps.append("adopt_indices")
        return {"ok": True, "key_length": len(record.key_bits), "phase_sample": encode_bits(disclosed)}

    def _qkd_measure_e91(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Single private E91 key round: Alice keeps her click and returns
        only Bob's conditional one-qubit density; Bob measures that
        conditional with his own worker RNG and keeps only his click.

        Lease, session, role, pair, ordered-round, and original-instance
        scope are all validated. There is no joint coordinator sampler and
        no candidate bit ever crosses the wire. Each endpoint consumes one
        owned lease per round through sole-authority lifecycle.
        """
        self._qkd_require_live(record)
        self._qkd_require_protocol(record, "E91")
        for marker in ("adopt_indices", "syndrome", "correct", "tag", "extract"):
            if marker in record.steps:
                raise QuantumNodeError(409, "session_step", "E91 key rounds are closed for this session")
        expected = len(record.e91_rounds)
        round_index = ctx["round_index"]
        if round_index < expected:
            raise QuantumNodeError(409, "stale_round", "E91 round was already recorded")
        if round_index > expected:
            raise QuantumNodeError(409, "future_round", "E91 rounds must arrive in order")
        pair_id = ctx["pair_id"]
        if any(entry["pair"] == pair_id for entry in record.e91_rounds):
            raise QuantumNodeError(409, "duplicate_round", "E91 pair is already spent in this session")
        lease = self._owned(ctx["lease_id"])
        if lease.state not in ("active", "staged"):
            raise QuantumNodeError(409, "lease_unavailable", "E91 round needs an unconsumed owned lease")
        density = ctx["density"]
        alice_side = record.role == "alice"
        if alice_side != (density.qubits == 2):
            raise QuantumNodeError(
                400, "invalid_state",
                "alice takes the joint pair density; bob takes the conditional density",
            )
        setting = ctx["setting"]
        try:
            rotated = density.apply_single(H, 0) if setting == 1 else density
            branch = rotated.measure_z((0,), self._rng)
        except (TypeError, ValueError) as exc:
            raise QuantumNodeError(503, "rng_failure", "worker RNG produced an out-of-range draw") from exc
        click = int(branch.bits[0])
        if click not in (0, 1):
            raise QuantumNodeError(503, "rng_failure", "measurement did not yield a bit")
        record.key_bits.append(click)
        record.e91_rounds.append({"round": round_index, "pair": pair_id})
        lease.state = "measured"
        lease.rho = None
        if alice_side:
            conditional = branch.state.partial_trace((1,))
            return {
                "ok": True,
                "round_index": round_index,
                "pair_id": pair_id,
                "conditional": encode_density(conditional),
            }
        return {"ok": True, "round_index": round_index, "pair_id": pair_id, "count": len(record.key_bits)}

    def _qkd_syndrome(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Alice announces public Hamming syndromes; the bits stay private."""
        self._qkd_require_live(record)
        self._qkd_require_role(record, "alice", "only the sending node announces the syndrome")
        if "adopt_indices" not in record.steps:
            raise QuantumNodeError(409, "session_step", "no candidate key to reconcile yet")
        self._qkd_require_once(record, "syndrome", "syndrome was already announced")
        n = len(record.key_bits)
        if n == 0:
            raise QuantumNodeError(409, "insufficient_sample", "candidate key is empty")
        order = ctx["order"]
        if len(order) != n or set(order) != set(range(n)):
            raise QuantumNodeError(400, "invalid_order", "order must permute the candidate positions")
        try:
            syndromes, total = syndrome_blocks(record.key_bits, list(order))
        except (ReconciliationFailed, ValueError) as exc:
            raise QuantumNodeError(400, "invalid_syndrome", "syndrome inputs were rejected") from exc
        record.syndrome_len = total
        record.steps.append("syndrome")
        return {
            "ok": True,
            "syndrome": encode_bits(_syndrome_ints_to_bits(syndromes, n)),
            "leaked": total,
        }

    def _qkd_correct(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Bob applies the public syndrome to his own candidate string."""
        self._qkd_require_live(record)
        self._qkd_require_role(record, "bob", "only the receiving node applies the syndrome")
        if "adopt_indices" not in record.steps:
            raise QuantumNodeError(409, "session_step", "no candidate key to reconcile yet")
        self._qkd_require_once(record, "correct", "syndrome was already applied")
        n = len(record.key_bits)
        if n == 0:
            raise QuantumNodeError(409, "insufficient_sample", "candidate key is empty")
        order = ctx["order"]
        if len(order) != n or set(order) != set(range(n)):
            raise QuantumNodeError(400, "invalid_order", "order must permute the candidate positions")
        try:
            announced = _syndrome_bits_to_ints(ctx["syndrome"], n)
            corrected, corrections = correct_blocks(record.key_bits, list(order), list(announced))
        except (ReconciliationFailed, ValueError) as exc:
            raise QuantumNodeError(400, "invalid_syndrome", "syndrome inputs were rejected") from exc
        record.key_bits = list(corrected)
        record.corrections = corrections
        record.steps.append("correct")
        return {"ok": True, "corrected_count": corrections, "leaked": len(ctx["syndrome"])}

    def _qkd_tag(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """32-bit Toeplitz verification tag over this endpoint's candidate.

        Alice generates ONE fresh public seed for this operation with her
        worker RNG; Bob receives that SAME seed from the controller and
        hashes his own candidate. Seeds are independent between tag and
        extraction and independent of the candidates.
        """
        self._qkd_require_live(record)
        if record.role == "alice":
            if "syndrome" not in record.steps:
                raise QuantumNodeError(409, "session_step", "announce the syndrome before tagging")
        elif "correct" not in record.steps:
            raise QuantumNodeError(409, "session_step", "apply the syndrome before tagging")
        self._qkd_require_once(record, "tag", "verification tag was already produced")
        n = len(record.key_bits)
        if n == 0:
            raise QuantumNodeError(409, "insufficient_sample", "candidate key is empty")
        seed = ctx["seed"]
        if record.role == "alice":
            if seed is not None:
                raise QuantumNodeError(400, "invalid_seed", "alice generates the tag seed")
            seed = tuple(random_bits(self._rng, n + 31))
        elif seed is None or len(seed) != n + 31:
            raise QuantumNodeError(400, "invalid_seed", "tag seed must hold key_length+31 bits")
        try:
            tag = toeplitz_hash(seed, record.key_bits, 32)
        except ValueError as exc:
            raise QuantumNodeError(400, "invalid_tag", "verification seed was rejected") from exc
        record.steps.append("tag")
        return {"ok": True, "seed": encode_bits(seed), "tag": encode_bits(tag)}

    def _qkd_extract(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Extract locally: public seed, blinded commitment, length only.

        Same public-seed discipline as ``tag``. Per-endpoint blinding is
        drawn with this worker's RNG and never exchanged. The key,
        blinding, and capability stay in this vault until owner ``use``.
        """
        self._qkd_require_live(record)
        if "tag" not in record.steps:
            raise QuantumNodeError(409, "session_step", "verify the tag before extraction")
        self._qkd_require_once(record, "extract", "key was already extracted")
        n = len(record.key_bits)
        if n == 0:
            raise QuantumNodeError(409, "insufficient_sample", "candidate key is empty")
        ell = ctx["output_length"]
        seed = ctx["seed"]
        if record.role == "alice":
            if seed is not None:
                raise QuantumNodeError(400, "invalid_seed", "alice generates the extraction seed")
            seed = tuple(random_bits(self._rng, n + ell - 1))
        elif seed is None or len(seed) != n + ell - 1:
            raise QuantumNodeError(400, "invalid_seed", "extraction seed must hold key_length+ell-1 bits")
        try:
            key = toeplitz_extract(seed, record.key_bits)
            blinding = random_bytes(self._rng, 32)
            commitment = node_commitment(self.node_id, record.session_id, blinding, key)
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
        record.raw_bases = []
        record.phase_bits = []
        record.steps.append("extract")
        return {
            "ok": True,
            "seed": encode_bits(seed),
            "commitment": commitment,
            "output_length": ell,
        }

    def _qkd_abort(self, record: _QKDRecord, ctx: Mapping[str, Any]) -> dict[str, Any]:
        """Destroy session availability; buffers compacted, replay retained."""
        self._qkd_require_live(record)
        record.aborted = True
        record.abort_reason = ctx["reason"]
        record.available = False
        self._qkd_compact(record)
        record.steps.append("abort")
        self._qkd_reap_terminals()
        return {"ok": True, "session_id": record.session_id, "state": "aborted"}

    async def qkd_owner(
        self,
        *,
        operation_id: str,
        session_id: str,
        action: str,
        payload: Mapping[str, Any],
        token: str,
        node: str,
        instance: str,
    ) -> dict[str, Any]:
        """Private owning-node path: ``capability`` retrieval and one-shot ``use``.

        The owner is derived from the authenticated node identity, never a
        body field, and the gateway never proxies this path. Terminal scope
        is checked before cached capability replies so finished sessions
        never re-serve private material. ``use`` binds the replay digest to
        a stable hash of the capability (never the raw value), destroys
        raw/candidate/key/blinding/capability buffers one-shot, and returns
        the public outcome/commitment only.
        """
        operation_id = _check_id(operation_id, "operation_id")
        session_id = _check_id(session_id, "session_id")
        self._auth(token, node, instance)
        if not isinstance(action, str) or action not in QKD_OWNER_ACTIONS:
            raise QuantumNodeError(400, "unknown_action", "qkd_owner action is not allowlisted")
        if not isinstance(payload, dict):
            raise QuantumNodeError(400, "invalid_payload", "qkd_owner payload must be an object")
        async with self._lock:
            record = self._qkd_session(session_id)
            self._qkd_check_binding(record, node, instance)
            if action == "capability":
                self._qkd_exact_fields(payload, action, set(), set())
                # Stable readonly retrieval: the capability value is fixed
                # at extraction, so re-reads need no replay gate and stay
                # available at history saturation. Terminal scope is still
                # checked first so finished sessions never re-serve it.
                if record.used:
                    raise QuantumNodeError(409, "already_used", "key capability was already consumed")
                if record.aborted:
                    raise QuantumNodeError(409, "already_aborted", "QKD session was already aborted")
                if not record.available or record.key is None or record.capability is None:
                    raise QuantumNodeError(409, "key_unavailable", "no agreed key is available for this session")
                return {"ok": True, "session_id": session_id, "capability": record.capability}
            self._qkd_exact_fields(payload, action, {"operation", "capability"}, {"operation", "capability"})
            operation = payload["operation"]
            if operation not in QKD_USE_OPERATIONS:
                raise QuantumNodeError(400, "invalid_operation", "use operation is not allowlisted")
            presented = payload["capability"]
            if not isinstance(presented, str) or not presented:
                raise QuantumNodeError(400, "invalid_capability", "capability must be a non-empty string")
            cap_hash = hashlib.sha256(presented.encode()).hexdigest()
            digest = {
                "action": "use", "session_id": session_id,
                "operation": operation, "capability_sha256": cap_hash,
            }
            replay = self._idempotency(operation_id, digest, "use_key")
            if replay is not None:
                return replay
            if record.used:
                raise QuantumNodeError(409, "already_used", "key capability was already consumed")
            if record.aborted:
                raise QuantumNodeError(409, "already_aborted", "QKD session was already aborted")
            if not record.available or record.key is None or record.capability is None:
                raise QuantumNodeError(409, "key_unavailable", "no agreed key is available for this session")
            if not hmac.compare_digest(presented.encode(), record.capability.encode()):
                raise QuantumNodeError(403, "wrong_capability", "key capability does not match")
            commitment = record.commitment_hex
            record.used = True
            self._qkd_compact(record)
            record.steps.append("use")
            self._qkd_reap_terminals()
            response = {"ok": True, "outcome": "accepted", "operation": operation, "commitment": commitment}
            self._remember(operation_id, digest, response)
            return response


# -- Starlette worker app --------------------------------------------------

def create_node_app(worker: QuantumNodeWorker):  # type: ignore[no-untyped-def]
    """Build the fixed-path Starlette app serving one worker's command set."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _body(request: Request) -> Any:
        # Streamed 64 KiB cap: stop reading once the limit is exceeded
        # instead of buffering an unbounded body first.
        total = 0
        chunks: list[bytes] = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_BODY_BYTES:
                raise QuantumNodeError(413, "body_too_large", "request body exceeds 64 KiB")
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise QuantumNodeError(400, "invalid_json", "request body is not valid JSON") from exc

    def _creds(request: Request) -> str:
        return parse_bearer(request.headers.get("authorization", ""))

    def _pre_auth(request: Request) -> str:
        # Bearer check before any body buffering: unauthenticated bulk
        # senders are rejected without reading their bytes. Node/instance
        # scope is still enforced per command inside the worker.
        presented = _creds(request)
        if not presented or not hmac.compare_digest(presented.encode(), worker._token.encode()):
            raise QuantumNodeError(401, "unauthenticated", "invalid worker credential")
        return presented


    def _handler(action: str):  # type: ignore[no-untyped-def]
        async def handle(request: Request):  # type: ignore[no-untyped-def]
            try:
                token = _pre_auth(request)
                body = await _body(request)
                if not isinstance(body, dict):
                    raise QuantumNodeError(400, "invalid_json", "request body must be a JSON object")
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
                    result = await worker.inspect(
                        token=token, node=node, instance=instance,
                        lease_offset=body.get("lease_offset", 0),
                        lease_limit=body.get("lease_limit", 64),
                        resource_ids=body.get("resource_ids"),
                    )
                elif action in ("qkd_step", "qkd_owner"):
                    # Fixed QKD envelopes carry no credential, owner, URL,
                    # RNG, capability, blinding, or key material: unknown or
                    # forbidden top-level fields are 400, never ignored.
                    allowed = {"node", "instance", "operation_id", "session_id", "action", "payload"}
                    forbidden = {
                        "token", "owner", "url", "rng", "capability",
                        "blinding", "key", "key_bytes", "key_bits",
                    }
                    if not isinstance(body, dict) or not set(body) <= allowed:
                        raise QuantumNodeError(400, "invalid_envelope", "qkd envelope fields are not allowlisted")
                    if set(body) & forbidden:
                        raise QuantumNodeError(400, "invalid_envelope", "qkd envelope carries a forbidden field")
                    if action == "qkd_step":
                        result = await worker.qkd_step(
                            operation_id=operation_id,
                            session_id=body.get("session_id", ""),
                            action=body.get("action", ""),
                            payload=body.get("payload", {}),
                            token=token,
                            node=node,
                            instance=instance,
                        )
                    else:
                        result = await worker.qkd_owner(
                            operation_id=operation_id,
                            session_id=body.get("session_id", ""),
                            action=body.get("action", ""),
                            payload=body.get("payload", {}),
                            token=token,
                            node=node,
                            instance=instance,
                        )
                else:  # pragma: no cover - fixed action table
                    raise QuantumNodeError(404, "unknown_action", "unknown worker action")
                # Measured reply cap: actual serialized bytes, never truncated.
                if len(json.dumps(result).encode("utf-8")) > MAX_BODY_BYTES:
                    raise QuantumNodeError(500, "reply_too_large", "worker reply exceeds 64 KiB")
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
