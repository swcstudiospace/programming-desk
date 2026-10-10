"""Durable append-only Merkle receipt ledger for quantum teleportation executions.

Faithful *distributed classical numerical simulator* record-keeping. This module
makes no physical, device-independent, or secrecy claim: it durably commits
public simulator events, binds them into a binary Merkle tree, and serves
frozen inclusion proofs. Private key material must never reach this module;
:func:`append_event` rejects it at admission.

Trust model: hash linkage plus SQLite triggers detect accidental or partial
tampering, not an administrator replacing the whole file and recomputing every
hash. Previously published prefix roots (e.g. Devnet-anchored roots) are the
external checkpoint against privileged rollback. There is no destructive
rollback API here on purpose.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import sqlite3
import stat
import struct
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


LEDGER_VERSION = 1
DB_FILENAME = "quantum_teleportation.sqlite3"

EMPTY_ROOT_HEX = hashlib.sha256(b"QTELEPORT/empty-root/v1").hexdigest()
GENESIS_PREDECESSOR_HEX = "00" * 32

TELEPORT_LEAF_SIZE = 71
DRILL_LEAF_SIZE = 150
EXEC_LEAF_VERSION = 1
LEAF_TYPE_TELEPORT = 1
LEAF_TYPE_DRILL = 2

MAX_EVENT_TYPE_LEN = 128
MAX_SESSION_ID_LEN = 256
MAX_ACTOR_LEN = 256
MAX_ID_LIST = 64
MAX_ID_LEN = 256
MAX_OUTCOME_LEN = 64
MAX_STRING_VALUE_LEN = 4096
MAX_CANONICAL_BYTES = 65536

_SQLITE_INT_MAX = (1 << 63) - 1

_TOP_LEVEL_FIELDS = (
    "event_type",
    "session_id",
    "actor",
    "nodes",
    "resources",
    "outcome",
    "payload",
)

# Exact public key names that must never enter the ledger. Count/commitment
# aggregates (sifted_count, key_commitment_hex, key_agreement, output_bits,
# test_count, error_count) are intentionally NOT on this list.
_FORBIDDEN_EXACT = frozenset(
    {
        "raw_key",
        "sifted_key",
        "sifted_bits",
        "key_bytes",
        "key_hex",
        "secret",
        "secret_key",
        "private_key",
        "private_seed",
        "shared_key",
        "shared_secret",
        "final_shared_key",
        "final_shared_key_hex",
        "clean_key",
        "clean_key_hex",
        "candidate_bits",
        "private_bits",
        "raw_bits",
        "seed_bytes",
        "blinding",
        "blinding_factor",
        "private_blinding",
        "private_blind",
        "capability",
        "capabilities",
        "bearer",
        "bearer_token",
        "signer",
        "signer_key",
        "signer_bytes",
        "password",
        "auth_token",
        "key_material",
        "key_prefix",
        "seed_phrase",
        "mnemonic",
    }
)

# Substring scan over key names (lowercased). Deliberately narrow so that
# legitimate aggregate fields such as key_commitment_hex, key_agreement,
# sifted_count, output_bits, test_count pass untouched.
_FORBIDDEN_SUBSTR = ("blinding", "blinded", "bearer", "signer", "secret", "passwd")


class LedgerError(Exception):
    """Base class for ledger failures."""


class LedgerCorruptError(LedgerError):
    """Stored state failed replay/integrity; the ledger refuses to open/operate."""


class LedgerClosedError(LedgerError):
    """Operation attempted on a closed ledger."""


@dataclass(frozen=True)
class QuantumQKDReceipt:
    receipt_id: str
    seq: int
    leaf_digest_hex: str
    tree_size: int
    prefix_root_hex: str


@dataclass(frozen=True)
class FrozenSnapshot:
    tree_size: int
    root_hex: str
    receipts: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class InclusionProof:
    version: int
    leaf_index: int
    tree_size: int
    leaf_preimage_bytes: bytes
    siblings: tuple = field(default_factory=tuple)  # tuple[(direction, digest32)]
    expected_root_hex: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    eligible: bool = False
    leaf_digest_hex: str = ""


def _hash_leaf(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def _hash_branch(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _check_json_scalar_safe(value: Any, where: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        if isinstance(value, str) and len(value) > MAX_STRING_VALUE_LEN:
            raise ValueError(f"oversize string at {where}")
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {where}")
        return
    raise ValueError(f"unsupported value type at {where}: {type(value).__name__}")


def _screen_mapping(mapping: Mapping[str, Any], where: str) -> None:
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise ValueError(f"non-string key at {where}")
        lowered = key.lower()
        if lowered in _FORBIDDEN_EXACT or any(s in lowered for s in _FORBIDDEN_SUBSTR):
            raise ValueError(f"forbidden private/secret field at {where}: {key!r}")
        sub = f"{where}.{key}"
        if isinstance(value, Mapping):
            _screen_mapping(value, sub)
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, Mapping):
                    _screen_mapping(item, f"{sub}[{i}]")
                else:
                    _check_json_scalar_safe(item, f"{sub}[{i}]")
        else:
            _check_json_scalar_safe(value, sub)


def canonical_event_bytes(metadata: Mapping[str, Any]) -> bytes:
    """Deterministic UTF-8 canonical encoding of complete event metadata.

    Sorted keys, compact separators, pure ASCII. The same function feeds
    ordinary leaf preimages and eligible binary-leaf metadata commitments,
    so any alteration of any committed field changes the digest.
    """
    raw = json.dumps(
        dict(metadata),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    data = raw.encode("utf-8")
    if len(data) > MAX_CANONICAL_BYTES:
        raise ValueError("canonical event exceeds size bound")
    return data


def metadata_commit_hex(metadata: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical metadata bytes (never caller-supplied)."""
    return hashlib.sha256(canonical_event_bytes(metadata)).hexdigest()


# ---------------------------------------------------------------------------
# Compact versioned binary execution-leaf codec (eligible events only)
# ---------------------------------------------------------------------------
#
# Teleport leaf (71 B):
#   u8 version=1 | u8 type=1 | u16BE flags | u64BE seq | 16B event UUID |
#   32B full-metadata commitment | u8 frame/BSM bits | u8 gate bits |
#   u8 node count | f64BE raw teleport fidelity
# Drill leaf (150 B): teleport 71 B +
#   f64BE purif baseline | f64BE purif output | f64BE swap fidelity (24 B) |
#   u32BE clean sifted | u32BE clean test | u32BE clean errors |
#   u16BE clean output bits (14 B) |
#   u32BE eve test | u32BE eve errors | u8 eve basis (9 B) |
#   32B aggregate independent-node key commitment
# All integers big-endian. No padding bytes anywhere; reserved bits must be
# zero on decode. The leaf carries digests plus direct numeric fields only --
# never raw identifiers, keys, or private blinds.
#
# Flags u16BE bits: 0 teleport_passed, 1 purification_passed, 2 swap_passed,
# 3 clean_established, 4 eve_aborted, 5 both_keyless, 6 independent agreement,
# 7..15 reserved zero.
# Frame/BSM byte bits 0..7: frame_x, frame_z, bsm_x, bsm_z, correction_x,
# correction_z, input_destroyed, resource_consumed.
# Gate byte bits 0..3: gate_x, gate_z, correction_applied, acknowledged.

_FLAG_TELEPORT = 1 << 0
_FLAG_PURIF = 1 << 1
_FLAG_SWAP = 1 << 2
_FLAG_CLEAN = 1 << 3
_FLAG_EVE_ABORT = 1 << 4
_FLAG_BOTH_KEYLESS = 1 << 5
_FLAG_AGREEMENT = 1 << 6

_TELEPORT_FIELD_NAMES = (
    "frame_x",
    "frame_z",
    "bsm_x",
    "bsm_z",
    "correction_x",
    "correction_z",
)
_GATE_FIELD_NAMES = ("gate_x", "gate_z", "correction_applied", "acknowledged")


def _require_bit(value: Any, name: str) -> int:
    if type(value) is not int or value not in (0, 1):
        raise ValueError(f"{name} must be integer 0/1")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be boolean")
    return value


# Documented kernel upper rounding slack: the numerical Bell/teleport kernel
# derives fidelity from floating-point density arithmetic and may round a true
# 1.0 to marginally above it. Values within this epsilon of 1.0 are accepted
# as 1.0-adjacent and stored unclamped (never silently normalized). The strict
# raw lower bound (0.95 for teleport/swap success) is never relaxed.
_KERNEL_FIDELITY_UPPER_SLACK = 1e-9

