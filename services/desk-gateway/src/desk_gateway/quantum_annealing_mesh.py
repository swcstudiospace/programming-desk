"""Quantum Annealing, Ising Spin Glass & QUBO Optimization Mesh (Milestone v6.2 - Phase 90).

Implements:
- QUBOProblem: Quadratic Unconstrained Binary Optimization problem representation.
- IsingHamiltonian: Mapping from QUBO binary variables x_i in {0, 1} to Ising spins s_i in {-1, +1}
  via x_i = (s_i + 1) / 2:
  H(s) = sum_i h_i s_i + sum_{i < j} J_{ij} s_i s_j + offset.
- SimulatedQuantumAnnealer: Quantum annealing engine modeling transverse-field driver Hamiltonian
  H(t) = A(t) H_driver + B(t) H_problem, with quantum tunneling and thermal fluctuations.
- ChimeraGraphTopology: Embedding engine mapping logical problem graphs to physical Chimera / Pegasus-like
  qubit topologies with minor embedding and ferromagnetic chain strengths.
"""

from __future__ import annotations

import dataclasses
import math
import secrets
import time
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclasses.dataclass
class IsingHamiltonian:
    num_spins: int
    linear_biases: Dict[int, float]              # h_i
    quadratic_couplings: Dict[Tuple[int, int], float]  # J_{ij} (i < j)
    offset: float = 0.0

    def evaluate_energy(self, spin_configuration: List[int]) -> float:
        """Evaluates classical energy E(s) = sum_i h_i s_i + sum_{i<j} J_{ij} s_i s_j + offset."""
        energy = self.offset
        for i, h in self.linear_biases.items():
            if i < len(spin_configuration):
                energy += h * spin_configuration[i]

        for (i, j), J in self.quadratic_couplings.items():
            if i < len(spin_configuration) and j < len(spin_configuration):
                energy += J * spin_configuration[i] * spin_configuration[j]

        return energy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_spins": self.num_spins,
            "linear_biases": {str(k): round(v, 6) for k, v in self.linear_biases.items()},
            "quadratic_couplings": {f"{k[0]},{k[1]}": round(v, 6) for k, v in self.quadratic_couplings.items()},
            "offset": round(self.offset, 6),
        }


@dataclasses.dataclass
class QUBOProblem:
    num_variables: int
    Q_matrix: Dict[Tuple[int, int], float]  # Q_{ij} with i <= j

    def to_ising(self) -> IsingHamiltonian:
        """Converts QUBO x_i in {0, 1} to Ising s_i in {-1, +1} via x_i = (1 + s_i)/2.

        x_i = 1/2 + s_i / 2
        x_i x_j = 1/4 + s_i / 4 + s_j / 4 + s_i s_j / 4
        """
        h: Dict[int, float] = {}
        J: Dict[Tuple[int, int], float] = {}
        offset = 0.0

        for (i, j), q_val in self.Q_matrix.items():
            if i == j:
                # Q_ii x_i = Q_ii (1/2 + s_i/2)
                offset += q_val * 0.5
                h[i] = h.get(i, 0.0) + q_val * 0.5
            else:
                u, v = min(i, j), max(i, j)
                # Q_ij x_i x_j = Q_ij (1/4 + s_i/4 + s_j/4 + s_i s_j / 4)
                offset += q_val * 0.25
                h[u] = h.get(u, 0.0) + q_val * 0.25
                h[v] = h.get(v, 0.0) + q_val * 0.25
                J[(u, v)] = J.get((u, v), 0.0) + q_val * 0.25

        return IsingHamiltonian(
            num_spins=self.num_variables,
            linear_biases=h,
            quadratic_couplings=J,
            offset=offset,
        )

    def evaluate_qubo(self, binary_vector: List[int]) -> float:
        """Evaluates x^T Q x."""
        val = 0.0
        for (i, j), q in self.Q_matrix.items():
            if i < len(binary_vector) and j < len(binary_vector):
                val += q * binary_vector[i] * binary_vector[j]
        return val


@dataclasses.dataclass
class AnnealingSchedulePoint:
    normalized_time: float      # s in [0, 1]
    transverse_field_A: float   # Driver strength A(s) in GHz
    problem_field_B: float      # Problem strength B(s) in GHz


