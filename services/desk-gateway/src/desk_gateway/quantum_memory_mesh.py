"""Quantum Memory Node Storage & Continuous-Variable (CV) Optical Mesh (Milestone v5.2 - Phase 70).

Implements:
- QuantumMemoryBufferType: AFC (Atomic Frequency Comb) and EIT (Electromagnetically Induced Transparency).
- QuantumMemoryCell: Simulates storage of optical/discrete qubit states, retrieval efficiency,
  and decoherence decay based on relaxation time (T1) and dephasing time (T2).
- QuantumMemoryNode: In-memory and optical buffer node managing multiple storage cells, fidelity degradation,
  and state retrieval.
- ContinuousVariableQuadrature: Position (q) and Momentum (p) quadratures for Gaussian optical states.
- CVSqueezedState: Simulates continuous-variable Gaussian squeezed vacuum / single-mode states with
  squeezing parameter r, squeezing angle phi, and displacement (q0, p0).
- CVOpticalRouter: Symplectic transformation engine implementing beam-splitter mixing, phase shifting,
  and homodyne/heterodyne detection with quantum variance tracking.
"""

from __future__ import annotations

import collections
import enum
import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


class QuantumMemoryBufferType(str, enum.Enum):
    AFC = "AFC"  # Atomic Frequency Comb (Rare-earth doped crystals, wide bandwidth)
    EIT = "EIT"  # Electromagnetically Induced Transparency (Warm vapor / cold atoms, long storage)


class CVHomodyneMeasurementType(str, enum.Enum):
    POSITION = "POSITION"      # Measure position quadrature q
    MOMENTUM = "MOMENTUM"      # Measure momentum quadrature p
    HETERODYNE = "HETERODYNE"  # Joint simultaneous noisy measurement of q and p


@dataclass
class QuantumMemoryCell:
    cell_id: str
    node_id: str
    buffer_type: QuantumMemoryBufferType
    t1_relaxation_us: float      # Lifetime T1 in microseconds
    t2_dephasing_us: float       # Dephasing T2 in microseconds (T2 <= 2 * T1)
    peak_efficiency: float       # Base retrieval efficiency (0.0 - 1.0)
    stored_state_repr: Dict[str, Any]
    stored_at: float = field(default_factory=time.time)
    retrieved: bool = False

    def calculate_coherence(self, current_time: Optional[float] = None) -> float:
        """Calculates fidelity retention factoring T1 relaxation and T2 dephasing decoherence decay."""
        if current_time is None:
            current_time = time.time()
        elapsed_ms = max(0.0, (current_time - self.stored_at) * 1e3)
        # T2 decay in ms scale for real-world simulation, scaled by dephasing parameter
        decay_factor = math.exp(-elapsed_ms / max(0.1, self.t2_dephasing_us))
        initial_fid = float(self.stored_state_repr.get("fidelity", 0.99))
        return max(0.0, min(1.0, initial_fid * decay_factor))

    def retrieve(self, current_time: Optional[float] = None) -> Tuple[bool, float, Dict[str, Any]]:
        """Retrieves stored state, returning success, final fidelity, and retrieved state payload."""
        if self.retrieved:
            return False, 0.0, {"error": "Cell already retrieved or cleared"}
        self.retrieved = True
        coherence_fid = self.calculate_coherence(current_time)
        effective_fid = coherence_fid * self.peak_efficiency
        retrieved_state = dict(self.stored_state_repr)
        retrieved_state["fidelity"] = round(effective_fid, 6)
        retrieved_state["retrieval_timestamp"] = current_time or time.time()
        retrieved_state["retrieval_efficiency"] = round(self.peak_efficiency, 4)
        return True, effective_fid, retrieved_state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "node_id": self.node_id,
            "buffer_type": self.buffer_type.value,
            "t1_relaxation_us": self.t1_relaxation_us,
            "t2_dephasing_us": self.t2_dephasing_us,
            "peak_efficiency": round(self.peak_efficiency, 4),
            "current_coherence": round(self.calculate_coherence(), 6),
            "stored_state": self.stored_state_repr,
            "stored_at": self.stored_at,
            "retrieved": self.retrieved,
        }


