"""Multi-Substrate Hardware Acceleration Engine & Kernel Compilation (Milestone v4.7 - Phase 60).

Implements:
- HardwareSubstrate: Heterogeneous compute substrates (CPU, GPU, TPU, NPU, NEUROMORPHIC, PHOTONIC).
- SubstrateProfile: Performance characteristics, memory bandwidth, TOPS/W, and thermal ceilings.
- SubstrateRegistry: Hardware inventory tracking availability, utilization, and health of substrates.
- SubstrateKernelCompiler: Compiles high-level tensor operations into optimized target intermediate representations.
- CompiledKernel: Intermediate representation artifact with estimated cycles, memory footprint, and digest.
- SubstrateWorkloadDispatcher: Energy- and latency-aware scheduler routing tasks to optimal hardware substrates.
- SubstrateTelemetryProfiler: Real-time telemetry monitoring power consumption, thermal dissipation, and throttling.
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
from typing import Any, Dict, List, Optional, Set, Tuple


class HardwareSubstrate(str, enum.Enum):
    CPU_X86 = "cpu_x86"
    CPU_ARM = "cpu_arm"
    GPU_CUDA = "gpu_cuda"
    TPU_XLA = "tpu_xla"
    NPU_EMBEDDED = "npu_embedded"
    NEUROMORPHIC = "neuromorphic"
    PHOTONIC = "photonic"


class KernelOpType(str, enum.Enum):
    GEMM = "gemm"
    CONV2D = "conv2d"
    ATTENTION_FLASH = "attention_flash"
    SPARSE_MATMUL = "sparse_matmul"
    SPIKE_PROPAGATION = "spike_propagation"
    ELEMENTWISE_ACTIVATION = "elementwise_activation"


@dataclass
class SubstrateProfile:
    substrate: HardwareSubstrate
    name: str
    peak_tops: float  # Tera-Operations Per Second (INT8/FP16 equivalent)
    memory_bandwidth_gbps: float  # Memory Bandwidth in GB/s
    vram_bytes: int  # Total addressable memory in bytes
    idle_power_watts: float
    max_power_watts: float
    thermal_limit_celsius: float
    is_available: bool = True
    current_temp_celsius: float = 35.0
    allocated_memory_bytes: int = 0
    active_jobs_count: int = 0

    @property
    def tops_per_watt(self) -> float:
        if self.max_power_watts <= 0:
            return 0.0
        return self.peak_tops / self.max_power_watts

    @property
    def available_memory_bytes(self) -> int:
        return max(0, self.vram_bytes - self.allocated_memory_bytes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "substrate": self.substrate.value,
            "name": self.name,
            "peak_tops": round(self.peak_tops, 2),
            "memory_bandwidth_gbps": round(self.memory_bandwidth_gbps, 2),
            "vram_bytes": self.vram_bytes,
            "available_memory_bytes": self.available_memory_bytes,
            "allocated_memory_bytes": self.allocated_memory_bytes,
            "idle_power_watts": self.idle_power_watts,
            "max_power_watts": self.max_power_watts,
            "tops_per_watt": round(self.tops_per_watt, 3),
            "thermal_limit_celsius": self.thermal_limit_celsius,
            "current_temp_celsius": round(self.current_temp_celsius, 2),
            "is_available": self.is_available,
            "active_jobs_count": self.active_jobs_count,
        }


class SubstrateRegistry:
    """Manages inventory of heterogeneous compute accelerators and their operational statuses."""

    def __init__(self) -> None:
        self.substrates: Dict[str, SubstrateProfile] = {}
        self._initialize_default_substrates()

    def _initialize_default_substrates(self) -> None:
        defaults = [
            SubstrateProfile(
                substrate=HardwareSubstrate.CPU_X86,
                name="Host Xeon Platinum 8480+",
                peak_tops=16.0,
                memory_bandwidth_gbps=307.2,
                vram_bytes=64 * 1024 * 1024 * 1024,  # 64 GB
                idle_power_watts=45.0,
                max_power_watts=350.0,
                thermal_limit_celsius=85.0,
            ),
            SubstrateProfile(
                substrate=HardwareSubstrate.GPU_CUDA,
                name="NVIDIA H100 SXM5",
                peak_tops=989.0,
                memory_bandwidth_gbps=3350.0,
                vram_bytes=80 * 1024 * 1024 * 1024,  # 80 GB
                idle_power_watts=60.0,
                max_power_watts=700.0,
                thermal_limit_celsius=82.0,
            ),
            SubstrateProfile(
                substrate=HardwareSubstrate.TPU_XLA,
                name="Google Cloud TPU v5e",
                peak_tops=393.0,
                memory_bandwidth_gbps=819.0,
                vram_bytes=16 * 1024 * 1024 * 1024,  # 16 GB
                idle_power_watts=30.0,
                max_power_watts=250.0,
                thermal_limit_celsius=80.0,
            ),
            SubstrateProfile(
                substrate=HardwareSubstrate.NPU_EMBEDDED,
                name="Qualcomm Hexagon NPU",
                peak_tops=45.0,
                memory_bandwidth_gbps=135.0,
                vram_bytes=8 * 1024 * 1024 * 1024,  # 8 GB
                idle_power_watts=2.0,
                max_power_watts=15.0,
                thermal_limit_celsius=75.0,
            ),
            SubstrateProfile(
                substrate=HardwareSubstrate.NEUROMORPHIC,
                name="Intel Loihi 2 Synaptic Mesh",
                peak_tops=120.0,  # Equivalent spiking operations
                memory_bandwidth_gbps=512.0,
                vram_bytes=4 * 1024 * 1024 * 1024,  # 4 GB
                idle_power_watts=0.05,
                max_power_watts=4.0,  # Ultra-low power spiking
                thermal_limit_celsius=70.0,
            ),
            SubstrateProfile(
                substrate=HardwareSubstrate.PHOTONIC,
                name="Lightmatter Envise Photonic Matrix",
                peak_tops=1500.0,
                memory_bandwidth_gbps=4000.0,
                vram_bytes=32 * 1024 * 1024 * 1024,  # 32 GB
                idle_power_watts=20.0,
                max_power_watts=120.0,
                thermal_limit_celsius=65.0,
            ),
        ]
        for sub in defaults:
            self.substrates[sub.substrate.value] = sub

    def register_substrate(self, profile: SubstrateProfile) -> None:
        self.substrates[profile.substrate.value] = profile

    def get_substrate(self, substrate_type: HardwareSubstrate | str) -> Optional[SubstrateProfile]:
        key = substrate_type.value if isinstance(substrate_type, HardwareSubstrate) else str(substrate_type)
        return self.substrates.get(key)

    def list_substrates(self) -> List[SubstrateProfile]:
        return list(self.substrates.values())

    def update_telemetry(
        self,
        substrate_type: HardwareSubstrate | str,
        delta_temp: float = 0.0,
        allocated_bytes_delta: int = 0,
        active_jobs_delta: int = 0,
    ) -> SubstrateProfile:
        sub = self.get_substrate(substrate_type)
        if not sub:
            raise ValueError(f"Unknown substrate: {substrate_type}")
        sub.current_temp_celsius = max(20.0, min(100.0, sub.current_temp_celsius + delta_temp))
        sub.allocated_memory_bytes = max(0, min(sub.vram_bytes, sub.allocated_memory_bytes + allocated_bytes_delta))
        sub.active_jobs_count = max(0, sub.active_jobs_count + active_jobs_delta)

        # Thermal throttling
        if sub.current_temp_celsius >= sub.thermal_limit_celsius:
            sub.is_available = False
        else:
            sub.is_available = True
        return sub


@dataclass
class CompiledKernel:
    kernel_id: str
    target_substrate: HardwareSubstrate
    op_type: KernelOpType
    input_shapes: List[List[int]]
    output_shape: List[int]
    optimization_passes: List[str]  # e.g., ["operator_fusion", "loop_tiling_32x32", "vectorize_avx512"]
    estimated_flops: int
    estimated_latency_us: float
    estimated_memory_bytes: int
    ir_assembly: str
    kernel_digest: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kernel_id": self.kernel_id,
            "target_substrate": self.target_substrate.value,
            "op_type": self.op_type.value,
            "input_shapes": self.input_shapes,
            "output_shape": self.output_shape,
            "optimization_passes": self.optimization_passes,
            "estimated_flops": self.estimated_flops,
            "estimated_latency_us": round(self.estimated_latency_us, 3),
            "estimated_memory_bytes": self.estimated_memory_bytes,
            "ir_assembly": self.ir_assembly,
            "kernel_digest": self.kernel_digest,
            "created_at": self.created_at,
        }


class SubstrateKernelCompiler:
    """Compiles multi-dimensional tensor operations into architecture-tailored kernel IRs."""

    def __init__(self) -> None:
        self.compiled_cache: Dict[str, CompiledKernel] = {}

    def compile(
        self,
        op_type: KernelOpType,
        target_substrate: HardwareSubstrate,
        input_shapes: List[List[int]],
        optimization_level: int = 3,
    ) -> CompiledKernel:
        # Calculate dimension arithmetic
        if op_type == KernelOpType.GEMM:
            # Assumes [M, K] x [K, N] -> [M, N]
            m = input_shapes[0][0] if len(input_shapes[0]) > 0 else 1
            k = input_shapes[0][1] if len(input_shapes[0]) > 1 else 1
            n = input_shapes[1][1] if len(input_shapes) > 1 and len(input_shapes[1]) > 1 else 1
            flops = 2 * m * k * n
            output_shape = [m, n]
            mem_bytes = (m * k + k * n + m * n) * 4  # FP32/INT32
        elif op_type == KernelOpType.ATTENTION_FLASH:
            # Batch, Seq, Heads, Dim
            b, s, h, d = (
                input_shapes[0][0] if len(input_shapes[0]) > 0 else 1,
                input_shapes[0][1] if len(input_shapes[0]) > 1 else 128,
                input_shapes[0][2] if len(input_shapes[0]) > 2 else 8,
                input_shapes[0][3] if len(input_shapes[0]) > 3 else 64,
            )
            flops = 4 * b * h * s * s * d
            output_shape = [b, s, h, d]
            mem_bytes = 3 * b * s * h * d * 4
        elif op_type == KernelOpType.SPIKE_PROPAGATION:
            # Sparse spike vector [spikes] x syn_matrix [neurons_in, neurons_out]
            spikes = input_shapes[0][0] if len(input_shapes[0]) > 0 else 100
            n_out = input_shapes[1][1] if len(input_shapes) > 1 and len(input_shapes[1]) > 1 else 1024
            flops = spikes * n_out
            output_shape = [n_out]
            mem_bytes = (spikes + spikes * n_out + n_out) * 2  # INT16 synaptic weights
        else:
            flops = 1000000
            output_shape = input_shapes[0] if input_shapes else [1]
            mem_bytes = 1024 * 1024

        passes: List[str] = []
        if optimization_level >= 1:
            passes.append("dead_code_elimination")
            passes.append("constant_folding")
        if optimization_level >= 2:
            passes.append("operator_fusion")
            passes.append("loop_tiling_auto")
        if optimization_level >= 3:
            if target_substrate == HardwareSubstrate.GPU_CUDA:
                passes.extend(["warp_synchronous_reduction", "shared_memory_pipelining_cp_async"])
            elif target_substrate == HardwareSubstrate.NEUROMORPHIC:
                passes.extend(["synaptic_sparsity_compression", "event_queue_unrolling", "zero_leak_coalescing"])
            elif target_substrate == HardwareSubstrate.PHOTONIC:
                passes.extend(["mesh_unitary_decomposition", "phase_shifter_calibration_map"])
            elif target_substrate == HardwareSubstrate.TPU_XLA:
                passes.extend(["xla_layout_transform", "hbm_prefetch_stream"])
            else:
                passes.extend(["simd_vectorize_avx512", "cache_l2_blocking"])

        # Hardware speedup factor relative to baseline CPU
        speedup_map = {
            HardwareSubstrate.CPU_X86: 1.0,
            HardwareSubstrate.CPU_ARM: 0.9,
            HardwareSubstrate.GPU_CUDA: 25.0,
            HardwareSubstrate.TPU_XLA: 20.0,
            HardwareSubstrate.NPU_EMBEDDED: 4.5,
            HardwareSubstrate.NEUROMORPHIC: 40.0 if op_type == KernelOpType.SPIKE_PROPAGATION else 2.0,
            HardwareSubstrate.PHOTONIC: 60.0 if op_type in (KernelOpType.GEMM, KernelOpType.CONV2D) else 5.0,
        }
        speedup = speedup_map.get(target_substrate, 1.0)
        base_latency_us = (flops / 1e7) * 1000.0  # baseline in microseconds
        est_latency_us = max(0.5, (base_latency_us / speedup) / (1.0 + 0.15 * optimization_level))

        raw_repr = f"KERNEL_IR({target_substrate.value}_{op_type.value}_{input_shapes}->{output_shape}_{passes})"
        digest = hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()
        kernel_id = f"kern-{digest[:12]}"

        ir_assembly = f"""// COMPILER: desk-accelerate-v4.7
