"""Private numerical helpers for the trusted-device QKD simulator (phase 69-02).

Faithful distributed classical numerical simulator. No physical,
device-independent, or production-secrecy claim is made anywhere in this
module: every budget below is a simulator numerical budget for the
trusted-device model ``trusted-device-simulator-v1``.

Locked epsilon budget (declared before allocation, never refit)::

    EPS_PE  = 1e-9    phase-error estimation smoothing
    EPS_PA  = 1e-9    privacy-amplification smoothing
    EPS_COR = 2**-32  correctness (the 32-bit verification tag, counted once)
    EPS_W   = 1e-6    entanglement-witness (CHSH) estimation

``L_BRANCH_*`` bounds count every public key-dependent disclosure (acks,
correction counts, verification admission, extraction admission) against
fixed upper bounds declared before allocation. Phase-test samples are
removed from ``n`` and counted once. Public Toeplitz seeds are public
randomness, not key leakage.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Sequence

from .quantum_state import H, QuantumDensityMatrix, QuantumStateVector

__all__ = [
    "EPS_PE",
    "EPS_PA",
    "EPS_COR",
    "EPS_W",
    "L_TAG32",
    "L_BRANCH_TOTAL",
    "MAX_QKD_UNITS",
    "MAX_EXTRACT_BITS",
    "MIN_EXTRACT_BITS",
    "ReconciliationFailed",
    "binary_entropy",
    "validate_count",
    "validate_requested_bits",
    "qber_exceeds",
    "finite_sample_budget",
    "toeplitz_hash",
    "toeplitz_extract",
    "reconcile_candidates",
    "sample_chsh_outcome",
    "estimate_chsh",
    "node_commitment",
    "aggregate_commitment",
    "random_bits",
    "random_bytes",
]

#: Locked budget: phase-error estimation smoothing.
EPS_PE = 1e-9
#: Locked budget: privacy-amplification smoothing.
EPS_PA = 1e-9
#: Locked budget: correctness, i.e. the 32-bit verification tag (counted once).
EPS_COR = 2.0**-32
#: Locked budget: CHSH witness estimation.
EPS_W = 1e-6

#: Verification tag length in bits (the EPS_COR mechanism, counted once).
L_TAG32 = 32
#: Fixed upper bounds for public key-dependent disclosures, in bits.
L_BRANCH_ACK = 16
L_BRANCH_CORR = 16
L_BRANCH_VERIFY = 8
L_BRANCH_EXTRACT = 8
#: Sum of the branch disclosure bounds above.
L_BRANCH_TOTAL = L_BRANCH_ACK + L_BRANCH_CORR + L_BRANCH_VERIFY + L_BRANCH_EXTRACT

#: Maximum ``bit_length`` / ``pair_count`` per session (allocation guard).
MAX_QKD_UNITS = 20000
#: Maximum extracted key bits per session.
MAX_EXTRACT_BITS = 256
#: Minimum extracted key bits for an established session.
MIN_EXTRACT_BITS = 128

_COMMIT_DOMAIN = b"qkd-commit-v1"

#: CHSH correlator settings: A0=Z, A1=X, B0=(Z+X)/sqrt(2), B1=(Z-X)/sqrt(2).
CHSH_N_SETTINGS = 4

_C8 = math.cos(math.pi / 8.0)
_S8 = math.sin(math.pi / 8.0)
#: R_y(+pi/4): maps |0> onto the +1 eigenvector of (Z+X)/sqrt(2); the
#: B0 measurement rotation is its inverse ``_RY_M`` (eigenvector onto |0>).
_RY_P = ((_C8 + 0j, -_S8 + 0j), (_S8 + 0j, _C8 + 0j))
#: R_y(-pi/4): maps |0> onto the +1 eigenvector of (Z-X)/sqrt(2); the
#: B1 measurement rotation is its inverse ``_RY_P``.
_RY_M = ((_C8 + 0j, _S8 + 0j), (-_S8 + 0j, _C8 + 0j))


class ReconciliationFailed(Exception):
    """Single-error block reconciliation cannot be completed honestly."""


def binary_entropy(p: float) -> float:
    """Binary entropy ``h`` with ``h(0) == 0``; inputs are truncated at 1/2."""
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        raise ValueError(f"entropy argument must be numeric, got {p!r}")
    value = float(p)
    if not math.isfinite(value) or value < 0.0 or value > 0.5:
        raise ValueError(f"entropy argument must lie in [0, 1/2], got {p!r}")
    if value == 0.0:
        return 0.0
    if value == 0.5:
        return 1.0
    return -value * math.log2(value) - (1.0 - value) * math.log2(1.0 - value)


def validate_count(name: str, value: object, maximum: int = MAX_QKD_UNITS) -> int:
    """Validate a session size: reject bools/strings/negative/oversize.

    Zero is valid (the caller maps it to an ``insufficient_sample`` abort).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer in 0..{maximum}")
    if value < 0 or value > maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")
    return value


