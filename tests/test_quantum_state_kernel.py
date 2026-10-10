"""Behavioral kernel tests for the bounded quantum-state simulator (phase 68-01).

Every assertion targets consumer-visible math: gate truth tables, invariant
preservation, Born-branch probabilities, frame-aware corrections, Werner
channel oracles, BBPSSW accept/reject branches, and input validation.  No
assertion inspects source text, log prose, or mocked payloads, and no test
prints private data.
"""

import dataclasses
import math

import pytest

from desk_gateway.quantum_state import (
    BELL_KINDS,
    H,
    I,
    S,
    X,
    Z,
    BellState,
    MeasurementBranch,
    QuantumDensityMatrix,
    QuantumStateVector,
    werner_twirl,
)

FID_TOL = 1e-9
ORACLE_TOL = 1e-9


class ScriptedRNG:
    """Deterministic ``random() -> float`` source for CDF selection tests."""

    def __init__(self, values):
        self._values = list(values)
        self.calls = 0

    def random(self):
        if self.calls >= len(self._values):
            raise AssertionError("scripted RNG exhausted")
        value = self._values[self.calls]
        self.calls += 1
        return value


def test_positive_rare_born_outcome_remains_sampleable():
    rho = QuantumStateVector.from_qubit(1, 1e-7).density()
    by_bits = {branch.bits: branch for branch in rho.branches_z((0,))}
    assert by_bits[(1,)].probability == pytest.approx(1e-14, rel=1e-10, abs=0)

    selected = rho.measure_z((0,), ScriptedRNG([1.0 - 4.0e-15]))
    assert selected.bits == (1,)
    assert selected.state.fidelity_pure(
        QuantumStateVector.from_qubit(0, 1)
    ) == pytest.approx(1.0)


def close(a, b, tol=ORACLE_TOL):
    return abs(a - b) <= tol


def vectors_close(left, right, tol=ORACLE_TOL):
    return all(abs(a - b) <= tol for a, b in zip(left, right))


def _corrected_teleport_receiver(branch, frame):
    """Frame-aware X-then-Z correction on the traced-out receiver qubit."""
    (mz, mx), (fx, fz) = branch.bits, frame
    rho = branch.state.partial_trace((2,))
    if mx ^ fx:
        rho = rho.apply_single(X, 0)
    if mz ^ fz:
        rho = rho.apply_single(Z, 0)
    return rho


def _teleport_branches(input_state, pair_rho):
    joint = input_state.density().tensor(pair_rho)
    joint = joint.apply_cnot(0, 1).apply_single(H, 0)
    return joint.branches_z((0, 1))


def _ensemble_fidelity(input_state, pair_rho, frame):
    """Probability-weighted corrected-receiver fidelity over all BSM branches."""
    total = [[0j, 0j], [0j, 0j]]
    for branch in _teleport_branches(input_state, pair_rho):
        corrected = _corrected_teleport_receiver(branch, frame)
        for i in range(2):
            for j in range(2):
                total[i][j] += branch.probability * corrected.rows[i][j]
    averaged = QuantumDensityMatrix(
        (tuple(total[0]), tuple(total[1]))
    )
    return averaged.fidelity_pure(input_state)


def _swap_branch_fidelity(pair_rho_a, pair_rho_b, frame_a, frame_b, permute_b=False):
    """Worst-case corrected-endpoint fidelity over all four BSM outcomes."""
    if permute_b:
        pair_rho_b = pair_rho_b.permute((1, 0))
    joint = pair_rho_a.tensor(pair_rho_b)
    joint = joint.apply_cnot(1, 2).apply_single(H, 1)
    branches = joint.branches_z((1, 2))
    assert len(branches) == 4
    target = BellState("PHI_PLUS").ideal_vector()
    worst = 1.0
    for branch in branches:
        assert close(branch.probability, 0.25)
        mz, mx = branch.bits
        kept = branch.state.partial_trace((0, 3))
        if mx ^ frame_a[0] ^ frame_b[0]:
            kept = kept.apply_single(X, 0)
        if mz ^ frame_a[1] ^ frame_b[1]:
            kept = kept.apply_single(Z, 0)
        fidelity = kept.fidelity_pure(target)
        worst = min(worst, fidelity)
        assert fidelity > 1.0 - 1e-9
    return worst


