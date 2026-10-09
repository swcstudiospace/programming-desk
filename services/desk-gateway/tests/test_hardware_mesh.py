"""Unit tests for Multi-Substrate Hardware Acceleration Engine & Kernel Compilation (Phase 60)."""

import pytest

from desk_gateway.hardware_mesh import (
    CompiledKernel,
    HardwareSubstrate,
    KernelOpType,
    SubstrateKernelCompiler,
    SubstrateProfile,
    SubstrateRegistry,
    SubstrateTelemetryProfiler,
    SubstrateWorkloadDispatcher,
    WorkloadAssignment,
)


def test_substrate_registry_and_telemetry():
    registry = SubstrateRegistry()
    substrates = registry.list_substrates()
    assert len(substrates) >= 5

    gpu = registry.get_substrate(HardwareSubstrate.GPU_CUDA)
    assert gpu is not None
    assert gpu.peak_tops > 500.0
    assert gpu.is_available is True

    # Update telemetry
    updated = registry.update_telemetry(
        HardwareSubstrate.GPU_CUDA,
        delta_temp=5.0,
        allocated_bytes_delta=1024 * 1024 * 1024,
        active_jobs_delta=2,
    )
    assert updated.current_temp_celsius == 40.0
    assert updated.allocated_memory_bytes == 1024 * 1024 * 1024
    assert updated.active_jobs_count == 2
    assert updated.is_available is True


def test_substrate_thermal_throttling():
    registry = SubstrateRegistry()
    updated = registry.update_telemetry(
        HardwareSubstrate.NPU_EMBEDDED,
        delta_temp=50.0,  # Exceeds thermal_limit_celsius (75.0)
    )
    assert updated.current_temp_celsius >= 75.0
    assert updated.is_available is False


def test_substrate_kernel_compiler():
    compiler = SubstrateKernelCompiler()

    # Compile GEMM on GPU
    k_gpu = compiler.compile(
        op_type=KernelOpType.GEMM,
        target_substrate=HardwareSubstrate.GPU_CUDA,
        input_shapes=[[1024, 1024], [1024, 1024]],
        optimization_level=3,
    )
    assert isinstance(k_gpu, CompiledKernel)
    assert k_gpu.target_substrate == HardwareSubstrate.GPU_CUDA
    assert k_gpu.estimated_flops == 2 * 1024 * 1024 * 1024
    assert "warp_synchronous_reduction" in k_gpu.optimization_passes
    assert k_gpu.kernel_digest is not None

    # Compile Spike Propagation on Neuromorphic substrate
    k_nm = compiler.compile(
        op_type=KernelOpType.SPIKE_PROPAGATION,
        target_substrate=HardwareSubstrate.NEUROMORPHIC,
        input_shapes=[[200, 1], [200, 1024]],
        optimization_level=3,
    )
    assert "synaptic_sparsity_compression" in k_nm.optimization_passes
    assert k_nm.estimated_latency_us > 0.0


def test_substrate_workload_dispatcher():
    registry = SubstrateRegistry()
    compiler = SubstrateKernelCompiler()
    dispatcher = SubstrateWorkloadDispatcher(registry, compiler, energy_preference_weight=0.5)

    assignment = dispatcher.schedule_task(
        op_type=KernelOpType.GEMM,
        input_shapes=[[512, 512], [512, 512]],
        priority=7,
    )
    assert isinstance(assignment, WorkloadAssignment)
    assert assignment.status == "DISPATCHED"
    assert assignment.estimated_energy_joules > 0.0
    assert assignment.estimated_latency_us > 0.0

    # Verify spike propagation routes with high neuromorphic affinity
    spk_assignment = dispatcher.schedule_task(
        op_type=KernelOpType.SPIKE_PROPAGATION,
        input_shapes=[[100, 1], [100, 512]],
        priority=5,
    )
    assert spk_assignment.target_substrate == HardwareSubstrate.NEUROMORPHIC


def test_substrate_telemetry_profiler():
    registry = SubstrateRegistry()
    profiler = SubstrateTelemetryProfiler(registry)
    telemetry = profiler.collect_cluster_telemetry()

    assert telemetry["total_substrates"] >= 5
    assert telemetry["total_peak_tops"] > 1000.0
    assert telemetry["estimated_cluster_power_watts"] > 0.0
    assert "throttled_substrates" in telemetry