def validate_requested_bits(value: object) -> int:
    """Validate ``requested_bits``: an integer in 1..256."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("requested_bits must be an integer in 1..256")
    if not 1 <= value <= MAX_EXTRACT_BITS:
        raise ValueError("requested_bits must be an integer in 1..256")
    return value


def qber_exceeds(errors: object, samples: object) -> bool:
    """Exact integer QBER admission gate: abort iff ``100*errors > 11*sample``.

    Exactly 11/100 passes (``1100 > 1100`` is false); 12/100 aborts. NaN,
    infinite, missing, negative, or inconsistent inputs raise instead of
    ever reporting a stand-in QBER of 0.
    """
    for label, item in (("errors", errors), ("samples", samples)):
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{label} must be an integer count")
    if samples <= 0:  # type: ignore[operator]
        raise ValueError("samples must be positive to estimate QBER")
    if errors < 0 or errors > samples:  # type: ignore[operator]
        raise ValueError("errors must lie in 0..samples")
    return 100 * errors > 11 * samples  # type: ignore[operator]


def finite_sample_budget(
    n: int,
    k: int,
    q_phase: float,
    syndrome_len: int,
    requested_bits: int,
) -> dict[str, Any]:
    """Locked finite-sample budget (no refit after seeing results).

    ``n`` = undisclosed candidate bits after removing the ``k`` disjoint
    phase-test bits. Returns ``mu``, ``q_upper``, ``h_est``, ``h_after``,
    ``ell_max``, and ``ell`` (``min(requested, 256, ell_max)`` rounded down
    to a multiple of 8; 0 when the budget is empty).
    """
    for label, item in (("n", n), ("k", k), ("syndrome_len", syndrome_len)):
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(f"{label} must be a non-negative integer")
    if isinstance(q_phase, bool) or not isinstance(q_phase, (int, float)):
        raise ValueError("q_phase must be numeric")
    q_phase = float(q_phase)
    if not math.isfinite(q_phase) or q_phase < 0.0 or q_phase > 1.0:
        raise ValueError("q_phase must lie in [0, 1]")
    requested_bits = validate_requested_bits(requested_bits)
    if n == 0 or k == 0:
        return {
            "mu": None,
            "q_upper": None,
            "h_est": 0.0,
            "h_after": float(-syndrome_len - L_TAG32 - L_BRANCH_TOTAL),
            "ell_max": -1,
            "ell": 0,
        }
    mu = math.sqrt((n + k) / (n * k) * ((k + 1) / k) * math.log(4.0 / EPS_PE))
    q_upper = min(0.5, q_phase + mu)
    h_est = n * (1.0 - binary_entropy(q_upper))
    h_after = h_est - float(syndrome_len) - float(L_TAG32) - float(L_BRANCH_TOTAL)
    ell_max = math.floor(h_after - 2.0 * math.log2(1.0 / EPS_PA))
    ell = min(requested_bits, MAX_EXTRACT_BITS, ell_max) if ell_max > 0 else 0
    ell = max(0, (int(ell) // 8) * 8)
    return {
        "mu": mu,
        "q_upper": q_upper,
        "h_est": h_est,
        "h_after": h_after,
        "ell_max": ell_max,
        "ell": ell,
    }


def _check_bit_list(bits: Sequence[object], name: str) -> tuple[int, ...]:
    try:
        items = tuple(bits)
    except TypeError:
        raise ValueError(f"{name} must be a sequence of 0/1") from None
    for pos, bit in enumerate(items):
        if isinstance(bit, bool) or bit not in (0, 1):
            raise ValueError(f"{name}[{pos}] must be 0 or 1")
    return items  # type: ignore[return-value]


def toeplitz_hash(
    seed_bits: Sequence[object], input_bits: Sequence[object], out_len: int
) -> tuple[int, ...]:
    """Universal Toeplitz hash: ``T[i, j] = seed[n-1+i-j]``, parity output.

    Integer masks with ``bit_count`` parity; no dense matrix is formed.
    ``len(seed)`` must equal ``n + out_len - 1``. The seed is public
    randomness, not key leakage.
    """
    seed = _check_bit_list(seed_bits, "seed_bits")
    data = _check_bit_list(input_bits, "input_bits")
    if isinstance(out_len, bool) or not isinstance(out_len, int) or out_len <= 0:
        raise ValueError("out_len must be a positive integer")
    n = len(data)
    if n == 0:
        raise ValueError("input_bits must be non-empty")
    if len(seed) != n + out_len - 1:
        raise ValueError(
            f"seed must hold n+ell-1={n + out_len - 1} bits, got {len(seed)}"
        )
    data_int = 0
    for pos, bit in enumerate(data):
        if bit:
            data_int |= 1 << pos
    out: list[int] = []
    for i in range(out_len):
        mask = 0
        base = n - 1 + i
        for j in range(n):
            if seed[base - j]:
                mask |= 1 << j
        out.append((mask & data_int).bit_count() & 1)
    return tuple(out)


def toeplitz_extract(seed_bits: Sequence[object], input_bits: Sequence[object]) -> bytes:
    """Toeplitz randomness extraction to bytes (``out_len`` multiple of 8).

    The seed length determines the output: ``ell = len(seed) - n + 1`` and
    must be a positive multiple of 8.
    """
    data = _check_bit_list(input_bits, "input_bits")
    seed = _check_bit_list(seed_bits, "seed_bits")
    ell = len(seed) - len(data) + 1
    if ell <= 0 or ell % 8 != 0:
        raise ValueError("seed length must give a positive multiple-of-8 output")
    bits = toeplitz_hash(seed, data, ell)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return value.to_bytes(ell // 8, "big")


def bb84_state(bit: int, basis: str) -> Any:
    """Kernel signal state for one BB84 round: |bit> in the Z or X basis."""
    if isinstance(bit, bool) or bit not in (0, 1):
        raise ValueError("bit must be 0 or 1")
    if basis not in ("+", "x"):
        raise ValueError("basis must be '+' or 'x'")
    vec = QuantumStateVector((1 + 0j, 0j) if bit == 0 else (0j, 1 + 0j))
    if basis == "x":
        vec = vec.apply_single(H, 0)
    return vec


def _hamming_r(length: int) -> int:
    """Parity-check width of one block: ``ceil(log2(L+1))``."""
    if length < 1:
        raise ValueError("block length must be positive")
    return math.ceil(math.log2(length + 1))


def _as_permutation(order: Sequence[int], length: int) -> tuple[int, ...]:
    try:
        items = tuple(order)
    except TypeError:
        raise ReconciliationFailed("order must be a permutation of 0..L-1") from None
    if len(items) != length:
        raise ReconciliationFailed("order must be a permutation of 0..L-1")
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ReconciliationFailed("order must be a permutation of 0..L-1")
    if sorted(items) != list(range(length)):
        raise ReconciliationFailed("order must be a permutation of 0..L-1")
    return items


def _check_block_size(block_size: object) -> int:
    if isinstance(block_size, bool) or not isinstance(block_size, int) or not 1 <= block_size <= 63:
        raise ValueError("block_size must be an integer in 1..63")
    return block_size


def block_syndrome(block: Sequence[int], r: int) -> int:
    """Hamming syndrome of one block: XOR of 1-based positions holding 1."""
    syndrome = 0
    for pos, bit in enumerate(block):
        if bit:
            syndrome ^= pos + 1
    return syndrome & ((1 << r) - 1)


def syndrome_blocks(
    bits: Sequence[object],
    order: Sequence[int],
    block_size: int = 63,
) -> tuple[tuple[int, ...], int]:
    """Public block syndromes of one party's string under a public permutation.

    ``r`` is computed per block (``ceil(log2(L+1))``), never from the full
    string. Returns ``(syndromes, syndrome_bit_count)``. The bits themselves
    are not returned.
    """
    data = _check_bit_list(bits, "bits")
    if not data:
        raise ReconciliationFailed("empty candidate cannot be reconciled")
    width = _check_block_size(block_size)
    perm = _as_permutation(order, len(data))
    shuffled = [data[i] for i in perm]
    syndromes: list[int] = []
    total = 0
    for start in range(0, len(shuffled), width):
        chunk = shuffled[start : start + width]
        parity_bits = _hamming_r(len(chunk))
        syndromes.append(block_syndrome(chunk, parity_bits))
        total += parity_bits
    return tuple(syndromes), total


def correct_blocks(
    bits: Sequence[object],
    order: Sequence[int],
    syndromes: Sequence[object],
    block_size: int = 63,
    flip_positions: Sequence[int] = (),
) -> tuple[tuple[int, ...], int]:
    """Apply public syndromes to this party's string. Single-error blocks only.

    ``flip_positions`` are post-permutation indices (test seam). A syndrome
    that does not name a bit inside the block is left uncorrected so the
    verification tag can reject a multi-error block. Returns
    ``(corrected_bits, correction_count)`` in the original order.
    """
    data = list(_check_bit_list(bits, "bits"))
    if not data:
        raise ReconciliationFailed("empty candidate cannot be reconciled")
    width = _check_block_size(block_size)
    perm = _as_permutation(order, len(data))
    shuffled = [data[i] for i in perm]
    try:
        flips = tuple(flip_positions)
    except TypeError:
        raise ValueError("flip_positions must be a sequence of indices") from None
    for pos in flips:
        if isinstance(pos, bool) or not isinstance(pos, int) or not 0 <= pos < len(shuffled):
            raise ValueError("flip_positions must hold indices in 0..L-1")
        shuffled[pos] ^= 1
    try:
        announced = tuple(syndromes)
    except TypeError:
        raise ReconciliationFailed("syndromes must be a sequence of integers") from None
    expected = math.ceil(len(shuffled) / width)
    if len(announced) != expected:
        raise ReconciliationFailed("syndrome block count does not match the string")
    corrections = 0
    for index, start in enumerate(range(0, len(shuffled), width)):
        chunk = shuffled[start : start + width]
        parity_bits = _hamming_r(len(chunk))
        announced_bits = announced[index]
        if isinstance(announced_bits, bool) or not isinstance(announced_bits, int):
            raise ReconciliationFailed("syndrome entries must be integers")
        error_pos = block_syndrome(chunk, parity_bits) ^ announced_bits
        if error_pos == 0:
            continue
        if 1 <= error_pos <= len(chunk):
            shuffled[start + error_pos - 1] ^= 1
            corrections += 1
    corrected = [0] * len(data)
    for new_pos, old_pos in enumerate(perm):
        corrected[old_pos] = shuffled[new_pos]
    return tuple(corrected), corrections


def reconcile_candidates(
    alice_bits: Sequence[object],
    bob_bits: Sequence[object],
    rng: Any,
    *,
    block_size: int = 63,
    flip_positions: Sequence[int] = (),
) -> tuple[tuple[int, ...], int, int, int]:
    """Shuffled block Hamming reconciliation on Bob's candidate string.

    The permutation is public randomness drawn from ``rng``. Each block is at
    most 63 bits and announces ``r = ceil(log2(L+1))`` parity bits of its own
    length. Single-error correction only. ``flip_positions`` injects faults
    at post-permutation indices. Returns
    ``(corrected_bob, syndrome_len, block_count, corrections)`` in the
    original order. Residual multi-errors stay for the verification tag.
    """
    alice = _check_bit_list(alice_bits, "alice_bits")
    bob = _check_bit_list(bob_bits, "bob_bits")
    if len(alice) != len(bob):
        raise ReconciliationFailed("candidate strings differ in length")
    if not alice:
        raise ReconciliationFailed("empty candidate cannot be reconciled")
    order = list(range(len(alice)))
    rng.shuffle(order)
    syndromes, syndrome_len = syndrome_blocks(alice, order, block_size)
    corrected, corrections = correct_blocks(
        bob, order, syndromes, block_size, flip_positions
    )
    return corrected, syndrome_len, len(syndromes), corrections


def sample_chsh_outcome(
    rho: Any, setting_a: int, setting_b: int, rng: Any
) -> tuple[int, int]:
    """Sample one CHSH round from a two-qubit density through the kernel.

    Settings: A0=Z, A1=X, B0=(Z+X)/sqrt(2), B1=(Z-X)/sqrt(2). Each
    observable is diagonalized with a kernel unitary (``H`` for X,
    ``R_y(+/-pi/4)`` for the tilted Bob settings) and then Born-sampled
    with ``rng``. Returns ``(a_bit, b_bit)``.
    """
    if setting_a not in (0, 1):
        raise ValueError("setting_a must be 0 or 1")
    if setting_b not in (0, 1):
        raise ValueError("setting_b must be 0 or 1")
    if not isinstance(rho, QuantumDensityMatrix) or rho.qubits != 2:
        raise ValueError("CHSH sampling needs a two-qubit density")
    gate_a = H if setting_a == 1 else None
    # Diagonalize first: the measurement rotation maps the observable's +1
    # eigenvector onto |0> (the inverse of the eigenvector preparation).
    gate_b = _RY_M if setting_b == 0 else _RY_P
    evolved = rho
    if gate_a is not None:
        evolved = evolved.apply_single(gate_a, 0)
    evolved = evolved.apply_single(gate_b, 1)
    branch = evolved.measure_z((0, 1), rng)
    a_bit, b_bit = branch.bits
    return int(a_bit), int(b_bit)


def estimate_chsh(records: Sequence[tuple[int, int, int]]) -> dict[str, Any]:
    """CHSH estimator over ``(setting_index, a_bit, b_bit)`` records.

    ``S = E00 + E01 + E10 - E11`` from observed +/-1 products with
    ``setting_index = 2*a_setting + b_setting``. All four buckets must be
    non-empty (else ``ValueError``). ``S_lower = |S| - sum_b
    sqrt(2*ln(8/EPS_W)/m_b)``; ``passed`` is ``S_lower > 2``. The actual
    density is kept by the caller; no Werner reconstruction is performed.
    """
    buckets: dict[int, list[int]] = {0: [], 1: [], 2: [], 3: []}
    for entry in records:
        try:
            setting, a_bit, b_bit = entry
        except (TypeError, ValueError):
            raise ValueError("CHSH record must be (setting, a_bit, b_bit)") from None
        if setting not in buckets:
            raise ValueError("CHSH setting must lie in 0..3")
        if a_bit not in (0, 1) or b_bit not in (0, 1):
            raise ValueError("CHSH outcomes must be 0/1")
        buckets[setting].append(1 if a_bit == b_bit else -1)
    for setting, products in buckets.items():
        if not products:
            raise ValueError(f"CHSH bucket {setting} is empty")
    means = {s: math.fsum(p) / len(p) for s, p in buckets.items()}
    s_value = means[0] + means[1] + means[2] - means[3]
    bound = sum(
        math.sqrt(2.0 * math.log(8.0 / EPS_W) / len(buckets[s])) for s in buckets
    )
    s_lower = abs(s_value) - bound
    return {
        "S": s_value,
        "S_lower": s_lower,
        "counts": {s: len(buckets[s]) for s in buckets},
        "passed": bool(s_lower > 2.0),
    }


def node_commitment(
    node_id: str, session_id: str, blinding: bytes, key: bytes
) -> str:
    """``SHA256(b"qkd-commit-v1" || node_id || session_id || blinding || key)``.

    The blinding never leaves the node; only the hex digest is public.
    """
    if not isinstance(blinding, (bytes, bytearray)) or len(blinding) != 32:
        raise ValueError("blinding must be 32 bytes")
    if not isinstance(key, (bytes, bytearray)) or not key:
        raise ValueError("key must be non-empty bytes")
    digest = hashlib.sha256(
        _COMMIT_DOMAIN + node_id.encode() + session_id.encode() + bytes(blinding) + bytes(key)
    )
    return digest.hexdigest()


def aggregate_commitment(commit_alice_hex: str, commit_bob_hex: str) -> str:
    """``SHA256(commit_alice || commit_bob)`` over the raw 32-byte digests."""
    try:
        raw = bytes.fromhex(commit_alice_hex) + bytes.fromhex(commit_bob_hex)
    except ValueError:
        raise ValueError("commitments must be hex") from None
    if len(raw) != 64:
        raise ValueError("commitments must each be 32 bytes")
    return hashlib.sha256(raw).hexdigest()


def random_bits(rng: Any, count: int) -> tuple[int, ...]:
    """Draw ``count`` unbiased bits from ``rng.random()`` only."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    return tuple(1 if rng.random() < 0.5 else 0 for _ in range(count))


def random_bytes(rng: Any, count: int) -> bytes:
    """Draw ``count`` bytes from ``rng.random()`` only (test-seam friendly)."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    return bytes(int(rng.random() * 256) for _ in range(count))
