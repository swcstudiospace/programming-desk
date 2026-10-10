"""Bounded synchronous numerical kernel for the faithful distributed simulator.

Phase 68-01 (decision D-01): immutable 1--4 qubit state vectors and density
matrices, explicit gate / measurement / partial-trace operations, Bell
descriptors with Pauli frames, and Werner-noise construction.  This module
performs no I/O, holds no shared mutable state, and depends only on the
Python standard library.

Conventions (frozen for all downstream consumers):

* Big-endian qubit order: in ``tensor`` operands appear left-to-right and
  qubit 0 is the leftmost (most significant) bit.  The basis index bit for
  qubit ``q`` of an ``n``-qubit system is ``(index >> (n - 1 - q)) & 1``.
* ``QuantumStateVector.amplitudes`` is a ``tuple[complex, ...]`` of length
  ``2 ** qubits``; ``QuantumDensityMatrix.rows`` is a
  ``tuple[tuple[complex, ...], ...]`` of shape ``2 ** qubits`` square.
* Numerical tolerances below are acceptance windows for floating-point
  noise only.  Invalid inputs are rejected, never mutated, clamped, or
  replaced with a fallback state.

Numerical tolerance (documented, applied to validation only):

* ``NORM_TOLERANCE`` -- squared state-vector norm satisfies ``|norm**2 - 1|``.
* ``TRACE_TOLERANCE`` -- density trace satisfies ``|Re(tr) - 1|``.
* ``HERMITICITY_TOLERANCE`` -- max ``|rho[i][j] - conj(rho[j][i])|``.
* ``POSITIVITY_TOLERANCE`` -- smallest eigenvalue must be ``>= -tol``.
* ``UNITARY_TOLERANCE`` -- gate ``G`` must satisfy ``G G^dagger ~= I``.

Every operation revalidates its result against the same absolute windows.
Near-limit input errors can accumulate under tensoring or conditioning and
then fail closed; no constructor or operation silently renormalizes caller
data. Only nonpositive Born weights are omitted, not rare positive outcomes.
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Protocol, Sequence, Tuple

__all__ = [
    "BELL_KINDS",
    "H",
    "I",
    "S",
    "X",
    "Z",
    "HERMITICITY_TOLERANCE",
    "MAX_QUBITS",
    "NORM_TOLERANCE",
    "POSITIVITY_TOLERANCE",
    "RNGProtocol",
    "TRACE_TOLERANCE",
    "UNITARY_TOLERANCE",
    "BellState",
    "MeasurementBranch",
    "QuantumDensityMatrix",
    "QuantumStateVector",
    "werner_twirl",
]

#: Qubit dimensions supported by the kernel (2..16 amplitudes).
MAX_QUBITS = 4

#: Documented validation tolerances (see module docstring).
NORM_TOLERANCE = 1e-9
TRACE_TOLERANCE = 1e-9
HERMITICITY_TOLERANCE = 1e-9
POSITIVITY_TOLERANCE = 1e-9
UNITARY_TOLERANCE = 1e-9

#: Validated Bell wire-kind strings (same spellings as the existing
#: ``BellStateType`` values, taken as plain strings so this module never
#: imports ``quantum_teleportation`` and no import cycle is created).
BELL_KINDS: Tuple[str, ...] = ("PHI_PLUS", "PHI_MINUS", "PSI_PLUS", "PSI_MINUS")

#: Pauli-frame ``(x, z)`` per Bell kind.  The kind is generated from
#: ``|Phi+>`` by applying ``X`` ``x`` times then ``Z`` ``z`` times on the
#: second qubit (global sign is physically irrelevant).
_BELL_FRAMES = {
    "PHI_PLUS": (0, 0),
    "PHI_MINUS": (0, 1),
    "PSI_PLUS": (1, 0),
    "PSI_MINUS": (1, 1),
}

Gate2 = Tuple[Tuple[complex, complex], Tuple[complex, complex]]

I: Gate2 = ((1 + 0j, 0j), (0j, 1 + 0j))
X: Gate2 = ((0j, 1 + 0j), (1 + 0j, 0j))
Z: Gate2 = ((1 + 0j, 0j), (0j, -1 + 0j))
_SQRT1_2 = 1.0 / math.sqrt(2.0)
H: Gate2 = (
    (complex(_SQRT1_2), complex(_SQRT1_2)),
    (complex(_SQRT1_2), complex(-_SQRT1_2)),
)
S: Gate2 = ((1 + 0j, 0j), (0j, 1j))


class RNGProtocol(Protocol):
    """Minimal randomness seam: the only nondeterminism source.

    Only ``random()`` is ever called, and its result must lie in
    ``[0, 1)``.  Production default is ``secrets.SystemRandom``; tests
    inject scripted deterministic doubles.
    """

    def random(self) -> float: ...  # pragma: no cover - protocol shape


def _reject_bool(value: object, name: str) -> None:
    if isinstance(value, bool):
        raise TypeError(f"{name} must not be a bool")


def _as_complex(value: object, name: str) -> complex:
    """Validate one numeric entry and return it as ``complex``."""
    _reject_bool(value, name)
    if isinstance(value, complex):
        result = value
    elif isinstance(value, (int, float)):
        result = complex(value)
    else:
        raise TypeError(
            f"{name} must be a real or complex number, got {type(value).__name__}"
        )
    if not (math.isfinite(result.real) and math.isfinite(result.imag)):
        raise ValueError(f"{name} must be finite, got {result!r}")
    return result


def _as_fidelity(value: object, name: str) -> float:
    """Validate a real scalar in ``[0, 1]`` (bools/strings rejected)."""
    _reject_bool(value, name)
    if isinstance(value, complex):
        raise TypeError(f"{name} must be a real scalar, got complex")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"{name} must be a real scalar, got {type(value).__name__}"
        )
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1], got {result!r}")
    return result


def _as_qubit_index(value: object, n_qubits: int, name: str) -> int:
    _reject_bool(value, name)
    if not isinstance(value, int):
        raise TypeError(
            f"{name} must be an int qubit index, got {type(value).__name__}"
        )
    if not 0 <= value < n_qubits:
        raise ValueError(
            f"{name}={value} out of range for a {n_qubits}-qubit system"
        )
    return value


def _dimension_to_qubits(length: int, name: str) -> int:
    for qubits in range(1, MAX_QUBITS + 1):
        if 2**qubits == length:
            return qubits
    raise ValueError(
        f"{name} has length {length}: kernel supports 1-{MAX_QUBITS} qubits "
        f"(dimensions {[2**q for q in range(1, MAX_QUBITS + 1)]})"
    )


def _qubit_bit(index: int, qubit: int, n_qubits: int) -> int:
    return (index >> (n_qubits - 1 - qubit)) & 1


def _with_qubit_bit(index: int, qubit: int, n_qubits: int, value: int) -> int:
    mask = 1 << (n_qubits - 1 - qubit)
    return (index | mask) if value else (index & ~mask)


def _validate_gate(gate: object) -> Gate2:
    if isinstance(gate, (str, bytes)) or not isinstance(gate, Sequence):
        raise TypeError("gate must be a 2x2 nested sequence of numbers")
    rows = list(gate)
    if len(rows) != 2:
        raise ValueError("gate must be 2x2")
    checked = []
    for r, row in enumerate(rows):
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
            raise TypeError(f"gate row {r} must be a length-2 sequence")
        cells = list(row)
        if len(cells) != 2:
            raise ValueError("gate must be 2x2")
        checked.append((_as_complex(cells[0], f"gate[{r}][0]"), _as_complex(cells[1], f"gate[{r}][1]")))
    g = ((checked[0][0], checked[0][1]), (checked[1][0], checked[1][1]))
    # Unitarity: G G^dagger == I within tolerance; non-unitary
    # "gates" would silently break norm/positivity invariants.
    for i in range(2):
        for j in range(2):
            entry = g[i][0] * g[j][0].conjugate() + g[i][1] * g[j][1].conjugate()
            want = 1.0 if i == j else 0.0
            if abs(entry - want) > UNITARY_TOLERANCE:
                raise ValueError("gate must be unitary within 1e-9")
    return g


def _matmul2(a: Gate2, b: Gate2) -> Gate2:
    return (
        (
            a[0][0] * b[0][0] + a[0][1] * b[1][0],
            a[0][0] * b[0][1] + a[0][1] * b[1][1],
        ),
        (
            a[1][0] * b[0][0] + a[1][1] * b[1][0],
            a[1][0] * b[0][1] + a[1][1] * b[1][1],
        ),
    )


def _real_symmetric_eigvals(matrix: Sequence[Sequence[float]]) -> list:
    """Eigenvalues via maximum-pivot Jacobi rotations; failures are rejected."""
    n = len(matrix)
    a = [list(map(float, row)) for row in matrix]
    for _ in range(100 * n * n):
        p, q, biggest = 0, 1, 0.0
        for i in range(n):
            for j in range(i + 1, n):
                if abs(a[i][j]) > biggest:
                    p, q, biggest = i, j, abs(a[i][j])
        if biggest < 1e-13:
            if any(not math.isfinite(value) for row in a for value in row):
                raise ValueError("density eigensolver produced nonfinite values")
            return [a[i][i] for i in range(n)]
        theta = 0.5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        a[p][p] = c * c * app - 2.0 * c * s * apq + s * s * aqq
        a[q][q] = s * s * app + 2.0 * c * s * apq + c * c * aqq
        a[p][q] = a[q][p] = 0.0
        for r in range(n):
            if r != p and r != q:
                arp, arq = a[r][p], a[r][q]
                a[r][p] = a[p][r] = c * arp - s * arq
                a[r][q] = a[q][r] = s * arp + c * arq
    raise ValueError("density eigensolver did not converge")


def _hermitian_min_eigenvalue(rows: Sequence[Sequence[complex]]) -> float:
    """Smallest eigenvalue of a Hermitian matrix (stdlib Jacobi kernel).

    Maps the ``n``-dimensional Hermitian input to its ``2n``-dimensional
    real symmetric representation (whose spectrum doubles each
    eigenvalue) and diagonalizes that with maximum-pivot Jacobi rotations.
    The validity predicate uses the Hermitian part without rewriting the
    stored rows, so tolerated asymmetry cannot make validity basis-dependent.
    """
    n = len(rows)
    size = 2 * n
    real = [[0.0] * size for _ in range(size)]
    for i in range(n):
        for j in range(n):
            entry = 0.5 * complex(rows[i][j]) + 0.5 * complex(rows[j][i]).conjugate()
            real[i][j] = entry.real
            real[i][j + n] = -entry.imag
            real[i + n][j] = entry.imag
            real[i + n][j + n] = entry.real
    return min(_real_symmetric_eigvals(real))


@dataclass(frozen=True, slots=True)
class QuantumStateVector:
    """Immutable normalized pure state of 1--4 qubits (big-endian)."""

    amplitudes: Tuple[complex, ...]

    def __post_init__(self) -> None:
        raw = self.amplitudes
        if isinstance(raw, (str, bytes)):
            raise TypeError("amplitudes must be a sequence of numbers")
        try:
            items = tuple(raw)
        except TypeError:
            raise TypeError("amplitudes must be a sequence of numbers")
        if len(items) == 0:
            raise ValueError("amplitudes must be non-empty (1-4 qubits)")
        checked = tuple(_as_complex(v, f"amplitudes[{i}]") for i, v in enumerate(items))
        _dimension_to_qubits(len(checked), "amplitudes")
        squared_norm = math.fsum(a.real * a.real + a.imag * a.imag for a in checked)
        if not math.isfinite(squared_norm) or abs(squared_norm - 1.0) > NORM_TOLERANCE:
            raise ValueError("state vector must have unit squared norm")
        object.__setattr__(self, "amplitudes", checked)

    @property
    def qubits(self) -> int:
        """Number of qubits (big-endian: qubit 0 is the leftmost bit)."""
        return _dimension_to_qubits(len(self.amplitudes), "amplitudes")

    @property
    def norm(self) -> float:
        """Euclidean norm of the amplitude vector (1 within tolerance)."""
        return math.sqrt(sum(abs(a) ** 2 for a in self.amplitudes))

    @classmethod
    def from_qubit(cls, alpha: object, beta: object) -> "QuantumStateVector":
        """Validated normalized one-qubit state from ``(alpha, beta)``.

        Normalization is scale-first: entries are divided by the largest
        absolute real/imaginary *component* before the norm is taken, so
        finite but huge inputs (e.g. ``1e308``) cannot overflow through
        ``complex.__abs__`` (which may overflow on finite huge
        components).  Zero vectors, nonfinite entries, bools, and strings
        are rejected, never replaced with ``|0>``.
        """
        a = _as_complex(alpha, "alpha")
        b = _as_complex(beta, "beta")
        scale = max(abs(a.real), abs(a.imag), abs(b.real), abs(b.imag))
        if scale == 0.0:
            raise ValueError("from_qubit rejects the zero vector")
        a_scaled = a / scale
        b_scaled = b / scale
        norm = math.sqrt(abs(a_scaled) ** 2 + abs(b_scaled) ** 2)
        return cls((a_scaled / norm, b_scaled / norm))

    def tensor(self, other: "QuantumStateVector") -> "QuantumStateVector":
        """Kronecker product; ``self`` is the left (more significant) factor."""
        if not isinstance(other, QuantumStateVector):
            raise TypeError("tensor operand must be a QuantumStateVector")
        if self.qubits + other.qubits > MAX_QUBITS:
            raise ValueError("tensor product exceeds 4 qubits")
        return QuantumStateVector(
            tuple(a * b for a in self.amplitudes for b in other.amplitudes)
        )

    def apply_single(self, gate: object, target: int) -> "QuantumStateVector":
        """Apply a 2x2 unitary ``gate`` to ``target`` (indexed, no full unitary)."""
        g = _validate_gate(gate)
        n = self.qubits
        q = _as_qubit_index(target, n, "target")
        mask = 1 << (n - 1 - q)
        amps = self.amplitudes
        out: list = [0j] * len(amps)
        for i in range(len(amps)):
            if i & mask == 0:
                j0, j1 = i, i | mask
                a0, a1 = amps[j0], amps[j1]
                out[j0] = g[0][0] * a0 + g[0][1] * a1
                out[j1] = g[1][0] * a0 + g[1][1] * a1
        return QuantumStateVector(tuple(out))

    def apply_cnot(self, control: int, target: int) -> "QuantumStateVector":
        """Apply CNOT with ``control`` and distinct ``target`` (bit permutation)."""
        n = self.qubits
        c = _as_qubit_index(control, n, "control")
        t = _as_qubit_index(target, n, "target")
        if c == t:
            raise ValueError("CNOT control and target must differ")
        mask_c = 1 << (n - 1 - c)
        mask_t = 1 << (n - 1 - t)
        amps = self.amplitudes
        return QuantumStateVector(
            tuple(amps[i ^ mask_t] if (i & mask_c) else amps[i] for i in range(len(amps)))
        )

    def density(self) -> "QuantumDensityMatrix":
        """Rank-one density matrix ``|psi><psi|``."""
        amps = self.amplitudes
        return QuantumDensityMatrix(
            tuple(
                tuple(a * b.conjugate() for b in amps) for a in amps
            )
        )


@dataclass(frozen=True, slots=True)
class MeasurementBranch:
    """One Born outcome: ordered ``bits``, ``probability``, collapsed full state."""

    bits: Tuple[int, ...]
    probability: float
    state: "QuantumDensityMatrix"

    def __post_init__(self) -> None:
        bits = tuple(self.bits)
        if len(bits) == 0:
            raise ValueError("branch bits must be non-empty")
        for i, bit in enumerate(bits):
            _reject_bool(bit, f"bits[{i}]")
            if not isinstance(bit, int):
                raise TypeError(f"bits[{i}] must be an integer")
            if bit not in (0, 1):
                raise ValueError(f"bits[{i}] must be 0 or 1, got {bit!r}")
        object.__setattr__(self, "bits", bits)
        prob = self.probability
        _reject_bool(prob, "probability")
        if not isinstance(prob, (int, float)) or not math.isfinite(float(prob)):
            raise ValueError(f"branch probability must be finite, got {prob!r}")
        prob = float(prob)
        if not 0.0 < prob <= 1.0 + 1e-9:
            raise ValueError(f"branch probability out of range: {prob!r}")
        object.__setattr__(self, "probability", prob)
        if not isinstance(self.state, QuantumDensityMatrix):
            raise TypeError("branch state must be a QuantumDensityMatrix")


@dataclass(frozen=True, slots=True)
class QuantumDensityMatrix:
    """Immutable density matrix of 1--4 qubits (big-endian rows)."""

    rows: Tuple[Tuple[complex, ...], ...]

    def __post_init__(self) -> None:
        raw = self.rows
        if isinstance(raw, (str, bytes)):
            raise TypeError("rows must be a nested sequence of numbers")
        try:
            outer = tuple(raw)
        except TypeError:
            raise TypeError("rows must be a nested sequence of numbers")
        if len(outer) == 0:
            raise ValueError("rows must be non-empty (1-4 qubits)")
        checked_rows = []
        for i, row in enumerate(outer):
            if isinstance(row, (str, bytes)):
                raise TypeError(f"rows[{i}] must be a sequence of numbers")
            try:
                cells = tuple(row)
            except TypeError:
                raise TypeError(f"rows[{i}] must be a sequence of numbers")
            checked_rows.append(
                tuple(_as_complex(v, f"rows[{i}][{j}]") for j, v in enumerate(cells))
            )
        dim = len(checked_rows)
        if any(len(row) != dim for row in checked_rows):
            raise ValueError("density matrix must be square")
        _dimension_to_qubits(dim, "rows")
        checked = tuple(checked_rows)
        worst = 0.0
        for i in range(dim):
            for j in range(dim):
                diff = abs(checked[i][j] - checked[j][i].conjugate())
                worst = max(worst, diff)
        if worst > HERMITICITY_TOLERANCE:
            raise ValueError("density matrix must be Hermitian")
        trace = sum(checked[i][i] for i in range(dim))
        if (
            not math.isfinite(trace.real)
            or not math.isfinite(trace.imag)
            or abs(trace.imag) > HERMITICITY_TOLERANCE
            or abs(trace.real - 1.0) > TRACE_TOLERANCE
        ):
            raise ValueError(f"density matrix must have unit trace, got {trace!r}")
        if _hermitian_min_eigenvalue(checked) < -POSITIVITY_TOLERANCE:
            raise ValueError("density matrix must be positive semidefinite")
        object.__setattr__(self, "rows", checked)

    @property
    def qubits(self) -> int:
        """Number of qubits (big-endian: qubit 0 is the leftmost bit)."""
        return _dimension_to_qubits(len(self.rows), "rows")

    @property
    def trace(self) -> float:
        """Real part of the trace (1 within tolerance)."""
        return float(sum(row[i] for i, row in enumerate(self.rows)).real)

    @classmethod
    def from_statevector(cls, vector: QuantumStateVector) -> "QuantumDensityMatrix":
        """Rank-one density matrix from a normalized state vector."""
        if not isinstance(vector, QuantumStateVector):
            raise TypeError("from_statevector requires a QuantumStateVector")
        return vector.density()

    @classmethod
    def bell_mixture(cls, kind: str, fidelity: object) -> "QuantumDensityMatrix":
        """Werner/isotropic resource for Bell ``kind`` at overlap ``fidelity``.

        ``rho_B(F) = F * |B><B| + ((1 - F) / 3) * (I_4 - |B><B|)``.
        ``fidelity`` must be finite in ``[0, 1]``; out-of-range values are
        rejected, never clipped.
        """
        if not isinstance(kind, str) or kind not in _BELL_FRAMES:
            raise ValueError(
                f"unknown Bell kind {kind!r}: expected one of {BELL_KINDS}"
            )
        fid = _as_fidelity(fidelity, "fidelity")
        psi = BellState(kind).ideal_vector().amplitudes
        dim = 4
        rows = []
        for i in range(dim):
            row = []
            for j in range(dim):
                projector = psi[i] * psi[j].conjugate()
                identity = 1.0 if i == j else 0.0
                row.append(fid * projector + ((1.0 - fid) / 3.0) * (identity - projector))
            rows.append(tuple(row))
        return cls(tuple(rows))

    def tensor(self, other: "QuantumDensityMatrix") -> "QuantumDensityMatrix":
        """Kronecker product; ``self`` is the left (more significant) factor."""
        if not isinstance(other, QuantumDensityMatrix):
            raise TypeError("tensor operand must be a QuantumDensityMatrix")
        if self.qubits + other.qubits > MAX_QUBITS:
            raise ValueError("tensor product exceeds 4 qubits")
        a, b = self.rows, other.rows
        return QuantumDensityMatrix(
            tuple(
                tuple(a[i0][j0] * b[i1][j1] for j0 in range(len(a)) for j1 in range(len(b)))
                for i0 in range(len(a))
                for i1 in range(len(b))
            )
        )

    def apply_single(self, gate: object, target: int) -> "QuantumDensityMatrix":
        """Evolve ``rho -> U rho U^dagger`` for one qubit (indexed blocks)."""
        g = _validate_gate(gate)
        n = self.qubits
        q = _as_qubit_index(target, n, "target")
        dim = len(self.rows)
        src = self.rows
        out = [[0j] * dim for _ in range(dim)]
        for i in range(dim):
            bi = _qubit_bit(i, q, n)
            i0 = _with_qubit_bit(i, q, n, 0)
            i1 = _with_qubit_bit(i, q, n, 1)
            for j in range(dim):
                bj = _qubit_bit(j, q, n)
                j0 = _with_qubit_bit(j, q, n, 0)
                j1 = _with_qubit_bit(j, q, n, 1)
                out[i][j] = (
                    g[bi][0] * src[i0][j0] * g[bj][0].conjugate()
                    + g[bi][0] * src[i0][j1] * g[bj][1].conjugate()
                    + g[bi][1] * src[i1][j0] * g[bj][0].conjugate()
                    + g[bi][1] * src[i1][j1] * g[bj][1].conjugate()
                )
        return QuantumDensityMatrix(tuple(tuple(row) for row in out))

    def apply_cnot(self, control: int, target: int) -> "QuantumDensityMatrix":
        """Apply CNOT with ``control`` and distinct ``target`` (index permutation)."""
        n = self.qubits
        c = _as_qubit_index(control, n, "control")
        t = _as_qubit_index(target, n, "target")
        if c == t:
            raise ValueError("CNOT control and target must differ")

        def permuted(index: int) -> int:
            if index & (1 << (n - 1 - c)):
                return index ^ (1 << (n - 1 - t))
            return index

        src = self.rows
        dim = len(src)
        return QuantumDensityMatrix(
            tuple(
                tuple(src[permuted(i)][permuted(j)] for j in range(dim))
                for i in range(dim)
            )
        )

    def partial_trace(self, keep: Sequence[int]) -> "QuantumDensityMatrix":
        """Reduce to the ordered ``keep`` qubits; ``keep`` order sets output order."""
        if isinstance(keep, (str, bytes)):
            raise TypeError("keep must be a sequence of qubit indices")
        keep_tuple = tuple(keep)
        if len(keep_tuple) == 0:
            raise ValueError("partial_trace keep must be non-empty")
        n = self.qubits
        for pos, q in enumerate(keep_tuple):
            _as_qubit_index(q, n, f"keep[{pos}]")
        if len(set(keep_tuple)) != len(keep_tuple):
            raise ValueError("partial_trace keep must list distinct qubits")
        keep_set = set(keep_tuple)
        traced = [q for q in range(n) if q not in keep_set]
        k = len(keep_tuple)
        dim_out = 2**k
        dim_trace = 2 ** (n - k)
        src = self.rows
        out = [[0j] * dim_out for _ in range(dim_out)]
        for ro in range(dim_out):
            for co in range(dim_out):
                total = 0j
                for t in range(dim_trace):
                    full_r = 0
                    full_c = 0
                    for pos, q in enumerate(keep_tuple):
                        bit_r = (ro >> (k - 1 - pos)) & 1
                        bit_c = (co >> (k - 1 - pos)) & 1
                        full_r |= bit_r << (n - 1 - q)
                        full_c |= bit_c << (n - 1 - q)
                    for pos, q in enumerate(traced):
                        bit = (t >> (len(traced) - 1 - pos)) & 1
                        full_r |= bit << (n - 1 - q)
                        full_c |= bit << (n - 1 - q)
                    total += src[full_r][full_c]
                out[ro][co] = total
        return QuantumDensityMatrix(tuple(tuple(row) for row in out))

    def permute(self, order: Sequence[int]) -> "QuantumDensityMatrix":
        """Reorder qubits; new qubit ``i`` is old qubit ``order[i]``."""
        if isinstance(order, (str, bytes)):
            raise TypeError("order must be a sequence of qubit indices")
        order_tuple = tuple(order)
        n = self.qubits
        if sorted(order_tuple) != list(range(n)) or len(order_tuple) != n:
            raise ValueError(f"order must be a permutation of range({n})")
        for pos, q in enumerate(order_tuple):
            _as_qubit_index(q, n, f"order[{pos}]")
        dim = len(self.rows)
        src = self.rows

        def remap(index: int) -> int:
            old = 0
            for new_pos, old_q in enumerate(order_tuple):
                if (index >> (n - 1 - new_pos)) & 1:
                    old |= 1 << (n - 1 - old_q)
            return old

        return QuantumDensityMatrix(
            tuple(tuple(src[remap(i)][remap(j)] for j in range(dim)) for i in range(dim))
        )

    def fidelity_pure(self, vector: QuantumStateVector) -> float:
        """Overlap ``Re(<psi|rho|psi>)`` against a pure target (squared convention)."""
        if not isinstance(vector, QuantumStateVector):
            raise TypeError("fidelity target must be a QuantumStateVector")
        if vector.qubits != self.qubits:
            raise ValueError("fidelity target must have matching qubit count")
        amps = vector.amplitudes
        dim = len(amps)
        total = 0j
        for i in range(dim):
            for j in range(dim):
                total += amps[i].conjugate() * self.rows[i][j] * amps[j]
        return float(total.real)

    def _validate_targets(self, targets: object, name: str) -> Tuple[int, ...]:
        if isinstance(targets, (str, bytes)):
            raise TypeError(f"{name} must be a sequence of qubit indices")
        items = tuple(targets) if isinstance(targets, Sequence) else None
        if items is None:
            raise TypeError(f"{name} must be a sequence of qubit indices")
        if len(items) == 0:
            raise ValueError(f"{name} must be non-empty")
        n = self.qubits
        for pos, q in enumerate(items):
            _as_qubit_index(q, n, f"{name}[{pos}]")
        if len(set(items)) != len(items):
            raise ValueError(f"{name} must list distinct qubits")
        return items

    def branches_z(self, targets: Sequence[int]) -> Tuple[MeasurementBranch, ...]:
        """Z-basis Born branches for ``targets`` (bit order follows ``targets``).

        Each returned branch carries its outcome ``bits``, its Born
        ``probability``, and the normalized collapsed *full-system* state
        ``P rho P / p``. Only nonpositive outcomes are omitted; every
        representable positive probability remains sampleable. Returned
        probabilities sum to one within numerical tolerance.
        """
        tg = self._validate_targets(targets, "targets")
        n = self.qubits
        dim = len(self.rows)
        k = len(tg)
        branches = []
        for outcome in range(2**k):
            bits = tuple((outcome >> (k - 1 - i)) & 1 for i in range(k))
            prob = 0.0
            for d in range(dim):
                if all(_qubit_bit(d, q, n) == b for q, b in zip(tg, bits)):
                    prob += self.rows[d][d].real
            if prob <= 0.0:
                continue
            collapsed = [[0j] * dim for _ in range(dim)]
            for i in range(dim):
                row_ok = all(_qubit_bit(i, q, n) == b for q, b in zip(tg, bits))
                if not row_ok:
                    continue
                for j in range(dim):
                    if all(_qubit_bit(j, q, n) == b for q, b in zip(tg, bits)):
                        collapsed[i][j] = self.rows[i][j] / prob
            branches.append(
                MeasurementBranch(
                    bits=bits,
                    probability=float(prob),
                    state=QuantumDensityMatrix(
                        tuple(tuple(row) for row in collapsed)
                    ),
                )
            )
        return tuple(branches)

    def measure_z(
        self, targets: Sequence[int], rng: RNGProtocol | None = None
    ) -> MeasurementBranch:
        """Sample one Born branch via cumulative probabilities and ``rng``.

        Only ``rng.random()`` is consulted; results outside ``[0, 1)``
        are rejected.  Zero-probability branches are never selected.
        ``rng`` defaults to ``secrets.SystemRandom``.
        """
        sampler: RNGProtocol = rng if rng is not None else secrets.SystemRandom()
        branches = self.branches_z(targets)
        if not branches:
            raise ValueError("measurement has no nonzero-probability branch")
        drawn = sampler.random()
        _reject_bool(drawn, "rng.random()")
        if not isinstance(drawn, (int, float)):
            raise TypeError("rng.random() must return a float in [0, 1)")
        if not math.isfinite(float(drawn)) or not 0.0 <= float(drawn) < 1.0:
            raise ValueError(f"rng.random() must lie in [0, 1), got {drawn!r}")
        cutoff = float(drawn) * math.fsum(branch.probability for branch in branches)
        cumulative = 0.0
        for branch in branches:
            cumulative += branch.probability
            if cutoff < cumulative:
                return branch
        return branches[-1]

    def to_public_matrix(self) -> list:
        """One-qubit density as JSON-safe ``[[[re, im], ...], ...]`` (2x2)."""
        if self.qubits != 1:
            raise ValueError("to_public_matrix requires a one-qubit density")
        return [
            [[entry.real, entry.imag] for entry in row] for row in self.rows
        ]


@dataclass(frozen=True, slots=True)
class BellState:
    """Mathematical Bell descriptor: validated ``kind``, Pauli frame, ideal state."""

    kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in _BELL_FRAMES:
            raise ValueError(
                f"unknown Bell kind {self.kind!r}: expected one of {BELL_KINDS}"
            )

    @property
    def frame(self) -> Tuple[int, int]:
        """Pauli frame ``(x, z)`` mapping ``|Phi+>`` to this kind (X-then-Z)."""
        return _BELL_FRAMES[self.kind]

    def ideal_vector(self) -> QuantumStateVector:
        """Gate-generated ideal two-qubit vector: H(0), CNOT(0->1), frame on qubit 1."""
        x, z = self.frame
        state = QuantumStateVector((1 + 0j, 0j, 0j, 0j)).apply_single(H, 0).apply_cnot(0, 1)
        if x:
            state = state.apply_single(X, 1)
        if z:
            state = state.apply_single(Z, 1)
        return state

    def density(self, fidelity: object = 1.0) -> QuantumDensityMatrix:
        """Werner resource ``rho_B(F)`` for this kind (default: pure ideal)."""
        return QuantumDensityMatrix.bell_mixture(self.kind, fidelity)


def _conjugated_gate(gate: Gate2) -> Gate2:
    return (
        (gate[0][0].conjugate(), gate[0][1].conjugate()),
        (gate[1][0].conjugate(), gate[1][1].conjugate()),
    )


def werner_twirl(
    rho: QuantumDensityMatrix, kind: str = "PHI_PLUS"
) -> QuantumDensityMatrix:
    """Explicit six-unitary channel, isotropizing Bell-diagonal inputs only.

    Computes the ensemble average ``mean_U [(U (x) U*) rho (U (x) U*)^dagger]``
    over the six single-qubit Clifford representatives ``I, H, S, HS, SH,
    HSH`` (applied as ``U`` on qubit 0 and entrywise-conjugated ``U*`` on
    qubit 1).  These six fix ``|Phi+>`` while permuting the other three
    Bell states through all six orders, so for Bell-diagonal input the
    target overlap is preserved and the three error weights are
    equalized.  Inputs of another Bell frame are first canonicalized to
    ``|Phi+>`` with real local frame gates and restored afterwards.

    For other inputs this remains the same honest ensemble-average channel,
    not a general Werner projection. It is never applied implicitly: later
    protocols keep the exact untwirled density unless they call this helper.
    """
    if not isinstance(rho, QuantumDensityMatrix):
        raise TypeError("werner_twirl requires a QuantumDensityMatrix")
    if rho.qubits != 2:
        raise ValueError("werner_twirl requires a two-qubit density")
    if not isinstance(kind, str) or kind not in _BELL_FRAMES:
        raise ValueError(f"unknown Bell kind {kind!r}: expected one of {BELL_KINDS}")
    x, z = _BELL_FRAMES[kind]

    canonical = rho
    if x and z:
        canonical = canonical.apply_single(Z, 1).apply_single(X, 1)
    elif x:
        canonical = canonical.apply_single(X, 1)
    elif z:
        canonical = canonical.apply_single(Z, 1)

    representatives = (
        I,
        H,
        S,
        _matmul2(H, S),
        _matmul2(S, H),
        _matmul2(H, _matmul2(S, H)),
    )
    dim = 4
    total = [[0j] * dim for _ in range(dim)]
    for rep in representatives:
        evolved = canonical.apply_single(rep, 0).apply_single(_conjugated_gate(rep), 1)
        for i in range(dim):
            for j in range(dim):
                total[i][j] += evolved.rows[i][j] / 6.0
    twirled = QuantumDensityMatrix(tuple(tuple(row) for row in total))

    if x and z:
        twirled = twirled.apply_single(X, 1).apply_single(Z, 1)
    elif x:
        twirled = twirled.apply_single(X, 1)
    elif z:
        twirled = twirled.apply_single(Z, 1)
    return twirled
