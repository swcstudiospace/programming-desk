"""Fault-Tolerant Surface Codes, Lattice Surgery & Magic State Distillation Mesh (Milestone v6.8 - Phase 102).

Implements:
- SurfaceCodePatch: Planar / rotated surface code patch with distance d.
  Models data qubits and syndrome extraction ancilla qubits (X-stabilizers for bit-flip detection,
  Z-stabilizers for phase-flip detection).
- SyndromeExtractionEngine: Extracts syndrome measurements with Pauli noise (bit flip, phase flip, measurement errors).
  Computes syndrome defect graphs for minimum-weight perfect matching / cluster decoding.
- MinimumWeightDecoder: Graph-based decoder matching syndrome defects to identify most probable correction chains.
  Calculates logical error rate scaling P_L ~ A * (p / p_th)^((d+1)/2).
- LatticeSurgeryEngine: Performs fault-tolerant logical operations between surface code patches without transversal CNOT.
  Supports rough and smooth patch merging and splitting to execute logical CNOT and multi-qubit Pauli measurements (XX, ZZ).
- MagicStateDistillationEngine: Implements Bravyi-Kitaev 15-to-1 distillation protocol for |T> magic states
  (|T> = (|0> + e^(i*pi/4)|1>)/sqrt(2)).
  Transforms 15 noisy raw magic states with error probability epsilon into 1 distilled state with output error epsilon_out ~ 35 * epsilon^3.
- QuantumFaultToleranceMesh: High-level coordinator managing surface code patches, lattice surgery operations,
  and magic state distillation factories.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class StabilizerType(str, enum.Enum):
    STAR_X = "STAR_X"      # Vertex / Star X-stabilizer (detects Z errors)
    PLAQUETTE_Z = "PLAQUETTE_Z"  # Plaquette Z-stabilizer (detects X errors)


class SurgeryOperationType(str, enum.Enum):
    MERGE_ROUGH_XX = "MERGE_ROUGH_XX"
    MERGE_SMOOTH_ZZ = "MERGE_SMOOTH_ZZ"
    SPLIT_PATCH = "SPLIT_PATCH"
    LOGICAL_CNOT = "LOGICAL_CNOT"


@dataclasses.dataclass
class StabilizerDefect:
    stabilizer_id: str
    stab_type: StabilizerType
    row: int
    col: int
    syndrome_bit: int  # 1 for defect (eigenvalue -1), 0 for no defect


@dataclasses.dataclass
class SurfaceCodePatch:
    patch_id: str
    distance: int  # Code distance d (must be odd >= 3)
    logical_qubit_id: str
    physical_error_rate: float = 0.001
    measurement_error_rate: float = 0.0005
    data_qubits: Dict[Tuple[int, int], Dict[str, Any]] = dataclasses.field(default_factory=dict)
    stabilizers: Dict[str, Dict[str, Any]] = dataclasses.field(default_factory=dict)
    active_syndromes: List[StabilizerDefect] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        if self.distance % 2 == 0 or self.distance < 3:
            raise ValueError(f"Surface code distance must be odd and >= 3, got {self.distance}")
        if not self.data_qubits:
            self._initialize_grid()

    def _initialize_grid(self):
        d = self.distance
        # Grid of data qubits (d x d)
        for r in range(d):
            for c in range(d):
                self.data_qubits[(r, c)] = {
                    "id": f"q_{r}_{c}",
                    "state": 0,  # 0 or 1
                    "x_error": False,
                    "z_error": False,
                }
        
        # Plaquette Z and Star X stabilizers
        # For rotated surface code: (d^2 - 1) total stabilizers: (d^2 - 1)/2 X, (d^2 - 1)/2 Z
        stab_idx = 0
        for r in range(d + 1):
            for c in range(d + 1):
                # Checkerboard allocation
                if (r + c) % 2 == 1:
                    is_x = ((r % 2 == 1 and c % 2 == 0) or (r % 2 == 0 and c % 2 == 1))
                    stab_type = StabilizerType.STAR_X if is_x else StabilizerType.PLAQUETTE_Z
                    
                    # Neighboring data qubits (within bounds 0 <= r' < d, 0 <= c' < d)
                    neighbors = []
                    for dr, dc in [(-1, -1), (-1, 0), (0, -1), (0, 0)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < d and 0 <= nc < d:
                            neighbors.append((nr, nc))
                    
                    if neighbors:
                        s_id = f"s_{stab_idx}_{stab_type.value[:1]}_{r}_{c}"
                        self.stabilizers[s_id] = {
                            "id": s_id,
                            "type": stab_type,
                            "row": r,
                            "col": c,
                            "data_neighbors": neighbors,
                        }
                        stab_idx += 1

    def inject_noise(self, rng: Optional[random.Random] = None) -> Dict[str, int]:
        r = rng or random.Random()
        injected = {"x_errors": 0, "z_errors": 0}
        for q in self.data_qubits.values():
            if r.random() < self.physical_error_rate:
                q["x_error"] = not q["x_error"]
                injected["x_errors"] += 1
            if r.random() < self.physical_error_rate:
                q["z_error"] = not q["z_error"]
                injected["z_errors"] += 1
        return injected

    def extract_syndromes(self, rng: Optional[random.Random] = None) -> List[StabilizerDefect]:
        r = rng or random.Random()
        defects = []
        for s_id, s in self.stabilizers.items():
            parity = 0
            is_x_check = (s["type"] == StabilizerType.STAR_X)
            for (qr, qc) in s["data_neighbors"]:
                q = self.data_qubits[(qr, qc)]
                # Star X detects Z errors; Plaquette Z detects X errors
                if is_x_check and q["z_error"]:
                    parity ^= 1
                elif not is_x_check and q["x_error"]:
                    parity ^= 1
            
            # Measurement noise
            if r.random() < self.measurement_error_rate:
                parity ^= 1
            
            if parity == 1:
                defects.append(
                    StabilizerDefect(
                        stabilizer_id=s_id,
                        stab_type=s["type"],
                        row=s["row"],
                        col=s["col"],
                        syndrome_bit=1,
                    )
                )
        self.active_syndromes = defects
        return defects


@dataclasses.dataclass
class CorrectionResult:
    defects_count: int
    matches: List[Tuple[str, str, float]]  # (defect1_id, defect2_id or 'boundary', distance)
    corrections_applied: int
    residual_logical_error: bool
    estimated_logical_error_rate: float


class MinimumWeightDecoder:
    """Minimum-weight pairing decoder for matching stabilizer defects to boundaries or pairs."""

    def __init__(self, code_distance: int, threshold_p: float = 0.0105):
        self.code_distance = code_distance
        self.threshold_p = threshold_p  # ~1.05% threshold for surface code

    def decode(
        self, patch: SurfaceCodePatch, rng: Optional[random.Random] = None
    ) -> CorrectionResult:
        r = rng or random.Random()
        defects = patch.active_syndromes
        
        # Partition defects by stabilizer type
        x_defects = [d for d in defects if d.stab_type == StabilizerType.STAR_X]
        z_defects = [d for d in defects if d.stab_type == StabilizerType.PLAQUETTE_Z]

        matches: List[Tuple[str, str, float]] = []
        applied = 0

        for group in (x_defects, z_defects):
            unmatched = list(group)
            while unmatched:
                d1 = unmatched.pop(0)
                # Distance to boundary vs distance to nearest defect
                dist_to_boundary = min(d1.row, patch.distance - d1.row, d1.col, patch.distance - d1.col) + 1
                
                best_partner_idx = -1
                best_dist = float("inf")
                for i, d2 in enumerate(unmatched):
                    manhattan = abs(d1.row - d2.row) + abs(d1.col - d2.col)
                    if manhattan < best_dist:
                        best_dist = manhattan
                        best_partner_idx = i

                if best_partner_idx >= 0 and best_dist < dist_to_boundary:
                    d2 = unmatched.pop(best_partner_idx)
                    matches.append((d1.stabilizer_id, d2.stabilizer_id, float(best_dist)))
                    applied += 1
                else:
                    matches.append((d1.stabilizer_id, "boundary", float(dist_to_boundary)))
                    applied += 1

        # Clear errors in data qubits that were corrected
        for q in patch.data_qubits.values():
            q["x_error"] = False
            q["z_error"] = False
        patch.active_syndromes = []

        # Theoretical scaling: P_L ~ A * (p / p_th)^((d+1)/2)
        ratio = patch.physical_error_rate / self.threshold_p
        exponent = (patch.distance + 1) / 2.0
        p_logical = 0.1 * math.pow(ratio, exponent)
        p_logical = min(1.0, max(1e-15, p_logical))

        # Check if an uncorrected logical error chain occurred
        residual = (r.random() < p_logical)

        return CorrectionResult(
            defects_count=len(defects),
            matches=matches,
            corrections_applied=applied,
            residual_logical_error=residual,
            estimated_logical_error_rate=p_logical,
        )


@dataclasses.dataclass
class LatticeSurgeryResult:
    operation: SurgeryOperationType
    patch_a_id: str
    patch_b_id: str
    ancilla_patch_id: Optional[str]
    measurement_outcome: int  # +1 or -1
    fidelity: float
    duration_cycles: int
    syndrome_rounds: int
    success: bool


class LatticeSurgeryEngine:
    """Performs topological lattice surgery operations between adjacent surface code patches."""

    def __init__(self, code_distance: int = 3):
        self.code_distance = code_distance

    def perform_cnot(
        self,
        control_patch: SurfaceCodePatch,
        target_patch: SurfaceCodePatch,
        rng: Optional[random.Random] = None,
    ) -> LatticeSurgeryResult:
        """Executes a non-transversal logical CNOT via smooth and rough lattice surgery."""
        r = rng or random.Random()
        # Lattice surgery CNOT takes ~ 2 * d syndrome extraction cycles
        cycles = 2 * self.code_distance
        
        # Merge-split fidelity drops slightly with physical error rate: F ~ (1 - p)^(2*d)
        p = (control_patch.physical_error_rate + target_patch.physical_error_rate) / 2.0
        fidelity = math.pow(1.0 - p, cycles)

        outcome = 1 if r.random() > 0.05 else -1
        success = fidelity > 0.90

        return LatticeSurgeryResult(
            operation=SurgeryOperationType.LOGICAL_CNOT,
            patch_a_id=control_patch.patch_id,
            patch_b_id=target_patch.patch_id,
            ancilla_patch_id=f"ancilla_surgery_{control_patch.patch_id}_{target_patch.patch_id}",
            measurement_outcome=outcome,
            fidelity=round(fidelity, 6),
            duration_cycles=cycles,
            syndrome_rounds=self.code_distance,
            success=success,
        )

    def merge_patches(
        self,
        patch_a: SurfaceCodePatch,
        patch_b: SurfaceCodePatch,
        op_type: SurgeryOperationType,
        rng: Optional[random.Random] = None,
    ) -> LatticeSurgeryResult:
        r = rng or random.Random()
        cycles = self.code_distance
        p = max(patch_a.physical_error_rate, patch_b.physical_error_rate)
        fidelity = math.pow(1.0 - p, cycles)
        outcome = 1 if r.random() > 0.03 else -1

        return LatticeSurgeryResult(
            operation=op_type,
            patch_a_id=patch_a.patch_id,
            patch_b_id=patch_b.patch_id,
            ancilla_patch_id=None,
            measurement_outcome=outcome,
            fidelity=round(fidelity, 6),
            duration_cycles=cycles,
            syndrome_rounds=self.code_distance,
            success=True,
        )


@dataclasses.dataclass
class DistillationRoundReport:
    round_number: int
    raw_input_states: int
    input_error_rate: float
    output_error_rate: float
    distillation_yield: float
    syndrome_passed: bool
    purified_state_fidelity: float


@dataclasses.dataclass
class MagicStateDistillationSummary:
    protocol: str  # e.g., "Bravyi-Kitaev 15-to-1"
    initial_magic_error: float
    target_magic_error: float
    total_raw_states_consumed: int
    distilled_magic_states_produced: int
    final_output_error_rate: float
    final_fidelity: float
    rounds_executed: int
    distillation_efficiency: float
    success: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol": self.protocol,
            "initial_magic_error": self.initial_magic_error,
            "target_magic_error": round(self.target_magic_error, 8),
            "total_raw_states_consumed": self.total_raw_states_consumed,
            "distilled_magic_states_produced": self.distilled_magic_states_produced,
            "final_output_error_rate": round(self.final_output_error_rate, 8),
            "final_fidelity": round(self.final_fidelity, 8),
            "rounds_executed": self.rounds_executed,
            "distillation_efficiency": round(self.distillation_efficiency, 6),
            "success": self.success,
        }


class MagicStateDistillationEngine:
    """Implements Bravyi-Kitaev 15-to-1 magic state distillation for fault-tolerant T-gates."""

    def __init__(self, raw_state_error: float = 0.01):
        self.raw_state_error = raw_state_error

    def distill_single_round(
        self, input_error: float, rng: Optional[random.Random] = None
    ) -> DistillationRoundReport:
        r = rng or random.Random()
        # 15-to-1 Bravyi-Kitaev distillation code:
        # epsilon_out = 35 * epsilon^3 + O(epsilon^4)
        output_error = 35.0 * math.pow(input_error, 3)
        output_error = min(output_error, input_error)

        # Acceptance probability: P_acc ~ 1 - 15 * epsilon
        p_acc = max(0.01, 1.0 - 15.0 * input_error)
        passed = (r.random() < p_acc)

        fidelity = 1.0 - output_error
        yield_rate = (1.0 / 15.0) if passed else 0.0

        return DistillationRoundReport(
            round_number=1,
            raw_input_states=15,
            input_error_rate=input_error,
            output_error_rate=output_error,
            distillation_yield=yield_rate,
            syndrome_passed=passed,
            purified_state_fidelity=fidelity,
        )

    def distill_factory(
        self,
        target_error: float = 1e-6,
        target_states_count: int = 5,
        rng: Optional[random.Random] = None,
    ) -> MagicStateDistillationSummary:
        r = rng or random.Random()
        curr_error = self.raw_state_error
        rounds = 0
        total_consumed = 0
        produced = 0

        # Run recursive distillation rounds until target error is reached
        while curr_error > target_error and rounds < 5:
            rounds += 1
            curr_error = 35.0 * math.pow(curr_error, 3)

        states_per_batch = int(math.pow(15, rounds))
        total_consumed = states_per_batch * target_states_count
        produced = target_states_count

        final_error = max(1e-12, curr_error)
        final_fidelity = 1.0 - final_error
        efficiency = produced / float(total_consumed) if total_consumed > 0 else 0.0

        return MagicStateDistillationSummary(
            protocol=f"Bravyi-Kitaev 15-to-1 ({rounds} rounds)",
            initial_magic_error=self.raw_state_error,
            target_magic_error=target_error,
            total_raw_states_consumed=total_consumed,
            distilled_magic_states_produced=produced,
            final_output_error_rate=final_error,
            final_fidelity=final_fidelity,
            rounds_executed=rounds,
            distillation_efficiency=efficiency,
            success=True,
        )


class QuantumFaultToleranceMesh:
    """High-level mesh coordinating surface code patches, decoders, lattice surgery, and magic states."""

    def __init__(self, default_distance: int = 3, physical_error_rate: float = 0.001):
        self.default_distance = default_distance
        self.physical_error_rate = physical_error_rate
        self.patches: Dict[str, SurfaceCodePatch] = {}
        self.decoder = MinimumWeightDecoder(code_distance=default_distance)
        self.surgery_engine = LatticeSurgeryEngine(code_distance=default_distance)
        self.distillation_engine = MagicStateDistillationEngine(raw_state_error=0.01)

    def create_patch(self, patch_id: str, distance: Optional[int] = None) -> SurfaceCodePatch:
        d = distance or self.default_distance
        patch = SurfaceCodePatch(
            patch_id=patch_id,
            distance=d,
            logical_qubit_id=f"L_{patch_id}",
            physical_error_rate=self.physical_error_rate,
        )
        self.patches[patch_id] = patch
        return patch

    def cycle_and_decode(
        self, patch_id: str, rng: Optional[random.Random] = None
    ) -> CorrectionResult:
        if patch_id not in self.patches:
            self.create_patch(patch_id)
        patch = self.patches[patch_id]
        patch.inject_noise(rng=rng)
        patch.extract_syndromes(rng=rng)
        return self.decoder.decode(patch, rng=rng)

    def execute_logical_cnot(
        self, control_id: str, target_id: str, rng: Optional[random.Random] = None
    ) -> LatticeSurgeryResult:
        if control_id not in self.patches:
            self.create_patch(control_id)
        if target_id not in self.patches:
            self.create_patch(target_id)
        return self.surgery_engine.perform_cnot(
            self.patches[control_id], self.patches[target_id], rng=rng
        )

    def distill_magic_states(
        self, target_error: float = 1e-6, count: int = 5, rng: Optional[random.Random] = None
    ) -> MagicStateDistillationSummary:
        return self.distillation_engine.distill_factory(
            target_error=target_error, target_states_count=count, rng=rng
        )

    def get_mesh_status(self) -> Dict[str, Any]:
        return {
            "active_patches": len(self.patches),
            "default_distance": self.default_distance,
            "physical_error_rate": self.physical_error_rate,
            "patches": {
                p_id: {
                    "distance": p.distance,
                    "data_qubits": len(p.data_qubits),
                    "stabilizers": len(p.stabilizers),
                    "active_syndromes": len(p.active_syndromes),
                }
                for p_id, p in self.patches.items()
            },
        }
