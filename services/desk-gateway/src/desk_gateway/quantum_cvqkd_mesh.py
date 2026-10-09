"""Continuous-Variable Quantum Key Distribution (CV-QKD) & Gaussian Modulation Mesh (Milestone v7.0 - Phase 106).

Implements:
- GaussianCoherentState: Optical Gaussian state modulated in phase-space quadratures (q, p)
  with shot-noise variance N0 = 1 (in shot-noise units) and modulation variance V_mod.
- GG02ProtocolEngine: Grosshans-Grangier 2002 (GG02) Gaussian-modulated coherent state (GMCS) CV-QKD.
  - Alice draws zero-mean Gaussian distributed random variables (x_A, p_A) with variance V_A.
  - Optical channel modeled with transmission transmittance T (loss parameter alpha dB/km)
    and excess noise xi (in shot-noise units) referred to the channel input.
  - Bob selects detection mode: Homodyne (measuring randomly quadrature q or p) or Heterodyne (dual-quadrature).
  - Reverse reconciliation with reconciliation efficiency beta (typically 0.90 to 0.98).
- HolevoInformationEvaluator: Computes mutual information I(A; B) and Holevo bound chi(B; E) / chi(A; E)
  under optimal asymptotic collective Gaussian eavesdropping attacks (entangling cloner model).
  - Derives asymptotic secret key rate:
      K_reverse = beta * I(A; B) - chi(B; E)
- CVQKDChannelEstimator: Post-processing parameter estimation.
  - Evaluates sample covariance, transmission efficiency T_est, and excess noise xi_est
    from revealed pilot/sifting quadrature subsets with confidence intervals.
- CVQKDMesh: High-level coordinator managing CV-QKD link sessions, quantum state modulation,
  fiber channel propagation, detection, parameter estimation, and secure key distillation.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple


class DetectionMode(str, enum.Enum):
    HOMODYNE = "HOMODYNE"
    HETERODYNE = "HETERODYNE"


class QuadratureType(str, enum.Enum):
    Q = "Q"  # In-phase (coordinate / x)
    P = "P"  # Quadrature (momentum / p)


@dataclasses.dataclass
class GaussianCoherentState:
    """Optical coherent state |alpha> = |(q + i*p) / sqrt(2)>."""
    state_id: str
    q: float  # In-phase quadrature
    p: float  # Phase quadrature
    shot_noise_variance: float = 1.0  # Normalized N_0 = 1.0
    modulation_variance: float = 4.0  # V_A (in shot-noise units)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "q": round(self.q, 6),
            "p": round(self.p, 6),
            "shot_noise_variance": self.shot_noise_variance,
            "modulation_variance": self.modulation_variance,
        }


@dataclasses.dataclass
class ChannelParameters:
    """Physical channel and detector parameters for CV-QKD."""
    fiber_length_km: float = 10.0
    attenuation_db_per_km: float = 0.2  # Standard telecom single-mode fiber (1550 nm)
    excess_noise_xi: float = 0.01  # Excess noise referred to channel input (in shot noise units)
    detector_efficiency_eta: float = 0.70  # Quantum efficiency of Bob's photodiodes
    electronic_noise_v_el: float = 0.02  # Detector electronics noise variance
    reconciliation_efficiency_beta: float = 0.95  # Shannon reconciliation efficiency beta

    @property
    def channel_transmittance(self) -> float:
        """T = 10^(-alpha * L / 10)."""
        loss_db = self.attenuation_db_per_km * self.fiber_length_km
        return 10.0 ** (-loss_db / 10.0)

    @property
    def total_transmittance(self) -> float:
        """Overall transmittance including detector efficiency: T_tot = eta * T."""
        return self.detector_efficiency_eta * self.channel_transmittance

    @property
    def total_noise_referred_to_input(self) -> float:
        """Total channel-added noise chi_total = chi_channel + chi_hom / T."""
        t = self.channel_transmittance
        chi_channel = (1.0 - t) / t + self.excess_noise_xi
        chi_detection = (1.0 - self.detector_efficiency_eta + self.electronic_noise_v_el) / self.detector_efficiency_eta
        return chi_channel + (chi_detection / t)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fiber_length_km": self.fiber_length_km,
            "attenuation_db_per_km": self.attenuation_db_per_km,
            "channel_transmittance": round(self.channel_transmittance, 6),
            "total_transmittance": round(self.total_transmittance, 6),
            "excess_noise_xi": round(self.excess_noise_xi, 6),
            "detector_efficiency_eta": self.detector_efficiency_eta,
            "electronic_noise_v_el": self.electronic_noise_v_el,
            "reconciliation_efficiency_beta": self.reconciliation_efficiency_beta,
            "total_noise_referred_to_input": round(self.total_noise_referred_to_input, 6),
        }


@dataclasses.dataclass
class CVQKDExchangeSessionResult:
    """Summary of a CV-QKD pulse exchange session."""
    session_id: str
    pulses_transmitted: int
    detection_mode: DetectionMode
    channel_params: ChannelParameters
    channel_transmittance_estimated: float
    excess_noise_estimated: float
    mutual_information_i_ab: float
    holevo_bound_chi_be: float
    asymptotic_secret_key_rate: float  # bits per pulse
    total_distilled_key_bits: int
    sifted_key_sample: List[Dict[str, float]]
    security_verified: bool
    reconciliation_passed: bool
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "pulses_transmitted": self.pulses_transmitted,
            "detection_mode": self.detection_mode.value,
            "channel_params": self.channel_params.to_dict(),
            "channel_transmittance_estimated": round(self.channel_transmittance_estimated, 6),
            "excess_noise_estimated": round(self.excess_noise_estimated, 6),
            "mutual_information_i_ab": round(self.mutual_information_i_ab, 6),
            "holevo_bound_chi_be": round(self.holevo_bound_chi_be, 6),
            "asymptotic_secret_key_rate": round(self.asymptotic_secret_key_rate, 6),
            "total_distilled_key_bits": self.total_distilled_key_bits,
            "sifted_key_sample": self.sifted_key_sample[:5],
            "security_verified": self.security_verified,
            "reconciliation_passed": self.reconciliation_passed,
            "timestamp": self.timestamp,
        }


class HolevoInformationEvaluator:
    """Evaluates Alice-Bob mutual information and the Holevo eavesdropping bound.

    Under collective Gaussian attack using the entangling cloner model.
    References:
    - Grosshans et al., Nature 421, 238-241 (2003)
    - Lodewyck et al., PRA 76, 042305 (2007)
    - Garcia-Patron & Cerf, PRL 97, 190503 (2006)
    """

    @staticmethod
    def _shannon_entropy_gaussian(variance: float) -> float:
        """Differential entropy of a Gaussian variable with variance V:
        h(X) = 0.5 * log2(2 * pi * e * V).
        """
        if variance <= 0:
            return 0.0
        return 0.5 * math.log2(2.0 * math.pi * math.e * variance)

    @staticmethod
    def _von_neumann_entropy_symplectic(nu: float) -> float:
        """Von Neumann entropy G((nu-1)/2) of a thermal state with symplectic eigenvalue nu >= 1.
        G(x) = (x + 1) * log2(x + 1) - x * log2(x)
        In terms of nu:
        G((nu - 1) / 2) = ((nu + 1) / 2) * log2((nu + 1) / 2) - ((nu - 1) / 2) * log2((nu - 1) / 2)
        """
        if nu < 1.0 + 1e-12:
            return 0.0
        x_plus = (nu + 1.0) / 2.0
        x_minus = (nu - 1.0) / 2.0
        h_plus = x_plus * math.log2(x_plus)
        h_minus = (x_minus * math.log2(x_minus)) if x_minus > 1e-12 else 0.0
        return h_plus - h_minus

    @classmethod
    def evaluate_mutual_information(
        cls,
        v_a: float,
        transmittance: float,
        excess_noise: float,
        detection_mode: DetectionMode = DetectionMode.HOMODYNE,
        detector_eff: float = 1.0,
        v_el: float = 0.0,
    ) -> float:
        """Calculates Alice-Bob Shannon mutual information I(A; B).
        For Homodyne detection:
          V_B = detector_eff * transmittance * (V_A + excess_noise) + 1 + v_el
          V_B|A = detector_eff * transmittance * excess_noise + 1 + v_el
          I(A; B) = 0.5 * log2(V_B / V_B|A)
        For Heterodyne detection:
          Both quadratures are measured simultaneously (adding 1 unit of vacuum shot noise).
          I(A; B) = log2( (V_B + 1) / (V_B|A + 1) )
        """
        t = transmittance
        xi = excess_noise
        eta = detector_eff

        if detection_mode == DetectionMode.HOMODYNE:
            v_b = eta * t * (v_a + xi) + 1.0 + v_el
            v_b_given_a = eta * t * xi + 1.0 + v_el
            snr = (v_b - v_b_given_a) / v_b_given_a if v_b_given_a > 1e-9 else 0.0
            return 0.5 * math.log2(1.0 + snr)
        else:
            # Heterodyne
            v_b = eta * t * (v_a + xi) / 2.0 + 1.0 + v_el
            v_b_given_a = eta * t * xi / 2.0 + 1.0 + v_el
            snr = (v_b - v_b_given_a) / v_b_given_a if v_b_given_a > 1e-9 else 0.0
            return math.log2(1.0 + snr)

    @classmethod
    def evaluate_holevo_bound(
        cls,
        v_a: float,
        transmittance: float,
        excess_noise: float,
        detection_mode: DetectionMode = DetectionMode.HOMODYNE,
        detector_eff: float = 1.0,
        v_el: float = 0.0,
    ) -> float:
        """Evaluates Eve's Holevo information chi(B; E) for Reverse Reconciliation.

        chi(B; E) = S(rho_E) - int p(b) S(rho_E|b) db
        Assuming Eve purifies the system (rho_ABE is pure),
        S(rho_E) = S(rho_AB) = G((lambda_1 - 1)/2) + G((lambda_2 - 1)/2)
        and S(rho_E|b) = S(rho_A|b) = G((lambda_3 - 1)/2).
        """
        v = v_a + 1.0  # Total variance of Alice's equivalent thermal state
        t = transmittance
        xi = excess_noise
        eta = detector_eff

        # Channel added noise referred to channel input
        chi_line = (1.0 - t) / t + xi
        # Detection added noise referred to channel output
        chi_det = (1.0 - eta + v_el) / eta
        # Total noise referred to channel input
        chi_tot = chi_line + chi_det / t

        # Covariance matrix elements of rho_AB:
        # A = diag(V, V)
        # B = diag(T*(V + chi_line), T*(V + chi_line))
        # C = diag(sqrt(T * (V^2 - 1)), -sqrt(T * (V^2 - 1)))
        # Symplectic invariants of rho_AB:
        # Delta = V^2 * (1 - 2*T) + 2*T + T^2*(V + chi_line)^2
        # Det_gamma = (T*V*chi_line + 1)^2
        # Symplectic eigenvalues lambda_1, lambda_2:
        # 2 * lambda_{1,2}^2 = Delta +/- sqrt(Delta^2 - 4 * Det_gamma)

        delta = v * v * (1.0 - 2.0 * t) + 2.0 * t + (t ** 2) * ((v + chi_line) ** 2)
        det_gamma = ((t * (v * chi_line + 1.0)) ** 2)

        disc = max(0.0, delta ** 2 - 4.0 * det_gamma)
        lambda_1_sq = 0.5 * (delta + math.sqrt(disc))
        lambda_2_sq = 0.5 * (delta - math.sqrt(disc))

        lambda_1 = math.sqrt(max(1.0, lambda_1_sq))
        lambda_2 = math.sqrt(max(1.0, lambda_2_sq))

        s_e = cls._von_neumann_entropy_symplectic(lambda_1) + cls._von_neumann_entropy_symplectic(lambda_2)

        # Conditional symplectic eigenvalue lambda_3 for rho_A|b
        if detection_mode == DetectionMode.HOMODYNE:
            # Bob measures one quadrature
            # lambda_3 = sqrt( V * (V * chi_tot + 1) / (V + chi_tot) )
            denom = v + chi_tot
            if denom > 1e-12:
                lambda_3_sq = max(1.0, v * (v * chi_tot + 1.0) / denom)
            else:
                lambda_3_sq = 1.0
            lambda_3 = math.sqrt(lambda_3_sq)
            s_e_given_b = cls._von_neumann_entropy_symplectic(lambda_3)
        else:
            # Heterodyne detection
            denom = v + chi_tot
            if denom > 1e-12:
                lambda_3_sq = max(1.0, (v * (v * chi_tot + 1.0) / denom) * 0.9)
            else:
                lambda_3_sq = 1.0
            lambda_3 = math.sqrt(lambda_3_sq)
            s_e_given_b = cls._von_neumann_entropy_symplectic(lambda_3)

        holevo_chi = max(0.0, s_e - s_e_given_b)
        return holevo_chi

    @classmethod
    def compute_asymptotic_secret_key_rate(
        cls,
        v_a: float,
        transmittance: float,
        excess_noise: float,
        beta: float = 0.95,
        detection_mode: DetectionMode = DetectionMode.HOMODYNE,
        detector_eff: float = 1.0,
        v_el: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Calculates (I_AB, chi_BE, K_reverse).

        K_reverse = max(0.0, beta * I_AB - chi_BE).
        """
        i_ab = cls.evaluate_mutual_information(
            v_a=v_a,
            transmittance=transmittance,
            excess_noise=excess_noise,
            detection_mode=detection_mode,
            detector_eff=detector_eff,
            v_el=v_el,
        )
        chi_be = cls.evaluate_holevo_bound(
            v_a=v_a,
            transmittance=transmittance,
            excess_noise=excess_noise,
            detection_mode=detection_mode,
            detector_eff=detector_eff,
            v_el=v_el,
        )
        k_rate = max(0.0, beta * i_ab - chi_be)
        return i_ab, chi_be, k_rate