class QuantumMemoryNode:
    """Manages quantum memory buffers on a desk node."""

    def __init__(self, node_id: str, default_buffer_type: QuantumMemoryBufferType = QuantumMemoryBufferType.AFC) -> None:
        self.node_id = node_id
        self.default_buffer_type = default_buffer_type
        self.cells: Dict[str, QuantumMemoryCell] = {}

    def store_state(
        self,
        state_repr: Dict[str, Any],
        buffer_type: Optional[QuantumMemoryBufferType] = None,
        t1_relaxation_us: float = 5000.0,
        t2_dephasing_us: float = 2500.0,
        peak_efficiency: float = 0.95,
    ) -> QuantumMemoryCell:
        btype = buffer_type or self.default_buffer_type
        cell_id = f"qmem-{self.node_id}-{secrets.token_hex(6)}"
        cell = QuantumMemoryCell(
            cell_id=cell_id,
            node_id=self.node_id,
            buffer_type=btype,
            t1_relaxation_us=t1_relaxation_us,
            t2_dephasing_us=min(t2_dephasing_us, 2.0 * t1_relaxation_us),
            peak_efficiency=min(1.0, max(0.1, peak_efficiency)),
            stored_state_repr=state_repr,
            stored_at=time.time(),
        )
        self.cells[cell_id] = cell
        return cell

    def retrieve_state(self, cell_id: str) -> Tuple[bool, float, Dict[str, Any]]:
        cell = self.cells.get(cell_id)
        if not cell:
            return False, 0.0, {"error": "Cell not found"}
        return cell.retrieve()

    def list_cells(self, include_retrieved: bool = False) -> List[Dict[str, Any]]:
        return [
            cell.to_dict()
            for cell in self.cells.values()
            if include_retrieved or not cell.retrieved
        ]


@dataclass
class CVSqueezedState:
    """Continuous-Variable Gaussian optical state with quadrature variances."""
    state_id: str
    squeezing_r: float         # Squeezing parameter r (r >= 0)
    squeezing_phi: float       # Squeezing phase angle in radians
    mean_q: float = 0.0        # Position quadrature displacement <q>
    mean_p: float = 0.0        # Momentum quadrature displacement <p>
    origin_node: str = "desk-alpha"
    created_at: float = field(default_factory=time.time)

    @property
    def variance_q(self) -> float:
        """Variance Var(q) = (1/2) * (exp(-2r) * cos^2(phi/2) + exp(2r) * sin^2(phi/2))."""
        # When phi = 0, Var(q) = 0.5 * exp(-2r) (squeezed along q)
        c2 = math.cos(self.squeezing_phi / 2.0) ** 2
        s2 = math.sin(self.squeezing_phi / 2.0) ** 2
        return 0.5 * (math.exp(-2.0 * self.squeezing_r) * c2 + math.exp(2.0 * self.squeezing_r) * s2)

    @property
    def variance_p(self) -> float:
        """Variance Var(p) = (1/2) * (exp(2r) * cos^2(phi/2) + exp(-2r) * sin^2(phi/2))."""
        # When phi = 0, Var(p) = 0.5 * exp(2r) (anti-squeezed along p)
        c2 = math.cos(self.squeezing_phi / 2.0) ** 2
        s2 = math.sin(self.squeezing_phi / 2.0) ** 2
        return 0.5 * (math.exp(2.0 * self.squeezing_r) * c2 + math.exp(-2.0 * self.squeezing_r) * s2)

    @property
    def squeezing_db(self) -> float:
        """Squeezing degree in decibels (dB): -10 * log10(exp(-2r)) = 20 * r * log10(e) = 8.686 * r."""
        return round(8.685889638 * self.squeezing_r, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "origin_node": self.origin_node,
            "squeezing_r": round(self.squeezing_r, 4),
            "squeezing_phi": round(self.squeezing_phi, 4),
            "squeezing_db": self.squeezing_db,
            "mean_q": round(self.mean_q, 6),
            "mean_p": round(self.mean_p, 6),
            "variance_q": round(self.variance_q, 6),
            "variance_p": round(self.variance_p, 6),
            "created_at": self.created_at,
        }