INPUT_STATES = {
    "zero": QuantumStateVector.from_qubit(1, 0),
    "one": QuantumStateVector.from_qubit(0, 1),
    "plus": QuantumStateVector.from_qubit(1, 1),
    "minus": QuantumStateVector.from_qubit(1, -1),
    "plus_i": QuantumStateVector.from_qubit(1, 1j),
    "minus_i": QuantumStateVector.from_qubit(1, -1j),
    "asymmetric": QuantumStateVector.from_qubit(1 + 2j, 1 - 1j),
}



def test_single_qubit_gate_truth_tables():
    zero = QuantumStateVector.from_qubit(1, 0)
    plus = zero.apply_single(H, 0)
    assert vectors_close(plus.amplitudes, (1 / math.sqrt(2), 1 / math.sqrt(2)))
    assert vectors_close(zero.apply_single(X, 0).amplitudes, (0j, 1 + 0j))
    minus = plus.apply_single(Z, 0)
    assert vectors_close(minus.amplitudes, (1 / math.sqrt(2), -1 / math.sqrt(2)))
    plus_i = plus.apply_single(S, 0)
    assert vectors_close(plus_i.amplitudes, (1 / math.sqrt(2), 1j / math.sqrt(2)))
    assert vectors_close(zero.apply_single(I, 0).amplitudes, zero.amplitudes)


def test_cnot_big_endian_truth_table():
    def basis(i):
        amps = [0j] * 4
        amps[i] = 1 + 0j
        return QuantumStateVector(tuple(amps))

    assert basis(2).apply_cnot(0, 1).amplitudes == basis(3).amplitudes
    assert basis(3).apply_cnot(0, 1).amplitudes == basis(2).amplitudes
    assert basis(1).apply_cnot(0, 1).amplitudes == basis(1).amplitudes
    assert basis(0).apply_cnot(0, 1).amplitudes == basis(0).amplitudes
    assert basis(1).apply_cnot(1, 0).amplitudes == basis(3).amplitudes
    assert basis(3).apply_cnot(1, 0).amplitudes == basis(1).amplitudes


def test_from_qubit_normalization_and_huge_finite_inputs():
    state = QuantumStateVector.from_qubit(3, 4)
    assert vectors_close(state.amplitudes, (0.6 + 0j, 0.8 + 0j))
    huge = QuantumStateVector.from_qubit(1e308, 1e308)
    assert vectors_close(huge.amplitudes, (1 / math.sqrt(2), 1 / math.sqrt(2)), tol=1e-12)
    huge_complex = QuantumStateVector.from_qubit(complex(1e308, 1e308), 0)
    expected = ((1 + 1j) / math.sqrt(2), 0j)
    assert vectors_close(huge_complex.amplitudes, expected, tol=1e-12)
    tiny = QuantumStateVector.from_qubit(1e-308, 0)
    assert vectors_close(tiny.amplitudes, (1 + 0j, 0j))
    asymmetric = QuantumStateVector.from_qubit(1 + 2j, 1 - 1j)
    assert close(asymmetric.norm, 1.0, tol=1e-12)
    assert close(abs(asymmetric.amplitudes[0]) ** 2, 5.0 / 7.0, tol=1e-12)


def test_state_vector_constructor_rejections():
    with pytest.raises(ValueError):
        QuantumStateVector(())
    with pytest.raises(ValueError):
        QuantumStateVector((1 + 0j, 0j, 0j))
    with pytest.raises(ValueError):
        QuantumStateVector(tuple([0j] * 32))
    with pytest.raises(ValueError):
        QuantumStateVector((0j, 0j))
    with pytest.raises(ValueError):
        QuantumStateVector((1 + 0j, 1 + 0j))
    with pytest.raises(ValueError):
        QuantumStateVector((float("inf"), 0j))
    with pytest.raises(ValueError):
        QuantumStateVector((complex(0, float("nan")), 1 + 0j))
    with pytest.raises((TypeError, ValueError)):
        QuantumStateVector((True, 1 + 0j))
    with pytest.raises((TypeError, ValueError)):
        QuantumStateVector(("0", "1"))
    with pytest.raises((TypeError, ValueError)):
        QuantumStateVector.from_qubit(True, 0)
    with pytest.raises((TypeError, ValueError)):
        QuantumStateVector.from_qubit("1", "0")
    with pytest.raises(ValueError):
        QuantumStateVector.from_qubit(0, 0)
    with pytest.raises(ValueError):
        QuantumStateVector.from_qubit(float("nan"), 1)


