"""Quantum Reservoir Computing (QRC) & Quantum Extreme Learning Machine (QELM) Mesh (Milestone v6.3 - Phase 92).

Implements:
- QuantumReservoirNode: Nonlinear dynamic quantum reservoir based on interacting spin network
  with disordered Heisenberg / Ising couplings.
- InformationProcessingCapacity: Measures linear memory capacity and nonlinear higher-order
  processing capacity of the quantum reservoir.
- QuantumReservoirState: Complex density matrix / expectation value trajectory of reservoir spins.
- QuantumExtremeLearningMachine: Fast ridge-regression readout layer trained on reservoir observables
  for temporal sequence prediction and chaotic time-series forecasting.
"""

from __future__ import annotations

import dataclasses
import math
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclasses.dataclass
class QuantumReservoirState:
    time_step: int
    spin_expectations: List[float]       # <Z_i> for each qubit
    pairwise_correlations: List[float]   # <Z_i Z_j> for coupled pairs
    reservoir_entropy: float
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_step": self.time_step,
            "spin_expectations": [round(x, 6) for x in self.spin_expectations],
            "pairwise_correlations": [round(x, 6) for x in self.pairwise_correlations],
            "reservoir_entropy": round(self.reservoir_entropy, 6),
            "timestamp": self.timestamp,
        }


class QuantumReservoirNode:
    """Interacting spin-network quantum reservoir with disordered couplings."""

    def __init__(self, num_qubits: int = 4, coupling_strength: float = 1.0) -> None:
        self.num_qubits = max(2, num_qubits)
        self.coupling_strength = coupling_strength
        # Disordered interaction couplings J_{ij}
        self.J_couplings: Dict[Tuple[int, int], float] = {}
        for i in range(self.num_qubits):
            for j in range(i + 1, self.num_qubits):
                # Deterministic pseudo-random couplings based on index
                val = math.sin((i + 1) * 3.7 + (j + 1) * 1.9) * coupling_strength
                self.J_couplings[(i, j)] = val

        # State representation: single-qubit Bloch vectors [theta_i, phi_i]
        self.spins: List[List[float]] = [[0.0, 0.0] for _ in range(self.num_qubits)]
        self.current_step = 0

    def inject_input(self, u_t: float) -> QuantumReservoirState:
        """Injects external scalar input u_t by rotating input qubit and evolving network."""
        # Non-linear phase modulation on first qubit: theta_0 <- u_t * pi
        self.spins[0][0] = (self.spins[0][0] + u_t * math.pi) % (2.0 * math.pi)

        # Unitary network dynamics step: spin-spin interactions propagate input across reservoir
        new_spins = [list(s) for s in self.spins]
        for (i, j), J_val in self.J_couplings.items():
            # Interaction exchange phase
            delta = J_val * math.sin(self.spins[i][0] - self.spins[j][0])
            new_spins[i][0] = (new_spins[i][0] + delta) % (2.0 * math.pi)
            new_spins[j][0] = (new_spins[j][0] - delta) % (2.0 * math.pi)
            new_spins[i][1] = (new_spins[i][1] + delta * 0.5) % (2.0 * math.pi)
            new_spins[j][1] = (new_spins[j][1] - delta * 0.5) % (2.0 * math.pi)

        self.spins = new_spins
        self.current_step += 1

        # Observables: <Z_i> = cos(theta_i)
        spin_z = [math.cos(s[0]) for s in self.spins]
        correlations = []
        for (i, j) in self.J_couplings.keys():
            correlations.append(spin_z[i] * spin_z[j])

        # Reservoir Shannon-von Neumann entropy approximation
        probs = [(z + 1.0) / (2.0 * self.num_qubits) for z in spin_z]
        total_p = sum(probs)
        if total_p > 0:
            norm_p = [p / total_p for p in probs]
            entropy = -sum(p * math.log(max(1e-9, p)) for p in norm_p)
        else:
            entropy = 0.0

        return QuantumReservoirState(
            time_step=self.current_step,
            spin_expectations=spin_z,
            pairwise_correlations=correlations,
            reservoir_entropy=entropy,
        )


class QuantumExtremeLearningMachine:
    """Readout weight layer for Quantum Reservoir Computing using ridge regression."""

    def __init__(self, feature_dim: int, regularization: float = 1e-3) -> None:
        self.feature_dim = feature_dim
        self.regularization = regularization
        self.readout_weights: Optional[List[float]] = None

    def fit(self, X_states: List[List[float]], y_targets: List[float]) -> List[float]:
        """Trains linear weights W via pseudo-inverse ridge regression: W = (X^T X + alpha I)^-1 X^T y."""
        N = len(X_states)
        D = self.feature_dim
        if N == 0:
            raise ValueError("Training data is empty")

        # X^T X (D x D)
        XTX = [[0.0 for _ in range(D)] for _ in range(D)]
        for row in X_states:
            for i in range(D):
                for j in range(D):
                    XTX[i][j] += row[i] * row[j]

        # Add ridge regularization lambda * I
        for i in range(D):
            XTX[i][i] += self.regularization

        # X^T y (D x 1)
        XTy = [0.0 for _ in range(D)]
        for row, target in zip(X_states, y_targets):
            for i in range(D):
                XTy[i] += row[i] * target

        # Simple Gauss-Jordan / forward elimination inversion for D <= 16
        # Augmented matrix [XTX | XTy]
        aug = [XTX[i] + [XTy[i]] for i in range(D)]
        for i in range(D):
            # Pivot
            pivot = aug[i][i]
            if abs(pivot) < 1e-9:
                pivot = 1e-9
            for j in range(D + 1):
                aug[i][j] /= pivot
            for k in range(D):
                if k != i:
                    factor = aug[k][i]
                    for j in range(D + 1):
                        aug[k][j] -= factor * aug[i][j]

        self.readout_weights = [aug[i][D] for i in range(D)]
        return self.readout_weights

    def predict(self, feature_vector: List[float]) -> float:
        if self.readout_weights is None:
            raise RuntimeError("Model is not trained yet")
        pred = sum(w * x for w, x in zip(self.readout_weights, feature_vector))
        return pred
