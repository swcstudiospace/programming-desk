"""Quantum Thermodynamic Resource Theories, Maxwell's Demon & Landauer Erasure Ledger (Milestone v6.6 - Phase 98).

Implements:
- QuantumThermalReservoir: Models macroscopic thermal bath at inverse temperature beta = 1/(k_B * T)
  with canonical Gibbs thermal state rho_th = exp(-beta * H) / Z.
- QuantumWorkExtractionEngine: Evaluates passivity, extractable ergotropy W_erg = Tr(rho * H) - Tr(rho_passive * H),
  and non-equilibrium free energy F(rho) = <H> - T * S(rho).
- MaxwellQuantumDemon: Measures quantum system (qubit/multilevel) acquiring mutual information I(S : D),
  converting information into extractable mechanical/thermodynamic work (Szilard engine model).
- LandauerErasureEngine: Enforces fundamental thermodynamic cost of information erasure
  Q_dissipated >= k_B * T * ln(2) * Delta S, tracking heat dissipation into the reservoir.
- QuantumHeatEngineCycle: Otto cycle (Isentropic compression -> Isochoric heating -> Isentropic expansion ->
  Isochoric cooling) operating with Carnot efficiency bounds eta_Otto = 1 - omega_cold / omega_hot <= eta_Carnot.
- QuantumThermodynamicMesh: High-level mesh coordinating thermodynamic state transformations,
  heat-to-work conversions, Landauer bounds, and demon measurement fidelity.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple


# Boltzmann constant in normalized energy units (set to 1.0 for dimensionless quantum thermodynamics)
K_B: float = 1.0


class ThermodynamicCycleState(str, enum.Enum):
    COMPRESSION = "isentropic_compression"
    HEATING = "isochoric_heating"
    EXPANSION = "isentropic_expansion"
    COOLING = "isochoric_cooling"


@dataclasses.dataclass
class ThermalState:
    temperature: float
    beta: float  # 1 / (k_B * T)
    energy_levels: List[float]
    probabilities: List[float]
    partition_function: float
    mean_energy: float
    von_neumann_entropy: float
    free_energy: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": round(self.temperature, 4),
            "beta": round(self.beta, 4),
            "energy_levels": [round(e, 4) for e in self.energy_levels],
            "probabilities": [round(p, 6) for p in self.probabilities],
            "partition_function": round(self.partition_function, 6),
            "mean_energy": round(self.mean_energy, 6),
            "von_neumann_entropy": round(self.von_neumann_entropy, 6),
            "free_energy": round(self.free_energy, 6),
        }


@dataclasses.dataclass
class WorkExtractionResult:
    initial_energy: float
    passive_energy: float
    extractable_ergotropy: float
    is_passive: bool
    entropy: float
    bound_free_energy_work: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "initial_energy": round(self.initial_energy, 6),
            "passive_energy": round(self.passive_energy, 6),
            "extractable_ergotropy": round(self.extractable_ergotropy, 6),
            "is_passive": self.is_passive,
            "entropy": round(self.entropy, 6),
            "bound_free_energy_work": round(self.bound_free_energy_work, 6),
        }


@dataclasses.dataclass
class DemonFeedbackResult:
    measurement_outcome: int
    system_initial_state: List[float]
    mutual_information_bits: float
    work_extracted: float
    entropy_reduction: float
    demon_memory_bits: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measurement_outcome": self.measurement_outcome,
            "system_initial_state": [round(p, 6) for p in self.system_initial_state],
            "mutual_information_bits": round(self.mutual_information_bits, 6),
            "work_extracted": round(self.work_extracted, 6),
            "entropy_reduction": round(self.entropy_reduction, 6),
            "demon_memory_bits": round(self.demon_memory_bits, 4),
        }


@dataclasses.dataclass
class LandauerErasureResult:
    bits_erased: float
    reservoir_temperature: float
    theoretical_minimum_heat: float  # k_B * T * ln(2) * bits
    actual_heat_dissipated: float
    entropy_increase_reservoir: float
    landauer_bound_satisfied: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bits_erased": round(self.bits_erased, 4),
            "reservoir_temperature": round(self.reservoir_temperature, 4),
            "theoretical_minimum_heat": round(self.theoretical_minimum_heat, 6),
            "actual_heat_dissipated": round(self.actual_heat_dissipated, 6),
            "entropy_increase_reservoir": round(self.entropy_increase_reservoir, 6),
            "landauer_bound_satisfied": self.landauer_bound_satisfied,
        }


@dataclasses.dataclass
class HeatEngineCycleResult:
    stage: ThermodynamicCycleState
    th_cold: float
    th_hot: float
    omega_cold: float
    omega_hot: float
    heat_absorbed_qh: float
    heat_rejected_qc: float
    net_work_extracted: float
    otto_efficiency: float
    carnot_limit: float
    second_law_satisfied: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage.value,
            "th_cold": round(self.th_cold, 4),
            "th_hot": round(self.th_hot, 4),
            "omega_cold": round(self.omega_cold, 4),
            "omega_hot": round(self.omega_hot, 4),
            "heat_absorbed_qh": round(self.heat_absorbed_qh, 6),
            "heat_rejected_qc": round(self.heat_rejected_qc, 6),
            "net_work_extracted": round(self.net_work_extracted, 6),
            "otto_efficiency": round(self.otto_efficiency, 6),
            "carnot_limit": round(self.carnot_limit, 6),
            "second_law_satisfied": self.second_law_satisfied,
        }


class QuantumThermalReservoir:
    """Simulates a canonical thermal reservoir at temperature T."""

    def __init__(self, temperature: float = 1.0) -> None:
        if temperature <= 0:
            raise ValueError("Temperature must be strictly positive.")
        self.temperature = float(temperature)
        self.beta = 1.0 / (K_B * self.temperature)

    def compute_thermal_state(self, energy_levels: List[float]) -> ThermalState:
        """Computes the Gibbs canonical density matrix diagonal for given Hamiltonian eigenvalues."""
        e_min = min(energy_levels)
        # Shift energies by e_min to avoid numerical underflow/overflow
        unnormalized_weights = [math.exp(-self.beta * (e - e_min)) for e in energy_levels]
        z_shifted = sum(unnormalized_weights)
        probs = [w / z_shifted for w in unnormalized_weights]

        mean_e = sum(p * e for p, e in zip(probs, energy_levels))

        # Von Neumann / Shannon entropy S = -sum(p * ln(p))
        entropy = 0.0
        for p in probs:
            if p > 1e-15:
                entropy -= p * math.log(p)

        # Free energy F = <H> - T * S
        f_energy = mean_e - self.temperature * entropy
        # Exact partition function
        partition_func = sum(math.exp(-self.beta * e) for e in energy_levels)

        return ThermalState(
            temperature=self.temperature,
            beta=self.beta,
            energy_levels=energy_levels,
            probabilities=probs,
            partition_function=partition_func,
            mean_energy=mean_e,
            von_neumann_entropy=entropy,
            free_energy=f_energy,
        )


class QuantumWorkExtractionEngine:
    """Analyzes passivity and extractable ergotropy under unitary operations."""

    @staticmethod
    def calculate_ergotropy(
        energy_levels: List[float],
        state_probabilities: List[float],
        reservoir_temperature: Optional[float] = None,
    ) -> WorkExtractionResult:
        """Calculates ergotropy W_erg = Tr(rho * H) - Tr(rho_sigma * H).

        A state is passive iff its eigenvectors commute with H and populations are sorted in
        non-increasing order with increasing energy.
        """
        if len(energy_levels) != len(state_probabilities):
            raise ValueError("Energy levels and state probabilities must have identical dimensions.")

        total_p = sum(state_probabilities)
        if abs(total_p - 1.0) > 1e-5:
            state_probabilities = [p / total_p for p in state_probabilities]

        initial_energy = sum(p * e for p, e in zip(state_probabilities, energy_levels))

        # Sort energy levels in ascending order
        sorted_energies = sorted(energy_levels)
        # Passive state sorts probabilities in strictly descending order paired with ascending energies
        sorted_probs = sorted(state_probabilities, reverse=True)

        passive_energy = sum(p * e for p, e in zip(sorted_probs, sorted_energies))
        ergotropy = max(0.0, initial_energy - passive_energy)
        is_passive = ergotropy < 1e-8

        # Calculate entropy
        entropy = -sum(p * math.log(p) for p in state_probabilities if p > 1e-15)

        # Non-equilibrium free energy bound on work: W_max = F(rho) - F(rho_th) = Delta F
        bound_free_energy = ergotropy
        if reservoir_temperature and reservoir_temperature > 0:
            res = QuantumThermalReservoir(reservoir_temperature)
            th = res.compute_thermal_state(energy_levels)
            free_energy_current = initial_energy - reservoir_temperature * entropy
            bound_free_energy = max(0.0, free_energy_current - th.free_energy)

        return WorkExtractionResult(
            initial_energy=initial_energy,
            passive_energy=passive_energy,
            extractable_ergotropy=ergotropy,
            is_passive=is_passive,
            entropy=entropy,
            bound_free_energy_work=bound_free_energy,
        )


class MaxwellQuantumDemon:
    """Simulates quantum Maxwell's demon converting measurement information into work."""

    def __init__(self, measurement_fidelity: float = 1.0) -> None:
        self.measurement_fidelity = max(0.5, min(1.0, float(measurement_fidelity)))

    def measure_and_extract_work(
        self,
        qubit_state: Tuple[float, float],
        energy_gap: float = 1.0,
        temperature: float = 1.0,
    ) -> DemonFeedbackResult:
        """Measures a two-level system and applies conditional feedback to extract work.

        For a qubit in state (p0, p1) with H = diag(0, Delta),
        demon measures state. Work extracted via Szilard protocol is:
        W = k_B * T * ln(2) * [1 - H(p0)].
        """
        p0, p1 = qubit_state
        total = p0 + p1
        p0, p1 = p0 / total, p1 / total

        # Shannon binary entropy H(p) = -p log2 p - (1-p) log2(1-p)
        if 0.0 < p0 < 1.0:
            h_bits = -(p0 * math.log2(p0) + p1 * math.log2(p1))
        else:
            h_bits = 0.0

        # Information acquired by demon: I = 1 - H(p0) (assuming 1 bit prior maximal uncertainty)
        mutual_info = max(0.0, 1.0 - h_bits) * self.measurement_fidelity

        # Work extraction via feedback: W = k_B * T * ln(2) * I
        w_extracted = K_B * temperature * math.log(2) * mutual_info

        # Simulated outcome: outcome 0 if p0 >= p1 else 1 (deterministic best outcome for demonstration)
        outcome = 0 if p0 >= p1 else 1

        entropy_reduction = math.log(2) * mutual_info

        return DemonFeedbackResult(
            measurement_outcome=outcome,
            system_initial_state=[p0, p1],
            mutual_information_bits=mutual_info,
            work_extracted=w_extracted,
            entropy_reduction=entropy_reduction,
            demon_memory_bits=1.0,
        )


