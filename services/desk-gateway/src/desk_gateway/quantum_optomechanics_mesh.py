r"""Quantum Coherent Optomechanics & Phononic Cavity Routing Mesh (Milestone v7.3 - Phase 112).

Implements:
- Cavity Optomechanics Physics Engine:
  - Hamiltonian: H = \hbar \omega_c a^\dagger a + \hbar \omega_m b^\dagger b - \hbar g_0 a^\dagger a (b + b^\dagger)
  - Resolved-sideband regime (\omega_m \gg \kappa) where mechanical frequency exceeds cavity decay rate.
  - Linearized optomechanical coupling: G = g_0 \sqrt{n_c} where n_c is intra-cavity photon count.
  - Optomechanical Cooperativity: C = 4 G^2 / (\kappa \gamma_m).
  - Dynamical backaction: Radiation pressure dynamical damping \Gamma_{\text{opt}} and optical spring shift \delta\omega_m.
  - Sideband cooling: Laser red-detuned (\Delta \approx -\omega_m) extracting mechanical phonons down to ground state:
      n_{\text{eff}} = \frac{\gamma_m n_{\text{th}} + A_-}{\gamma_m + \Gamma_{\text{opt}}} \to n_{\text{eff}} < 1.0 (quantum ground state).
  - Blue-detuned optomechanical parametric amplification and ponderomotive squeezing.
- Phononic Crystal Waveguide & Cavity Routing:
  - Acoustic bandgap phononic defect cavities trapping localized phonon modes.
  - Phonon-polariton state transfer between optical photon wavepackets and phononic mechanical oscillators.
  - Quantum State Transfer Fidelity: F_{\text{transfer}} = \frac{C}{1 + C} e^{-\tau / T_{\text{coh}}}.
  - Multi-node phononic bus routing: High-efficiency photon-to-phonon and phonon-to-photon transduction
    enabling quantum interconnects between disparate superconducting and optical quantum processors.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple


class SidebandDetuningMode(str, enum.Enum):
    RED_SIDEBAND_COOLING = "RED_SIDEBAND_COOLING"      # \Delta = -\omega_m (state swap / cooling)
    BLUE_SIDEBAND_AMPLIFY = "BLUE_SIDEBAND_AMPLIFY"    # \Delta = +\omega_m (two-mode squeezing / entanglement)
    RESONANT = "RESONANT"                              # \Delta = 0 (dispersive readout / phase sensing)


@dataclasses.dataclass
class OptomechanicalCavityParams:
    cavity_id: str
    omega_c_ghz: float          # Optical cavity resonance frequency (e.g. 193400 GHz / 1550 nm)
    omega_m_mhz: float          # Mechanical resonance frequency (e.g. 50.0 MHz)
    kappa_mhz: float            # Optical cavity decay rate \kappa (e.g. 2.0 MHz)
    gamma_m_khz: float          # Mechanical intrinsic dissipation rate \gamma_m (e.g. 1.0 kHz)
    g0_hz: float                # Single-photon optomechanical coupling rate g_0 (e.g. 5000.0 Hz)
    temperature_k: float        # Cryogenic ambient temperature (e.g. 0.020 K = 20 mK)
    laser_power_uw: float       # Driving laser power (microWatts)

    @property
    def is_resolved_sideband(self) -> bool:
        r"""Resolved sideband regime condition: \omega_m > \kappa."""
        return self.omega_m_mhz > self.kappa_mhz

    def thermal_phonon_occupation(self) -> float:
        r"""Bose-Einstein thermal phonon occupation: n_th = k_B * T / (\hbar * \omega_m)."""
        k_b = 1.380649e-23  # J / K
        hbar = 1.0545718e-34  # J * s
        omega_m_rad = self.omega_m_mhz * 1e6 * 2.0 * math.pi
        if self.temperature_k <= 0:
            return 0.0
        exponent = (hbar * omega_m_rad) / (k_b * self.temperature_k)
        if exponent > 50.0:
            return 0.0
        return 1.0 / (math.exp(exponent) - 1.0)


@dataclasses.dataclass
class OptomechanicalState:
    cavity_id: str
    detuning_mode: SidebandDetuningMode
    laser_detuning_mhz: float
    intra_cavity_photons: float
    linearized_coupling_g_khz: float
    cooperativity: float
    optical_damping_khz: float
    effective_phonon_occupation: float
    ground_state_cooled: bool
    ponderomotive_squeezing_db: float
    state_transfer_fidelity: float
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cavity_id": self.cavity_id,
            "detuning_mode": self.detuning_mode.value,
            "laser_detuning_mhz": round(self.laser_detuning_mhz, 4),
            "intra_cavity_photons": round(self.intra_cavity_photons, 2),
            "linearized_coupling_g_khz": round(self.linearized_coupling_g_khz, 4),
            "cooperativity": round(self.cooperativity, 4),
            "optical_damping_khz": round(self.optical_damping_khz, 4),
            "effective_phonon_occupation": round(self.effective_phonon_occupation, 6),
            "ground_state_cooled": self.ground_state_cooled,
            "ponderomotive_squeezing_db": round(self.ponderomotive_squeezing_db, 3),
            "state_transfer_fidelity": round(self.state_transfer_fidelity, 5),
            "timestamp": self.timestamp,
        }


@dataclasses.dataclass
class PhononicRouteHop:
    from_node: str
    to_node: str
    channel_type: str         # "PHONONIC_WAVEGUIDE" or "OPTICAL_FIBER"
    coupling_efficiency: float
    delay_ns: float
    loss_db: float


@dataclasses.dataclass
class PhononicRoutingResult:
    route_id: str
    source_node: str
    destination_node: str
    path: List[str]
    hops: List[PhononicRouteHop]
    total_loss_db: float
    net_transduction_efficiency: float
    end_to_end_fidelity: float
    quantum_state_preserved: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "source_node": self.source_node,
            "destination_node": self.destination_node,
            "path": self.path,
            "hops": [dataclasses.asdict(h) for h in self.hops],
            "total_loss_db": round(self.total_loss_db, 3),
            "net_transduction_efficiency": round(self.net_transduction_efficiency, 5),
            "end_to_end_fidelity": round(self.end_to_end_fidelity, 5),
            "quantum_state_preserved": self.quantum_state_preserved,
        }


class CoherentOptomechanicsEngine:
    """Physics simulation engine for cavity optomechanical interactions."""

    def __init__(self, default_params: Optional[OptomechanicalCavityParams] = None) -> None:
        if default_params is None:
            self.params = OptomechanicalCavityParams(
                cavity_id="cavity-optomech-01",
                omega_c_ghz=193400.0,
                omega_m_mhz=50.0,
                kappa_mhz=2.0,
                gamma_m_khz=1.0,
                g0_hz=5000.0,
                temperature_k=0.020,  # 20 mK dilution fridge
                laser_power_uw=50.0,
            )
        else:
            self.params = default_params

    def compute_intra_cavity_photons(
        self,
        laser_power_uw: float,
        detuning_mhz: float,
        params: Optional[OptomechanicalCavityParams] = None,
    ) -> float:
        r"""Intra-cavity photon number n_c = (P_laser / (\hbar \omega_c)) * (\kappa / (\Delta^2 + (\kappa/2)^2))."""
        p = params or self.params
        hbar = 1.0545718e-34
        omega_c_rad = p.omega_c_ghz * 1e9 * 2.0 * math.pi
        power_watts = laser_power_uw * 1e-6
        photon_flux = power_watts / (hbar * omega_c_rad)

        kappa_rad = p.kappa_mhz * 1e6 * 2.0 * math.pi
        delta_rad = detuning_mhz * 1e6 * 2.0 * math.pi

        lorentzian = (kappa_rad / 2.0) / (delta_rad ** 2 + (kappa_rad / 2.0) ** 2)
        n_c = photon_flux * lorentzian
        return max(1.0, n_c)

    def simulate_interaction(
        self,
        mode: SidebandDetuningMode = SidebandDetuningMode.RED_SIDEBAND_COOLING,
        laser_power_uw: Optional[float] = None,
        custom_detuning_mhz: Optional[float] = None,
        params: Optional[OptomechanicalCavityParams] = None,
    ) -> OptomechanicalState:
        """Simulate sideband cooling, amplification, and photon-phonon quantum state transfer."""
        p = params or self.params
        power = laser_power_uw if laser_power_uw is not None else p.laser_power_uw

        # Determine detuning
        if custom_detuning_mhz is not None:
            detuning = custom_detuning_mhz
        elif mode == SidebandDetuningMode.RED_SIDEBAND_COOLING:
            detuning = -p.omega_m_mhz  # \Delta = -\omega_m
        elif mode == SidebandDetuningMode.BLUE_SIDEBAND_AMPLIFY:
            detuning = p.omega_m_mhz   # \Delta = +\omega_m
        else:
            detuning = 0.0

        n_c = self.compute_intra_cavity_photons(power, detuning, p)

        # Linearized coupling G = g_0 * \sqrt{n_c} in kHz
        g_linear_hz = p.g0_hz * math.sqrt(n_c)
        g_linear_khz = g_linear_hz / 1e3

        # Cooperativity C = 4 * G^2 / (\kappa * \gamma_m)
        kappa_hz = p.kappa_mhz * 1e6
        gamma_m_hz = p.gamma_m_khz * 1e3
        cooperativity = (4.0 * (g_linear_hz ** 2)) / (kappa_hz * gamma_m_hz)

        # Radiation pressure dynamical damping \Gamma_{\text{opt}} in kHz
        # For red detuning in resolved sideband: \Gamma_{\text{opt}} \approx 4 G^2 / \kappa = C * \gamma_m
        if mode == SidebandDetuningMode.RED_SIDEBAND_COOLING:
            gamma_opt_hz = 4.0 * (g_linear_hz ** 2) / kappa_hz
            gamma_opt_khz = gamma_opt_hz / 1e3
        elif mode == SidebandDetuningMode.BLUE_SIDEBAND_AMPLIFY:
            gamma_opt_hz = -4.0 * (g_linear_hz ** 2) / kappa_hz
            gamma_opt_khz = gamma_opt_hz / 1e3
        else:
            gamma_opt_khz = 0.0

        # Thermal occupation
        n_th = p.thermal_phonon_occupation()

        # Sideband cooling effective phonon occupancy: n_eff = n_th / (1 + C) + quantum backaction floor
        quantum_backaction = (p.kappa_mhz / (4.0 * p.omega_m_mhz)) ** 2 if p.is_resolved_sideband else 0.1
        if mode == SidebandDetuningMode.RED_SIDEBAND_COOLING:
            n_eff = (n_th / (1.0 + cooperativity)) + quantum_backaction
        elif mode == SidebandDetuningMode.BLUE_SIDEBAND_AMPLIFY:
            n_eff = n_th * (1.0 + cooperativity)
        else:
            n_eff = n_th

        ground_state = (n_eff < 1.0)

        # Ponderomotive squeezing in dB (parametric noise reduction below vacuum level)
        if cooperativity > 0.0:
            squeezing_factor = 1.0 / (1.0 + 2.0 * math.sqrt(cooperativity))
            ponderomotive_db = -10.0 * math.log10(max(1e-4, squeezing_factor))
        else:
            ponderomotive_db = 0.0

        # Quantum state transfer fidelity: F = C / (1 + C) * exp(-1 / (2*C))
        if cooperativity > 0.0:
            decay_factor = math.exp(-1.0 / (2.0 * max(0.01, cooperativity)))
            state_transfer_fidelity = (cooperativity / (1.0 + cooperativity)) * decay_factor
        else:
            state_transfer_fidelity = 0.0
        state_transfer_fidelity = min(0.9999, max(0.0, state_transfer_fidelity))

        return OptomechanicalState(
            cavity_id=p.cavity_id,
            detuning_mode=mode,
            laser_detuning_mhz=detuning,
            intra_cavity_photons=n_c,
            linearized_coupling_g_khz=g_linear_khz,
            cooperativity=cooperativity,
            optical_damping_khz=gamma_opt_khz,
            effective_phonon_occupation=n_eff,
            ground_state_cooled=ground_state,
            ponderomotive_squeezing_db=ponderomotive_db,
            state_transfer_fidelity=state_transfer_fidelity,
        )


class PhononicCavityRoutingEngine:
    """Routing mesh for phononic crystal waveguides and optomechanical cavity buses."""

    def __init__(self) -> None:
        self.nodes: Dict[str, OptomechanicalCavityParams] = {}
        self.topology: Dict[str, List[Tuple[str, str, float, float]]] = {}  # src -> [(dst, channel_type, loss_db, delay_ns)]
        self._init_default_network()

    def _init_default_network(self) -> None:
        """Initialize default 4-node quantum phononic routing mesh."""
        nodes = [
            OptomechanicalCavityParams("node-alpha", 193400.0, 50.0, 2.0, 1.0, 5000.0, 0.020, 50.0),
            OptomechanicalCavityParams("node-beta", 193400.0, 50.0, 2.2, 1.1, 4800.0, 0.022, 50.0),
            OptomechanicalCavityParams("node-gamma", 193400.0, 50.0, 1.9, 0.9, 5200.0, 0.018, 55.0),
            OptomechanicalCavityParams("node-delta", 193400.0, 50.0, 2.1, 1.0, 5100.0, 0.020, 50.0),
        ]
        for n in nodes:
            self.nodes[n.cavity_id] = n
            self.topology[n.cavity_id] = []

        # Interconnects:
        # alpha <-> beta (phononic crystal defect waveguide)
        self.add_link("node-alpha", "node-beta", "PHONONIC_WAVEGUIDE", loss_db=0.15, delay_ns=120.0)
        # beta <-> gamma (cryogenic optical fiber link)
        self.add_link("node-beta", "node-gamma", "OPTICAL_FIBER", loss_db=0.30, delay_ns=25.0)
        # gamma <-> delta (phononic crystal defect waveguide)
        self.add_link("node-gamma", "node-delta", "PHONONIC_WAVEGUIDE", loss_db=0.18, delay_ns=140.0)
        # alpha <-> gamma (direct optical bus)
        self.add_link("node-alpha", "node-gamma", "OPTICAL_FIBER", loss_db=0.55, delay_ns=40.0)

    def add_link(self, src: str, dst: str, channel_type: str, loss_db: float, delay_ns: float) -> None:
        if src not in self.topology:
            self.topology[src] = []
        if dst not in self.topology:
            self.topology[dst] = []
        self.topology[src].append((dst, channel_type, loss_db, delay_ns))
        self.topology[dst].append((src, channel_type, loss_db, delay_ns))

    def find_optimal_route(self, src: str, dst: str) -> List[Tuple[str, str, float, float]]:
        """Dijkstra shortest path optimizing minimum cumulative loss (dB)."""
        if src not in self.nodes or dst not in self.nodes:
            raise ValueError(f"Unknown node {src} or {dst}")
        if src == dst:
            return []

        distances: Dict[str, float] = {node: float("inf") for node in self.nodes}
        previous: Dict[str, Optional[Tuple[str, str, float, float]]] = {node: None for node in self.nodes}
        distances[src] = 0.0
        unvisited = set(self.nodes.keys())

        while unvisited:
            curr = min(unvisited, key=lambda n: distances[n])
            if curr == dst or distances[curr] == float("inf"):
                break
            unvisited.remove(curr)

            for neighbor, c_type, loss, delay in self.topology.get(curr, []):
                if neighbor in unvisited:
                    new_dist = distances[curr] + loss
                    if new_dist < distances[neighbor]:
                        distances[neighbor] = new_dist
                        previous[neighbor] = (curr, c_type, loss, delay)

        # Backtrack path
        hops: List[Tuple[str, str, float, float]] = []
        curr = dst
        while previous[curr] is not None:
            prev_node, c_type, loss, delay = previous[curr]  # type: ignore[misc]
            hops.append((prev_node, curr, loss, delay, c_type))  # type: ignore[misc]
            curr = prev_node
        hops.reverse()
        return hops  # type: ignore[return-value]

    def route_quantum_state(
        self,
        src: str,
        dst: str,
        optomech_engine: CoherentOptomechanicsEngine,
    ) -> PhononicRoutingResult:
        """Route quantum photon/phonon state across optomechanical cavity mesh."""
        raw_hops = self.find_optimal_route(src, dst)
        if not raw_hops:
            raise ValueError(f"No viable route found between {src} and {dst}")

        path = [src]
        hops: List[PhononicRouteHop] = []
        cumulative_loss_db = 0.0

        for hop_tuple in raw_hops:
            u, v, loss, delay, c_type = hop_tuple  # type: ignore[misc]
            path.append(v)
            cumulative_loss_db += loss
            efficiency = 10.0 ** (-loss / 10.0)
            hops.append(
                PhononicRouteHop(
                    from_node=u,
                    to_node=v,
                    channel_type=c_type,
                    coupling_efficiency=round(efficiency, 4),
                    delay_ns=delay,
                    loss_db=loss,
                )
            )

        # Evaluate nodal conversion and transport fidelity
        src_state = optomech_engine.simulate_interaction(
            mode=SidebandDetuningMode.RED_SIDEBAND_COOLING,
            params=self.nodes[src],
        )
        dst_state = optomech_engine.simulate_interaction(
            mode=SidebandDetuningMode.RED_SIDEBAND_COOLING,
            params=self.nodes[dst],
        )

        # Net efficiency: product of channel transmission and nodal transduction fidelities
        channel_transmission = 10.0 ** (-cumulative_loss_db / 10.0)
        net_efficiency = channel_transmission * src_state.state_transfer_fidelity * dst_state.state_transfer_fidelity
        end_to_end_fidelity = math.sqrt(net_efficiency)

        route_id = f"qroute-{hashlib.sha256(f'{src}:{dst}:{time.time()}'.encode()).hexdigest()[:12]}"

        return PhononicRoutingResult(
            route_id=route_id,
            source_node=src,
            destination_node=dst,
            path=path,
            hops=hops,
            total_loss_db=cumulative_loss_db,
            net_transduction_efficiency=net_efficiency,
            end_to_end_fidelity=end_to_end_fidelity,
            quantum_state_preserved=(end_to_end_fidelity >= 0.70),
        )


class QuantumOptomechanicsMesh:
    """Unified coordinator for coherent optomechanical simulation and phononic routing."""

    def __init__(self) -> None:
        self.optomech_engine = CoherentOptomechanicsEngine()
        self.routing_engine = PhononicCavityRoutingEngine()

    def simulate_cavity_cooling(
        self,
        cavity_id: str = "node-alpha",
        laser_power_uw: float = 50.0,
    ) -> OptomechanicalState:
        node_params = self.routing_engine.nodes.get(cavity_id, self.optomech_engine.params)
        return self.optomech_engine.simulate_interaction(
            mode=SidebandDetuningMode.RED_SIDEBAND_COOLING,
            laser_power_uw=laser_power_uw,
            params=node_params,
        )

    def simulate_ponderomotive_squeezing(
        self,
        cavity_id: str = "node-alpha",
        laser_power_uw: float = 80.0,
    ) -> OptomechanicalState:
        node_params = self.routing_engine.nodes.get(cavity_id, self.optomech_engine.params)
        return self.optomech_engine.simulate_interaction(
            mode=SidebandDetuningMode.RESONANT,
            laser_power_uw=laser_power_uw,
            params=node_params,
        )

    def route_quantum_packet(
        self,
        source_node: str = "node-alpha",
        destination_node: str = "node-delta",
    ) -> PhononicRoutingResult:
        return self.routing_engine.route_quantum_state(
            src=source_node,
            dst=destination_node,
            optomech_engine=self.optomech_engine,
        )