def test_density_constructor_rejections():
    with pytest.raises(ValueError):
        QuantumDensityMatrix(())
    with pytest.raises(ValueError):
        QuantumDensityMatrix(((1 + 0j, 0j, 0j), (0j,) * 3, (0j,) * 3))
    with pytest.raises(ValueError):
        QuantumDensityMatrix(((0.6 + 0j, 0j), (0j, 0.6 + 0j)))
    with pytest.raises(ValueError):
        QuantumDensityMatrix(((0.5 + 0j, 0.5 + 0j), (0j, 0.5 + 0j)))
    for indefinite in (
        ((1.5 + 0j, 0j), (0j, -0.5 + 0j)),
        ((0.5, 0.75), (0.75, 0.5)),
        ((0.5, 0.75j), (-0.75j, 0.5)),
    ):
        with pytest.raises(ValueError):
            QuantumDensityMatrix(indefinite)
    with pytest.raises(TypeError):
        QuantumDensityMatrix(((True, 0j), (0j, 1 + 0j)))
    with pytest.raises(TypeError):
        QuantumDensityMatrix((("1", "0"), ("0", "1")))
    with pytest.raises(ValueError):
        QuantumDensityMatrix(((float("inf"), 0j), (0j, 1 + 0j)))


def test_finite_extreme_indefinite_density_fails_closed():
    huge = 1.7e308
    rows = tuple(
        tuple(huge if i != j else (huge, -huge, 1.0, 0.0)[i] for j in range(4))
        for i in range(4)
    )
    with pytest.raises(ValueError):
        QuantumDensityMatrix(rows)


def test_accepted_vector_density_preserves_squared_norm_boundary():
    amplitude = 1 + 4e-10
    vector = QuantumStateVector((amplitude, 0))
    assert vector.density().trace == pytest.approx(amplitude * amplitude, abs=1e-15)
    assert vector.density().trace > 1.0
    with pytest.raises(ValueError):
        QuantumStateVector((1 + 7.5e-10, 0))
    with pytest.raises(ValueError):
        QuantumStateVector((1e308, 0))
    with pytest.raises(ValueError):
        vector.tensor(vector)


def test_complex_rank_deficient_density_is_valid():
    rho = QuantumDensityMatrix(((0.5, -0.5j), (0.5j, 0.5)))
    assert rho.fidelity_pure(QuantumStateVector.from_qubit(1, 1j)) == pytest.approx(1.0)


def test_measurement_branch_requires_integer_correction_bits():
    one = QuantumStateVector.from_qubit(0, 1).density()
    for bad in (1.0, 1 + 0j, True, "1"):
        with pytest.raises(TypeError):
            MeasurementBranch((bad,), 1.0, one)


def test_gate_and_index_validation():
    zero = QuantumStateVector.from_qubit(1, 0)
    pair = zero.tensor(zero)
    with pytest.raises(ValueError):
        zero.apply_single(((1 + 0j, 1 + 0j), (0j, 1 + 0j)), 0)
    with pytest.raises(ValueError):
        zero.apply_single(((1 + 0j,), (0j,)), 0)
    with pytest.raises(ValueError):
        pair.apply_single(H, 2)
    with pytest.raises(ValueError):
        pair.apply_cnot(0, 0)
    with pytest.raises(ValueError):
        pair.apply_cnot(0, 5)
    with pytest.raises(ValueError):
        zero.tensor(QuantumStateVector((1 + 0j, 0j, 0j, 0j, 0j, 0j, 0j, 0j,
                                        0j, 0j, 0j, 0j, 0j, 0j, 0j, 0j)))
    with pytest.raises(ValueError):
        pair.density().tensor(pair.density()).tensor(pair.density())
    with pytest.raises(ValueError):
        pair.density().partial_trace(())
    with pytest.raises(ValueError):
        pair.density().partial_trace((0, 0))
    with pytest.raises(ValueError):
        pair.density().partial_trace((0, 7))
    with pytest.raises(ValueError):
        pair.density().permute((0, 0))
    with pytest.raises(ValueError):
        pair.density().permute((0, 2))
    with pytest.raises(ValueError):
        pair.density().to_public_matrix()
    with pytest.raises(ValueError):
        pair.density().fidelity_pure(zero)