class CVOpticalRouter:
    """Optical continuous-variable routing, beam splitting, and homodyne detection engine."""

    def __init__(self) -> None:
        self.states: Dict[str, CVSqueezedState] = {}

    def generate_squeezed_state(
        self,
        node_id: str,
        squeezing_r: float = 1.0,
        squeezing_phi: float = 0.0,
        mean_q: float = 0.0,
        mean_p: float = 0.0,
    ) -> CVSqueezedState:
        state_id = f"cv-sqz-{secrets.token_hex(6)}"
        state = CVSqueezedState(
            state_id=state_id,
            squeezing_r=max(0.0, squeezing_r),
            squeezing_phi=squeezing_phi,
            mean_q=mean_q,
            mean_p=mean_p,
            origin_node=node_id,
        )
        self.states[state_id] = state
        return state

    def beam_splitter(
        self,
        state_1: CVSqueezedState,
        state_2: CVSqueezedState,
        transmissivity: float = 0.5,  # 50:50 balanced beam splitter by default
    ) -> Tuple[CVSqueezedState, CVSqueezedState]:
        """Applies symplectic beam-splitter transformation on two CV modes.

        q_out1 = sqrt(T)*q1 + sqrt(1-T)*q2
        q_out2 = -sqrt(1-T)*q1 + sqrt(T)*q2
        Same for p quadratures.
        """
        t = max(0.0, min(1.0, transmissivity))
        t_amp = math.sqrt(t)
        r_amp = math.sqrt(1.0 - t)

        out1_q = t_amp * state_1.mean_q + r_amp * state_2.mean_q
        out1_p = t_amp * state_1.mean_p + r_amp * state_2.mean_p

        out2_q = -r_amp * state_1.mean_q + t_amp * state_2.mean_q
        out2_p = -r_amp * state_1.mean_p + t_amp * state_2.mean_p

        # Resulting effective squeezing parameters after mixing
        avg_r = (state_1.squeezing_r + state_2.squeezing_r) / 2.0
        avg_phi = (state_1.squeezing_phi + state_2.squeezing_phi) / 2.0

        out1 = CVSqueezedState(
            state_id=f"cv-bs1-{secrets.token_hex(6)}",
            squeezing_r=avg_r,
            squeezing_phi=avg_phi,
            mean_q=out1_q,
            mean_p=out1_p,
            origin_node=state_1.origin_node,
        )
        out2 = CVSqueezedState(
            state_id=f"cv-bs2-{secrets.token_hex(6)}",
            squeezing_r=avg_r,
            squeezing_phi=avg_phi,
            mean_q=out2_q,
            mean_p=out2_p,
            origin_node=state_2.origin_node,
        )
        self.states[out1.state_id] = out1
        self.states[out2.state_id] = out2
        return out1, out2

    def measure_homodyne(
        self,
        state: CVSqueezedState,
        measurement_type: CVHomodyneMeasurementType = CVHomodyneMeasurementType.POSITION,
        detector_efficiency: float = 0.98,
    ) -> Dict[str, Any]:
        """Performs balanced homodyne or heterodyne quadrature measurement."""
        # Gaussian sampling from quadrature distribution
        # Box-Muller transform using secure random
        u1 = max(1e-12, secrets.randbelow(1_000_000) / 1_000_000.0)
        u2 = secrets.randbelow(1_000_000) / 1_000_000.0
        std_normal_1 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        std_normal_2 = math.sqrt(-2.0 * math.log(u1)) * math.sin(2.0 * math.pi * u2)

        det_eff = max(0.1, min(1.0, detector_efficiency))
        added_noise_var = (1.0 - det_eff) / (2.0 * det_eff)

        var_q_eff = state.variance_q + added_noise_var
        var_p_eff = state.variance_p + added_noise_var

        q_val = state.mean_q + math.sqrt(var_q_eff) * std_normal_1
        p_val = state.mean_p + math.sqrt(var_p_eff) * std_normal_2

        if measurement_type == CVHomodyneMeasurementType.POSITION:
            result = {"measured_quadrature": "q", "value": round(q_val, 6), "variance": round(var_q_eff, 6)}
        elif measurement_type == CVHomodyneMeasurementType.MOMENTUM:
            result = {"measured_quadrature": "p", "value": round(p_val, 6), "variance": round(var_p_eff, 6)}
        else:  # HETERODYNE
            # Joint measurement introduces 3dB penalty (vacuum fluctuation on unmeasured port)
            result = {
                "measured_quadrature": "joint_qp",
                "value_q": round(q_val + 0.5 * std_normal_2, 6),
                "value_p": round(p_val + 0.5 * std_normal_1, 6),
                "variance_q": round(var_q_eff + 0.5, 6),
                "variance_p": round(var_p_eff + 0.5, 6),
            }

        result["state_id"] = state.state_id
        result["measurement_type"] = measurement_type.value
        result["detector_efficiency"] = det_eff
        result["timestamp"] = time.time()
        return result