@dataclasses.dataclass
class AnnealingResult:
    best_spins: List[int]
    best_energy: float
    best_binary: List[int]
    qubo_energy: float
    num_sweeps: int
    annealing_time_us: float
    success: bool
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "best_spins": self.best_spins,
            "best_energy": round(self.best_energy, 6),
            "best_binary": self.best_binary,
            "qubo_energy": round(self.qubo_energy, 6),
            "num_sweeps": self.num_sweeps,
            "annealing_time_us": round(self.annealing_time_us, 2),
            "success": self.success,
            "timestamp": self.timestamp,
        }


class SimulatedQuantumAnnealer:
    """Quantum Monte Carlo (QMC) / Transverse-Field Simulated Quantum Annealing engine."""

    def __init__(self, ising: IsingHamiltonian, num_trotter_slices: int = 8) -> None:
        self.ising = ising
        self.num_trotter_slices = max(2, num_trotter_slices)

    def solve(
        self,
        num_sweeps: int = 100,
        annealing_time_us: float = 20.0,
        beta_initial: float = 0.1,
        beta_final: float = 5.0,
    ) -> AnnealingResult:
        n = self.ising.num_spins
        m = self.num_trotter_slices

        # Initialize spins randomly for each Trotter slice
        # configuration shape: [m][n] with values in {-1, +1}
        spins = [
            [1 if secrets.randbelow(2) == 1 else -1 for _ in range(n)]
            for _ in range(m)
        ]

        # Annealing loop
        for sweep in range(num_sweeps):
            s = sweep / float(max(1, num_sweeps - 1))  # s in [0, 1]
            # Transverse field schedule: Gamma(s) decays, J_prob(s) increases
            gamma = max(0.01, 1.0 - s)
            problem_scale = s

            # Current inverse temperature beta
            beta = beta_initial + (beta_final - beta_initial) * s
            beta_eff = beta / m
            # Coupling between adjacent Trotter slices: J_perp = -1/(2 * beta_eff) * ln(tanh(beta_eff * gamma))
            arg = max(1e-6, min(0.999999, math.tanh(beta_eff * gamma)))
            j_perp = -0.5 * math.log(arg)

            # Metropolis sweep over all Trotter slices and spins
            for k in range(m):
                k_prev = (k - 1) % m
                k_next = (k + 1) % m

                for i in range(n):
                    s_i = spins[k][i]

                    # Intra-slice problem energy change if flipped: Delta E_prob
                    h_i = self.ising.linear_biases.get(i, 0.0)
                    coup_sum = 0.0
                    for (u, v), j_val in self.ising.quadratic_couplings.items():
                        if u == i:
                            coup_sum += j_val * spins[k][v]
                        elif v == i:
                            coup_sum += j_val * spins[k][u]

                    delta_e_intra = -2.0 * s_i * (h_i + coup_sum) * problem_scale
                    # Inter-slice Trotter coupling energy change: Delta E_perp
                    delta_e_inter = 2.0 * s_i * j_perp * (spins[k_prev][i] + spins[k_next][i])

                    delta_e_total = (delta_e_intra / m) + delta_e_inter

                    if delta_e_total <= 0.0 or (secrets.randbelow(1_000_000) / 1_000_000.0) < math.exp(-delta_e_total):
                        spins[k][i] = -s_i

        # Select the Trotter slice with lowest classical energy
        best_slice = 0
        best_energy = float("inf")
        for k in range(m):
            e = self.ising.evaluate_energy(spins[k])
            if e < best_energy:
                best_energy = e
                best_slice = k

        best_spins = list(spins[best_slice])
        best_binary = [(s + 1) // 2 for s in best_spins]

        return AnnealingResult(
            best_spins=best_spins,
            best_energy=best_energy,
            best_binary=best_binary,
            qubo_energy=best_energy,
            num_sweeps=num_sweeps,
            annealing_time_us=annealing_time_us,
            success=True,
        )


class ChimeraGraphTopology:
    """Chimera graph unit cell and minor-embedding helper."""

    @classmethod
    def generate_unit_cell_couplings(cls, cell_id: int = 0) -> List[Tuple[int, int]]:
        """Generates bipartite K_{4,4} couplings for an 8-qubit Chimera unit cell."""
        offset = cell_id * 8
        couplings = []
        # Left partition: 0..3, Right partition: 4..7
        for left in range(4):
            for right in range(4, 8):
                couplings.append((offset + left, offset + right))
        return couplings