def test_immutability_and_idempotent_repeated_calls():
    zero = QuantumStateVector.from_qubit(1, 0)
    rho = zero.density()
    with pytest.raises(dataclasses.FrozenInstanceError):
        zero.amplitudes = (0j, 1 + 0j)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rho.rows = (((1 + 0j, 0j), (0j, 0j)),)
    branch = rho.tensor(rho).branches_z((0,))[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        branch.probability = 0.0
    first = zero.apply_single(H, 0).tensor(zero).density()
    second = zero.apply_single(H, 0).tensor(zero).density()
    assert first == second
    assert first.branches_z((0, 1)) == second.branches_z((0, 1))


def test_tensor_order_and_partial_trace_marginals():
    zero = QuantumStateVector.from_qubit(1, 0)
    one = QuantumStateVector.from_qubit(0, 1)
    pair = zero.tensor(one)
    assert pair.amplitudes == (0j, 1 + 0j, 0j, 0j)
    assert pair.qubits == 2
    assert pair.density().partial_trace((0,)) == zero.density()
    assert pair.density().partial_trace((1,)) == one.density()
    for kind in BELL_KINDS:
        bell = BellState(kind).density()
        for endpoint in (0, 1):
            marginal = bell.partial_trace((endpoint,))
            for alpha, beta in ((1, 0), (1, 1), (1, 1j)):
                probe = QuantumStateVector.from_qubit(alpha, beta)
                assert marginal.fidelity_pure(probe) == pytest.approx(0.5)


def test_asymmetric_complex_noncontiguous_trace_and_noninverse_permutation():
    raw = ((1 + 1j, 2), (1, 1j), (3, 2 - 1j), (2 + 3j, 1 - 2j))
    factors = tuple(
        tuple(value / math.sqrt(abs(a) ** 2 + abs(b) ** 2) for value in (a, b))
        for a, b in raw
    )
    for count, order in ((3, (2, 0, 1)), (4, (2, 0, 3, 1))):
        state = QuantumStateVector.from_qubit(*raw[0])
        for pair in raw[1:count]:
            state = state.tensor(QuantumStateVector.from_qubit(*pair))
        rho = state.density()
        keep = (count - 1, 0)
        for actual, positions in (
            (rho.partial_trace(keep), keep),
            (rho.permute(order), order),
        ):
            expected = tuple(
                math.prod(
                    factors[position][(index >> (len(positions) - 1 - bit)) & 1]
                    for bit, position in enumerate(positions)
                )
                for index in range(2 ** len(positions))
            )
            for i, left in enumerate(expected):
                for j, right in enumerate(expected):
                    assert actual.rows[i][j] == pytest.approx(
                        left * right.conjugate(), abs=1e-12
                    )


def test_measurement_bits_follow_requested_target_order():
    ten = QuantumStateVector((0, 0, 1, 0)).density()
    assert ten.measure_z((1, 0), ScriptedRNG([0.4])).bits == (0, 1)


# Task 2: projective measurement branches with Born sampling.


def test_direct_bell_measurement_retains_correlated_outcomes():
    bell = BellState("PHI_PLUS").density()
    branches = bell.branches_z((0, 1))
    assert [branch.bits for branch in branches] == [(0, 0), (1, 1)]
    assert close(sum(branch.probability for branch in branches), 1.0, tol=1e-12)
    for branch in branches:
        assert close(branch.probability, 0.5)
        assert branch.state.qubits == 2
        assert close(branch.state.trace, 1.0, tol=1e-12)
        target = QuantumStateVector(
            tuple(1 + 0j if i == (branch.bits[0] * 2 + branch.bits[1]) else 0j for i in range(4))
        )
        assert close(branch.state.fidelity_pure(target), 1.0, tol=1e-12)


def test_measure_z_scripted_rng_selects_each_uniform_branch_interior():
    plus = QuantumStateVector.from_qubit(1, 1)
    product = plus.tensor(plus).density()
    assert product.measure_z((0, 1), ScriptedRNG([0.10])).bits == (0, 0)
    assert product.measure_z((0, 1), ScriptedRNG([0.26])).bits == (0, 1)
    assert product.measure_z((0, 1), ScriptedRNG([0.51])).bits == (1, 0)
    assert product.measure_z((0, 1), ScriptedRNG([0.99])).bits == (1, 1)
    assert product.measure_z((0, 1), ScriptedRNG([0.0])).bits == (0, 0)


def test_zero_probability_branches_skipped_and_invalid_rng_rejected():
    product = QuantumStateVector.from_qubit(1, 0).tensor(
        QuantumStateVector.from_qubit(1, 0)
    ).density()
    branches = product.branches_z((0, 1))
    assert len(branches) == 1
    assert branches[0].bits == (0, 0)
    assert close(branches[0].probability, 1.0)
    assert product.measure_z((0,), ScriptedRNG([0.999])).bits == (0,)
    assert product.measure_z((1,), ScriptedRNG([0.0])).bits == (0,)
    bell = BellState("PHI_PLUS").density()
    for bad in (1.0, -0.1, 2.0, float("nan"), float("inf"), True):
        with pytest.raises((TypeError, ValueError)):
            bell.measure_z((0, 1), ScriptedRNG([bad]))
    with pytest.raises((TypeError, ValueError)):
        bell.measure_z((0, 1), ScriptedRNG(["0.5"]))
    with pytest.raises(ValueError):
        bell.measure_z((), ScriptedRNG([0.1]))
    with pytest.raises(ValueError):
        bell.branches_z((0, 0))


# Task 3: Bell descriptors, Werner construction, fidelity oracles.


def test_bell_vectors_gate_generated_and_orthonormal():
    vectors = {kind: BellState(kind).ideal_vector() for kind in BELL_KINDS}
    assert set(vectors) == set(BELL_KINDS)
    assert BellState("PHI_PLUS").frame == (0, 0)
    assert BellState("PHI_MINUS").frame == (0, 1)
    assert BellState("PSI_PLUS").frame == (1, 0)
    assert BellState("PSI_MINUS").frame == (1, 1)
    for kind, vector in vectors.items():
        assert vector.qubits == 2
        assert close(vector.norm, 1.0, tol=1e-12)
    for left_kind, left in vectors.items():
        for right_kind, right in vectors.items():
            overlap = abs(sum(a.conjugate() * b for a, b in zip(left.amplitudes, right.amplitudes))) ** 2
            assert close(overlap, 1.0 if left_kind == right_kind else 0.0, tol=1e-12)


def test_bell_kind_and_fidelity_validation():
    for bad in ("phi_plus", "", "BELL", "PHI_PLUS ", None, 42, b"PHI_PLUS"):
        with pytest.raises((TypeError, ValueError)):
            BellState(bad)
    for bad in (-0.1, 1.1, float("nan"), float("inf"), True, "0.9", None):
        with pytest.raises((TypeError, ValueError)):
            QuantumDensityMatrix.bell_mixture("PHI_PLUS", bad)
    with pytest.raises((TypeError, ValueError)):
        QuantumDensityMatrix.bell_mixture("UNKNOWN", 0.9)
    with pytest.raises((TypeError, ValueError)):
        BellState("PHI_PLUS").density(1.5)


def test_werner_overlaps_all_frames_and_fidelities():
    for kind in BELL_KINDS:
        ideal = BellState(kind).ideal_vector()
        for fidelity in (0.0, 0.25, 0.5, 0.9, 1.0):
            rho = QuantumDensityMatrix.bell_mixture(kind, fidelity)
            assert close(rho.fidelity_pure(ideal), fidelity, tol=1e-12)
            assert close(rho.trace, 1.0, tol=1e-12)
    maximally_mixed = QuantumDensityMatrix.bell_mixture("PHI_PLUS", 0.25)
    for i in range(4):
        for j in range(4):
            want = 0.25 if i == j else 0.0
            assert close(maximally_mixed.rows[i][j].real, want, tol=1e-12)
            assert close(maximally_mixed.rows[i][j].imag, 0.0, tol=1e-12)
    pure = QuantumDensityMatrix.bell_mixture("PSI_MINUS", 1.0)
    ideal = BellState("PSI_MINUS").ideal_vector()
    assert pure == ideal.density()


def test_teleport_sixteen_ideal_branches_recover_every_input():
    for kind in BELL_KINDS:
        frame = BellState(kind).frame
        pair_rho = BellState(kind).density()
        for name, input_state in INPUT_STATES.items():
            branches = _teleport_branches(input_state, pair_rho)
            assert len(branches) == 4, (kind, name)
            for branch in branches:
                assert close(branch.probability, 0.25, tol=1e-12), (kind, name, branch.bits)
                corrected = _corrected_teleport_receiver(branch, frame)
                assert close(corrected.fidelity_pure(input_state), 1.0, tol=1e-9), (
                    kind, name, branch.bits,
                )


def test_swap_sixty_four_ideal_branches_recover_phi_plus():
    frames = {kind: BellState(kind).frame for kind in BELL_KINDS}
    rhos = {kind: BellState(kind).density() for kind in BELL_KINDS}
    for kind_a in BELL_KINDS:
        for kind_b in BELL_KINDS:
            _swap_branch_fidelity(rhos[kind_a], rhos[kind_b], frames[kind_a], frames[kind_b])
            _swap_branch_fidelity(
                rhos[kind_a], rhos[kind_b], frames[kind_a], frames[kind_b], permute_b=True
            )


def test_werner_teleport_channel_fidelity_oracles():
    for resource_fidelity, expected in (
        (0.99, 0.993333333333),
        (0.90, 0.933333333333),
        (0.25, 0.5),
    ):
        pair_rho = BellState("PHI_PLUS").density(resource_fidelity)
        for name, input_state in INPUT_STATES.items():
            fidelity = _ensemble_fidelity(input_state, pair_rho, (0, 0))
            assert close(fidelity, expected, tol=1e-9), (name, fidelity)
            if resource_fidelity <= 0.90:
                assert fidelity < 0.95


def test_werner_boundary_point_925_reports_unrounded_and_just_below_fails():
    boundary = _ensemble_fidelity(
        INPUT_STATES["zero"], BellState("PHI_PLUS").density(0.925), (0, 0)
    )
    assert close(boundary, 0.95, tol=1e-9)
    just_below = _ensemble_fidelity(
        INPUT_STATES["zero"], BellState("PHI_PLUS").density(0.92), (0, 0)
    )
    assert just_below < 0.95 - 1e-6
    just_above = _ensemble_fidelity(
        INPUT_STATES["zero"], BellState("PHI_PLUS").density(0.93), (0, 0)
    )
    assert just_above > 0.95


def test_swap_werner_formula_oracles():
    target = BellState("PHI_PLUS").ideal_vector()
    for fidelity_a, fidelity_b, expected in (
        (0.98, 0.98, 0.960533333333),
        (0.25, 0.25, 0.25),
        (0.99, 0.99, 0.980133333333),
    ):
        rho_a = BellState("PHI_PLUS").density(fidelity_a)
        rho_b = BellState("PHI_PLUS").density(fidelity_b)
        joint = rho_a.tensor(rho_b).apply_cnot(1, 2).apply_single(H, 1)
        total = [[0j] * 4 for _ in range(4)]
        for branch in joint.branches_z((1, 2)):
            kept = branch.state.partial_trace((0, 3))
            if branch.bits[1]:
                kept = kept.apply_single(X, 0)
            if branch.bits[0]:
                kept = kept.apply_single(Z, 0)
            for i in range(4):
                for j in range(4):
                    total[i][j] += branch.probability * kept.rows[i][j]
        averaged = QuantumDensityMatrix(tuple(tuple(row) for row in total))
        assert close(averaged.fidelity_pure(target), expected, tol=1e-9)


def _bbpssw_outcome(fidelity_a, fidelity_b):
    rho_a = BellState("PHI_PLUS").density(fidelity_a)
    rho_b = BellState("PHI_PLUS").density(fidelity_b)
    joint = rho_a.tensor(rho_b).apply_cnot(0, 2).apply_cnot(1, 3)
    branches = {branch.bits: branch for branch in joint.branches_z((2, 3))}
    accept_prob = sum(
        branches[bits].probability for bits in ((0, 0), (1, 1)) if bits in branches
    )
    total = [[0j] * 4 for _ in range(4)]
    for bits in ((0, 0), (1, 1)):
        if bits not in branches:
            continue
        kept = branches[bits].state.partial_trace((0, 1))
        for i in range(4):
            for j in range(4):
                total[i][j] += branches[bits].probability * kept.rows[i][j]
    accepted = QuantumDensityMatrix(
        tuple(tuple(entry / accept_prob for entry in row) for row in total)
    )
    return branches, accept_prob, accepted


def test_bbpssw_accept_reject_branches_and_untwirled_weights():
    branches, accept_prob, accepted = _bbpssw_outcome(0.90, 0.92)
    assert close(branches[(0, 0)].probability, 0.443555555556, tol=1e-9)
    assert close(branches[(1, 1)].probability, 0.443555555556, tol=1e-9)
    assert close(branches[(0, 1)].probability, 0.056444444444, tol=1e-9)
    assert close(branches[(1, 0)].probability, 0.056444444444, tol=1e-9)
    assert close(accept_prob, 0.887111111111, tol=1e-9)
    ideal = BellState("PHI_PLUS").ideal_vector()
    assert close(accepted.fidelity_pure(ideal), 0.934368737475, tol=1e-9)
    weights = {
        kind: accepted.fidelity_pure(BellState(kind).ideal_vector()) for kind in BELL_KINDS
    }
    assert close(weights["PHI_PLUS"], 0.934368737475, tol=1e-9)
    assert close(weights["PHI_MINUS"], 0.061623246493, tol=1e-9)
    assert close(weights["PSI_PLUS"], 0.002004008016, tol=1e-9)
    assert close(weights["PSI_MINUS"], 0.002004008016, tol=1e-9)

    _, accept_half, half = _bbpssw_outcome(0.5, 0.5)
    assert close(accept_half, 0.555555555556, tol=1e-9)
    assert close(half.fidelity_pure(ideal), 0.5, tol=1e-9)

    _, accept_low, low = _bbpssw_outcome(0.4, 0.4)
    assert close(accept_low, 0.52, tol=1e-9)
    assert close(low.fidelity_pure(ideal), 0.384615384615, tol=1e-9)

    perfect_branches, accept_one, one = _bbpssw_outcome(1.0, 1.0)
    assert close(accept_one, 1.0, tol=1e-12)
    assert close(one.fidelity_pure(ideal), 1.0, tol=1e-12)
    assert set(perfect_branches) == {(0, 0), (1, 1)}


def test_werner_twirl_preserves_overlap_and_equalizes_errors():
    _, _, accepted = _bbpssw_outcome(0.90, 0.92)
    twirled = werner_twirl(accepted)
    ideal = BellState("PHI_PLUS").ideal_vector()
    assert close(twirled.fidelity_pure(ideal), 0.934368737475, tol=1e-9)
    others = [
        twirled.fidelity_pure(BellState(kind).ideal_vector())
        for kind in ("PHI_MINUS", "PSI_PLUS", "PSI_MINUS")
    ]
    assert close(others[0], 0.021877087508, tol=1e-9)
    assert close(others[0], others[1], tol=1e-12)
    assert close(others[1], others[2], tol=1e-12)
    pure_twirl = werner_twirl(BellState("PHI_PLUS").density())
    assert close(pure_twirl.fidelity_pure(ideal), 1.0, tol=1e-12)
    psi_mixture = BellState("PSI_MINUS").density(0.9)
    framed = werner_twirl(psi_mixture, kind="PSI_MINUS")
    assert close(
        framed.fidelity_pure(BellState("PSI_MINUS").ideal_vector()), 0.9, tol=1e-9
    )
    with pytest.raises(ValueError):
        werner_twirl(BellState("PHI_PLUS").density().partial_trace((0,)))
    with pytest.raises(ValueError):
        werner_twirl(BellState("PHI_PLUS").density(), kind="NOPE")


def test_public_density_preserves_imaginary_coherence_sign():
    matrix = QuantumStateVector.from_qubit(1, 1j).density().to_public_matrix()
    upper = complex(*matrix[0][1])
    lower = complex(*matrix[1][0])
    assert upper == pytest.approx(-0.5j)
    assert lower == pytest.approx(0.5j)
    assert upper == pytest.approx(lower.conjugate())


def test_six_unitary_channel_is_not_general_werner_projection():
    zero = QuantumStateVector.from_qubit(1, 0)
    output = werner_twirl(zero.tensor(zero).density())
    marginal = output.partial_trace((0,))
    assert marginal.fidelity_pure(zero) == pytest.approx(2 / 3)
    assert marginal.fidelity_pure(QuantumStateVector.from_qubit(1, 1)) == pytest.approx(2 / 3)
    assert output.fidelity_pure(BellState("PHI_PLUS").ideal_vector()) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "rows",
    (
        ((0.5, 0.5000000008), (0.5000000016, 0.5)),
        ((0.5, 0.5000000016), (0.5000000008, 0.5)),
    ),
)
def test_tolerated_asymmetry_cannot_hide_negative_eigenvalue(rows):
    with pytest.raises(ValueError):
        QuantumDensityMatrix(rows)