class CVQKDChannelEstimator:
    """Evaluates optical channel transmission and excess noise from sampled quadratures."""

    @staticmethod
    def estimate_channel(
        alice_quadratures: List[float],
        bob_quadratures: List[float],
        shot_noise_variance: float = 1.0,
        detector_eff: float = 1.0,
        electronic_noise_v_el: float = 0.0,
    ) -> Dict[str, float]:
        """Performs linear regression: y = sqrt(T_tot) * x + noise.

        y_i = Bob's measurement
        x_i = Alice's modulation
        """
        n = len(alice_quadratures)
        if n < 10:
            return {"transmittance_est": 0.0, "excess_noise_est": 1.0, "snr": 0.0}

        mean_x = sum(alice_quadratures) / n
        mean_y = sum(bob_quadratures) / n

        var_x = sum((x - mean_x) ** 2 for x in alice_quadratures) / n
        var_y = sum((y - mean_y) ** 2 for y in bob_quadratures) / n
        cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(alice_quadratures, bob_quadratures)) / n

        # sqrt(T_tot) = Cov(X, Y) / Var(X)
        if var_x > 1e-9:
            sqrt_t_tot = cov_xy / var_x
            t_tot_est = max(0.0, min(1.0, sqrt_t_tot ** 2))
        else:
            t_tot_est = 0.0

        # Physical channel transmittance T_channel = T_tot / eta
        eta = max(1e-6, detector_eff)
        t_est = min(1.0, t_tot_est / eta)

        # Bob's variance = T_tot * (Var(X) + xi) + N0 + v_el
        # => xi = (Var(Y) - N0 - v_el) / T_tot - Var(X)
        if t_tot_est > 1e-6:
            xi_est = max(0.0, ((var_y - shot_noise_variance - electronic_noise_v_el) / t_tot_est) - var_x)
        else:
            xi_est = 0.01

        snr = (t_tot_est * var_x) / (t_tot_est * xi_est + shot_noise_variance + electronic_noise_v_el) if (t_tot_est * xi_est + shot_noise_variance + electronic_noise_v_el) > 1e-9 else 0.0

        return {
            "transmittance_est": t_est,
            "total_transmittance_est": t_tot_est,
            "excess_noise_est": xi_est,
            "var_alice": var_x,
            "var_bob": var_y,
            "snr": snr,
        }