class LandauerErasureEngine:
    """Enforces Landauer's principle for resetting memory states."""

    @staticmethod
    def erase_memory(
        bits_to_erase: float,
        reservoir_temperature: float = 1.0,
        dissipation_efficiency: float = 1.05,  # actual heat >= theoretical limit
    ) -> LandauerErasureResult:
        """Erases memory bits against a thermal bath at temperature T.

        Theoretical minimum heat dissipated: Q_min = k_B * T * ln(2) * bits_to_erase.
        """
        if bits_to_erase < 0:
            raise ValueError("Bits to erase cannot be negative.")
        if reservoir_temperature <= 0:
            raise ValueError("Reservoir temperature must be strictly positive.")

        theoretical_q = K_B * reservoir_temperature * math.log(2) * bits_to_erase
        # Actual dissipation must be at least theoretical minimum
        actual_q = theoretical_q * max(1.0, float(dissipation_efficiency))
        entropy_increase = actual_q / reservoir_temperature

        bound_satisfied = actual_q >= (theoretical_q - 1e-9)

        return LandauerErasureResult(
            bits_erased=bits_to_erase,
            reservoir_temperature=reservoir_temperature,
            theoretical_minimum_heat=theoretical_q,
            actual_heat_dissipated=actual_q,
            entropy_increase_reservoir=entropy_increase,
            landauer_bound_satisfied=bound_satisfied,
        )


