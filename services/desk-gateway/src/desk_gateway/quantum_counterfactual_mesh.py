"""Quantum Counterfactual Communication & Ghost Imaging Mesh (Milestone v6.9 - Phase 104).

Implements:
- InteractionFreeMeasurement: Elitzur-Vaidman interaction-free bomb tester and chained quantum Zeno effect.
  Enables detection of an absorbing object (e.g., sensitive quantum object / bomb) without transferring
  a single photon / energy quanta through the interaction path in the asymptotic limit (N stages).
- CounterfactualDirectCommunication: Salih, Li, Al-Amri, and Zubairy (Salih et al.) chained Mach-Zehnder
  interferometer protocol for direct classical counterfactual communication without physical particle transmission.
  Encodes bit 0 or bit 1 using nested outer and inner interferometers with chained quantum Zeno interrogation.
- QuantumGhostImagingEngine: Ghost imaging protocol utilizing spatially correlated entangled photon pairs
  (EPR / SPDC signal and idler photons).
  Reconstructs high-resolution images of objects located exclusively in the signal beam path
  using single-pixel bucket detector data correlated with an idler multipixel camera (or rasterized detector),
  where neither photon beam alone carries spatial object information.
- QuantumCounterfactualMesh: High-level coordinator managing counterfactual communication channels,
  interaction-free interrogation sessions, and ghost imaging sensor reconstruction matrices.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple


class TransmissionOutcome(str, enum.Enum):
    DETECTION_WITHOUT_INTERACTION = "DETECTION_WITHOUT_INTERACTION"
    CLASSICAL_INTERACTION = "CLASSICAL_INTERACTION"
    NO_DETECTION = "NO_DETECTION"
    TRANSMISSION_ABSENCE_CONFIRMED = "TRANSMISSION_ABSENCE_CONFIRMED"


@dataclasses.dataclass
class InteractionFreeMeasurementResult:
    """Result of an Elitzur-Vaidman / Chained Zeno interaction-free measurement."""
    object_present: bool
    zeno_cycles: int
    photon_absorbed: bool
    detection_successful: bool
    counterfactual_efficiency: float  # eta = P(detection) / (P(detection) + P(absorption))
    channel_leakage_probability: float  # Probability of photon traversing the object channel
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_present": self.object_present,
            "zeno_cycles": self.zeno_cycles,
            "photon_absorbed": self.photon_absorbed,
            "detection_successful": self.detection_successful,
            "counterfactual_efficiency": round(self.counterfactual_efficiency, 6),
            "channel_leakage_probability": round(self.channel_leakage_probability, 6),
            "details": self.details,
        }


class InteractionFreeMeasurement:
    """Elitzur-Vaidman bomb testing and Chained Quantum Zeno interrogation engine."""

    def __init__(self, default_zeno_cycles: int = 50):
        self.default_zeno_cycles = max(1, default_zeno_cycles)

    def elitzur_vaidman_single_stage(self, object_present: bool) -> InteractionFreeMeasurementResult:
        """Standard 1-stage Mach-Zehnder Elitzur-Vaidman bomb tester.
        
        Beam splitter 50:50.
        Without object: constructive interference at Dark detector D0 (or Bright detector D1).
        With object in path 1:
        - 50% photon takes path 1: absorbed (bomb explodes).
        - 50% photon takes path 0: enters BS2:
            - 25% Dark detector (interaction-free detection!)
            - 25% Bright detector (inconclusive).
        Counterfactual efficiency eta = P(dark) / (P(dark) + P(absorbed)) = 0.25 / (0.25 + 0.50) = 1/3 ~ 33.3%.
        """
        if not object_present:
            # Constructive interference to detector D_bright, 0 to D_dark
            return InteractionFreeMeasurementResult(
                object_present=False,
                zeno_cycles=1,
                photon_absorbed=False,
                detection_successful=False,
                counterfactual_efficiency=1.0,
                channel_leakage_probability=0.5,
                details={"detector": "D_BRIGHT", "mode": "free_constructive"},
            )

        # Object is present
        rand_val = random.random()
        if rand_val < 0.50:
            # Photon took path 1 -> absorbed
            return InteractionFreeMeasurementResult(
                object_present=True,
                zeno_cycles=1,
                photon_absorbed=True,
                detection_successful=False,
                counterfactual_efficiency=1.0 / 3.0,
                channel_leakage_probability=0.5,
                details={"detector": "NONE", "mode": "absorbed_by_object"},
            )
        elif rand_val < 0.75:
            # Photon took path 0 -> BS2 -> detected at Dark port (interaction-free success!)
            return InteractionFreeMeasurementResult(
                object_present=True,
                zeno_cycles=1,
                photon_absorbed=False,
                detection_successful=True,
                counterfactual_efficiency=1.0 / 3.0,
                channel_leakage_probability=0.5,
                details={"detector": "D_DARK", "mode": "counterfactual_detection"},
            )
        else:
            # Detected at Bright port (inconclusive)
            return InteractionFreeMeasurementResult(
                object_present=True,
                zeno_cycles=1,
                photon_absorbed=False,
                detection_successful=False,
                counterfactual_efficiency=1.0 / 3.0,
                channel_leakage_probability=0.5,
                details={"detector": "D_BRIGHT", "mode": "inconclusive"},
            )

    def chained_zeno_interrogation(
        self,
        object_present: bool,
        cycles: Optional[int] = None,
    ) -> InteractionFreeMeasurementResult:
        """Chained Quantum Zeno effect interrogation across N cycles.
        
        Using N beam splitters with rotation theta = pi / (2 * N):
        - If no object: photon state rotates by N * theta = pi / 2 from |0> to |1>.
        - If object is present in path 1 at each cycle:
            At each cycle, state is cos(theta)|0> + sin(theta)|1>.
            Measurement collapses state to |0> with probability cos^2(theta).
            After N cycles without absorption:
            P_survival = (cos(pi / (2*N)))^(2*N) -> 1 as N -> inf.
            Absorption probability P_abs = 1 - P_survival ~ pi^2 / (4*N) -> 0.
            Counterfactual efficiency eta = P_det / (P_det + P_abs) -> 1.0 (100% asymptotic counterfactuality).
        """
        N = cycles if cycles is not None else self.default_zeno_cycles
        theta = math.pi / (2.0 * N)

        if not object_present:
            # Without object, photon rotates deterministically from |0> to |1>
            return InteractionFreeMeasurementResult(
                object_present=False,
                zeno_cycles=N,
                photon_absorbed=False,
                detection_successful=False,
                counterfactual_efficiency=1.0,
                channel_leakage_probability=0.0,
                details={"final_state": "|1>", "rotation_rad": math.pi / 2.0},
            )

        # With object present in path 1:
        absorbed = False
        p_stay_0 = math.cos(theta) ** 2

        for step in range(N):
            if random.random() > p_stay_0:
                # Photon entered path 1 and was absorbed
                absorbed = True
                break

        survival_prob = math.cos(theta) ** (2 * N)
        channel_leakage = 1.0 - survival_prob
        efficiency = survival_prob / (survival_prob + channel_leakage) if (survival_prob + channel_leakage) > 0 else 0.5

        return InteractionFreeMeasurementResult(
            object_present=True,
            zeno_cycles=N,
            photon_absorbed=absorbed,
            detection_successful=not absorbed,
            counterfactual_efficiency=efficiency,
            channel_leakage_probability=channel_leakage,
            details={
                "steps_completed": N if not absorbed else step + 1,
                "theoretical_survival_prob": survival_prob,
                "theta_step_rad": theta,
            },
        )


@dataclasses.dataclass
class CounterfactualTransmissionResult:
    """Result of transmitting classical information counterfactually."""
    message_bits: str
    received_bits: str
    bit_error_rate: float
    total_photons_used: int
    channel_traversed_photons: int
    counterfactual_purity: float  # 1.0 - (channel_traversed_photons / total_photons_used)
    outer_cycles: int
    inner_cycles: int
    duration_ms: float
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_bits": self.message_bits,
            "received_bits": self.received_bits,
            "bit_error_rate": round(self.bit_error_rate, 6),
            "total_photons_used": self.total_photons_used,
            "channel_traversed_photons": self.channel_traversed_photons,
            "counterfactual_purity": round(self.counterfactual_purity, 6),
            "outer_cycles": self.outer_cycles,
            "inner_cycles": self.inner_cycles,
            "duration_ms": round(self.duration_ms, 3),
            "details": self.details,
        }


class CounterfactualDirectCommunication:
    """Chained nested Mach-Zehnder counterfactual direct communication (Salih et al.).
    
    Bob sets his optical blocker/phase switch depending on the bit to transmit:
    - Bit 0: Bob blocks the inner channel path.
    - Bit 1: Bob leaves the channel unblocked.
    Through nested quantum Zeno interrogation (outer loop M cycles, inner loop N cycles),
    Alice's detectors register the bit without any photon passing through the transmission link
    between Alice and Bob.
    """

    def __init__(self, outer_cycles: int = 15, inner_cycles: int = 15):
        self.outer_cycles = max(2, outer_cycles)
        self.inner_cycles = max(2, inner_cycles)

    def transmit_bit(self, bit: int) -> Tuple[int, bool, float]:
        """Transmits a single bit (0 or 1).
        
        Returns:
            (received_bit, photon_traversed_channel, error_probability)
        """
        M = self.outer_cycles
        N = self.inner_cycles

        # Inner and outer rotation angles
        theta = math.pi / (2.0 * M)
        alpha = math.pi / (2.0 * N)

        # Theoretical probabilities according to Salih et al.
        if bit == 0:
            # Bob blocks: inner Zeno effect locks state in Alice's outer path
            # P(channel transmission) -> 0 as N, M -> infinity
            p_leakage = (math.sin(theta) ** 2) * (math.sin(alpha) ** 2)
            p_error = (1.0 - math.cos(theta) ** (2 * M)) * 0.1
        else:
            # Bob leaves unblocked: outer destructive interference guides photon to detector D1
            p_leakage = (math.sin(theta) ** 2) / (N ** 2)
            p_error = (1.0 - math.cos(alpha) ** (2 * N)) * 0.05

        photon_traversed = random.random() < p_leakage
        has_error = random.random() < p_error

        received = bit if not has_error else (1 - bit)
        return received, photon_traversed, p_leakage

    def transmit_message(self, bitstring: str) -> CounterfactualTransmissionResult:
        """Transmits a binary message over the counterfactual channel."""
        t0 = time.perf_counter()
        received_chars: List[str] = []
        errors = 0
        total_photons = 0
        traversed_count = 0

        for b_char in bitstring:
            bit = int(b_char)
            # Send single photon pulses (with repetition if needed)
            received_bit, traversed, _ = self.transmit_bit(bit)
            total_photons += 1
            if traversed:
                traversed_count += 1
            if received_bit != bit:
                errors += 1
            received_chars.append(str(received_bit))

        duration_ms = (time.perf_counter() - t0) * 1000.0
        ber = errors / len(bitstring) if bitstring else 0.0
        purity = 1.0 - (traversed_count / total_photons) if total_photons > 0 else 1.0

        return CounterfactualTransmissionResult(
            message_bits=bitstring,
            received_bits="".join(received_chars),
            bit_error_rate=ber,
            total_photons_used=total_photons,
            channel_traversed_photons=traversed_count,
            counterfactual_purity=purity,
            outer_cycles=self.outer_cycles,
            inner_cycles=self.inner_cycles,
            duration_ms=duration_ms,
            details={
                "error_count": errors,
                "bit_count": len(bitstring),
            },
        )


@dataclasses.dataclass
class GhostImageReconstruction:
    """Result of quantum ghost imaging reconstruction."""
    resolution: Tuple[int, int]  # (height, width)
    pattern_name: str
    reconstructed_matrix: List[List[float]]
    ground_truth_matrix: List[List[float]]
    visibility: float  # (I_max - I_min) / (I_max + I_min)
    snr_db: float
    correlation_contrast: float
    total_photon_pairs: int
    computation_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolution": list(self.resolution),
            "pattern_name": self.pattern_name,
            "reconstructed_matrix": self.reconstructed_matrix,
            "visibility": round(self.visibility, 6),
            "snr_db": round(self.snr_db, 4),
            "correlation_contrast": round(self.correlation_contrast, 6),
            "total_photon_pairs": self.total_photon_pairs,
            "computation_time_ms": round(self.computation_time_ms, 3),
        }


class QuantumGhostImagingEngine:
    """Quantum Ghost Imaging simulation using spatially correlated entangled photon pairs.
    
    Generates biphotons from Spontaneous Parametric Down-Conversion (SPDC) or classical pseudothermal speckle.
    Signal arm: photon interacts with transmission mask T(x, y) and triggers bucket detector (no spatial resolution).
    Idler arm: photon never touches the mask, measured by spatially resolved array detector I_idler(x, y).
    Image reconstruction: Cross-correlation G^(2)(x, y) = <Bucket * I_idler(x, y)> - <Bucket><I_idler(x, y)>.
    """

    def __init__(self, default_resolution: Tuple[int, int] = (8, 8)):
        self.default_resolution = default_resolution

    def create_synthetic_target(self, name: str, resolution: Tuple[int, int]) -> List[List[float]]:
        """Generates standard binary test patterns: 'slit', 'cross', 'desk_q'."""
        h, w = resolution
        target = [[0.0 for _ in range(w)] for _ in range(h)]

        if name == "slit":
            # Double slit
            mid_w = w // 2
            for r in range(h // 4, 3 * h // 4):
                if 0 <= mid_w - 1 < w:
                    target[r][mid_w - 1] = 1.0
                if 0 <= mid_w + 1 < w:
                    target[r][mid_w + 1] = 1.0
        elif name == "cross":
            mid_h, mid_w = h // 2, w // 2
            for c in range(w):
                target[mid_h][c] = 1.0
            for r in range(h):
                target[r][mid_w] = 1.0
        else:  # 'desk_q' or default
            # Letter 'Q' or box with dot
            for r in range(h):
                for c in range(w):
                    if r == 1 or r == h - 2 or c == 1 or c == w - 2:
                        target[r][c] = 1.0
                    if r == c and r >= h // 2:
                        target[r][c] = 1.0
        return target

    def simulate_ghost_imaging(
        self,
        pattern_name: str = "cross",
        resolution: Optional[Tuple[int, int]] = None,
        photon_pairs: int = 5000,
        noise_level: float = 0.05,
    ) -> GhostImageReconstruction:
        """Simulates quantum ghost imaging with photon pairs and cross-correlation reconstruction."""
        t0 = time.perf_counter()
        res = resolution or self.default_resolution
        h, w = res
        target = self.create_synthetic_target(pattern_name, res)

        # Accumulators for cross-correlation:
        # Cross-term: sum(Bucket * I_idler[r][c])
        # Bucket sum: sum(Bucket)
        # Idler sum: sum(I_idler[r][c])
        cross_term = [[0.0 for _ in range(w)] for _ in range(h)]
        idler_sum = [[0.0 for _ in range(w)] for _ in range(h)]
        bucket_sum = 0.0

        for _ in range(photon_pairs):
            # Generate random correlated spatial spot for entangled pair (SPDC spot)
            spot_r = random.randint(0, h - 1)
            spot_c = random.randint(0, w - 1)

            # Idler arm registers spatial location with quantum shot noise
            idler_frame = [[0.0 for _ in range(w)] for _ in range(h)]
            idler_frame[spot_r][spot_c] = 1.0 + random.gauss(0.0, noise_level)

            # Signal arm hits target mask at (spot_r, spot_c)
            # Bucket detector integrates total transmitted light
            transmission = target[spot_r][spot_c]
            # Bucket detector adds ambient dark counts / noise
            bucket_signal = transmission + max(0.0, random.gauss(0.0, noise_level * 0.5))

            bucket_sum += bucket_signal
            for r in range(h):
                for c in range(w):
                    cross_term[r][c] += bucket_signal * idler_frame[r][c]
                    idler_sum[r][c] += idler_frame[r][c]

        n = float(photon_pairs)
        mean_bucket = bucket_sum / n
        reconstructed = [[0.0 for _ in range(w)] for _ in range(h)]

        min_val = float("inf")
        max_val = float("-inf")

        for r in range(h):
            for c in range(w):
                # Covariance / G^(2) correlation
                cov = (cross_term[r][c] / n) - (mean_bucket * (idler_sum[r][c] / n))
                val = max(0.0, cov)
                reconstructed[r][c] = val
                if val < min_val:
                    min_val = val
                if val > max_val:
                    max_val = val

        # Normalize reconstructed matrix to [0.0, 1.0]
        span = (max_val - min_val) if (max_val - min_val) > 1e-9 else 1.0
        normalized = [[(reconstructed[r][c] - min_val) / span for c in range(w)] for r in range(h)]

        # Calculate visibility and contrast
        visibility = (max_val - min_val) / (max_val + min_val) if (max_val + min_val) > 1e-9 else 0.0

        # Calculate SNR against ground truth
        signal_power = 0.0
        noise_power = 0.0
        for r in range(h):
            for c in range(w):
                gt = target[r][c]
                pred = normalized[r][c]
                signal_power += gt ** 2
                noise_power += (gt - pred) ** 2

        snr_db = 10.0 * math.log10(signal_power / noise_power) if noise_power > 1e-9 else 40.0
        contrast = visibility * 0.95

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return GhostImageReconstruction(
            resolution=res,
            pattern_name=pattern_name,
            reconstructed_matrix=normalized,
            ground_truth_matrix=target,
            visibility=visibility,
            snr_db=snr_db,
            correlation_contrast=contrast,
            total_photon_pairs=photon_pairs,
            computation_time_ms=duration_ms,
        )


class QuantumCounterfactualMesh:
    """High-level coordinator managing counterfactual interrogation, transmission, and ghost imaging."""

    def __init__(self):
        self.ifm_engine = InteractionFreeMeasurement(default_zeno_cycles=40)
        self.comm_engine = CounterfactualDirectCommunication(outer_cycles=20, inner_cycles=20)
        self.ghost_engine = QuantumGhostImagingEngine(default_resolution=(8, 8))

    def run_interaction_free_test(
        self,
        object_present: bool = True,
        cycles: int = 50,
    ) -> InteractionFreeMeasurementResult:
        """Runs chained Zeno interaction-free interrogation."""
        return self.ifm_engine.chained_zeno_interrogation(object_present=object_present, cycles=cycles)

    def run_counterfactual_communication(self, message_bits: str) -> CounterfactualTransmissionResult:
        """Executes counterfactual direct communication."""
        return self.comm_engine.transmit_message(message_bits)

    def run_ghost_imaging(
        self,
        pattern_name: str = "cross",
        photon_pairs: int = 4000,
        resolution: Tuple[int, int] = (8, 8),
    ) -> GhostImageReconstruction:
        """Executes quantum ghost imaging reconstruction."""
        return self.ghost_engine.simulate_ghost_imaging(
            pattern_name=pattern_name,
            resolution=resolution,
            photon_pairs=photon_pairs,
        )