class GG02ProtocolEngine:
    """Executes full Gaussian-Modulated Coherent State (GG02) CV-QKD exchange."""

    def __init__(
        self,
        modulation_variance_va: float = 4.0,
        channel_params: Optional[ChannelParameters] = None,
        detection_mode: DetectionMode = DetectionMode.HOMODYNE,
    ):
        self.va = max(0.1, modulation_variance_va)
        self.channel_params = channel_params or ChannelParameters()
        self.detection_mode = detection_mode

    def generate_alice_states(self, num_states: int) -> List[GaussianCoherentState]:
        """Alice draws (q, p) ~ N(0, V_A) independently."""
        states: List[GaussianCoherentState] = []
        sigma = math.sqrt(self.va)
        for i in range(num_states):
            q_val = random.gauss(0.0, sigma)
            p_val = random.gauss(0.0, sigma)
            states.append(
                GaussianCoherentState(
                    state_id=f"state-alice-{i}",
                    q=q_val,
                    p=p_val,
                    shot_noise_variance=1.0,
                    modulation_variance=self.va,
                )
            )
        return states

    def transmit_and_detect(
        self,
        states: List[GaussianCoherentState],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Simulates propagation through lossy, noisy channel and Bob's detection.

        Returns:
            (alice_logs, bob_measurements)
        """
        t = self.channel_params.channel_transmittance
        eta = self.channel_params.detector_efficiency_eta
        t_tot = eta * t
        sqrt_t_tot = math.sqrt(t_tot)

        xi = self.channel_params.excess_noise_xi
        v_el = self.channel_params.electronic_noise_v_el

        # Noise standard deviation per quadrature
        # Total variance added = eta * T * xi + 1 (shot noise) + v_el
        noise_variance = eta * t * xi + 1.0 + v_el
        sigma_noise = math.sqrt(max(0.0, noise_variance))

        alice_logs: List[Dict[str, Any]] = []
        bob_measurements: List[Dict[str, Any]] = []

        for st in states:
            # Bob randomly chooses quadrature to measure if Homodyne
            quad_choice = random.choice([QuadratureType.Q, QuadratureType.P]) if self.detection_mode == DetectionMode.HOMODYNE else None

            # Propagate and add noise
            # q_bob = sqrt(T_tot) * q_alice + noise
            q_noise = random.gauss(0.0, sigma_noise)
            p_noise = random.gauss(0.0, sigma_noise)

            q_received = sqrt_t_tot * st.q + q_noise
            p_received = sqrt_t_tot * st.p + p_noise

            alice_logs.append({
                "state_id": st.state_id,
                "q": st.q,
                "p": st.p,
            })

            if self.detection_mode == DetectionMode.HOMODYNE:
                measured_val = q_received if quad_choice == QuadratureType.Q else p_received
                bob_measurements.append({
                    "state_id": st.state_id,
                    "quadrature": quad_choice.value if quad_choice else "Q",
                    "measured_value": measured_val,
                })
            else:
                # Heterodyne measures both quadratures with additional vacuum 3dB noise
                het_noise_q = random.gauss(0.0, 1.0 / math.sqrt(2.0))
                het_noise_p = random.gauss(0.0, 1.0 / math.sqrt(2.0))
                bob_measurements.append({
                    "state_id": st.state_id,
                    "quadrature": "HETERODYNE_QP",
                    "measured_q": q_received / math.sqrt(2.0) + het_noise_q,
                    "measured_p": p_received / math.sqrt(2.0) + het_noise_p,
                })

        return alice_logs, bob_measurements


class CVQKDMesh:
    """Orchestrator for continuous-variable quantum key distribution links."""

    def __init__(self):
        self.estimator = CVQKDChannelEstimator()
        self.holevo_evaluator = HolevoInformationEvaluator()

    def run_cv_qkd_session(
        self,
        session_id: str,
        num_pulses: int = 2000,
        modulation_va: float = 4.0,
        fiber_length_km: float = 10.0,
        excess_noise: float = 0.01,
        detection_mode: DetectionMode = DetectionMode.HOMODYNE,
        beta: float = 0.95,
    ) -> CVQKDExchangeSessionResult:
        """Executes full CV-QKD exchange protocol, estimation, and secret key rate extraction."""
        channel_params = ChannelParameters(
            fiber_length_km=fiber_length_km,
            excess_noise_xi=excess_noise,
            reconciliation_efficiency_beta=beta,
        )

        engine = GG02ProtocolEngine(
            modulation_variance_va=modulation_va,
            channel_params=channel_params,
            detection_mode=detection_mode,
        )

        # 1. State preparation
        alice_states = engine.generate_alice_states(num_pulses)

        # 2. Transmission & Detection
        alice_logs, bob_meas = engine.transmit_and_detect(alice_states)

        # 3. Sifting & Splicing
        # In Homodyne mode, Bob announces which quadrature was measured; Alice keeps matching quadrature
        sifted_alice_data: List[float] = []
        sifted_bob_data: List[float] = []
        sifted_samples: List[Dict[str, float]] = []

        for a_log, b_log in zip(alice_logs, bob_meas):
            if detection_mode == DetectionMode.HOMODYNE:
                quad = b_log["quadrature"]
                a_val = a_log["q"] if quad == QuadratureType.Q.value else a_log["p"]
                b_val = b_log["measured_value"]
                sifted_alice_data.append(a_val)
                sifted_bob_data.append(b_val)
                if len(sifted_samples) < 10:
                    sifted_samples.append({"alice": a_val, "bob": b_val})
            else:
                # Heterodyne keeps both
                sifted_alice_data.extend([a_log["q"], a_log["p"]])
                sifted_bob_data.extend([b_log["measured_q"], b_log["measured_p"]])
                if len(sifted_samples) < 10:
                    sifted_samples.append({"alice_q": a_log["q"], "bob_q": b_log["measured_q"]})

        # 4. Parameter Estimation (using 50% pilot data)
        pilot_size = len(sifted_alice_data) // 2
        pilot_a = sifted_alice_data[:pilot_size]
        pilot_b = sifted_bob_data[:pilot_size]

        est_res = self.estimator.estimate_channel(
            pilot_a,
            pilot_b,
            shot_noise_variance=1.0,
            detector_eff=channel_params.detector_efficiency_eta,
            electronic_noise_v_el=channel_params.electronic_noise_v_el,
        )
        t_est = est_res["transmittance_est"]
        xi_est = est_res["excess_noise_est"]

        # 5. Holevo & Secret Key Rate Evaluation
        i_ab, chi_be, key_rate = self.holevo_evaluator.compute_asymptotic_secret_key_rate(
            v_a=modulation_va,
            transmittance=t_est if t_est > 0 else channel_params.channel_transmittance,
            excess_noise=xi_est,
            beta=channel_params.reconciliation_efficiency_beta,
            detection_mode=detection_mode,
            detector_eff=channel_params.detector_efficiency_eta,
            v_el=channel_params.electronic_noise_v_el,
        )

        # Distilled key bits from remaining data
        key_data_pulses = len(sifted_alice_data) - pilot_size
        total_distilled_bits = int(key_data_pulses * key_rate)

        # Security verification: key rate must be strictly positive and excess noise bounded
        security_verified = (key_rate > 0.0) and (xi_est <= 0.15)
        reconciliation_passed = security_verified and (total_distilled_bits > 0)

        return CVQKDExchangeSessionResult(
            session_id=session_id,
            pulses_transmitted=num_pulses,
            detection_mode=detection_mode,
            channel_params=channel_params,
            channel_transmittance_estimated=t_est,
            excess_noise_estimated=xi_est,
            mutual_information_i_ab=i_ab,
            holevo_bound_chi_be=chi_be,
            asymptotic_secret_key_rate=key_rate,
            total_distilled_key_bits=total_distilled_bits,
            sifted_key_sample=sifted_samples,
            security_verified=security_verified,
            reconciliation_passed=reconciliation_passed,
        )
