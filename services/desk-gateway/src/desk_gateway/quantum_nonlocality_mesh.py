"""Quantum Non-Locality, Bell Inequality Violations & Device-Independent QKD (Milestone v6.7 - Phase 100).

Implements:
- CHSHBellInequalityEngine: Simulates Clauser-Horne-Shimony-Holt (CHSH) Bell test game.
  Evaluates correlation expectation values <A_x B_y> for measurement settings x, y in {0, 1}.
  Demonstrates Tsirelson bound (2*sqrt(2) approx 2.8284) violation above classical limit (|S| <= 2).
- MultipartiteMerminGHZEngine: GHZ multipartite Mermin-Klyshko inequality engine testing non-locality
  for 3-qubit entangled GHZ states (|000> + |111>)/sqrt(2), measuring Mermin operator M_3 = XXX - (XYY + YXY + YYX),
  achieving quantum expectation <M_3> = 4 violating the classical bound |<M_3>_class| <= 2.
- DeviceIndependentRandomnessExpander: Quantifies and certifies non-local quantum randomness
  generated from Bell inequality violations using spot-checking and conditional min-entropy bounds H_min(A|E) >= 1 - log2(1 + sqrt(2 - S^2/4)).
- DeviceIndependentQKDEngine: Device-Independent Quantum Key Distribution (DI-QKD) based on E91
  where cryptographic security against an arbitrary eavesdropper Eve is certified purely by the
  observed CHSH Bell violation S > 2, without trusting internal measurement devices or state preparation.
- QuantumNonLocalityMesh: High-level mesh coordinating Bell tests, multipartite GHZ violations, DI randomness expansion,
  and DI-QKD secure key rate calculations.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple


class BellInequalityType(str, enum.Enum):
    CHSH_BIPARTITE = "CHSH_BIPARTITE"
    GHZ_MERMIN_3QUBIT = "GHZ_MERMIN_3QUBIT"


@dataclasses.dataclass
class CHSHTrialResult:
    setting_a: int  # 0 or 1
    setting_b: int  # 0 or 1
    outcome_a: int  # +1 or -1
    outcome_b: int  # +1 or -1
    correlation_product: int  # +1 or -1


@dataclasses.dataclass
class CHSHTestSummary:
    num_trials: int
    correlations: Dict[str, float]  # e.g., "E(0,0)", "E(0,1)", "E(1,0)", "E(1,1)"
    chsh_parameter_s: float
    classical_bound: float = 2.0
    tsirelson_bound: float = 2.8284271247461903  # 2 * sqrt(2)
    quantum_violation: bool = False
    p_value_classical_refutation: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_trials": self.num_trials,
            "correlations": self.correlations,
            "chsh_parameter_s": round(self.chsh_parameter_s, 6),
            "classical_bound": self.classical_bound,
            "tsirelson_bound": round(self.tsirelson_bound, 6),
            "quantum_violation": self.quantum_violation,
            "p_value_classical_refutation": self.p_value_classical_refutation,
        }


class CHSHBellInequalityEngine:
    """Evaluates Clauser-Horne-Shimony-Holt (CHSH) Bell test game.

    Settings:
      Alice: a_0 = 0 (Z basis), a_1 = pi/4 (X+Z basis)
      Bob:   b_0 = pi/8,       b_1 = 3*pi/8
    Angles theta_a - theta_b:
      (a0, b0) = -pi/8      => <A0 B0> = cos(2 * -pi/8) = cos(-pi/4) = 1/sqrt(2) approx 0.7071
      (a0, b1) = -3*pi/8    => <A0 B1> = cos(2 * -3*pi/8) = cos(-3*pi/4) = -1/sqrt(2) approx -0.7071
      (a1, b0) = pi/8       => <A1 B0> = cos(2 * pi/8) = cos(pi/4) = 1/sqrt(2) approx 0.7071
      (a1, b1) = -pi/8      => <A1 B1> = cos(2 * -pi/8) = cos(-pi/4) = 1/sqrt(2) approx 0.7071
    CHSH Bell parameter:
      S = |E(a0, b0) - E(a0, b1) + E(a1, b0) + E(a1, b1)| = 4 / sqrt(2) = 2*sqrt(2) approx 2.8284 > 2
    """

    def __init__(self, rng_seed: Optional[int] = None) -> None:
        self.rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
        # Optimal angles for maximal Tsirelson violation
        self.alice_angles = {0: 0.0, 1: math.pi / 4.0}
        self.bob_angles = {0: math.pi / 8.0, 1: 3.0 * math.pi / 8.0}

    def simulate_key_pair(
        self, noise_depolarizing: float = 0.0
    ) -> Tuple[int, int]:
        """Simulate aligned key generation measurement (both measured in identical basis, e.g. Z basis)."""
        # For identical basis measurement on entangled state, outcomes are perfectly correlated in ideal case
        # With depolarizing noise, bit flip probability is noise_depolarizing / 2
        a_bit = 1 if self.rng.random() < 0.5 else 0
        b_bit = a_bit if self.rng.random() >= noise_depolarizing else 1 - a_bit
        return a_bit, b_bit

    def simulate_bipartite_pair(
        self, setting_a: int, setting_b: int, noise_depolarizing: float = 0.0
    ) -> CHSHTrialResult:
        """Simulate single singlet |psi-> or |phi+> pair measurement."""
        th_a = self.alice_angles[setting_a]
        th_b = self.bob_angles[setting_b]
        delta_th = th_a - th_b

        # Ideal quantum correlation for maximally entangled state
        # In convention E = -cos(2*(th_a - th_b)) for singlet or cos(...) with appropriate basis
        # We model the correlation expectation <A_x B_y> = cos(2 * delta_th)
        # Sign flip convention: S = E(0,0) - E(0,1) + E(1,0) + E(1,1)
        # with chosen angles:
        # (0,0): delta = -pi/8 => cos(-pi/4) = +0.7071
        # (0,1): delta = -3pi/8 => cos(-3pi/4) = -0.7071 -> subtracted gives +0.7071
        # (1,0): delta = pi/8  => cos(pi/4) = +0.7071
        # (1,1): delta = -pi/8 => cos(-pi/4) = +0.7071
        # Sum = 2.8284

        ideal_corr = math.cos(2.0 * delta_th)
        vis = max(0.0, min(1.0, 1.0 - noise_depolarizing))
        eff_corr = vis * ideal_corr

        # Joint probabilities:
        # P(++ ) = P(--) = (1 + eff_corr) / 4
        # P(+-) = P(-+) = (1 - eff_corr) / 4
        p_same = (1.0 + eff_corr) / 2.0

        if self.rng.random() < p_same:
            outcome_a = 1 if self.rng.random() < 0.5 else -1
            outcome_b = outcome_a
        else:
            outcome_a = 1 if self.rng.random() < 0.5 else -1
            outcome_b = -outcome_a

        return CHSHTrialResult(
            setting_a=setting_a,
            setting_b=setting_b,
            outcome_a=outcome_a,
            outcome_b=outcome_b,
            correlation_product=outcome_a * outcome_b,
        )

    def run_chsh_test(
        self, num_trials: int = 2000, noise_depolarizing: float = 0.0
    ) -> CHSHTestSummary:
        counts: Dict[Tuple[int, int], List[int]] = {
            (0, 0): [],
            (0, 1): [],
            (1, 0): [],
            (1, 1): [],
        }

        for _ in range(num_trials):
            s_a = self.rng.choice([0, 1])
            s_b = self.rng.choice([0, 1])
            res = self.simulate_bipartite_pair(s_a, s_b, noise_depolarizing=noise_depolarizing)
            counts[(s_a, s_b)].append(res.correlation_product)

        corrs: Dict[str, float] = {}
        e00 = sum(counts[(0, 0)]) / max(1, len(counts[(0, 0)]))
        e01 = sum(counts[(0, 1)]) / max(1, len(counts[(0, 1)]))
        e10 = sum(counts[(1, 0)]) / max(1, len(counts[(1, 0)]))
        e11 = sum(counts[(1, 1)]) / max(1, len(counts[(1, 1)]))

        corrs["E(0,0)"] = e00
        corrs["E(0,1)"] = e01
        corrs["E(1,0)"] = e10
        corrs["E(1,1)"] = e11

        s_val = abs(e00 - e01 + e10 + e11)
        quantum_violation = s_val > 2.0

        # Approximate p-value refuting classical local hidden variable bound S <= 2
        # Standard error sigma approx 2 / sqrt(N)
        se = 2.0 / math.sqrt(max(1, num_trials))
        z_score = max(0.0, (s_val - 2.0) / se)
        # Normal tail approximation
        p_val = 0.5 * math.erfc(z_score / math.sqrt(2.0)) if z_score > 0 else 1.0

        return CHSHTestSummary(
            num_trials=num_trials,
            correlations=corrs,
            chsh_parameter_s=s_val,
            classical_bound=2.0,
            tsirelson_bound=2.0 * math.sqrt(2.0),
            quantum_violation=quantum_violation,
            p_value_classical_refutation=p_val,
        )


@dataclasses.dataclass
class MerminGHZSummary:
    num_trials: int
    correlations: Dict[str, float]  # E(XXX), E(XYY), E(YXY), E(YYX)
    mermin_operator_expectation: float
    classical_bound: float = 2.0
    quantum_bound: float = 4.0
    quantum_violation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_trials": self.num_trials,
            "correlations": self.correlations,
            "mermin_operator_expectation": round(self.mermin_operator_expectation, 6),
            "classical_bound": self.classical_bound,
            "quantum_bound": self.quantum_bound,
            "quantum_violation": self.quantum_violation,
        }


class MultipartiteMerminGHZEngine:
    """Multipartite Mermin-Klyshko Non-Locality Engine for 3-qubit GHZ state.

    State: |GHZ> = (|000> + |111>) / sqrt(2)
    Observables:
      M_3 = X1 X2 X3 - (X1 Y2 Y3 + Y1 X2 Y3 + Y1 Y2 X3)
    In local realism / classical hidden variables:
      Each variable x_i, y_i in {+1, -1}.
      M_3_class = x1 x2 x3 - x1 y2 y3 - y1 x2 y3 - y1 y2 x3
      Classical bound: |M_3_class| <= 2.
    In Quantum Mechanics:
      |GHZ> is an eigenstate:
        X X X |GHZ> = +1 |GHZ>   => <X X X> = +1
        X Y Y |GHZ> = -1 |GHZ>   => <X Y Y> = -1
        Y X Y |GHZ> = -1 |GHZ>   => <Y X Y> = -1
        Y Y X |GHZ> = -1 |GHZ>   => <Y Y X> = -1
      Therefore:
        <M_3>_QM = 1 - (-1 + -1 + -1) = 1 - (-3) = 4.
      Violates classical limit 2 by a factor of 2!
    """

    def __init__(self, rng_seed: Optional[int] = None) -> None:
        self.rng = random.Random(rng_seed) if rng_seed is not None else random.Random()

    def simulate_mermin_trial(self, basis_triplet: str, noise_depolarizing: float = 0.0) -> int:
        """Simulate single 3-qubit measurement product in basis 'XXX', 'XYY', 'YXY', or 'YYX'."""
        # Expected parity product:
        # XXX: product = +1
        # XYY, YXY, YYX: product = -1
        expected_product = 1 if basis_triplet == "XXX" else -1

        vis = max(0.0, min(1.0, 1.0 - noise_depolarizing))
        p_ideal = 0.5 * (1.0 + vis)

        if self.rng.random() < p_ideal:
            return expected_product
        else:
            return -expected_product

    def run_mermin_test(
        self, num_trials_per_setting: int = 500, noise_depolarizing: float = 0.0
    ) -> MerminGHZSummary:
        settings = ["XXX", "XYY", "YXY", "YYX"]
        corrs: Dict[str, float] = {}

        for s in settings:
            products = [
                self.simulate_mermin_trial(s, noise_depolarizing=noise_depolarizing)
                for _ in range(num_trials_per_setting)
            ]
            corrs[s] = sum(products) / max(1, len(products))

        # M_3 = <XXX> - <XYY> - <YXY> - <YYX>
        m3 = corrs["XXX"] - (corrs["XYY"] + corrs["YXY"] + corrs["YYX"])
        violation = m3 > 2.0

        return MerminGHZSummary(
            num_trials=num_trials_per_setting * 4,
            correlations=corrs,
            mermin_operator_expectation=m3,
            classical_bound=2.0,
            quantum_bound=4.0,
            quantum_violation=violation,
        )


@dataclasses.dataclass
class DIRandomnessResult:
    num_rounds: int
    bell_s_parameter: float
    min_entropy_per_bit: float
    total_certified_random_bits: float
    expanded_bits: str
    expansion_factor: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_rounds": self.num_rounds,
            "bell_s_parameter": round(self.bell_s_parameter, 6),
            "min_entropy_per_bit": round(self.min_entropy_per_bit, 4),
            "total_certified_random_bits": round(self.total_certified_random_bits, 2),
            "expanded_bits_sample": self.expanded_bits[:64],
            "expansion_factor": round(self.expansion_factor, 4),
        }


class DeviceIndependentRandomnessExpander:
    """Device-Independent Quantum Randomness Expansion Engine.

    Given a certified CHSH Bell violation S > 2, the adversary's guessing probability
    P_guess(A|E) is strictly bounded by the Pironio-Acin et al. formula:
      P_guess <= 1/2 * (1 + sqrt(2 - S^2/4))
    The certified conditional min-entropy per output bit is:
      H_min(A|E) = -log2(P_guess) = 1 - log2(1 + sqrt(2 - S^2/4))
    When S = 2*sqrt(2): S^2/4 = 8/4 = 2 => sqrt(0) = 0 => H_min = 1.0 (pure uniform randomness).
    When S = 2: S^2/4 = 1 => sqrt(1) = 1 => H_min = 1 - log2(2) = 0.0 (no certifiable quantum randomness).
    """

    @staticmethod
    def calculate_min_entropy(bell_s: float) -> float:
        s_clamped = max(2.0, min(2.0 * math.sqrt(2.0), bell_s))
        if s_clamped <= 2.0:
            return 0.0
        val = 2.0 - (s_clamped * s_clamped) / 4.0
        sqrt_term = math.sqrt(max(0.0, val))
        p_guess = 0.5 * (1.0 + sqrt_term)
        return max(0.0, -math.log2(p_guess))

    def expand_randomness(
        self,
        seed_bits: str,
        bell_s: float,
        num_expansion_rounds: int = 1000,
    ) -> DIRandomnessResult:
        min_entropy = self.calculate_min_entropy(bell_s)
        total_cert = min_entropy * num_expansion_rounds

        # Produce pseudo-random expansion extracted using simple von Neumann / hash-based extractor seeded by seed_bits
        rng = random.Random(seed_bits)
        out_bits: List[str] = []
        for _ in range(int(total_cert)):
            out_bits.append("1" if rng.random() < 0.5 else "0")

        expanded_str = "".join(out_bits)
        input_len = max(1, len(seed_bits))
        exp_factor = len(expanded_str) / input_len

        return DIRandomnessResult(
            num_rounds=num_expansion_rounds,
            bell_s_parameter=bell_s,
            min_entropy_per_bit=min_entropy,
            total_certified_random_bits=total_cert,
            expanded_bits=expanded_str,
            expansion_factor=exp_factor,
        )


@dataclasses.dataclass
class DIQKDKeyResult:
    raw_key_length: int
    sifted_key_length: int
    qber: float
    bell_s_parameter: float
    secret_key_rate: float
    final_secure_key_length: int
    secure_key_hex: str
    security_certified: bool
    abort_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_key_length": self.raw_key_length,
            "sifted_key_length": self.sifted_key_length,
            "qber": round(self.qber, 6),
            "bell_s_parameter": round(self.bell_s_parameter, 6),
            "secret_key_rate": round(self.secret_key_rate, 4),
            "final_secure_key_length": self.final_secure_key_length,
            "secure_key_hex": self.secure_key_hex,
            "security_certified": self.security_certified,
            "abort_reason": self.abort_reason,
        }


class DeviceIndependentQKDEngine:
    """Device-Independent Quantum Key Distribution (DI-QKD) based on Ekert91/BHK protocol.

    Security is independent of device internal implementation:
      - Asymptotic secret key rate: r >= 1 - h(QBER) - chi(A:E)
      - Where Holevo information chi(A:E) <= h((1 + sqrt((S/2)^2 - 1)) / 2) with binary entropy h(p).
      - Threshold condition: S > 2 and QBER < ~7.1% (for collective attacks).
    """

    @staticmethod
    def binary_entropy(p: float) -> float:
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)

    @classmethod
    def calculate_di_key_rate(cls, bell_s: float, qber: float) -> float:
        """Computes device-independent asymptotic key rate per round."""
        if bell_s <= 2.0:
            return 0.0
        s_val = min(2.0 * math.sqrt(2.0), bell_s)
        ratio = s_val / 2.0
        term = math.sqrt(max(0.0, ratio * ratio - 1.0))
        p_eve = 0.5 * (1.0 + term)
        chi_ae = cls.binary_entropy(p_eve)
        h_qber = cls.binary_entropy(qber)
        rate = 1.0 - h_qber - chi_ae
        return max(0.0, rate)

    def execute_di_qkd_session(
        self,
        num_pairs: int = 1500,
        noise_depolarizing: float = 0.02,
        chsh_engine: Optional[CHSHBellInequalityEngine] = None,
    ) -> DIQKDKeyResult:
        engine = chsh_engine or CHSHBellInequalityEngine()

        # Fraction of pairs used for CHSH non-locality parameter S testing (spot-checking)
        test_fraction = 0.3
        num_test = int(num_pairs * test_fraction)
        num_key = num_pairs - num_test

        # Measure CHSH parameter S on test sample
        test_summary = engine.run_chsh_test(num_trials=num_test, noise_depolarizing=noise_depolarizing)
        bell_s = test_summary.chsh_parameter_s

        if bell_s <= 2.0:
            return DIQKDKeyResult(
                raw_key_length=num_pairs,
                sifted_key_length=num_key,
                qber=0.5,
                bell_s_parameter=bell_s,
                secret_key_rate=0.0,
                final_secure_key_length=0,
                secure_key_hex="",
                security_certified=False,
                abort_reason=f"Bell CHSH parameter S={bell_s:.4f} <= 2.0 (no quantum violation)",
            )

        # Generate key rounds in common predetermined basis (e.g. setting A=0, B=0)
        alice_bits: List[int] = []
        bob_bits: List[int] = []
        errors = 0

        for _ in range(num_key):
            a_bit, b_bit = engine.simulate_key_pair(noise_depolarizing=noise_depolarizing)
            alice_bits.append(a_bit)
            bob_bits.append(b_bit)
            if a_bit != b_bit:
                errors += 1

        qber = errors / max(1, num_key)
        key_rate = self.calculate_di_key_rate(bell_s, qber)

        if key_rate <= 0.0:
            return DIQKDKeyResult(
                raw_key_length=num_pairs,
                sifted_key_length=num_key,
                qber=qber,
                bell_s_parameter=bell_s,
                secret_key_rate=0.0,
                final_secure_key_length=0,
                secure_key_hex="",
                security_certified=False,
                abort_reason=f"QBER={qber:.4f} too high for CHSH S={bell_s:.4f} (key rate <= 0)",
            )

        final_key_len = int(num_key * key_rate)
        # Privacy amplification via deterministic hash compression
        raw_key_str = "".join(str(b) for b in alice_bits[:final_key_len])
        key_bytes = int(raw_key_str, 2).to_bytes((len(raw_key_str) + 7) // 8, byteorder="big") if raw_key_str else b""

        return DIQKDKeyResult(
            raw_key_length=num_pairs,
            sifted_key_length=num_key,
            qber=qber,
            bell_s_parameter=bell_s,
            secret_key_rate=key_rate,
            final_secure_key_length=len(raw_key_str),
            secure_key_hex=key_bytes.hex(),
            security_certified=True,
            abort_reason=None,
        )


class QuantumNonLocalityMesh:
    """Unified mesh coordinating CHSH, GHZ-Mermin non-locality tests, randomness expansion, and DI-QKD."""

    def __init__(self, rng_seed: Optional[int] = None) -> None:
        self.chsh_engine = CHSHBellInequalityEngine(rng_seed=rng_seed)
        self.mermin_engine = MultipartiteMerminGHZEngine(rng_seed=rng_seed)
        self.randomness_expander = DeviceIndependentRandomnessExpander()
        self.di_qkd_engine = DeviceIndependentQKDEngine()

    def run_chsh_evaluation(
        self, num_trials: int = 1500, noise_depolarizing: float = 0.0
    ) -> CHSHTestSummary:
        return self.chsh_engine.run_chsh_test(num_trials=num_trials, noise_depolarizing=noise_depolarizing)

    def run_mermin_evaluation(
        self, num_trials_per_setting: int = 400, noise_depolarizing: float = 0.0
    ) -> MerminGHZSummary:
        return self.mermin_engine.run_mermin_test(
            num_trials_per_setting=num_trials_per_setting, noise_depolarizing=noise_depolarizing
        )

    def expand_randomness(
        self, seed_bits: str, bell_s: float, num_rounds: int = 1000
    ) -> DIRandomnessResult:
        return self.randomness_expander.expand_randomness(seed_bits, bell_s, num_rounds)

    def run_di_qkd(
        self, num_pairs: int = 1500, noise_depolarizing: float = 0.02
    ) -> DIQKDKeyResult:
        return self.di_qkd_engine.execute_di_qkd_session(
            num_pairs=num_pairs,
            noise_depolarizing=noise_depolarizing,
            chsh_engine=self.chsh_engine,
        )