def test_complex_mixed_states_match_dense_single_gate_reference():
    import random

    rng = random.Random(68)
    for qubits in range(1, 5):
        dim = 2 ** qubits
        for _ in range(6):
            vectors = []
            for _ in range(2):
                raw = [
                    complex(rng.uniform(-1, 1), rng.uniform(-1, 1))
                    for _ in range(dim)
                ]
                norm = math.sqrt(sum(abs(value) ** 2 for value in raw))
                vectors.append([value / norm for value in raw])
            a, b = vectors
            rows = tuple(
                tuple(
                    0.37 * a[i] * a[j].conjugate()
                    + 0.63 * b[i] * b[j].conjugate()
                    for j in range(dim)
                )
                for i in range(dim)
            )
            actual = QuantumDensityMatrix(rows).apply_single(H, qubits - 1)
            unitary = [
                [H[r & 1][c & 1] if r // 2 == c // 2 else 0j for c in range(dim)]
                for r in range(dim)
            ]
            left = [
                [sum(unitary[i][k] * rows[k][j] for k in range(dim)) for j in range(dim)]
                for i in range(dim)
            ]
            expected = [
                [
                    sum(left[i][k] * unitary[j][k].conjugate() for k in range(dim))
                    for j in range(dim)
                ]
                for i in range(dim)
            ]
            for i in range(dim):
                for j in range(dim):
                    assert actual.rows[i][j] == pytest.approx(
                        expected[i][j], rel=0, abs=5e-12
                    )


@pytest.mark.parametrize("delta", (-6e-10, 6e-10))
def test_near_unit_trace_keeps_positive_rare_born_tail(delta):
    rho = QuantumDensityMatrix(((1 + delta - 1e-14, 0), (0, 1e-14)))
    assert rho.measure_z((0,), ScriptedRNG([1 - 4e-15])).bits == (1,)


def test_conditioning_rejects_amplified_nonphysical_positive_branch():
    p = 1e-14
    coherence = 5e-10
    rho = QuantumDensityMatrix(
        (
            (1 - p, 0, 0, 0),
            (0, 0, 0, 0),
            (0, 0, p / 2, coherence),
            (0, 0, coherence, p / 2),
        )
    )
    with pytest.raises(ValueError):
        rho.branches_z((0,))