class QuantumHeatEngineCycle:
    """Simulates a quantum Otto engine cycle operating between hot and cold reservoirs."""

    def __init__(
        self,
        th_cold: float = 1.0,
        th_hot: float = 3.0,
        omega_cold: float = 1.0,
        omega_hot: float = 2.0,
    ) -> None:
        if th_cold >= th_hot:
            raise ValueError("Hot reservoir temperature must exceed cold reservoir temperature.")
        if omega_cold >= omega_hot:
            raise ValueError("Hot frequency omega_hot must exceed cold frequency omega_cold.")

        self.th_cold = float(th_cold)
        self.th_hot = float(th_hot)
        self.omega_cold = float(omega_cold)
        self.omega_hot = float(omega_hot)

    def execute_cycle(self) -> HeatEngineCycleResult:
        """Runs the 4-stage quantum Otto cycle:

        1. Stage 1: Isentropic compression: omega_cold -> omega_hot (state frozen)
        2. Stage 2: Isochoric heating: equilibrates with hot reservoir at omega_hot
        3. Stage 3: Isentropic expansion: omega_hot -> omega_cold (state frozen)
        4. Stage 4: Isochoric cooling: equilibrates with cold reservoir at omega_cold
        """
        # Thermal occupation numbers n = 1 / (exp(beta * omega) - 1) or two-level Gibbs state
        p1_cold = 1.0 / (1.0 + math.exp(self.omega_cold / (K_B * self.th_cold)))
        p1_hot = 1.0 / (1.0 + math.exp(self.omega_hot / (K_B * self.th_hot)))

        # Heat absorbed from hot bath: Q_H = omega_hot * (p1_hot - p1_cold)
        # Positive if p1_hot > p1_cold
        delta_p = p1_hot - p1_cold
        qh = self.omega_hot * delta_p
        qc = self.omega_cold * delta_p

        net_work = qh - qc

        # Efficiency eta = W / Q_H = 1 - omega_cold / omega_hot
        otto_efficiency = 1.0 - (self.omega_cold / self.omega_hot)
        carnot_limit = 1.0 - (self.th_cold / self.th_hot)

        second_law = otto_efficiency <= carnot_limit and net_work >= -1e-9

        return HeatEngineCycleResult(
            stage=ThermodynamicCycleState.COOLING,
            th_cold=self.th_cold,
            th_hot=self.th_hot,
            omega_cold=self.omega_cold,
            omega_hot=self.omega_hot,
            heat_absorbed_qh=qh,
            heat_rejected_qc=qc,
            net_work_extracted=net_work,
            otto_efficiency=otto_efficiency,
            carnot_limit=carnot_limit,
            second_law_satisfied=second_law,
        )