def _require_fidelity(value: Any, name: str, minimum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    f = float(value)
    if not math.isfinite(f) or f < minimum or f > 1.0 + _KERNEL_FIDELITY_UPPER_SLACK:
        raise ValueError(f"{name} out of accepted range")
    return f


def _validate_teleport_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    for name in ("model_version",):
        if payload.get(name) != 1:
            raise ValueError("teleport payload requires model_version == 1")
    bits = {n: _require_bit(payload.get(n), n) for n in _TELEPORT_FIELD_NAMES}
    if bits["correction_x"] != (bits["bsm_x"] ^ bits["frame_x"]):
        raise ValueError("correction_x must equal bsm_x XOR frame_x")
    if bits["correction_z"] != (bits["bsm_z"] ^ bits["frame_z"]):
        raise ValueError("correction_z must equal bsm_z XOR frame_z")
    gates = {n: _require_bool(payload.get(n), n) for n in _GATE_FIELD_NAMES}
    for n in ("input_destroyed", "resource_consumed"):
        if _require_bool(payload.get(n), n) is not True:
            raise ValueError(f"{n} must hold on teleport success")
    if gates["gate_x"] is not bool(bits["correction_x"]):
        raise ValueError("gate_x must match the actual x correction")
    if gates["gate_z"] is not bool(bits["correction_z"]):
        raise ValueError("gate_z must match the actual z correction")
    if gates["correction_applied"] is not True or gates["acknowledged"] is not True:
        raise ValueError("correction_applied and acknowledged must hold")
    fidelity = _require_fidelity(payload.get("fidelity"), "fidelity", 0.95)
    return {
        "bits": bits,
        "gates": gates,
        "input_destroyed": True,
        "resource_consumed": True,
        "fidelity": fidelity,
    }


def _validate_drill_extension(payload: Mapping[str, Any]) -> dict[str, Any]:
    purif = payload.get("purification")
    swap = payload.get("swap")
    clean = payload.get("clean")
    eve = payload.get("eve")
    if not isinstance(purif, Mapping) or not isinstance(swap, Mapping):
        raise ValueError("drill requires purification and swap mappings")
    if not isinstance(clean, Mapping) or not isinstance(eve, Mapping):
        raise ValueError("drill requires clean and eve mappings")
    base = purif.get("baseline_fidelity")
    out = purif.get("output_fidelity")
    for v, n in ((base, "baseline_fidelity"), (out, "output_fidelity")):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ValueError(f"{n} must be finite numeric")
    if not (0.0 <= float(base) <= 1.0 and 0.0 <= float(out) <= 1.0):
        raise ValueError("purification fidelities out of range")
    if not float(out) > float(base):
        raise ValueError("purification must show measured improvement")
    swap_f = _require_fidelity(swap.get("fidelity"), "swap fidelity", 0.95)

    def _u32(v: Any, name: str) -> int:
        if type(v) is not int or v < 0 or v > 0xFFFFFFFF:
            raise ValueError(f"{name} must be u32")
        return v

    sifted = _u32(clean.get("sifted_count"), "sifted_count")
    ctest = _u32(clean.get("test_count"), "clean test_count")
    cerr = _u32(clean.get("error_count"), "clean error_count")
    cbits = clean.get("output_bits")
    if type(cbits) is not int or cbits < 128 or cbits > 0xFFFF:
        raise ValueError("clean output_bits must be >= 128 usable bits")
    if not (sifted > 0 and 0 < ctest <= sifted and 0 <= cerr <= ctest):
        raise ValueError("clean counts inconsistent")
    if 100 * cerr > 11 * ctest:
        raise ValueError("clean sample exceeds QBER bound")
    if clean.get("established") is not True or clean.get("key_agreement") is not True:
        raise ValueError("clean establishment and independent agreement must hold")

    etest = _u32(eve.get("test_count"), "eve test_count")
    eerr = _u32(eve.get("error_count"), "eve error_count")
    basis = eve.get("basis")
    if type(basis) is not int or basis not in (0, 1, 2):
        raise ValueError("eve basis must be 0, 1, or 2")
    if not (etest > 0 and 0 <= eerr <= etest):
        raise ValueError("eve counts inconsistent")
    if not 100 * eerr > 11 * etest:
        raise ValueError("eve run must exceed the 11% abort boundary")
    if eve.get("aborted") is not True or eve.get("both_keyless") is not True:
        raise ValueError("eve abort with both nodes keyless must hold")

    commitment = payload.get("key_commitment_hex")
    if not isinstance(commitment, str) or len(commitment) != 64:
        raise ValueError("key_commitment_hex must be 64 hex chars")
    try:
        commitment_bytes = bytes.fromhex(commitment)
    except ValueError:
        raise ValueError("key_commitment_hex must be hex") from None
    if len(commitment_bytes) != 32 or commitment_bytes == bytes(32):
        raise ValueError("key_commitment_hex must commit to nonzero bytes")
    return {
        "purif_baseline": float(base),
        "purif_output": float(out),
        "swap_fidelity": swap_f,
        "clean_sifted": sifted,
        "clean_test": ctest,
        "clean_errors": cerr,
        "clean_output": cbits,
        "eve_test": etest,
        "eve_errors": eerr,
        "eve_basis": basis,
        "commitment": commitment_bytes,
    }


def classify_eligibility(event_type: str, outcome: str, payload: Mapping[str, Any]) -> int:
    """Return 1 (teleport), 2 (drill), or 0 (ordinary durable only).

    Raises ValueError when an event *claims* eligible shape but its numeric
    fields fail validation: such claims are rejected, never silently stored
    as ordinary events.
    """
    if event_type == "teleport.completed" and outcome == "success":
        _validate_teleport_payload(payload)
        return LEAF_TYPE_TELEPORT
    if event_type == "drill.summary" and outcome == "success":
        _validate_teleport_payload(payload.get("teleport"))
        _validate_drill_extension(payload)
        return LEAF_TYPE_DRILL
    return 0


def encode_execution_leaf(summary: Mapping[str, Any]) -> bytes:
    """Encode a validated execution summary to its exact binary preimage."""
    leaf_type = summary.get("leaf_type")
    if leaf_type == "teleport":
        leaf_type = LEAF_TYPE_TELEPORT
    elif leaf_type == "drill":
        leaf_type = LEAF_TYPE_DRILL
    if leaf_type not in (LEAF_TYPE_TELEPORT, LEAF_TYPE_DRILL):
        raise ValueError("leaf_type must be 'teleport'/'drill' or 1/2")
    flags = summary.get("flags")
    if type(flags) is not int or flags < 0 or flags > 0xFFFF:
        raise ValueError("flags must be u16")
    seq = summary.get("seq")
    if type(seq) is not int or seq <= 0 or seq > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("seq must be positive u64")
    event_id_hex = summary.get("event_id_hex")
    if not isinstance(event_id_hex, str) or len(event_id_hex) != 32:
        raise ValueError("event_id_hex must be 32 hex chars")
    try:
        event_uuid = bytes.fromhex(event_id_hex)
    except ValueError:
        raise ValueError("event_id_hex must be hex") from None
    commit_hex = summary.get("metadata_commit_hex")
    if not isinstance(commit_hex, str) or len(commit_hex) != 64:
        raise ValueError("metadata_commit_hex must be 64 hex chars")
    try:
        commit = bytes.fromhex(commit_hex)
    except ValueError:
        raise ValueError("metadata_commit_hex must be hex") from None

    teleport = summary.get("teleport")
    if not isinstance(teleport, Mapping):
        raise ValueError("teleport mapping required")
    frame_bsm = 0
    for i, n in enumerate(_TELEPORT_FIELD_NAMES):
        frame_bsm |= (_require_bit(teleport.get(n), n) & 1) << i
    frame_bsm |= (1 if _require_bool(teleport.get("input_destroyed"), "input_destroyed") else 0) << 6
    frame_bsm |= (1 if _require_bool(teleport.get("resource_consumed"), "resource_consumed") else 0) << 7
    gate = 0
    for i, n in enumerate(_GATE_FIELD_NAMES):
        gate |= (1 if _require_bool(teleport.get(n), n) else 0) << i
    node_count = teleport.get("node_count")
    if type(node_count) is not int or node_count <= 0 or node_count > 0xFF:
        raise ValueError("node_count must be u8 >= 1")
    fidelity = teleport.get("fidelity")
    if isinstance(fidelity, bool) or not isinstance(fidelity, (int, float)):
        raise ValueError("fidelity must be numeric")
    fidelity_f = float(fidelity)
    if not math.isfinite(fidelity_f):
        raise ValueError("fidelity must be finite")

    out = bytearray()
    out += bytes((EXEC_LEAF_VERSION, leaf_type))
    out += int(flags).to_bytes(2, "big")
    out += int(seq).to_bytes(8, "big")
    out += event_uuid
    out += commit
    out += bytes((frame_bsm, gate, node_count))
    out += struct.pack(">d", fidelity_f)
    if leaf_type == LEAF_TYPE_TELEPORT:
        if len(out) != TELEPORT_LEAF_SIZE:
            raise LedgerError("teleport codec length invariant broken")
        return bytes(out)
    drill = summary.get("drill")
    if not isinstance(drill, Mapping):
        raise ValueError("drill mapping required for drill leaves")
    for n in ("purif_baseline", "purif_output", "swap_fidelity"):
        v = drill.get(n)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ValueError(f"drill.{n} must be finite numeric")
        out += struct.pack(">d", float(v))
    for n in ("clean_sifted", "clean_test", "clean_errors"):
        v = drill.get(n)
        if type(v) is not int or v < 0 or v > 0xFFFFFFFF:
            raise ValueError(f"drill.{n} must be u32")
        out += int(v).to_bytes(4, "big")
    v = drill.get("clean_output")
    if type(v) is not int or v < 0 or v > 0xFFFF:
        raise ValueError("drill.clean_output must be u16")
    out += int(v).to_bytes(2, "big")
    for n in ("eve_test", "eve_errors"):
        v = drill.get(n)
        if type(v) is not int or v < 0 or v > 0xFFFFFFFF:
            raise ValueError(f"drill.{n} must be u32")
        out += int(v).to_bytes(4, "big")
    v = drill.get("eve_basis")
    if type(v) is not int or v not in (0, 1, 2):
        raise ValueError("drill.eve_basis must be 0, 1, or 2")
    out += bytes((v,))
    commitment = drill.get("key_commitment")
    if isinstance(commitment, str):
        try:
            commitment = bytes.fromhex(commitment)
        except ValueError:
            raise ValueError("drill.key_commitment must be 32 bytes") from None
    if not isinstance(commitment, (bytes, bytearray)) or len(commitment) != 32:
        raise ValueError("drill.key_commitment must be 32 bytes")
    out += bytes(commitment)
    if len(out) != DRILL_LEAF_SIZE:
        raise LedgerError("drill codec length invariant broken")
    return bytes(out)


def decode_execution_leaf(data: bytes) -> dict[str, Any]:
    """Decode and strictly validate a binary execution leaf."""
    if not isinstance(data, (bytes, bytearray)) or len(data) not in (TELEPORT_LEAF_SIZE, DRILL_LEAF_SIZE):
        raise ValueError("execution leaf must be exactly 71 or 150 bytes")
    data = bytes(data)
    version, leaf_type = data[0], data[1]
    if version != EXEC_LEAF_VERSION or leaf_type not in (LEAF_TYPE_TELEPORT, LEAF_TYPE_DRILL):
        raise ValueError("unknown execution leaf version/type")
    if leaf_type == LEAF_TYPE_TELEPORT and len(data) != TELEPORT_LEAF_SIZE:
        raise ValueError("teleport leaf must be exactly 71 bytes")
    if leaf_type == LEAF_TYPE_DRILL and len(data) != DRILL_LEAF_SIZE:
        raise ValueError("drill leaf must be exactly 150 bytes")
    flags = int.from_bytes(data[2:4], "big")
    if flags & 0xFF80:
        raise ValueError("reserved flag bits must be zero")
    if leaf_type == LEAF_TYPE_TELEPORT and flags != _FLAG_TELEPORT:
        raise ValueError("teleport leaf must carry exactly the teleport flag")
    if leaf_type == LEAF_TYPE_DRILL and flags != (
        _FLAG_TELEPORT | _FLAG_PURIF | _FLAG_SWAP | _FLAG_CLEAN
        | _FLAG_EVE_ABORT | _FLAG_BOTH_KEYLESS | _FLAG_AGREEMENT
    ):
        raise ValueError("drill leaf must carry exactly the seven stage flags")
    seq = int.from_bytes(data[4:12], "big")
    if seq <= 0:
        raise ValueError("seq must be positive")
    event_id_hex = data[12:28].hex()
    commit_hex = data[28:60].hex()
    frame_bsm, gate, node_count = data[60], data[61], data[62]
    if gate & 0xF0:
        raise ValueError("reserved gate bits must be zero")
    if node_count <= 0:
        raise ValueError("node_count must be u8 >= 1")
    fidelity = struct.unpack(">d", data[63:71])[0]
    if not math.isfinite(fidelity):
        raise ValueError("fidelity must be finite")
    # Strict typed success fields: the raw lower bound holds exactly and only
    # the documented kernel upper rounding slack is tolerated above 1.0.
    if fidelity < 0.95 or fidelity > 1.0 + _KERNEL_FIDELITY_UPPER_SLACK:
        raise ValueError("fidelity out of accepted range")
    frame = {
        "frame_x": (frame_bsm >> 0) & 1,
        "frame_z": (frame_bsm >> 1) & 1,
        "bsm_x": (frame_bsm >> 2) & 1,
        "bsm_z": (frame_bsm >> 3) & 1,
        "correction_x": (frame_bsm >> 4) & 1,
        "correction_z": (frame_bsm >> 5) & 1,
    }
    if frame["correction_x"] != (frame["bsm_x"] ^ frame["frame_x"]):
        raise ValueError("correction_x must equal bsm_x XOR frame_x")
    if frame["correction_z"] != (frame["bsm_z"] ^ frame["frame_z"]):
        raise ValueError("correction_z must equal bsm_z XOR frame_z")
    if bool((gate >> 0) & 1) is not bool(frame["correction_x"]):
        raise ValueError("gate_x must match the actual x correction")
    if bool((gate >> 1) & 1) is not bool(frame["correction_z"]):
        raise ValueError("gate_z must match the actual z correction")
    if not (frame_bsm >> 6) & 1 or not (frame_bsm >> 7) & 1:
        raise ValueError("input_destroyed and resource_consumed must hold")
    if not (gate >> 2) & 1 or not (gate >> 3) & 1:
        raise ValueError("correction_applied and acknowledged must hold")
    teleport = {
        "frame_x": (frame_bsm >> 0) & 1,
        "frame_z": (frame_bsm >> 1) & 1,
        "bsm_x": (frame_bsm >> 2) & 1,
        "bsm_z": (frame_bsm >> 3) & 1,
        "correction_x": (frame_bsm >> 4) & 1,
        "correction_z": (frame_bsm >> 5) & 1,
        "input_destroyed": bool((frame_bsm >> 6) & 1),
        "resource_consumed": bool((frame_bsm >> 7) & 1),
        "gate_x": bool((gate >> 0) & 1),
        "gate_z": bool((gate >> 1) & 1),
        "correction_applied": bool((gate >> 2) & 1),
        "acknowledged": bool((gate >> 3) & 1),
        "node_count": node_count,
        "fidelity": fidelity,
    }
    result: dict[str, Any] = {
        "version": version,
        "leaf_type": leaf_type,
        "flags": flags,
        "seq": seq,
        "event_id_hex": event_id_hex,
        "metadata_commit_hex": commit_hex,
        "teleport": teleport,
        "drill": None,
    }
    if leaf_type == LEAF_TYPE_TELEPORT:
        return result
    off = TELEPORT_LEAF_SIZE
    purif_baseline, purif_output, swap_f = struct.unpack(">ddd", data[off : off + 24])
    off += 24
    for value, name in (
        (purif_baseline, "purif_baseline"),
        (purif_output, "purif_output"),
    ):
        if not math.isfinite(value) or not 0.0 <= value <= 1.0 + _KERNEL_FIDELITY_UPPER_SLACK:
            raise ValueError(f"drill.{name} out of range")
    if not purif_output > purif_baseline:
        raise ValueError("purification must show measured improvement")
    if not math.isfinite(swap_f) or swap_f < 0.95 or swap_f > 1.0 + _KERNEL_FIDELITY_UPPER_SLACK:
        raise ValueError("drill.swap_fidelity out of accepted range")
    clean_sifted = int.from_bytes(data[off : off + 4], "big")
    clean_test = int.from_bytes(data[off + 4 : off + 8], "big")
    clean_errors = int.from_bytes(data[off + 8 : off + 12], "big")
    clean_output = int.from_bytes(data[off + 12 : off + 14], "big")
    off += 14
    if not (clean_sifted > 0 and 0 < clean_test <= clean_sifted and 0 <= clean_errors <= clean_test):
        raise ValueError("clean counts inconsistent")
    if 100 * clean_errors > 11 * clean_test:
        raise ValueError("clean sample exceeds QBER bound")
    if clean_output < 128:
        raise ValueError("clean output_bits must be >= 128 usable bits")
    eve_test = int.from_bytes(data[off : off + 4], "big")
    eve_errors = int.from_bytes(data[off + 4 : off + 8], "big")
    eve_basis = data[off + 8]
    off += 9
    if eve_basis not in (0, 1, 2):
        raise ValueError("drill.eve_basis must be 0, 1, or 2")
    if not (eve_test > 0 and 0 <= eve_errors <= eve_test):
        raise ValueError("eve counts inconsistent")
    if not 100 * eve_errors > 11 * eve_test:
        raise ValueError("eve run must exceed the 11% abort boundary")
    commitment = data[off : off + 32]
    if bytes(commitment) == bytes(32):
        raise ValueError("key_commitment must commit to nonzero bytes")
    result["drill"] = {
        "purif_baseline": purif_baseline,
        "purif_output": purif_output,
        "swap_fidelity": swap_f,
        "clean_sifted": clean_sifted,
        "clean_test": clean_test,
        "clean_errors": clean_errors,
        "clean_output": clean_output,
        "eve_test": eve_test,
        "eve_errors": eve_errors,
        "eve_basis": eve_basis,
        "key_commitment": bytes(commitment),
    }
    return result


def _widths_for_size(size: int) -> list[int]:
    widths = [size]
    while widths[-1] > 1:
        widths.append((widths[-1] + 1) // 2)
    return widths


def _proof_siblings_for(layers: list[list[bytes]], index: int, size: int) -> tuple[tuple[str, bytes], ...]:
    widths = _widths_for_size(size)
    if not 0 <= index < size:
        raise ValueError("leaf index out of range")
    if len(layers) != len(widths):
        raise LedgerError("layer cache inconsistent with tree size")
    out: list[tuple[str, bytes]] = []
    i = index
    for level, width in enumerate(widths[:-1]):
        layer = layers[level]
        if i % 2 == 1:
            out.append(("left", layer[i - 1]))
        elif i + 1 < width:
            out.append(("right", layer[i + 1]))
        else:
            out.append(("right", layer[i]))  # duplicate-last odd rule
        i //= 2
    return tuple(out)


def _root_from_proof(leaf: bytes, siblings: tuple[tuple[str, bytes], ...]) -> bytes:
    node = leaf
    for direction, digest in siblings:
        if direction == "left":
            node = _hash_branch(digest, node)
        elif direction == "right":
            node = _hash_branch(node, digest)
        else:
            raise ValueError("sibling direction must be left/right")
    return node


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_events (
    seq INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    nodes_json TEXT NOT NULL,
    resources_json TEXT NOT NULL,
    outcome TEXT NOT NULL,
    time TEXT NOT NULL,
    predecessor_hex TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    leaf_hex TEXT NOT NULL,
    eligible INTEGER NOT NULL,
    leaf_blob BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_checkpoints (
    tree_size INTEGER PRIMARY KEY,
    root_hex TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_anchor_claims (
    receipt_id TEXT NOT NULL,
    tree_size INTEGER NOT NULL,
    root_hex TEXT NOT NULL,
    leaf_index INTEGER NOT NULL,
    payer_b58 TEXT NOT NULL,
    last_valid INTEGER,
    claimed_at TEXT NOT NULL,
    PRIMARY KEY (receipt_id)
);
CREATE INDEX IF NOT EXISTS ledger_events_type_seq ON ledger_events(event_type, seq);
CREATE INDEX IF NOT EXISTS ledger_events_prepared_receipt ON ledger_events(event_type, json_extract(canonical_json, '$.payload.receipt_id'), seq);
CREATE INDEX IF NOT EXISTS ledger_events_anchor_sig ON ledger_events(event_type, json_extract(canonical_json, '$.payload.signature'));
CREATE TRIGGER IF NOT EXISTS ledger_no_update_events
BEFORE UPDATE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only');
END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete_events
BEFORE DELETE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only');
END;
CREATE TRIGGER IF NOT EXISTS ledger_no_update_checkpoints
BEFORE UPDATE ON ledger_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'ledger_checkpoints is append-only');
END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete_checkpoints
BEFORE DELETE ON ledger_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'ledger_checkpoints is append-only');
END;
"""


class QuantumTeleportationReceiptLedger:
    """Durable append-only receipt ledger with incremental Merkle frontier.

    Public sink: ``await append_event(mapping)``. Snapshots, proofs, and
    ``close`` are synchronous and bounded. The constructor replays and
    verifies all stored state and raises :class:`LedgerCorruptError` (fail
    closed, never reset) on any mismatch.
    """

    def __init__(self, data_dir: str | Path | None = None, *, busy_timeout_ms: int = 5000) -> None:
        raw_dir = data_dir if data_dir is not None else os.environ.get("DATA_DIR", "/var/lib/desk-gateway")
        self._data_dir = Path(raw_dir)
        self._lock = threading.Lock()
        self._closed = False
        self._conn: sqlite3.Connection | None = None
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._closed = True
            raise LedgerError(f"ledger open failed: {type(exc).__name__}") from None
        try:
            os.chmod(self._data_dir, 0o700)
        except OSError:
            pass
        self._db_path = self._data_dir / DB_FILENAME
        try:
            self._conn = sqlite3.connect(str(self._db_path), timeout=busy_timeout_ms / 1000.0, isolation_level=None, check_same_thread=False)
        except Exception as exc:
            # sqlite3.OperationalError / OSError opening the file: an open
            # failure, distinct from stored-state corruption. Startup
            # isolation catches the LedgerError base.
            self._closed = True
            raise LedgerError(f"ledger open failed: {type(exc).__name__}") from None
        try:
            try:
                os.chmod(self._db_path, 0o600)
            except OSError:
                pass
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=DELETE;")
            cur.execute("PRAGMA synchronous=EXTRA;")
            cur.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)};")
            cur.executescript(_SCHEMA)
            cur.execute("INSERT OR IGNORE INTO ledger_meta(key, value) VALUES ('version', '1');")
            integrity = cur.execute("PRAGMA integrity_check;").fetchall()
            if len(integrity) != 1 or str(integrity[0][0]).lower() != "ok":
                raise LedgerCorruptError("sqlite integrity check failed")
            rows = cur.execute(
                "SELECT seq, event_id, event_type, session_id, actor, nodes_json,"
                " resources_json, outcome, time, predecessor_hex,"
                " canonical_json, leaf_hex, eligible, leaf_blob"
                " FROM ledger_events ORDER BY seq;"
            ).fetchall()
            checkpoints = dict(cur.execute("SELECT tree_size, root_hex FROM ledger_checkpoints;").fetchall())
            self._replay(rows, checkpoints)
        except LedgerError:
            try:
                self._conn.close()
            except Exception:
                pass
            self._closed = True
            raise
        except Exception as exc:
            # sqlite3.DatabaseError / OSError on a damaged file: fail closed
            # as corruption, never half-open.
            try:
                self._conn.close()
            except Exception:
                pass
            self._closed = True
            raise LedgerCorruptError(f"stored state unreadable: {type(exc).__name__}") from None

    # -- introspection ----------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def tree_size(self) -> int:
        with self._lock:
            self._ensure_open()
            self._refresh_committed_delta_locked()
            return len(self._leaves)

    @property
    def current_root_hex(self) -> str:
        with self._lock:
            self._ensure_open()
            self._refresh_committed_delta_locked()
            if not self._leaves:
                return EMPTY_ROOT_HEX
            return self._layers[-1][0].hex()

    def _ensure_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("ledger is closed")

    def _refresh_committed_delta_locked(self) -> None:
        """Ingest rows committed by sibling handles on the same file.

        Caller must hold ``self._lock`` and have passed ``_ensure_open``.
        Read-only SELECTs observe only fully committed transactions, so a
        visible delta always carries both its event row and its checkpoint
        row. A corrupt/partial delta fails closed: in-memory state is
        truncated back to the pre-refresh length (never reset, never
        partially accepted, never reusing a sequence) and the error
        propagates.
        """
        base_len = len(self._leaves)
        cur = self._conn.cursor()
        try:
            delta = cur.execute(
                "SELECT seq, event_id, event_type, session_id, actor, nodes_json,"
                " resources_json, outcome, time, predecessor_hex,"
                " canonical_json, leaf_hex, eligible, leaf_blob"
                " FROM ledger_events WHERE seq > ? ORDER BY seq;",
                (base_len,),
            ).fetchall()
        except sqlite3.Error:
            raise LedgerError("ledger_unavailable: delta refresh failed") from None
        if not delta:
            return
        try:
            delta_checkpoints = dict(cur.execute(
                "SELECT tree_size, root_hex FROM ledger_checkpoints WHERE tree_size > ?;",
                (base_len,),
            ).fetchall())
        except sqlite3.Error:
            raise LedgerError("ledger_unavailable: delta refresh failed") from None
        prev = self._leaves[-1].hex() if self._leaves else GENESIS_PREDECESSOR_HEX
        try:
            for row in delta:
                prev = self._ingest_committed_row(row, delta_checkpoints, prev)
        except LedgerError:
            self._truncate_to(base_len)
            raise
    # -- replay -----------------------------------------------------------
    def _replay(self, rows: list[tuple], checkpoints: dict[int, str]) -> None:
        self._leaves: list[bytes] = []
        self._layers: list[list[bytes]] = []
        self._by_id: dict[str, int] = {}
        self._id_by_seq: dict[int, str] = {}
        self._metas: dict[int, dict[str, Any]] = {}
        self._eligible: dict[int, int] = {}
        prev_leaf_hex = GENESIS_PREDECESSOR_HEX
        for row in rows:
            prev_leaf_hex = self._ingest_committed_row(row, checkpoints, prev_leaf_hex)
        if len(checkpoints) != len(rows):
            raise LedgerCorruptError("checkpoint count mismatch")

    def _ingest_committed_row(
        self, row: tuple, checkpoints: Mapping[int, str], expected_predecessor: str
    ) -> str:
        """Verify one committed row and extend the in-memory frontier.

        Used both by startup replay and by the in-transaction delta refresh
        for same-file writers. Returns the new expected predecessor hex.
        """
        (
            seq, event_id, event_type, session_id, actor, nodes_json,
            resources_json, outcome, time, predecessor_hex,
            canonical_json, leaf_hex, eligible, leaf_blob,
        ) = row
        if seq != len(self._leaves) + 1:
            raise LedgerCorruptError("event sequence gap")
        try:
            metadata = json.loads(canonical_json)
        except ValueError:
            raise LedgerCorruptError("stored canonical JSON unreadable") from None
        if not isinstance(metadata, dict):
            raise LedgerCorruptError("stored metadata malformed")
        if metadata.get("seq") != seq or metadata.get("event_id") != event_id:
            raise LedgerCorruptError("stored seq/event_id mismatch")
        # Searchable columns are bound to the committed metadata: a
        # column-only rewrite (e.g. event_type) fails replay closed even when
        # the canonical JSON itself is untouched.
        if (
            metadata.get("event_type") != event_type
            or metadata.get("session_id") != session_id
            or metadata.get("actor") != actor
            or metadata.get("outcome") != outcome
            or metadata.get("time") != time
            or metadata.get("predecessor_digest_hex") != predecessor_hex
        ):
            raise LedgerCorruptError("searchable column mismatch")
        try:
            stored_nodes = json.loads(nodes_json)
            stored_resources = json.loads(resources_json)
        except ValueError:
            raise LedgerCorruptError("stored column JSON unreadable") from None
        if stored_nodes != metadata.get("nodes") or stored_resources != metadata.get("resources"):
            raise LedgerCorruptError("searchable column mismatch")
        if predecessor_hex != expected_predecessor:
            raise LedgerCorruptError("predecessor linkage broken")
        recomputed = self._recompute_leaf(metadata, int(eligible))
        if recomputed[1] != leaf_hex or bytes(leaf_blob) != recomputed[0]:
            raise LedgerCorruptError("stored leaf digest mismatch")
        try:
            leaf_bytes = bytes.fromhex(leaf_hex)
        except ValueError:
            raise LedgerCorruptError("stored leaf digest unreadable") from None
        self._leaves.append(leaf_bytes)
        self._by_id[event_id] = seq
        self._id_by_seq[seq] = event_id
        self._metas[seq] = metadata
        self._eligible[seq] = int(eligible)
        self._append_path(leaf_bytes)
        root_hex = self._layers[-1][0].hex()
        stored = checkpoints.get(seq)
        if stored is None or stored != root_hex:
            raise LedgerCorruptError("prefix checkpoint mismatch")
        return leaf_hex

    def _truncate_to(self, base_len: int) -> None:
        """Drop provisional/refresh in-memory state after a failed transaction."""
        if len(self._leaves) <= base_len:
            return
        for event_id, seq in [item for item in self._by_id.items() if item[1] > base_len]:
            del self._by_id[event_id]
            self._id_by_seq.pop(seq, None)
        for seq in range(base_len + 1, len(self._leaves) + 1):
            self._metas.pop(seq, None)
            self._eligible.pop(seq, None)
        self._leaves = self._leaves[:base_len]
        self._rebuild_layers()

    def _recompute_leaf(self, metadata: Mapping[str, Any], eligible: int) -> tuple[bytes, str]:
        if eligible in (LEAF_TYPE_TELEPORT, LEAF_TYPE_DRILL):
            summary = self._summary_for(metadata, eligible)
            preimage = encode_execution_leaf(summary)
        elif eligible == 0:
            preimage = canonical_event_bytes(metadata)
        else:
            raise LedgerCorruptError("stored eligibility flag invalid")
        return preimage, _hash_leaf(preimage).hex()

    def _summary_for(self, metadata: Mapping[str, Any], eligible: int) -> dict[str, Any]:
        payload = metadata.get("payload")
        if not isinstance(payload, Mapping):
            raise LedgerCorruptError("stored eligible payload malformed")
        nodes = metadata.get("nodes")
        node_count = len(nodes) if isinstance(nodes, list) else 0
        commit = metadata_commit_hex(metadata)
        if eligible == LEAF_TYPE_TELEPORT:
            checked = _validate_teleport_payload(payload)
            teleport = dict(payload)
            teleport["node_count"] = node_count
            return {
                "leaf_type": LEAF_TYPE_TELEPORT,
                "flags": _FLAG_TELEPORT,
                "seq": metadata.get("seq"),
                "event_id_hex": metadata.get("event_id"),
                "metadata_commit_hex": commit,
                "teleport": teleport,
                "drill": None,
            }
        drill_payload = payload.get("teleport")
        _validate_teleport_payload(drill_payload)
        checked_drill = _validate_drill_extension(payload)
        teleport = dict(drill_payload)
        teleport["node_count"] = node_count
        drill = {
            "purif_baseline": checked_drill["purif_baseline"],
            "purif_output": checked_drill["purif_output"],
            "swap_fidelity": checked_drill["swap_fidelity"],
            "clean_sifted": checked_drill["clean_sifted"],
            "clean_test": checked_drill["clean_test"],
            "clean_errors": checked_drill["clean_errors"],
            "clean_output": checked_drill["clean_output"],
            "eve_test": checked_drill["eve_test"],
            "eve_errors": checked_drill["eve_errors"],
            "eve_basis": checked_drill["eve_basis"],
            "key_commitment": checked_drill["commitment"],
        }
        full_flags = (
            _FLAG_TELEPORT | _FLAG_PURIF | _FLAG_SWAP | _FLAG_CLEAN
            | _FLAG_EVE_ABORT | _FLAG_BOTH_KEYLESS | _FLAG_AGREEMENT
        )
        return {
            "leaf_type": LEAF_TYPE_DRILL,
            "flags": full_flags,
            "seq": metadata.get("seq"),
            "event_id_hex": metadata.get("event_id"),
            "metadata_commit_hex": commit,
            "teleport": teleport,
            "drill": drill,
        }

    def _append_path(self, leaf: bytes) -> None:
        if not self._layers:
            self._layers = [[leaf]]
            return
        self._layers[0].append(leaf)
        idx = len(self._layers[0]) - 1
        level = 0
        while True:
            layer = self._layers[level]
            if idx % 2 == 1:
                parent = _hash_branch(layer[idx - 1], layer[idx])
            else:
                if idx + 1 < len(layer):
                    parent = _hash_branch(layer[idx], layer[idx + 1])
                else:
                    parent = _hash_branch(layer[idx], layer[idx])
            nxt = idx // 2
            if level + 1 >= len(self._layers):
                self._layers.append([parent])
                break
            upper = self._layers[level + 1]
            if nxt < len(upper):
                if upper[nxt] == parent:
                    break
                upper[nxt] = parent
                if len(upper) == 1:
                    # Replaced the single top node: it is the root, and
                    # there is no level above to update. Without this stop
                    # every append pushes a bogus H(root, root) level and
                    # the cascade degrades to O(n) per append.
                    break
            else:
                upper.append(parent)
            # Cascade upward; the loop exits on a stable parent, on the new
            # root, or by pushing a new root level. O(log n) total.
            idx = nxt
            level += 1

    def _layers_for(self, size: int) -> list[list[bytes]]:
        if size == len(self._leaves):
            return [list(layer) for layer in self._layers]
        layers: list[list[bytes]] = [list(self._leaves[:size])]
        while len(layers[-1]) > 1:
            prev = layers[-1]
            nxt = [
                _hash_branch(prev[i], prev[i + 1] if i + 1 < len(prev) else prev[i])
                for i in range(0, len(prev), 2)
            ]
            layers.append(nxt)
        return layers

    # -- public sink ------------------------------------------------------
    def _validate_input(self, event: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, Mapping):
            raise ValueError("event must be a mapping")
        unknown = set(event.keys()) - set(_TOP_LEVEL_FIELDS)
        if unknown:
            raise ValueError(f"unknown event fields: {sorted(unknown)}")
        event_type = event.get("event_type")
        session_id = event.get("session_id")
        outcome = event.get("outcome")
        payload = event.get("payload")
        actor = event.get("actor", "")
        nodes = event.get("nodes", [])
        resources = event.get("resources", [])
        if not isinstance(event_type, str) or not 1 <= len(event_type) <= MAX_EVENT_TYPE_LEN:
            raise ValueError("event_type must be a 1..128 char string")
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= MAX_SESSION_ID_LEN:
            raise ValueError("session_id must be a 1..256 char string")
        if not isinstance(outcome, str) or not 1 <= len(outcome) <= MAX_OUTCOME_LEN:
            raise ValueError("outcome must be a 1..64 char string")
        if not isinstance(actor, str) or len(actor) > MAX_ACTOR_LEN:
            raise ValueError("actor must be a string <= 256 chars")
        for name, seq_val in (("nodes", nodes), ("resources", resources)):
            if not isinstance(seq_val, (list, tuple)):
                raise ValueError(f"{name} must be a list of strings")
            if len(seq_val) > MAX_ID_LIST:
                raise ValueError(f"{name} exceeds entry bound")
            for entry in seq_val:
                if not isinstance(entry, str) or not 1 <= len(entry) <= MAX_ID_LEN:
                    raise ValueError(f"{name} entries must be 1..256 char strings")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a mapping")
        _screen_mapping(dict(payload), "payload")
        return {
            "event_type": event_type,
            "session_id": session_id,
            "actor": actor,
            "nodes": list(nodes),
            "resources": list(resources),
            "outcome": outcome,
            "payload": json.loads(json.dumps(dict(payload), allow_nan=False)),
        }

    def _rollback_failed_append(self, base_len: int) -> None:
        """Restore the prefix or irreversibly close an uncertain transaction."""
        try:
            self._conn.rollback()
        except BaseException:
            # Same-connection reads can otherwise serve pending rows as if
            # committed. Close the public handle before any close attempt;
            # preserve the original append error even if cleanup also fails.
            self._closed = True
            try:
                self._conn.close()
            except BaseException:
                pass
        self._truncate_to(base_len)

    async def append_event(self, event: Mapping[str, Any]) -> QuantumQKDReceipt:
        """Durably commit one public event; return the QuantumQKD receipt after commit."""
        with self._lock:
            self._ensure_open()
            clean = self._validate_input(event)
            base_len = len(self._leaves)
            cur = self._conn.cursor()
            try:
                # BEGIN IMMEDIATE precedes deriving seq/predecessor/root so a
                # second ledger object on the same file serializes here.
                cur.execute("BEGIN IMMEDIATE;")
                # Refresh the ENTIRE committed delta (leaves, metadata,
                # frontier, checkpoints) inside the transaction — never just
                # max(seq) — so a stale cache cannot reuse a taken sequence.
                delta = cur.execute(
                    "SELECT seq, event_id, event_type, session_id, actor, nodes_json,"
                    " resources_json, outcome, time, predecessor_hex,"
                    " canonical_json, leaf_hex, eligible, leaf_blob"
                    " FROM ledger_events WHERE seq > ? ORDER BY seq;",
                    (base_len,),
                ).fetchall()
                if delta:
                    delta_checkpoints = dict(cur.execute(
                        "SELECT tree_size, root_hex FROM ledger_checkpoints WHERE tree_size > ?;",
                        (base_len,),
                    ).fetchall())
                    prev = self._leaves[-1].hex() if self._leaves else GENESIS_PREDECESSOR_HEX
                    for row in delta:
                        prev = self._ingest_committed_row(row, delta_checkpoints, prev)
                seq = len(self._leaves) + 1
                event_id = uuid.uuid4().hex
                predecessor = self._leaves[-1].hex() if self._leaves else GENESIS_PREDECESSOR_HEX
                metadata: dict[str, Any] = {
                    "version": LEDGER_VERSION,
                    "event_type": clean["event_type"],
                    "seq": seq,
                    "event_id": event_id,
                    "session_id": clean["session_id"],
                    "actor": clean["actor"],
                    "nodes": clean["nodes"],
                    "resources": clean["resources"],
                    "time": datetime.now(timezone.utc).isoformat(),
                    "predecessor_digest_hex": predecessor,
                    "outcome": clean["outcome"],
                    "payload": clean["payload"],
                }
                eligible = classify_eligibility(clean["event_type"], clean["outcome"], clean["payload"])
                if eligible:
                    preimage = encode_execution_leaf(self._summary_for(metadata, eligible))
                else:
                    preimage = canonical_event_bytes(metadata)
                leaf_hex = _hash_leaf(preimage).hex()
                canonical_json = json.dumps(
                    metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
                )
                cur.execute(
                    "INSERT INTO ledger_events (seq, event_id, event_type, session_id, actor,"
                    " nodes_json, resources_json, outcome, time, predecessor_hex,"
                    " canonical_json, leaf_hex, eligible, leaf_blob)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (
                        seq,
                        event_id,
                        clean["event_type"],
                        clean["session_id"],
                        clean["actor"],
                        json.dumps(clean["nodes"]),
                        json.dumps(clean["resources"]),
                        clean["outcome"],
                        metadata["time"],
                        predecessor,
                        canonical_json,
                        leaf_hex,
                        eligible,
                        bytes(preimage),
                    ),
                )
                # Provisional in-memory root for the atomic checkpoint row.
                self._leaves.append(bytes.fromhex(leaf_hex))
                self._by_id[event_id] = seq
                self._id_by_seq[seq] = event_id
                self._metas[seq] = metadata
                self._eligible[seq] = eligible
                self._append_path(bytes.fromhex(leaf_hex))
                root_hex = self._layers[-1][0].hex()
                cur.execute(
                    "INSERT INTO ledger_checkpoints (tree_size, root_hex) VALUES (?, ?);",
                    (seq, root_hex),
                )
                self._conn.commit()
            except LedgerError:
                self._rollback_failed_append(base_len)
                raise
            except sqlite3.IntegrityError:
                # Residual race after the refresh (a commit landed between our
                # delta read and our insert): fail closed, never surface a raw
                # driver error and never reuse the sequence.
                self._rollback_failed_append(base_len)
                raise LedgerError("ledger_unavailable: concurrent append conflict after refresh") from None
            except sqlite3.Error:
                self._rollback_failed_append(base_len)
                raise LedgerError("ledger_unavailable: append transaction failed") from None
            except BaseException:
                self._rollback_failed_append(base_len)
                raise
            return QuantumQKDReceipt(
                receipt_id=event_id,
                seq=seq,
                leaf_digest_hex=leaf_hex,
                tree_size=seq,
                prefix_root_hex=root_hex,
            )

    def _rebuild_layers(self) -> None:
        self._layers = []
        for leaf in self._leaves:
            self._append_path(leaf)

    # -- snapshots / proofs -----------------------------------------------
    def _receipt_for_seq(self, seq: int) -> QuantumQKDReceipt:
        leaf_hex = self._leaves[seq - 1].hex()
        layers = self._layers_for(seq)
        root_hex = layers[-1][0].hex() if layers else EMPTY_ROOT_HEX
        event_id = self._id_by_seq[seq]
        return QuantumQKDReceipt(
            receipt_id=event_id,
            seq=seq,
            leaf_digest_hex=leaf_hex,
            tree_size=seq,
            prefix_root_hex=root_hex,
        )

    def snapshot(self, tree_size: int | None = None) -> FrozenSnapshot:
        """Frozen prefix snapshot; historical prefixes never change."""
        with self._lock:
            self._ensure_open()
            self._refresh_committed_delta_locked()
            size = len(self._leaves) if tree_size is None else tree_size
            if type(size) is not int or size < 0 or size > len(self._leaves):
                raise ValueError("tree_size out of range")
            if size == 0:
                return FrozenSnapshot(tree_size=0, root_hex=EMPTY_ROOT_HEX, receipts=())
            layers = self._layers_for(size)
            root_hex = layers[-1][0].hex()
            id_by_seq = {s: self._id_by_seq[s] for s in range(1, size + 1)}
            receipts = tuple(
                QuantumQKDReceipt(
                    receipt_id=id_by_seq[s],
                    seq=s,
                    leaf_digest_hex=self._leaves[s - 1].hex(),
                    tree_size=size,
                    prefix_root_hex=root_hex,
                )
                for s in range(1, size + 1)
            )
            return FrozenSnapshot(tree_size=size, root_hex=root_hex, receipts=receipts)

    def receipt(self, receipt_id: str) -> QuantumQKDReceipt:
        with self._lock:
            self._ensure_open()
            self._refresh_committed_delta_locked()
            seq = self._by_id.get(receipt_id)
            if seq is None:
                raise LookupError("unknown receipt_id")
            return self._receipt_for_seq(seq)

    def inclusion_proof(self, receipt_id: str, tree_size: int) -> InclusionProof:
        with self._lock:
            self._ensure_open()
            self._refresh_committed_delta_locked()
            seq = self._by_id.get(receipt_id)
            if seq is None:
                raise LookupError("unknown receipt_id")
            if type(tree_size) is not int or tree_size <= 0 or tree_size > len(self._leaves):
                raise ValueError("tree_size out of range")
            index = seq - 1
            if not 0 <= index < tree_size:
                raise ValueError("receipt is not part of the requested prefix")
            layers = self._layers_for(tree_size)
            siblings = _proof_siblings_for(layers, index, tree_size)
            # Deep copy: the caller owns the returned metadata; later caller
            # mutation must never damage the committed cache.
            metadata = copy.deepcopy(self._metas[seq])
            eligible = self._eligible[seq]
            if eligible:
                preimage = encode_execution_leaf(self._summary_for(metadata, eligible))
            else:
                preimage = canonical_event_bytes(metadata)
            leaf_hex = _hash_leaf(preimage).hex()
            if leaf_hex != self._leaves[index].hex():
                raise LedgerCorruptError("in-memory leaf inconsistent")
            root_hex = layers[-1][0].hex()
            # Bind the claimed tree_size/root against the trusted frozen
            # checkpoint row, not just the in-memory frontier.
            try:
                stored_row = self._conn.execute(
                    "SELECT root_hex FROM ledger_checkpoints WHERE tree_size = ?;",
                    (tree_size,),
                ).fetchone()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: checkpoint lookup failed") from None
            if stored_row is None or stored_row[0] != root_hex:
                raise LedgerCorruptError("prefix checkpoint mismatch")
            return InclusionProof(
                version=LEDGER_VERSION,
                leaf_index=index,
                tree_size=tree_size,
                leaf_preimage_bytes=preimage,
                siblings=siblings,
                expected_root_hex=root_hex,
                metadata=metadata,
                eligible=bool(eligible),
                leaf_digest_hex=leaf_hex,
            )

    @staticmethod
    def verify_proof(proof: Mapping[str, Any]) -> bool:
        """Verify exact membership AND metadata binding. Never raises on content."""
        try:
            if isinstance(proof, Mapping):
                version = proof.get("version")
                index = proof.get("leaf_index")
                size = proof.get("tree_size")
                preimage = proof.get("leaf_preimage_bytes")
                siblings = proof.get("siblings")
                expected = proof.get("expected_root_hex")
                metadata = proof.get("metadata")
                eligible = proof.get("eligible")
            else:
                version = proof.version  # type: ignore[union-attr]
                index = proof.leaf_index  # type: ignore[union-attr]
                size = proof.tree_size  # type: ignore[union-attr]
                preimage = proof.leaf_preimage_bytes  # type: ignore[union-attr]
                siblings = proof.siblings  # type: ignore[union-attr]
                expected = proof.expected_root_hex  # type: ignore[union-attr]
                metadata = proof.metadata  # type: ignore[union-attr]
                eligible = proof.eligible  # type: ignore[union-attr]

            if version != LEDGER_VERSION:
                return False
            if type(index) is not int or type(size) is not int:
                return False
            if not 0 <= index < size:
                return False
            if not isinstance(preimage, (bytes, bytearray)) or not preimage:
                return False
            preimage = bytes(preimage)
            if not isinstance(expected, str) or len(expected) != 64:
                return False
            try:
                bytes.fromhex(expected)
            except ValueError:
                return False
            if not isinstance(metadata, Mapping):
                return False
            # Source one-based seq convention: the committed seq is always
            # leaf_index + 1. A seq-mismatched proof is rejected even when its
            # recomputed root happens to match.
            if type(metadata.get("seq")) is not int or metadata.get("seq") != index + 1:
                return False
            sibs = list(siblings) if isinstance(siblings, (list, tuple)) else None
            if sibs is None:
                return False
            norm: list[tuple[str, bytes]] = []
            for entry in sibs:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    return False
                direction, digest = entry
                if direction not in ("left", "right"):
                    return False
                if not isinstance(digest, (bytes, bytearray)) or len(digest) != 32:
                    return False
                norm.append((direction, bytes(digest)))
            widths = _widths_for_size(size)
            if len(norm) != len(widths) - 1:
                return False
            # Directions must follow the deterministic duplicate-last rule.
            i = index
            for level, width in enumerate(widths[:-1]):
                if i % 2 == 1:
                    want = "left"
                else:
                    want = "right"
                if norm[level][0] != want:
                    return False
                i //= 2
            # Metadata binding: recompute the exact preimage from metadata.
            if eligible:
                if not isinstance(metadata.get("payload"), Mapping):
                    return False
                summary = QuantumTeleportationReceiptLedger._summary_for_static(metadata)
                if summary is None:
                    return False
                bound = encode_execution_leaf(summary)
            else:
                if eligible not in (False, 0, None):
                    return False
                bound = canonical_event_bytes(dict(metadata))
            if bound != preimage:
                return False
            leaf = _hash_leaf(preimage)
            if _root_from_proof(leaf, tuple(norm)).hex() != expected.lower():
                return False
            return True
        except (ValueError, LedgerError, KeyError, AttributeError, TypeError):
            return False

    def verify_committed_proof(self, proof: Mapping[str, Any] | InclusionProof) -> bool:
        """Verify a proof against the trusted committed checkpoint.

        The claimed ``tree_size``/``expected_root_hex`` must exactly match the
        stored ``ledger_checkpoints`` row (bounded single-row lookup); the
        remaining membership/metadata/index/duplicate-last checks reuse the
        algebraic :meth:`verify_proof`. Uncommitted sizes, unknown prefixes,
        malformed shapes, and integers outside the SQLite range return False
        (never raise on content, never OverflowError). Only a closed ledger
        raises.
        """
        try:
            if isinstance(proof, Mapping):
                size = proof.get("tree_size")
                expected = proof.get("expected_root_hex")
            else:
                size = proof.tree_size  # type: ignore[union-attr]
                expected = proof.expected_root_hex  # type: ignore[union-attr]
        except (AttributeError, TypeError):
            return False
        if type(size) is not int or size <= 0 or size > _SQLITE_INT_MAX:
            return False
        if not isinstance(expected, str) or len(expected) != 64:
            return False
        try:
            expected_norm = expected.lower()
            bytes.fromhex(expected_norm)
        except ValueError:
            return False
        with self._lock:
            self._ensure_open()
            try:
                row = self._conn.execute(
                    "SELECT root_hex FROM ledger_checkpoints WHERE tree_size = ?;",
                    (size,),
                ).fetchone()
            except sqlite3.Error:
                return False
            if row is None:
                return False
            try:
                stored_norm = str(row[0]).lower()
            except (IndexError, TypeError, ValueError):
                return False
            if stored_norm != expected_norm:
                return False
        return QuantumTeleportationReceiptLedger.verify_proof(proof)

    @staticmethod
    def _summary_for_static(metadata: Mapping[str, Any]) -> dict[str, Any] | None:
        try:
            eligible = classify_eligibility(
                metadata.get("event_type"), metadata.get("outcome"), metadata.get("payload")
            )
            if not eligible:
                return None
            commit = metadata_commit_hex(dict(metadata))
            nodes = metadata.get("nodes")
            node_count = len(nodes) if isinstance(nodes, list) else 0
            payload = metadata.get("payload")
            assert isinstance(payload, Mapping)
            if eligible == LEAF_TYPE_TELEPORT:
                teleport = dict(payload)
                teleport["node_count"] = node_count
                return {
                    "leaf_type": LEAF_TYPE_TELEPORT,
                    "flags": _FLAG_TELEPORT,
                    "seq": metadata.get("seq"),
                    "event_id_hex": metadata.get("event_id"),
                    "metadata_commit_hex": commit,
                    "teleport": teleport,
                    "drill": None,
                }
            teleport = dict(payload["teleport"])
            teleport["node_count"] = node_count
            full_flags = (
                _FLAG_TELEPORT | _FLAG_PURIF | _FLAG_SWAP | _FLAG_CLEAN
                | _FLAG_EVE_ABORT | _FLAG_BOTH_KEYLESS | _FLAG_AGREEMENT
            )
            ck = payload.get("key_commitment_hex")
            return {
                "leaf_type": LEAF_TYPE_DRILL,
                "flags": full_flags,
                "seq": metadata.get("seq"),
                "event_id_hex": metadata.get("event_id"),
                "metadata_commit_hex": commit,
                "teleport": teleport,
                "drill": {
                    "purif_baseline": payload["purification"]["baseline_fidelity"],
                    "purif_output": payload["purification"]["output_fidelity"],
                    "swap_fidelity": payload["swap"]["fidelity"],
                    "clean_sifted": payload["clean"]["sifted_count"],
                    "clean_test": payload["clean"]["test_count"],
                    "clean_errors": payload["clean"]["error_count"],
                    "clean_output": payload["clean"]["output_bits"],
                    "eve_test": payload["eve"]["test_count"],
                    "eve_errors": payload["eve"]["error_count"],
                    "eve_basis": payload["eve"]["basis"],
                    "key_commitment": bytes.fromhex(ck) if isinstance(ck, str) else ck,
                },
            }
        except (ValueError, KeyError, TypeError, AssertionError):
            return None

    def events_by_type(self, event_type: str, *, limit: int = 1000) -> tuple[dict[str, Any], ...]:
        with self._lock:
            self._ensure_open()
            if not isinstance(event_type, str) or not event_type:
                raise ValueError("event_type required")
            if type(limit) is not int or limit <= 0 or limit > 100000:
                raise ValueError("limit out of range")
            try:
                cur = self._conn.cursor()
                rows = cur.execute(
                    "SELECT canonical_json FROM ledger_events WHERE event_type = ? ORDER BY seq LIMIT ?;",
                    (event_type, limit),
                ).fetchall()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: event query failed") from None
            try:
                return tuple(json.loads(r[0]) for r in rows)
            except ValueError:
                raise LedgerCorruptError("stored event unreadable") from None

    def list_receipts(self, limit: int) -> tuple[QuantumQKDReceipt, ...]:
        """First at most ``limit`` receipts in sequence order.

        Bounded joined query over the indexed prefix — never a full snapshot,
        tree, or history materialization. ``limit`` is an exact int in
        1..1000. Each receipt carries its own frozen prefix (tree_size ==
        seq with the checkpointed root at that seq).
        """
        with self._lock:
            self._ensure_open()
            if type(limit) is not int or limit < 1 or limit > 1000:
                raise ValueError("limit must be an integer in 1..1000")
            try:
                cur = self._conn.cursor()
                rows = cur.execute(
                    "SELECT e.seq, e.event_id, e.leaf_hex, c.root_hex"
                    " FROM ledger_events e JOIN ledger_checkpoints c ON c.tree_size = e.seq"
                    " ORDER BY e.seq LIMIT ?;",
                    (limit,),
                ).fetchall()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: receipt listing failed") from None
            return tuple(
                QuantumQKDReceipt(
                    receipt_id=event_id,
                    seq=seq,
                    leaf_digest_hex=leaf_hex,
                    tree_size=seq,
                    prefix_root_hex=root_hex,
                )
                for seq, event_id, leaf_hex, root_hex in rows
            )

    def claim_anchor(
        self,
        receipt_id: str,
        *,
        tree_size: int,
        root_hex: str,
        leaf_index: int,
        payer_b58: str,
        last_valid: int | None,
    ) -> bool:
        """Atomically claim the single-send right for one receipt.

        The shared cross-exporter/process authority: the first claimer wins
        (True); any later claim for that receipt, even at a later prefix,
        observes False and must never sign or send. Raises LedgerError when
        the claim store is unavailable — callers fail closed, never treat outage as unclaimed.
        No network await happens inside the claim transaction.
        """
        if not isinstance(receipt_id, str) or not receipt_id:
            raise ValueError("receipt_id required")
        if type(tree_size) is not int or tree_size <= 0:
            raise ValueError("tree_size must be a positive integer")
        if not isinstance(root_hex, str) or len(root_hex) != 64:
            raise ValueError("root_hex must be 64 hex chars")
        try:
            bytes.fromhex(root_hex)
        except ValueError:
            raise ValueError("root_hex must be hex") from None
        if type(leaf_index) is not int or leaf_index < 0 or leaf_index >= tree_size:
            raise ValueError("leaf_index out of range for tree_size")
        if not isinstance(payer_b58, str) or not payer_b58:
            raise ValueError("payer_b58 required")
        if last_valid is not None and (type(last_valid) is not int or last_valid < 0):
            raise ValueError("last_valid must be a non-negative integer or None")
        with self._lock:
            self._ensure_open()
            try:
                cur = self._conn.cursor()
                cur.execute("BEGIN IMMEDIATE;")
                try:
                    cur.execute(
                        "INSERT INTO ledger_anchor_claims"
                        " (receipt_id, tree_size, root_hex, leaf_index, payer_b58, last_valid, claimed_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?);",
                        (
                            receipt_id, tree_size, root_hex, leaf_index,
                            payer_b58, last_valid,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    return False
                self._conn.commit()
                return True
            except sqlite3.Error:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise LedgerError("ledger_unavailable: anchor claim failed") from None

    def read_anchor_claim(self, receipt_id: str, tree_size: int | None = None) -> dict[str, Any] | None:
        """Return the stored claim matching the optional prefix, or None.

        An explicit tree_size pins the attested prefix; omitting it returns the
        receipt's sole claimed prefix. Raises LedgerError when the claim store is
        unavailable — callers fail closed, never treat outage as unclaimed.
        """
        with self._lock:
            self._ensure_open()
            if not isinstance(receipt_id, str) or not receipt_id:
                raise ValueError("receipt_id required")
            if tree_size is not None and (type(tree_size) is not int or tree_size <= 0):
                raise ValueError("tree_size must be a positive integer or None")
            try:
                cur = self._conn.cursor()
                if tree_size is None:
                    row = cur.execute(
                        "SELECT tree_size, root_hex, leaf_index, payer_b58, last_valid"
                        " FROM ledger_anchor_claims WHERE receipt_id = ?",
                        (receipt_id,),
                    ).fetchone()
                else:
                    row = cur.execute(
                        "SELECT tree_size, root_hex, leaf_index, payer_b58, last_valid"
                        " FROM ledger_anchor_claims WHERE receipt_id = ? AND tree_size = ?;",
                        (receipt_id, tree_size),
                    ).fetchone()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: anchor claim lookup failed") from None
            if row is None:
                return None
            size, root, index, payer, valid = row
            return {
                "receipt_id": receipt_id,
                "tree_size": size,
                "root_hex": root,
                "leaf_index": index,
                "payer_b58": payer,
                "last_valid": valid,
            }

    def anchor_prepared_events(self, receipt_id: str, *, limit: int = 10) -> tuple[dict[str, Any], ...]:
        """Complete indexed prepared-event lookup for one receipt ID.

        Targets the receipt directly (never an oldest-first window scan) and
        fails closed with LedgerError on query error.
        """
        with self._lock:
            self._ensure_open()
            if not isinstance(receipt_id, str) or not receipt_id:
                raise ValueError("receipt_id required")
            if type(limit) is not int or limit < 1 or limit > 100:
                raise ValueError("limit out of range")
            try:
                cur = self._conn.cursor()
                rows = cur.execute(
                    "SELECT canonical_json FROM ledger_events"
                    " WHERE event_type = 'anchor.prepared'"
                    " AND json_extract(canonical_json, '$.payload.receipt_id') = ?"
                    " ORDER BY seq LIMIT ?;",
                    (receipt_id, limit),
                ).fetchall()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: prepared lookup failed") from None
            try:
                return tuple(json.loads(r[0]) for r in rows)
            except ValueError:
                raise LedgerCorruptError("stored prepared event unreadable") from None

    def has_anchor_event(self, event_type: str, signature: str) -> bool:
        """Indexed existence check for a terminal anchor event signature."""
        with self._lock:
            self._ensure_open()
            if not isinstance(event_type, str) or not event_type:
                raise ValueError("event_type required")
            if not isinstance(signature, str) or not signature:
                raise ValueError("signature required")
            try:
                cur = self._conn.cursor()
                row = cur.execute(
                    "SELECT 1 FROM ledger_events"
                    " WHERE event_type = ?"
                    " AND json_extract(canonical_json, '$.payload.signature') = ?"
                    " LIMIT 1;",
                    (event_type, signature),
                ).fetchone()
            except sqlite3.Error:
                raise LedgerError("ledger_unavailable: anchor event lookup failed") from None
            return row is not None

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                try:
                    if self._conn is not None:
                        self._conn.close()
                finally:
                    self._closed = True

    def __enter__(self) -> "QuantumTeleportationReceiptLedger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def proof_to_jsonable(proof: InclusionProof | Mapping[str, Any]) -> dict[str, Any]:
    """REST projection of a proof: bytes surface as explicit hex, never raw."""
    if isinstance(proof, Mapping):
        version = proof["version"]
        index = proof["leaf_index"]
        size = proof["tree_size"]
        preimage = bytes(proof["leaf_preimage_bytes"])
        siblings = list(proof["siblings"])
        expected = proof["expected_root_hex"]
        metadata = copy.deepcopy(dict(proof["metadata"]))
        eligible = bool(proof.get("eligible", False))
        leaf_hex = str(proof.get("leaf_digest_hex", ""))
    else:
        version = proof.version
        index = proof.leaf_index
        size = proof.tree_size
        preimage = bytes(proof.leaf_preimage_bytes)
        siblings = list(proof.siblings)
        expected = proof.expected_root_hex
        metadata = copy.deepcopy(dict(proof.metadata))
        eligible = bool(proof.eligible)
        leaf_hex = proof.leaf_digest_hex
    return {
        "version": version,
        "leaf_index": index,
        "tree_size": size,
        "leaf_preimage_hex": preimage.hex(),
        "siblings": [{"direction": d, "digest_hex": bytes(h).hex()} for d, h in siblings],
        "expected_root_hex": expected,
        "metadata": metadata,
        "eligible": eligible,
        "leaf_digest_hex": leaf_hex,
    }


def proof_from_jsonable(data: Mapping[str, Any]) -> InclusionProof:
    """Rebuild a proof from its REST projection with strict shape checks."""
    if not isinstance(data, Mapping):
        raise ValueError("proof projection must be a mapping")
    try:
        preimage = bytes.fromhex(str(data["leaf_preimage_hex"]))
        siblings = tuple(
            (entry["direction"], bytes.fromhex(str(entry["digest_hex"]))) for entry in data["siblings"]
        )
        metadata = copy.deepcopy(dict(data["metadata"]))
    except (KeyError, ValueError, TypeError):
        raise ValueError("malformed proof projection") from None
    return InclusionProof(
        version=int(data["version"]),
        leaf_index=int(data["leaf_index"]),
        tree_size=int(data["tree_size"]),
        leaf_preimage_bytes=preimage,
        siblings=siblings,
        expected_root_hex=str(data["expected_root_hex"]),
        metadata=metadata,
        eligible=bool(data.get("eligible", False)),
        leaf_digest_hex=str(data.get("leaf_digest_hex", "")),
    )


__all__ = [
    "QuantumTeleportationReceiptLedger",
    "QuantumQKDReceipt",
    "FrozenSnapshot",
    "InclusionProof",
    "LedgerError",
    "LedgerCorruptError",
    "LedgerClosedError",
    "canonical_event_bytes",
    "metadata_commit_hex",
    "classify_eligibility",
    "encode_execution_leaf",
    "decode_execution_leaf",
    "proof_to_jsonable",
    "proof_from_jsonable",
    "EMPTY_ROOT_HEX",
    "GENESIS_PREDECESSOR_HEX",
    "TELEPORT_LEAF_SIZE",
    "DRILL_LEAF_SIZE",
    "DB_FILENAME",
    "LEDGER_VERSION",
]
