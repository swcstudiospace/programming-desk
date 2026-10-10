"""Devnet SPL Memo publisher for quantum teleportation inclusion proofs.

Narrow, existing-dependency publisher: the application builds one fixed-shape
legacy transaction (dedicated payer + ``SetComputeUnitLimit(400000)`` + one
standard Memo carrying a ``QTELEPORT1:`` attestation), signs it once with a
dedicated external Devnet signer, submits it once with preflight and
``maxRetries=0``, then observes the *same* signature with bounded status and
exact readback admission. Processed/null/pending/error/mismatch/expiry is
never reported green, slots are never fabricated, and nothing is ever
resent or re-signed.

Single-send scope is the receipt: the first export pins the attested prefix,
and every later call for the same receipt observes that same signature, even
if the ledger has grown since (anchor lifecycle events advance the current
root). A newer prefix is attested by exporting a newer receipt, never by
re-signing an old one. Prerequisite failures happen before signing, persist
nothing, and never block a later funded attempt.

Only non-secret simulator commitments may be published. Confirmed Memo
transactions are one-way: correct a bad attestation with a later explicit
superseding record, never by rewriting chain history.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import stat
import struct
import zlib
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Mapping

import httpx

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except ImportError:  # pragma: no cover - dependency declared by the gateway
    Ed25519PrivateKey = None  # type: ignore[assignment]

from .quantum_ledger import (
    InclusionProof,
    LedgerError,
    QuantumTeleportationReceiptLedger,
)


DEVNET_GENESIS_HASH = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"
MEMO_PROGRAM_ID = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"
COMPUTE_UNITS = 400000
MAX_MEMO_BYTES = 1021
MAX_PACKET_BYTES = 1232
MAX_RPC_RESPONSE_BYTES = 64 * 1024
_U64_MAX = (1 << 64) - 1

RPC_URL_ENV = "QUANTUM_SOLANA_RPC_URL"
SIGNER_PATH_ENV = "QUANTUM_SOLANA_SIGNER_PATH"

ATTEST_PREFIX = "QTELEPORT1:"
ATTEST_VERSION = 1

_CONFIRMED_STATUSES = ("confirmed", "finalized")

# Bound for observing a rival claim-holder's prepared event after losing the
# atomic claim race. The winner persists synchronously, so contention settles
# in milliseconds; a placeholder that never resolves is an interrupted claim
# and fails closed without re-sign/resubmit.
_CLAIM_SETTLE_S = 2.0
_CLAIM_SETTLE_POLL_S = 0.01

class AnchorError(Exception):
    """Publisher failure carrying a stable code and an HTTP mapping hint."""

    def __init__(self, error_code: str, detail: str, *, http_status: int = 500) -> None:
        super().__init__(f"{error_code}: {detail}")
        self.error_code = error_code
        self.error_detail = detail
        self.http_status = http_status


class SignerError(AnchorError):
    def __init__(self, error_code: str, detail: str) -> None:
        super().__init__(error_code, detail, http_status=503)


class PayloadTooLargeError(AnchorError):
    def __init__(self, error_code: str, detail: str) -> None:
        super().__init__(error_code, detail, http_status=413)


class _RpcTransportError(AnchorError):
    def __init__(self, detail: str) -> None:
        super().__init__("rpc_transport_failed", detail, http_status=502)


class _RpcShapeError(AnchorError):
    def __init__(self, detail: str) -> None:
        super().__init__("rpc_shape_invalid", detail, http_status=502)


# ---------------------------------------------------------------------------
# Base58 / shortvec codecs (minimal, bounded, no new dependency)
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58_ALPHABET)}


def b58encode(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("b58encode needs nonempty bytes")
    raw = bytes(data)
    num = int.from_bytes(raw, "big")
    out = ""
    while num > 0:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    leading = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading + out


def b58decode(text: str, *, max_len: int = 128) -> bytes:
    # Base58 expands by about 1.37. The default cap stays 256 characters so
    # short account keys keep the old bound. Memo readback passes a larger
    # max_len because a full inclusion path does not fit in 256 characters.
    text_cap = max(256, max_len * 2)
    if not isinstance(text, str) or not 1 <= len(text) <= text_cap:
        raise ValueError("base58 text out of bounds")
    for ch in text:
        if ch not in _B58_INDEX:
            raise ValueError("invalid base58 character")
    num = 0
    for ch in text:
        num = num * 58 + _B58_INDEX[ch]
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    leading = len(text) - len(text.lstrip("1"))
    out = b"\x00" * leading + raw
    if len(out) > max_len:
        raise ValueError("base58 payload exceeds bound")
    return out


def shortvec_encode(value: int) -> bytes:
    if type(value) is not int or value < 0 or value > 0xFFFF:
        raise ValueError("shortvec needs u16")
    out = bytearray()
    rem = value
    while True:
        byte = rem & 0x7F
        rem >>= 7
        if rem:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def shortvec_decode(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(3):
        if offset >= len(data):
            raise ValueError("shortvec truncated")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("shortvec exceeds u16")


_MEMO_PROGRAM = b58decode(MEMO_PROGRAM_ID)
_COMPUTE_BUDGET_PROGRAM = b58decode(COMPUTE_BUDGET_PROGRAM_ID)


# ---------------------------------------------------------------------------
# Fixed legacy wire shape
# ---------------------------------------------------------------------------

def build_message(payer: bytes, blockhash: bytes, memo: bytes) -> bytes:
    """Assemble the exact legacy Message bytes for our one fixed shape."""
    if not isinstance(payer, (bytes, bytearray)) or len(payer) != 32:
        raise ValueError("payer must be 32 bytes")
    if not isinstance(blockhash, (bytes, bytearray)) or len(blockhash) != 32:
        raise ValueError("blockhash must be 32 bytes")
    if not isinstance(memo, (bytes, bytearray)) or not memo:
        raise ValueError("memo must be nonempty bytes")
    memo = bytes(memo)
    cu_data = b"\x02" + struct.pack("<I", COMPUTE_UNITS)
    cu_ix = (
        bytes((1,))
        + shortvec_encode(0)
        + shortvec_encode(len(cu_data))
        + cu_data
    )
    memo_ix = (
        bytes((2,))
        + shortvec_encode(1)
        + bytes((0,))
        + shortvec_encode(len(memo))
        + memo
    )
    return (
        bytes((1, 0, 2))
        + shortvec_encode(3)
        + bytes(payer)
        + _COMPUTE_BUDGET_PROGRAM
        + _MEMO_PROGRAM
        + bytes(blockhash)
        + shortvec_encode(2)
        + cu_ix
        + memo_ix
    )


def parse_message(message: bytes) -> dict[str, Any]:
    """Strictly parse a legacy Message; reject trailing bytes/odd shapes."""
    if not isinstance(message, (bytes, bytearray)) or len(message) < 3:
        raise ValueError("message too short")
    message = bytes(message)
    required, readonly_signed, readonly_unsigned = message[0], message[1], message[2]
    count, off = shortvec_decode(message, 3)
    if count == 0 or count > 64:
        raise ValueError("account count out of bounds")
    accounts = []
    for _ in range(count):
        if off + 32 > len(message):
            raise ValueError("accounts truncated")
        accounts.append(message[off : off + 32])
        off += 32
    if off + 32 > len(message):
        raise ValueError("blockhash truncated")
    blockhash = message[off : off + 32]
    off += 32
    ix_count, off = shortvec_decode(message, off)
    if ix_count == 0 or ix_count > 16:
        raise ValueError("instruction count out of bounds")
    instructions = []
    for _ in range(ix_count):
        if off >= len(message):
            raise ValueError("instruction truncated")
        program_index = message[off]
        off += 1
        acct_count, off = shortvec_decode(message, off)
        if off + acct_count > len(message):
            raise ValueError("instruction accounts truncated")
        ix_accounts = list(message[off : off + acct_count])
        off += acct_count
        data_len, off = shortvec_decode(message, off)
        if off + data_len > len(message):
            raise ValueError("instruction data truncated")
        instructions.append(
            {
                "program_index": program_index,
                "accounts": ix_accounts,
                "data": message[off : off + data_len],
            }
        )
        off += data_len
    if off != len(message):
        raise ValueError("trailing bytes after message")
    return {
        "required_signatures": required,
        "readonly_signed": readonly_signed,
        "readonly_unsigned": readonly_unsigned,
        "accounts": accounts,
        "blockhash": blockhash,
        "instructions": instructions,
    }


def verify_message_shape(message: bytes, *, payer: bytes, memo: bytes) -> None:
    """Local decode check: the bytes must be exactly our fixed shape."""
    try:
        parsed = parse_message(message)
    except ValueError as exc:
        raise AnchorError("local_wire_invalid", f"unparsable message: {exc}", http_status=500) from None
    if (
        parsed["required_signatures"] != 1
        or parsed["readonly_signed"] != 0
        or parsed["readonly_unsigned"] != 2
    ):
        raise AnchorError("local_wire_invalid", "message header mismatch", http_status=500)
    if parsed["accounts"] != [bytes(payer), _COMPUTE_BUDGET_PROGRAM, _MEMO_PROGRAM]:
        raise AnchorError("local_wire_invalid", "account list mismatch", http_status=500)
    instructions = parsed["instructions"]
    if len(instructions) != 2:
        raise AnchorError("local_wire_invalid", "instruction count mismatch", http_status=500)
    first, second = instructions
    if (
        first["program_index"] != 1
        or first["accounts"] != []
        or first["data"] != b"\x02" + struct.pack("<I", COMPUTE_UNITS)
    ):
        raise AnchorError("local_wire_invalid", "compute-budget instruction mismatch", http_status=500)
    if second["program_index"] != 2 or second["accounts"] != [0] or second["data"] != bytes(memo):
        raise AnchorError("local_wire_invalid", "memo instruction mismatch", http_status=500)


def sign_message(seed: bytes, message: bytes) -> bytes:
    if Ed25519PrivateKey is None:  # pragma: no cover
        raise AnchorError("signer_unavailable", "Ed25519 backend missing", http_status=503)
    return Ed25519PrivateKey.from_private_bytes(bytes(seed)).sign(bytes(message))


def verify_signature(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes(public_key)).verify(bytes(signature), bytes(message))
        return True
    except InvalidSignature:
        return False
    except ValueError:
        return False


def transaction_bytes(message: bytes, signature: bytes) -> bytes:
    if len(signature) != 64:
        raise ValueError("signature must be 64 bytes")
    return b"\x01" + bytes(signature) + bytes(message)


# ---------------------------------------------------------------------------
# Versioned attestation envelope: QTELEPORT1: + unpadded base64url of
# u16BE version | u64BE tree_size | u64BE leaf_index | 32B root |
# u16BE leaf_len + leaf | u16BE path_len + 32B siblings...
# ---------------------------------------------------------------------------

def encode_attestation(
    *,
    tree_size: int,
    leaf_index: int,
    root_hex: str,
    leaf: bytes,
    siblings: list[bytes] | tuple[bytes, ...] = (),
) -> str:
    if type(tree_size) is not int or tree_size <= 0 or tree_size > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("tree_size must be positive u64")
    if type(leaf_index) is not int or leaf_index < 0 or leaf_index >= tree_size:
        raise ValueError("leaf_index out of range")
    try:
        root = bytes.fromhex(root_hex)
    except (ValueError, TypeError):
        raise ValueError("root_hex must be 64 hex chars") from None
    if len(root) != 32:
        raise ValueError("root must be 32 bytes")
    leaf = bytes(leaf)
    if not 1 <= len(leaf) <= 0xFFFF:
        raise ValueError("leaf length out of bounds")
    sibs = [bytes(s) for s in siblings]
    if len(sibs) > 0xFFFF or any(len(s) != 32 for s in sibs):
        raise ValueError("siblings must be 32-byte digests")
    envelope = (
        ATTEST_VERSION.to_bytes(2, "big")
        + tree_size.to_bytes(8, "big")
        + leaf_index.to_bytes(8, "big")
        + root
        + len(leaf).to_bytes(2, "big")
        + leaf
        + len(sibs).to_bytes(2, "big")
        + b"".join(sibs)
    )
    return ATTEST_PREFIX + base64.urlsafe_b64encode(envelope).decode("ascii").rstrip("=")


def decode_attestation(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.startswith(ATTEST_PREFIX):
        raise ValueError("attestation must start with QTELEPORT1:")
    body = text[len(ATTEST_PREFIX):]
    if not body or len(body) > 4096:
        raise ValueError("attestation body out of bounds")
    try:
        envelope = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("attestation body is not base64url") from None
    if len(envelope) < 2 + 8 + 8 + 32 + 2 + 1 + 2:
        raise ValueError("attestation envelope truncated")
    version = int.from_bytes(envelope[0:2], "big")
    if version != ATTEST_VERSION:
        raise ValueError("unsupported attestation version")
    tree_size = int.from_bytes(envelope[2:10], "big")
    leaf_index = int.from_bytes(envelope[10:18], "big")
    root = envelope[18:50]
    leaf_len = int.from_bytes(envelope[50:52], "big")
    if 52 + leaf_len + 2 > len(envelope):
        raise ValueError("attestation leaf truncated")
    leaf = envelope[52 : 52 + leaf_len]
    rest = envelope[52 + leaf_len :]
    path_len = int.from_bytes(rest[0:2], "big")
    blobs = rest[2:]
    if len(blobs) != 32 * path_len:
        raise ValueError("attestation path length mismatch")
    siblings = [blobs[i * 32 : (i + 1) * 32] for i in range(path_len)]
    if tree_size <= 0 or leaf_index >= tree_size or not leaf:
        raise ValueError("attestation fields out of range")
    return {
        "version": version,
        "tree_size": tree_size,
        "leaf_index": leaf_index,
        "root_hex": root.hex(),
        "leaf": leaf,
        "siblings": siblings,
    }


def assert_wire_caps(memo: bytes) -> tuple[int, int]:
    """Enforce Memo<=1021 and exact packet<=1232 on real serialized bytes."""
    memo = bytes(memo)
    if len(memo) > MAX_MEMO_BYTES:
        raise PayloadTooLargeError(
            "payload_too_large",
            f"memo {len(memo)}B exceeds {MAX_MEMO_BYTES}B cap",
        )
    # Exact measurement: message length is independent of key values.
    measured = build_message(bytes(32), bytes(32), memo)
    packet_len = 1 + 64 + len(measured)
    if packet_len > MAX_PACKET_BYTES:
        raise PayloadTooLargeError(
            "payload_too_large",
            f"packet {packet_len}B exceeds {MAX_PACKET_BYTES}B cap",
        )
    return len(memo), packet_len


# ---------------------------------------------------------------------------
# Private signer loader (external dedicated Devnet resource only)
# ---------------------------------------------------------------------------

@dataclass
class SignerIdentity:
    public_key_bytes: bytes
    _seed: bytes = field(repr=False)

    def __repr__(self) -> str:  # never leak key material
        return f"SignerIdentity(public_key={self.public_key_bytes.hex()[:8]}...)"

    def sign(self, message: bytes) -> bytes:
        return sign_message(self._seed, message)


def load_signer(signer_path: str | None) -> SignerIdentity:
    """Open only the configured external signer; errors never name values."""
    if not signer_path or not isinstance(signer_path, str):
        raise SignerError("signer_not_configured", f"dedicated signer path is not configured ({SIGNER_PATH_ENV})")
    if len(signer_path) > 1024:
        raise SignerError("signer_unsafe", "configured signer reference rejected")
    abs_path = os.path.abspath(signer_path)
    try:
        entry = os.lstat(abs_path)
    except OSError:
        raise SignerError("signer_unreadable", "dedicated signer file is not accessible") from None
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise SignerError("signer_unsafe", "dedicated signer must be a regular non-symlink file")
    if entry.st_uid != os.geteuid() or entry.st_mode & 0o077:
        raise SignerError("signer_unsafe", "dedicated signer file must be owner-only and owner-held")
    parent = os.path.dirname(abs_path)
    try:
        parent_stat = os.lstat(parent)
    except OSError:
        raise SignerError("signer_unsafe", "dedicated signer parent is not accessible") from None
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or parent_stat.st_uid != os.geteuid()
        or parent_stat.st_mode & 0o077
    ):
        raise SignerError("signer_unsafe", "dedicated signer parent must be a private owner-held directory")
    try:
        fd = os.open(abs_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise SignerError("signer_unsafe", "dedicated signer open refused") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise SignerError("signer_unsafe", "dedicated signer changed under open")
        chunks = []
        remaining = 8193
        while remaining > 0:
            piece = os.read(fd, remaining)
            if not piece:
                break
            chunks.append(piece)
            remaining -= len(piece)
        content = b"".join(chunks)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if not content or len(content) > 8192:
        raise SignerError("signer_invalid", "dedicated signer content out of bounds")
    keypair: bytes | None = None
    if len(content) == 64:
        keypair = bytes(content)
    else:
        try:
            parsed = json.loads(content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise SignerError("signer_invalid", "dedicated signer content unrecognized") from None
        if (
            isinstance(parsed, list)
            and len(parsed) == 64
            and all(type(n) is int and 0 <= n <= 255 for n in parsed)
        ):
            keypair = bytes(parsed)
        else:
            raise SignerError("signer_invalid", "dedicated signer content unrecognized")
    seed, supplied_pub = keypair[:32], keypair[32:]
    try:
        derived = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )
    except ValueError:
        raise SignerError("signer_invalid", "dedicated signer seed rejected") from None
    if derived != supplied_pub:
        raise SignerError("signer_invalid", "dedicated signer public half mismatch")
    return SignerIdentity(public_key_bytes=bytes(supplied_pub), _seed=bytes(seed))


# ---------------------------------------------------------------------------
# Publication result + exporter
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorResult:
    status: str  # confirmed | failed | unknown
    signature: str | None
    slot: int | None
    anchored_root_hex: str
    anchored_tree_size: int
    leaf_index: int
    current_root_hex: str
    current_tree_size: int
    error_code: str | None = None
    error_detail: str | None = None
    http_status: int = 200

    @property
    def ok(self) -> bool:
        return self.status == "confirmed"


@dataclass(frozen=True)
class _Prepared:
    """Durable single-send guard: one signature, payer, expiry, and prefix per receipt."""

    signature: str
    payer_b58: str
    last_valid: int | None
    tree_size: int


class QuantumTeleportationAnchorExporter:
    """One-sign, one-send Devnet publisher with exact readback admission."""

    def __init__(
        self,
        ledger: QuantumTeleportationReceiptLedger,
        *,
        rpc_url: str | None = None,
        signer_path: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        confirmation_timeout_s: float = 30.0,
        poll_interval_s: float = 1.0,
        rpc_timeout_s: float = 10.0,
    ) -> None:
        if not isinstance(ledger, QuantumTeleportationReceiptLedger):
            raise ValueError("exporter needs the receipt ledger")
        if confirmation_timeout_s <= 0 or poll_interval_s <= 0 or rpc_timeout_s <= 0:
            raise ValueError("timeouts must be positive")
        self._ledger = ledger
        self._rpc_url = rpc_url if rpc_url is not None else os.environ.get(RPC_URL_ENV)
        self._signer_path = signer_path if signer_path is not None else os.environ.get(SIGNER_PATH_ENV)
        self._injected_client = http_client
        self._owned_client: httpx.AsyncClient | None = None
        self._rpc_timeout = float(rpc_timeout_s)
        self._confirmation_timeout = float(confirmation_timeout_s)
        self._poll_interval = float(poll_interval_s)
        self._rpc_id = 0
        self._prepared: dict[str, _Prepared] = {}
        # No per-receipt asyncio-lock registry: the shared single-send
        # authority is the atomic SQLite claim in the ledger (claim_anchor),
        # which serializes exporters across objects, coroutines, and
        # processes. Local locks cannot cover a second exporter object.

    async def aclose(self) -> None:
        if self._owned_client is not None:
            try:
                await self._owned_client.aclose()
            finally:
                self._owned_client = None

    def prepared_signature(self, receipt_id: str, tree_size: int | None = None) -> str | None:
        """Return the already-prepared public signature for a receipt, if any.

        An explicit tree_size pins the attested prefix and only matches the
        record prepared for that prefix; omitting it returns whatever prefix
        was actually published.
        """
        found = self.prepared_record(receipt_id, tree_size)
        return found.signature if found is not None else None

    def prepared_record(self, receipt_id: str, tree_size: int | None = None) -> _Prepared | None:
        """Return the durable single-send guard for a receipt, if any.

        Raises LedgerError when the ledger is unavailable: callers fail
        closed and never treat an outage as "no prepared signature".
        """
        hit = self._prepared.get(receipt_id)
        if hit is not None:
            return hit if tree_size is None or tree_size == hit.tree_size else None
        return self._find_prepared_in_ledger(receipt_id, tree_size)

    def _find_prepared_in_ledger(self, receipt_id: str, tree_size: int | None) -> _Prepared | None:
        # Complete indexed lookup by receipt ID: the prepared event carries
        # the actual persisted signature. A ledger outage raises LedgerError
        # (fail closed) instead of returning a miss that would permit a
        # second sign/send.
        events = self._ledger.anchor_prepared_events(receipt_id)
        for event in events:
            payload = event.get("payload") if isinstance(event, Mapping) else None
            if not isinstance(payload, Mapping):
                continue
            if payload.get("receipt_id") != receipt_id:
                continue
            if tree_size is not None and payload.get("tree_size") != tree_size:
                continue
            sig = payload.get("signature")
            payer = payload.get("payer")
            last_valid = payload.get("last_valid_block_height")
            size = payload.get("tree_size")
            if isinstance(sig, str) and sig and isinstance(payer, str) and payer and type(size) is int:
                if last_valid is not None and type(last_valid) is not int:
                    continue
                found = _Prepared(signature=sig, payer_b58=payer, last_valid=last_valid, tree_size=size)
                self._prepared[receipt_id] = found
                return found
        return None

    async def _await_prepared_event(self, receipt_id: str, tree_size: int) -> _Prepared | None:
        """Wait briefly for a rival claim-holder's prepared event to land.

        The winner signs and persists synchronously right after winning the
        claim, so this normally returns on the first poll. A placeholder
        whose event never lands (interrupted claim) resolves to None: fail
        closed with no re-sign and no resubmit.
        """
        deadline = monotonic() + _CLAIM_SETTLE_S
        while True:
            found = self._find_prepared_in_ledger(receipt_id, tree_size)
            if found is not None:
                return found
            if monotonic() >= deadline:
                return None
            await asyncio.sleep(_CLAIM_SETTLE_POLL_S)

    def _client(self) -> httpx.AsyncClient:
        if self._injected_client is not None:
            return self._injected_client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._rpc_timeout),
                follow_redirects=False,
            )
        return self._owned_client

    def _check_rpc_url(self) -> str:
        url = self._rpc_url
        if not url or not isinstance(url, str):
            raise SignerError("rpc_url_not_configured", f"Devnet RPC target is not configured ({RPC_URL_ENV})")
        if not url.lower().startswith("https://"):
            raise SignerError("rpc_url_rejected", "Devnet RPC target must be an HTTPS URL")
        return url

    async def _rpc(self, method: str, params: Any) -> Any:
        url = self._check_rpc_url()
        self._rpc_id += 1
        request_id = self._rpc_id
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        content = bytearray()
        try:
            # Bound wire bytes AND inflated bytes before JSON admission. Limit
            # inflation itself, rather than letting HTTPX allocate an arbitrary
            # decoded chunk before applying the application budget.
            deadline = monotonic() + self._rpc_timeout
            async with asyncio.timeout(self._rpc_timeout):
                async with self._client().stream(
                    "POST", url, json=body, headers={"Accept-Encoding": "gzip, deflate, identity"},
                ) as response:
                    if response.status_code != 200:
                        raise _RpcTransportError(f"{method} HTTP {response.status_code}")
                    if response.is_stream_consumed:
                        # Injected transports may supply an already-read reply.
                        if (
                            len(response.content) > MAX_RPC_RESPONSE_BYTES
                            or response.num_bytes_downloaded > MAX_RPC_RESPONSE_BYTES
                        ):
                            raise _RpcShapeError(f"{method} response exceeds 64 KiB")
                        content.extend(response.content)
                    else:
                        encoding = response.headers.get("content-encoding", "identity").strip().lower()
                        if encoding not in ("identity", "gzip", "deflate"):
                            raise _RpcShapeError(f"{method} response encoding unsupported")
                        decoder = (
                            zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
                            if encoding != "identity" else None
                        )
                        wire_bytes = 0
                        async for chunk in response.aiter_raw():
                            if monotonic() >= deadline:
                                raise TimeoutError
                            wire_bytes += len(chunk)
                            if wire_bytes > MAX_RPC_RESPONSE_BYTES:
                                raise _RpcShapeError(f"{method} response exceeds 64 KiB")
                            if decoder is not None:
                                chunk = decoder.decompress(chunk, MAX_RPC_RESPONSE_BYTES - len(content) + 1)
                            if len(content) + len(chunk) > MAX_RPC_RESPONSE_BYTES:
                                raise _RpcShapeError(f"{method} response exceeds 64 KiB")
                            content.extend(chunk)
                            if decoder is not None and decoder.unused_data:
                                raise _RpcShapeError(f"{method} compressed response has trailing data")
                        if decoder is not None and not decoder.eof:
                            raise _RpcShapeError(f"{method} compressed response truncated")
                    if monotonic() >= deadline:
                        raise TimeoutError
        except zlib.error:
            raise _RpcShapeError(f"{method} compressed response invalid") from None
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            raise _RpcTransportError(f"{method} transport failed: {type(exc).__name__}") from None
        try:
            decoded = json.loads(content)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise _RpcShapeError(f"{method} returned non-JSON") from None
        if (
            not isinstance(decoded, dict)
            or decoded.get("jsonrpc") != "2.0"
            or type(decoded.get("id")) is not int
            or decoded["id"] != request_id
            or ("result" in decoded) == ("error" in decoded)
        ):
            raise _RpcShapeError(f"{method} envelope invalid")
        if "error" in decoded:
            err = decoded["error"]
            if (
                not isinstance(err, dict)
                or type(err.get("code")) is not int
                or not isinstance(err.get("message"), str)
            ):
                raise _RpcShapeError(f"{method} error envelope invalid")
            raise _RpcTransportError(f"{method} rpc error {err['code']}: {err['message'][:200]}")
        return decoded["result"]

    async def export_commitment(
        self, receipt_id: str, *, tree_size: int | None = None
    ) -> AnchorResult:
        """Publish one frozen inclusion proof; repeated calls observe, never resend."""
        if not isinstance(receipt_id, str) or not receipt_id:
            return self._empty_fail("unknown_receipt", "receipt id required", 400)
        try:
            current_size = self._ledger.tree_size
            current_root = self._ledger.current_root_hex
        except Exception:
            return self._empty_fail("ledger_unavailable", "receipt ledger unavailable", 503)
        size = current_size if tree_size is None else tree_size
        if type(size) is not int or size <= 0 or size > current_size:
            return self._empty_fail("receipt_not_in_prefix", "requested prefix out of range", 400)
        try:
            proof = self._ledger.inclusion_proof(receipt_id, size)
        except (LookupError, ValueError):
            return self._empty_fail("unknown_receipt", "receipt is not part of the requested prefix", 400)
        except LedgerError:
            return self._empty_fail("ledger_unavailable", "receipt ledger failed integrity", 503)
        if proof.eligible is not True:
            return self._anchored_fail(
                "ineligible_leaf", "receipt is not a successful execution leaf", 400,
                proof, size, current_size, current_root,
            )
        if not self._ledger.verify_proof(proof):
            return self._anchored_fail(
                "invalid_proof", "receipt inclusion proof failed validation", 400,
                proof, size, current_size, current_root,
            )
        # Single-send gate: the memory fast-path, then the durable ledger
        # claim/prepared state shared across exporter objects and processes.
        # A ledger outage fails closed here, never as a fresh attempt.
        try:
            prepared = self._prepared.get(receipt_id) or self._find_prepared_in_ledger(receipt_id, None)
        except LedgerError:
            return self._empty_fail("ledger_unavailable", "receipt ledger unavailable", 503)
        if prepared is not None:
            # Already signed/sent for this receipt: observe the same
            # signature at its pinned prefix, never resign. Aged
            # confirmations whose recent status was pruned recover through
            # historical readback before any expired verdict.
            try:
                pinned = self._ledger.inclusion_proof(receipt_id, prepared.tree_size)
            except (LookupError, ValueError, LedgerError):
                return self._empty_fail("ledger_unavailable", "receipt ledger unavailable", 503)
            memo_text, memo_bytes = self._attestation_for(pinned)
            result = await self._observe(
                prepared.signature, pinned, prepared.tree_size, memo_text, memo_bytes,
                payer_b58=prepared.payer_b58, last_valid=prepared.last_valid,
                historical=True,
            )
            await self._record_terminal(result, pinned, receipt_id, prepared.tree_size, prepared.signature)
            return result
        # Fresh attempt: every prerequisite below fails BEFORE signing.
        memo_text, memo_bytes = self._attestation_for(proof)
        try:
            assert_wire_caps(memo_bytes)
        except PayloadTooLargeError as exc:
            return self._anchored_fail(
                "payload_too_large", exc.error_detail, 413,
                proof, size, current_size, current_root,
            )
        try:
            self._check_rpc_url()
        except AnchorError as exc:
            return self._anchored_fail(exc.error_code, exc.error_detail, exc.http_status,
                                       proof, size, current_size, current_root)
        try:
            signer = load_signer(self._signer_path)
        except AnchorError as exc:
            return self._anchored_fail(exc.error_code, exc.error_detail, exc.http_status,
                                       proof, size, current_size, current_root)
        payer = bytes(signer.public_key_bytes)
        payer_b58 = b58encode(payer)
        try:
            genesis = await self._rpc("getGenesisHash", [])
        except AnchorError as exc:
            return self._anchored_fail("genesis_lookup_failed", exc.error_detail, 502,
                                       proof, size, current_size, current_root)
        if genesis != DEVNET_GENESIS_HASH:
            return self._anchored_fail("wrong_genesis", "connected cluster is not the pinned Devnet", 503,
                                       proof, size, current_size, current_root)
        try:
            latest = await self._rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
            blockhash_b58, last_valid = self._parse_blockhash(latest)
            blockhash = b58decode(blockhash_b58)
            if len(blockhash) != 32:
                raise _RpcShapeError("blockhash is not 32 bytes")
        except AnchorError as exc:
            if isinstance(exc, (_RpcTransportError, _RpcShapeError)):
                code, detail = exc.error_code, exc.error_detail
            else:  # pragma: no cover - defensive; _parse_blockhash only raises AnchorError
                code, detail = "blockhash_lookup_failed", str(exc)
            return self._anchored_fail(code, detail, 502, proof, size, current_size, current_root)
        except ValueError as exc:
            return self._anchored_fail("blockhash_lookup_failed", str(exc), 502,
                                       proof, size, current_size, current_root)
        try:
            message = build_message(payer, blockhash, memo_bytes)
            verify_message_shape(message, payer=payer, memo=memo_bytes)
        except (ValueError, AnchorError) as exc:
            return self._anchored_fail("local_wire_invalid", str(exc), 500,
                                       proof, size, current_size, current_root)
        try:
            fee_value = await self._rpc("getFeeForMessage", [base64.b64encode(message).decode("ascii")])
        except AnchorError as exc:
            return self._anchored_fail("fee_lookup_failed", exc.error_detail, 502,
                                       proof, size, current_size, current_root)
        fee = self._parse_u64_or_null(fee_value, nested=True)
        if fee is None:
            return self._anchored_fail("fee_unavailable", "fee estimator returned null", 503,
                                       proof, size, current_size, current_root)
        try:
            balance_value = await self._rpc("getBalance", [payer_b58])
        except AnchorError as exc:
            return self._anchored_fail("balance_lookup_failed", exc.error_detail, 502,
                                       proof, size, current_size, current_root)
        balance = self._parse_u64_or_null(balance_value, nested=True)
        if balance is None:
            return self._anchored_fail("balance_lookup_failed", "balance shape invalid", 502,
                                       proof, size, current_size, current_root)
        if balance < fee:
            return self._anchored_fail("insufficient_balance", "payer cannot cover the exact fee", 503,
                                       proof, size, current_size, current_root)
        # Atomic single-send claim AFTER proof/genesis/message/fee/balance
        # prerequisites pass and BEFORE signing. The winner signs exactly
        # once below; a rival that loses this race observes the winner's
        # prepared state and never signs. No network await happens inside
        # the claim transaction.
        try:
            won = self._ledger.claim_anchor(
                receipt_id, tree_size=size, root_hex=proof.expected_root_hex,
                leaf_index=proof.leaf_index, payer_b58=payer_b58, last_valid=last_valid,
            )
        except LedgerError:
            return self._anchored_fail("ledger_unavailable", "receipt ledger unavailable", 503,
                                       proof, size, current_size, current_root)
        if not won:
            try:
                claimed = self._ledger.read_anchor_claim(receipt_id)
                if claimed is None:
                    raise LedgerError("anchor claim missing after conflict")
                existing = await self._await_prepared_event(receipt_id, claimed["tree_size"])
            except LedgerError:
                return self._anchored_fail("ledger_unavailable", "receipt ledger unavailable", 503,
                                           proof, size, current_size, current_root)
            if existing is None:
                current = self._ledger_current()
                return AnchorResult(
                    "unknown", None, None, claimed["root_hex"], claimed["tree_size"],
                    claimed["leaf_index"], current[1], current[0],
                    error_code="claim_pending",
                    error_detail="single-send claim held elsewhere; no local signature was created",
                    http_status=503,
                )
            self._prepared[receipt_id] = existing
            try:
                pinned = self._ledger.inclusion_proof(receipt_id, existing.tree_size)
            except (LookupError, ValueError, LedgerError):
                return self._empty_fail("ledger_unavailable", "receipt ledger unavailable", 503)
            memo_text, memo_bytes = self._attestation_for(pinned)
            result = await self._observe(
                existing.signature, pinned, existing.tree_size, memo_text, memo_bytes,
                payer_b58=existing.payer_b58, last_valid=existing.last_valid,
                historical=True,
            )
            await self._record_terminal(result, pinned, receipt_id, existing.tree_size, existing.signature)
            return result
        signature = signer.sign(message)
        if not verify_signature(payer, signature, message):
            return self._anchored_fail("local_wire_invalid", "local signature check failed", 500,
                                       proof, size, current_size, current_root)
        sig_b58 = b58encode(signature)
        try:
            await self._ledger.append_event(
                {
                    "event_type": "anchor.prepared",
                    "session_id": str(proof.metadata.get("session_id", "")),
                    "actor": "anchor-exporter",
                    "nodes": list(proof.metadata.get("nodes", [])),
                    "resources": list(proof.metadata.get("resources", [])),
                    "outcome": "prepared",
                    "payload": {
                        "receipt_id": receipt_id,
                        "tree_size": size,
                        "root_hex": proof.expected_root_hex,
                        "leaf_index": proof.leaf_index,
                        "signature": sig_b58,
                        "payer": payer_b58,
                        "last_valid_block_height": last_valid,
                    },
                }
            )
        except Exception:
            return self._anchored_fail("prepared_persist_failed", "prepared signature not durable", 503,
                                       proof, size, current_size, current_root)
        self._prepared[receipt_id] = _Prepared(
            signature=sig_b58, payer_b58=payer_b58, last_valid=last_valid, tree_size=size
        )
        tx_bytes = transaction_bytes(message, signature)
        try:
            sent = await self._rpc(
                "sendTransaction",
                [
                    base64.b64encode(tx_bytes).decode("ascii"),
                    {
                        "encoding": "base64",
                        "skipPreflight": False,
                        "preflightCommitment": "confirmed",
                        "maxRetries": 0,
                    },
                ],
            )
        except AnchorError as exc:
            result = self._anchored_unknown(
                "send_failed", exc.error_detail, 502, proof, size,
                self._ledger_current(), sig_b58,
            )
            await self._record_terminal(result, proof, receipt_id, size, sig_b58)
            return result
        if sent != sig_b58:
            result = self._anchored_unknown(
                "send_sig_mismatch", "node returned a different signature", 502,
                proof, size, self._ledger_current(), sig_b58,
            )
            await self._record_terminal(result, proof, receipt_id, size, sig_b58)
            return result
        await self._record_submitted(proof, receipt_id, size, sig_b58)
        result = await self._observe(
            sig_b58, proof, size, memo_text, memo_bytes,
            payer_b58=payer_b58, last_valid=last_valid,
        )
        await self._record_terminal(result, proof, receipt_id, size, sig_b58)
        return result

    def _attestation_for(self, proof: InclusionProof) -> tuple[str, bytes]:
        siblings = [bytes(h) for _, h in proof.siblings]
        memo_text = encode_attestation(
            tree_size=proof.tree_size,
            leaf_index=proof.leaf_index,
            root_hex=proof.expected_root_hex,
            leaf=bytes(proof.leaf_preimage_bytes),
            siblings=siblings,
        )
        return memo_text, memo_text.encode("utf-8")

    # -- observation (pure: returns results, records nothing) ----------------
    async def _observe(
        self,
        sig_b58: str,
        proof: InclusionProof,
        size: int,
        memo_text: str,
        memo_bytes: bytes,
        *,
        payer_b58: str,
        last_valid: int | None,
        historical: bool = False,
    ) -> AnchorResult:
        """Observe confirmation for one prepared signature, never resending.

        ``historical`` is set when observing an already-stored signature
        (repeat export or a rival claim-holder's prepared event): a null
        recent status may mean pruned history rather than absence, so the
        exact historical status search plus transaction readback runs before
        any expired/deadline verdict. Fresh post-send observation keeps the
        existing direct expiry semantics.
        """
        deadline = monotonic() + self._confirmation_timeout
        while True:
            try:
                statuses = await self._rpc("getSignatureStatuses", [[sig_b58]])
            except AnchorError as exc:
                return self._anchored_unknown("status_lookup_failed", exc.error_detail, 502,
                                              proof, size, self._ledger_current(), sig_b58)
            entry = self._parse_status_entry(statuses)
            if entry is None:
                return self._anchored_fail("status_lookup_failed", "status shape invalid", 502,
                                           proof, size, self._ledger_current_size(),
                                           self._ledger_current_root(), sig_b58)
            if isinstance(entry, Mapping):
                if entry.get("err") is None and entry.get("confirmationStatus") in _CONFIRMED_STATUSES:
                    return await self._readback(
                        entry, sig_b58, proof, size, memo_text, memo_bytes, payer_b58=payer_b58
                    )
                if entry.get("err") is not None:
                    return self._anchored_fail("status_tx_error", "cluster reports transaction error", 200,
                                               proof, size, self._ledger_current_size(),
                                               self._ledger_current_root(), sig_b58)
            # Unconfirmed (null entry or below confirmed): for a stored
            # signature, consult pruned history before expiry, never resend.
            if historical and not isinstance(entry, Mapping):
                recovered = await self._historical_readback(
                    sig_b58, proof, size, memo_text, memo_bytes, payer_b58=payer_b58
                )
                if recovered is not None:
                    return recovered
            height: int | None = None
            try:
                height_value = await self._rpc("getBlockHeight", [])
                height = self._parse_u64_or_null(height_value)
            except AnchorError:
                height = None
            if height is not None and last_valid is not None and height > last_valid:
                return self._anchored_unknown("expired", "blockhash validity window passed", 504,
                                              proof, size, self._ledger_current(), sig_b58)
            if monotonic() >= deadline:
                return self._anchored_unknown("confirmation_deadline", "confirmation not observed in time", 504,
                                              proof, size, self._ledger_current(), sig_b58)
            await asyncio.sleep(self._poll_interval)

    async def _historical_readback(
        self,
        sig_b58: str,
        proof: InclusionProof,
        size: int,
        memo_text: str,
        memo_bytes: bytes,
        *,
        payer_b58: str,
    ) -> AnchorResult | None:
        """Recover an aged confirmation from pruned status history.

        Returns a decisive AnchorResult (confirmed via exact readback, or a
        definitive on-chain mismatch/error) or None when history holds
        nothing and the caller falls through to expiry/deadline observation.
        Never signs, never resubmits.
        """
        try:
            hist = await self._rpc(
                "getSignatureStatuses", [[sig_b58], {"searchTransactionHistory": True}]
            )
        except AnchorError as exc:
            return self._anchored_unknown("status_lookup_failed", exc.error_detail, 502,
                                          proof, size, self._ledger_current(), sig_b58)
        hist_entry = self._parse_status_entry(hist)
        if hist_entry is None:
            return self._anchored_unknown("status_lookup_failed", "historical status shape invalid", 502,
                                          proof, size, self._ledger_current(), sig_b58)
        if isinstance(hist_entry, Mapping):
            if hist_entry["err"] is None and hist_entry["confirmationStatus"] in _CONFIRMED_STATUSES:
                return await self._readback(
                    hist_entry, sig_b58, proof, size, memo_text, memo_bytes, payer_b58=payer_b58
                )
            if hist_entry["err"] is not None:
                return self._anchored_fail("status_tx_error", "cluster reports transaction error", 200,
                                           proof, size, self._ledger_current_size(),
                                           self._ledger_current_root(), sig_b58)
        # Statuses may be fully pruned while the transaction remains readable
        # at the confirmed commitment: exact getTransaction readback decides.
        try:
            tx = await self._rpc(
                "getTransaction",
                [sig_b58, {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
            )
        except AnchorError:
            return None
        if not isinstance(tx, dict) or self._parse_u64_or_null(tx.get("slot")) is None:
            return None
        return await self._readback(
            {"slot": tx["slot"]}, sig_b58, proof, size, memo_text, memo_bytes, payer_b58=payer_b58
        )

    async def _readback(
        self,
        entry: Mapping[str, Any],
        sig_b58: str,
        proof: InclusionProof,
        size: int,
        memo_text: str,
        memo_bytes: bytes,
        *,
        payer_b58: str,
    ) -> AnchorResult:
        try:
            tx = await self._rpc(
                "getTransaction",
                [sig_b58, {"encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
            )
        except AnchorError as exc:
            return self._anchored_unknown("readback_failed", exc.error_detail, 502,
                                          proof, size, self._ledger_current(), sig_b58)
        if tx is None:
            return self._anchored_unknown("readback_null", "confirmed status without transaction data", 502,
                                          proof, size, self._ledger_current(), sig_b58)
        current = self._ledger_current()
        if not isinstance(tx, dict):
            return self._anchored_fail("readback_failed", "transaction shape invalid", 502,
                                       proof, size, current[0], current[1], sig_b58)
        slot = tx.get("slot")
        if self._parse_u64_or_null(slot) is None:
            return self._anchored_fail("readback_slot_missing", "observed slot invalid", 502,
                                       proof, size, current[0], current[1], sig_b58)
        entry_slot = entry.get("slot")
        if self._parse_u64_or_null(entry_slot) is None or entry_slot != slot:
            return self._anchored_fail("readback_slot_missing", "status slot disagrees with transaction slot", 502,
                                       proof, size, current[0], current[1], sig_b58)
        meta = tx.get("meta")
        if not isinstance(meta, dict) or "err" not in meta:
            return self._anchored_fail("readback_failed", "transaction meta.err missing", 502,
                                       proof, size, current[0], current[1], sig_b58)
        if meta["err"] is not None:
            return self._anchored_fail("readback_tx_error", "transaction executed with error", 200,
                                       proof, size, current[0], current[1], sig_b58)
        txn = tx.get("transaction")
        if not isinstance(txn, dict):
            return self._anchored_fail("readback_failed", "transaction body missing", 502,
                                       proof, size, current[0], current[1], sig_b58)
        signatures = txn.get("signatures")
        if signatures != [sig_b58]:
            return self._anchored_fail("readback_sig_mismatch", "transaction signature mismatch", 502,
                                       proof, size, current[0], current[1], sig_b58)
        message = txn.get("message")
        if not isinstance(message, dict):
            return self._anchored_fail("readback_failed", "transaction message missing", 502,
                                       proof, size, current[0], current[1], sig_b58)
        keys = message.get("accountKeys")
        if not isinstance(keys, list) or not keys or keys[0] != payer_b58:
            return self._anchored_fail("readback_payer_mismatch", "fee payer mismatch", 502,
                                       proof, size, current[0], current[1], sig_b58)
        if not self._message_shape_matches(message, keys):
            return self._anchored_fail("readback_shape_mismatch", "on-chain program/memo shape mismatch", 502,
                                       proof, size, current[0], current[1], sig_b58)
        if not self._memo_matches(message, keys, memo_text):
            return self._anchored_fail("readback_memo_mismatch", "on-chain memo bytes differ from the frozen proof",
                                       502, proof, size, current[0], current[1], sig_b58)
        # Bind the admitted json message (including its recent blockhash) to
        # the already-prepared signature, not just a claimed signature string.
        try:
            payer = b58decode(payer_b58, max_len=32)
            observed_message = build_message(
                payer, b58decode(message["recentBlockhash"], max_len=32), memo_bytes,
            )
            signature_matches = verify_signature(
                payer, b58decode(sig_b58, max_len=64), observed_message,
            )
        except ValueError:
            signature_matches = False
        if not signature_matches:
            return self._anchored_fail("readback_sig_mismatch", "signature does not bind the readback message", 502,
                                       proof, size, current[0], current[1], sig_b58)
        # Frozen-root check: the readback memo must attest the anchored prefix.
        try:
            attestation = decode_attestation(memo_text)
            decoded_leaf = bytes(attestation["leaf"])
        except ValueError:
            return self._anchored_fail("readback_memo_mismatch", "memo does not decode", 502,
                                       proof, size, current[0], current[1], sig_b58)
        if (
            attestation["root_hex"] != proof.expected_root_hex
            or attestation["tree_size"] != size
            or attestation["leaf_index"] != proof.leaf_index
            or decoded_leaf != bytes(proof.leaf_preimage_bytes)
        ):
            return self._anchored_fail("readback_memo_mismatch", "memo does not match the frozen prefix", 502,
                                       proof, size, current[0], current[1], sig_b58)
        return AnchorResult(
            status="confirmed",
            signature=sig_b58,
            slot=slot,
            anchored_root_hex=proof.expected_root_hex,
            anchored_tree_size=size,
            leaf_index=proof.leaf_index,
            current_root_hex=current[1],
            current_tree_size=current[0],
            http_status=200,
        )

    # -- helpers ----------------------------------------------------------
    def _receipt_id_for_proof(self, proof: InclusionProof) -> str:
        metadata = proof.metadata
        if isinstance(metadata, Mapping) and isinstance(metadata.get("event_id"), str):
            return str(metadata["event_id"])
        return ""

    def _parse_blockhash(self, latest: Any) -> tuple[str, int]:
        if not isinstance(latest, dict):
            raise _RpcShapeError("latest blockhash shape invalid")
        value = latest.get("value")
        if not isinstance(value, dict):
            raise _RpcShapeError("latest blockhash value invalid")
        blockhash = value.get("blockhash")
        last_valid = value.get("lastValidBlockHeight")
        if not isinstance(blockhash, str) or not blockhash:
            raise _RpcShapeError("blockhash missing")
        if self._parse_u64_or_null(last_valid) is None:
            raise _RpcShapeError("lastValidBlockHeight invalid")
        return blockhash, last_valid

    @staticmethod
    def _parse_u64_or_null(value: Any, *, nested: bool = False) -> int | None:
        if nested:
            if not isinstance(value, dict):
                return None
            value = value.get("value")
        if value is None:
            return None
        if type(value) is int and 0 <= value <= _U64_MAX:
            return value
        return None

    @staticmethod
    def _parse_status_entry(statuses: Any) -> Mapping[str, Any] | bool | None:
        # None -> malformed; False -> unconfirmed (null entry); Mapping -> entry.
        if not isinstance(statuses, dict):
            return None
        value = statuses.get("value")
        if not isinstance(value, list) or len(value) != 1:
            return None
        entry = value[0]
        if entry is None:
            return False
        if not isinstance(entry, dict):
            return None
        if (
            "err" not in entry
            or QuantumTeleportationAnchorExporter._parse_u64_or_null(entry.get("slot")) is None
            or "confirmations" not in entry
            or (
                entry["confirmations"] is not None
                and QuantumTeleportationAnchorExporter._parse_u64_or_null(entry["confirmations"]) is None
            )
            or "confirmationStatus" not in entry
            or (
                entry["confirmationStatus"] not in ("processed", *_CONFIRMED_STATUSES)
                and not (entry["confirmationStatus"] is None and entry["err"] is not None)
            )
        ):
            return None
        return entry

    def _message_shape_matches(self, message: Mapping[str, Any], keys: list) -> bool:
        try:
            if keys != [keys[0], COMPUTE_BUDGET_PROGRAM_ID, MEMO_PROGRAM_ID]:
                return False
            header = message.get("header")
            expected_header = {
                "numRequiredSignatures": 1,
                "numReadonlySignedAccounts": 0,
                "numReadonlyUnsignedAccounts": 2,
            }
            if (
                not isinstance(header, dict)
                or header != expected_header
                or any(type(header.get(key)) is not int for key in expected_header)
            ):
                return False
            blockhash = message.get("recentBlockhash")
            if not isinstance(blockhash, str) or len(b58decode(blockhash, max_len=32)) != 32:
                return False
            instructions = message.get("instructions")
            if not isinstance(instructions, list) or len(instructions) != 2:
                return False
            for index, accounts in ((1, []), (2, [0])):
                ix = instructions[index - 1]
                if (
                    not isinstance(ix, dict)
                    or type(ix.get("programIdIndex")) is not int
                    or ix["programIdIndex"] != index
                    or not isinstance(ix.get("accounts"), list)
                    or ix["accounts"] != accounts
                    or any(type(account) is not int for account in ix["accounts"])
                    or not isinstance(ix.get("data"), str)
                ):
                    return False
            return (
                b58decode(instructions[0]["data"], max_len=16)
                == b"\x02" + struct.pack("<I", COMPUTE_UNITS)
            )
        except (ValueError, TypeError, IndexError):
            return False

    def _memo_matches(self, message: Mapping[str, Any], keys: list, memo_text: str) -> bool:
        try:
            ix = message["instructions"][1]
            return (
                type(ix.get("programIdIndex")) is int
                and ix["programIdIndex"] == 2
                and keys[2] == MEMO_PROGRAM_ID
                and isinstance(ix.get("data"), str)
                and b58decode(ix["data"], max_len=MAX_MEMO_BYTES) == memo_text.encode("utf-8")
            )
        except (ValueError, TypeError, IndexError, KeyError):
            return False

    # -- result builders --------------------------------------------------
    def _empty_fail(self, code: str, detail: str, http: int) -> AnchorResult:
        try:
            size = self._ledger.tree_size
            root = self._ledger.current_root_hex
        except Exception:
            size, root = 0, ""
        return AnchorResult("failed", None, None, "", 0, -1, root, size,
                            error_code=code, error_detail=detail, http_status=http)

    def _sized_fail(self, code: str, detail: str, http: int, size: int,
                    cur_size: int, cur_root: str, index: int) -> AnchorResult:
        return AnchorResult("failed", None, None, "", size, index, cur_root, cur_size,
                            error_code=code, error_detail=detail, http_status=http)

    def _anchored_fail(self, code: str, detail: str, http: int, proof: InclusionProof,
                       size: int, cur_size: int, cur_root: str,
                       sig: str | None = None) -> AnchorResult:
        return AnchorResult("failed", sig, None, proof.expected_root_hex, size,
                            proof.leaf_index, cur_root, cur_size,
                            error_code=code, error_detail=detail, http_status=http)

    def _anchored_unknown(self, code: str, detail: str, http: int, proof: InclusionProof,
                          size: int, current: tuple[int, str], sig: str) -> AnchorResult:
        return AnchorResult("unknown", sig, None, proof.expected_root_hex, size,
                            proof.leaf_index, current[1], current[0],
                            error_code=code, error_detail=detail, http_status=http)

    def _ledger_current(self) -> tuple[int, str]:
        try:
            return self._ledger.tree_size, self._ledger.current_root_hex
        except Exception:
            return 0, ""

    def _ledger_current_size(self) -> int:
        return self._ledger_current()[0]

    def _ledger_current_root(self) -> str:
        return self._ledger_current()[1]

    # -- lifecycle records (awaited; failures keep the already-built result) --
    async def _record_submitted(self, proof: InclusionProof, receipt_id: str, size: int, sig: str) -> None:
        await self._append_anchor_event(
            "anchor.submitted", "submitted", proof, receipt_id, size, sig, None, None
        )

    async def _record_terminal(self, result: AnchorResult, proof: InclusionProof,
                               receipt_id: str, size: int, sig: str) -> None:
        if not receipt_id:
            receipt_id = self._receipt_id_for_proof(proof)
        event_type = f"anchor.{result.status}"
        # Indexed existence check by signature, never an oldest-first window
        # scan. A lookup outage still appends the audit event best-effort:
        # duplicates here are harmless audit rows, while the single-send
        # guard lives in the claim plus the prepared event.
        try:
            if self._ledger.has_anchor_event(event_type, sig):
                return
        except LedgerError:
            pass
        await self._append_anchor_event(
            event_type, result.status, proof, receipt_id, size, sig,
            result.error_code, result.slot,
        )

    async def _append_anchor_event(self, event_type: str, outcome: str, proof: InclusionProof,
                                   receipt_id: str, size: int, sig: str,
                                   error_code: str | None, slot: int | None) -> None:
        metadata = proof.metadata if isinstance(proof.metadata, Mapping) else {}
        payload: dict[str, Any] = {
            "receipt_id": receipt_id,
            "tree_size": size,
            "root_hex": proof.expected_root_hex,
            "leaf_index": proof.leaf_index,
            "signature": sig,
        }
        if error_code:
            payload["error_code"] = error_code
        if slot is not None:
            payload["slot"] = slot
        try:
            await self._ledger.append_event(
                {
                    "event_type": event_type,
                    "session_id": str(metadata.get("session_id", "")),
                    "actor": "anchor-exporter",
                    "nodes": list(metadata.get("nodes", [])),
                    "resources": list(metadata.get("resources", [])),
                    "outcome": outcome,
                    "payload": payload,
                }
            )
        except Exception:
            # The AnchorResult already carries the outcome; a ledger outage
            # must not rewrite it. The prepared signature stays durable.
            pass


__all__ = [
    "QuantumTeleportationAnchorExporter",
    "AnchorResult",
    "AnchorError",
    "SignerError",
    "PayloadTooLargeError",
    "SignerIdentity",
    "load_signer",
    "build_message",
    "parse_message",
    "verify_message_shape",
    "sign_message",
    "verify_signature",
    "transaction_bytes",
    "encode_attestation",
    "decode_attestation",
    "assert_wire_caps",
    "b58encode",
    "b58decode",
    "shortvec_encode",
    "shortvec_decode",
    "DEVNET_GENESIS_HASH",
    "MEMO_PROGRAM_ID",
    "COMPUTE_BUDGET_PROGRAM_ID",
    "COMPUTE_UNITS",
    "MAX_MEMO_BYTES",
    "MAX_PACKET_BYTES",
    "RPC_URL_ENV",
    "SIGNER_PATH_ENV",
    "ATTEST_PREFIX",
    "ATTEST_VERSION",
]