class QuantumThermodynamicMesh:
    """High-level mesh managing quantum thermodynamic transformations, demons, and Landauer ledger."""

    def __init__(self, default_temperature: float = 1.0) -> None:
        self.default_reservoir = QuantumThermalReservoir(default_temperature)
        self.demon = MaxwellQuantumDemon(measurement_fidelity=1.0)
        self.landauer = LandauerErasureEngine()
        self.history: List[Dict[str, Any]] = []

    def thermalize(self, energy_levels: List[float], temperature: Optional[float] = None) -> ThermalState:
        res = QuantumThermalReservoir(temperature) if temperature else self.default_reservoir
        st = res.compute_thermal_state(energy_levels)
        self.history.append({"action": "THERMALIZE", "state": st.to_dict(), "timestamp": time.time()})
        return st

    def extract_ergotropy(
        self,
        energy_levels: List[float],
        probabilities: List[float],
        temperature: Optional[float] = None,
    ) -> WorkExtractionResult:
        res = QuantumWorkExtractionEngine.calculate_ergotropy(
            energy_levels=energy_levels,
            state_probabilities=probabilities,
            reservoir_temperature=temperature or self.default_reservoir.temperature,
        )
        self.history.append({"action": "EXTRACT_ERGOTROPY", "result": res.to_dict(), "timestamp": time.time()})
        return res

    def run_demon_cycle(
        self,
        p0: float,
        p1: float,
        energy_gap: float = 1.0,
        temperature: Optional[float] = None,
    ) -> Tuple[DemonFeedbackResult, LandauerErasureResult]:
        t = temperature or self.default_reservoir.temperature
        demon_res = self.demon.measure_and_extract_work((p0, p1), energy_gap=energy_gap, temperature=t)
        erasure_res = self.landauer.erase_memory(
            bits_to_erase=demon_res.demon_memory_bits,
            reservoir_temperature=t,
            dissipation_efficiency=1.02,
        )
        self.history.append({
            "action": "DEMON_SZILARD_CYCLE",
            "demon": demon_res.to_dict(),
            "erasure": erasure_res.to_dict(),
            "net_work_cost": erasure_res.actual_heat_dissipated - demon_res.work_extracted,
            "timestamp": time.time(),
        })
        return demon_res, erasure_res

    def run_heat_engine(
        self,
        th_cold: float,
        th_hot: float,
        omega_cold: float,
        omega_hot: float,
    ) -> HeatEngineCycleResult:
        engine = QuantumHeatEngineCycle(
            th_cold=th_cold,
            th_hot=th_hot,
            omega_cold=omega_cold,
            omega_hot=omega_hot,
        )
        res = engine.execute_cycle()
        self.history.append({"action": "HEAT_ENGINE_OTTO", "result": res.to_dict(), "timestamp": time.time()})
        return res