.target {target_substrate.value}
.op {op_type.value}
.in {input_shapes}
.out {output_shape}
.optimizations [{', '.join(passes)}]
.metrics flops={flops}, est_us={est_latency_us:.2f}, mem={mem_bytes}B
ENTRY_POINT {kernel_id}:
  alloc_tensor %out, {output_shape}
  bind_passes [{', '.join(passes)}]
  dispatch_kernel_grid
  ret %out
"""
        kernel = CompiledKernel(
            kernel_id=kernel_id,
            target_substrate=target_substrate,
            op_type=op_type,
            input_shapes=input_shapes,
            output_shape=output_shape,
            optimization_passes=passes,
            estimated_flops=flops,
            estimated_latency_us=est_latency_us,
            estimated_memory_bytes=mem_bytes,
            ir_assembly=ir_assembly,
            kernel_digest=digest,
        )
        self.compiled_cache[kernel_id] = kernel
        return kernel


@dataclass
class WorkloadAssignment:
    workload_id: str
    target_substrate: HardwareSubstrate
    kernel_id: str
    priority: int  # 1 (low) to 10 (critical)
    estimated_energy_joules: float
    estimated_latency_us: float
    status: str  # "ASSIGNED", "DISPATCHED", "COMPLETED", "REJECTED_THERMAL"
    assigned_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workload_id": self.workload_id,
            "target_substrate": self.target_substrate.value,
            "kernel_id": self.kernel_id,
            "priority": self.priority,
            "estimated_energy_joules": round(self.estimated_energy_joules, 6),
            "estimated_latency_us": round(self.estimated_latency_us, 3),
            "status": self.status,
            "assigned_at": self.assigned_at,
        }


class SubstrateWorkloadDispatcher:
    """Dispatches tensor workloads across heterogeneous substrates balancing latency, energy, and thermal constraints."""

    def __init__(
        self,
        registry: SubstrateRegistry,
        compiler: SubstrateKernelCompiler,
        energy_preference_weight: float = 0.5,  # 0.0 = pure latency, 1.0 = pure energy efficiency
    ) -> None:
        self.registry = registry
        self.compiler = compiler
        self.energy_preference_weight = energy_preference_weight
        self.dispatched_workloads: Dict[str, WorkloadAssignment] = {}

    def schedule_task(
        self,
        op_type: KernelOpType,
        input_shapes: List[List[int]],
        priority: int = 5,
        target_override: Optional[HardwareSubstrate] = None,
    ) -> WorkloadAssignment:
        workload_id = f"wl-{secrets.token_hex(6)}"
        candidates: List[Tuple[float, HardwareSubstrate, CompiledKernel, float, float]] = []

        eligible_substrates = [target_override] if target_override else list(HardwareSubstrate)

        for sub_type in eligible_substrates:
            profile = self.registry.get_substrate(sub_type)
            if not profile or not profile.is_available:
                continue

            # Compile or fetch cached kernel
            compiled = self.compiler.compile(op_type=op_type, target_substrate=sub_type, input_shapes=input_shapes)

            # Check memory fit
            if compiled.estimated_memory_bytes > profile.available_memory_bytes:
                continue

            # Energy estimate in Joules = Power (Watts) * Time (seconds)
            run_power = profile.idle_power_watts + (profile.max_power_watts - profile.idle_power_watts) * 0.8
            est_energy_j = run_power * (compiled.estimated_latency_us / 1e6)

            # Scoring: lower is better
            # Normalized latency (us) and energy (Joules)
            latency_score = compiled.estimated_latency_us
            energy_score = est_energy_j * 1e6  # scale up for numerical balance

            # Weighting
            w_e = self.energy_preference_weight
            w_l = 1.0 - w_e
            total_cost = (w_l * latency_score) + (w_e * energy_score)

            # Neuromorphic affinity bonus for spike propagation
            if op_type == KernelOpType.SPIKE_PROPAGATION and sub_type == HardwareSubstrate.NEUROMORPHIC:
                total_cost *= 0.1
            # Photonic affinity bonus for dense GEMM
            if op_type == KernelOpType.GEMM and sub_type == HardwareSubstrate.PHOTONIC:
                total_cost *= 0.2

            candidates.append((total_cost, sub_type, compiled, est_energy_j, compiled.estimated_latency_us))

        if not candidates:
            # Fallback to host CPU even if throttled
            cpu_profile = self.registry.get_substrate(HardwareSubstrate.CPU_X86)
            compiled = self.compiler.compile(op_type=op_type, target_substrate=HardwareSubstrate.CPU_X86, input_shapes=input_shapes)
            assignment = WorkloadAssignment(
                workload_id=workload_id,
                target_substrate=HardwareSubstrate.CPU_X86,
                kernel_id=compiled.kernel_id,
                priority=priority,
                estimated_energy_joules=0.01,
                estimated_latency_us=compiled.estimated_latency_us,
                status="DISPATCHED",
            )
            self.dispatched_workloads[workload_id] = assignment
            return assignment

        candidates.sort(key=lambda x: x[0])
        best = candidates[0]
        chosen_substrate, chosen_kernel, est_j, est_lat = best[1], best[2], best[3], best[4]

        # Allocate telemetry in registry
        self.registry.update_telemetry(
            substrate_type=chosen_substrate,
            delta_temp=0.5,
            allocated_bytes_delta=chosen_kernel.estimated_memory_bytes,
            active_jobs_delta=1,
        )

        assignment = WorkloadAssignment(
            workload_id=workload_id,
            target_substrate=chosen_substrate,
            kernel_id=chosen_kernel.kernel_id,
            priority=priority,
            estimated_energy_joules=est_j,
            estimated_latency_us=est_lat,
            status="DISPATCHED",
        )
        self.dispatched_workloads[workload_id] = assignment
        return assignment


class SubstrateTelemetryProfiler:
    """Monitors power draw, thermal saturation, and dynamic throttling across all substrates."""

    def __init__(self, registry: SubstrateRegistry) -> None:
        self.registry = registry

    def collect_cluster_telemetry(self) -> Dict[str, Any]:
        profiles = self.registry.list_substrates()
        total_peak_tops = sum(p.peak_tops for p in profiles)
        total_vram_bytes = sum(p.vram_bytes for p in profiles)
        total_allocated_vram = sum(p.allocated_memory_bytes for p in profiles)
        active_jobs = sum(p.active_jobs_count for p in profiles)
        avg_temp = sum(p.current_temp_celsius for p in profiles) / len(profiles) if profiles else 0.0

        current_total_power_watts = sum(
            p.idle_power_watts + (p.max_power_watts - p.idle_power_watts) * (min(1.0, p.active_jobs_count * 0.25))
            for p in profiles
        )

        throttled_devices = [p.name for p in profiles if not p.is_available or p.current_temp_celsius >= p.thermal_limit_celsius]

        return {
            "total_substrates": len(profiles),
            "total_peak_tops": round(total_peak_tops, 2),
            "total_vram_gb": round(total_vram_bytes / (1024**3), 2),
            "vram_utilization_ratio": round(total_allocated_vram / total_vram_bytes, 4) if total_vram_bytes > 0 else 0.0,
            "total_active_jobs": active_jobs,
            "estimated_cluster_power_watts": round(current_total_power_watts, 2),
            "average_temperature_celsius": round(avg_temp, 2),
            "throttled_substrates": throttled_devices,
            "substrates": [p.to_dict() for p in profiles],
            "timestamp": time.time(),
        }
