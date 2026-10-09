# Requirements: Milestone v4.7 — Autonomous Multi-Substrate Hardware Acceleration & Neuromorphic Compute Mesh

This document defines the requirements for Milestone v4.7 of Programming Desk.

## 1. Multi-Substrate Hardware Acceleration Engine & Kernel Compilation (Phase 60)

- [x] **REQ-HW-001**: Substrate Architecture Registry (`HardwareSubstrate`, `SubstrateProfile`, `SubstrateRegistry`) modeling heterogeneous compute backends: CPU (x86_64/ARM NEON), GPU (CUDA/Triton), TPU (XLA/VPU), NPU (Neural Processing Unit), and Photonic/Neuromorphic Co-processors, tracking memory topology, TOPS/W efficiency, latency profiles, and concurrency bounds.
- [x] **REQ-HW-002**: Multi-Substrate Kernel Compiler (`SubstrateKernelCompiler`, `CompiledKernel`, `CompilationTarget`) compiling high-level mathematical compute graphs and tensor kernels into target-specific intermediate representations (IR) and execution binaries with optimization passes (operator fusion, loop tiling, vectorization).
- [x] **REQ-HW-003**: Dynamic Substrate Workload Dispatcher (`SubstrateWorkloadDispatcher`, `WorkloadAssignment`) routing compute tasks (dense GEMM, sparse graph traversal, spike event streams, memory-bound activations) to optimal hardware substrates based on power, throughput, and thermal constraints.
- [x] **REQ-HW-004**: Substrate Thermal & Energy Telemetry Profiler (`SubstrateTelemetryProfiler`) continuously monitoring thermal throttling, watt-hour power consumption, compute saturation, and dynamic power fencing.
- [x] **REQ-HW-005**: Hardware Substrate REST API endpoints under `/v1/hardware/*` exposing substrate inventory, kernel compilation, workload dispatch, and energy profiling.

## 2. Neuromorphic Spiking Neural Mesh & Event-Driven Synaptic Attestation (Phase 61)

- [x] **REQ-HW-006**: Neuromorphic Spiking Mesh Simulator (`NeuromorphicMesh`, `SpikingNeuron`, `SynapticConnection`) implementing Leaky Integrate-and-Fire (LIF) / Izhikevich neuron dynamics, membrane potential decay, threshold event firing, and Spike-Timing-Dependent Plasticity (STDP) synaptic weight adaptation.
- [x] **REQ-HW-007**: Event-Driven Asynchronous Spike Router (`EventSpikeRouter`, `SpikeEvent`) routing sparse discrete spike events across simulated neuromorphic crossbars with microsecond temporal resolution and zero quiescent power overhead.
- [x] **REQ-HW-008**: Cryptographic Synaptic State & Spike Attestation Ledger (`SynapticAttestationLedger`, `SynapticProofReceipt`) recording immutable weight state transitions, firing rate distributions, and spike train digest hashes using HMAC-SHA256 signatures.
- [x] **REQ-HW-009**: External Neuromorphic Commitment & Solana Devnet Exporter (`NeuromorphicAnchorExporter`) publishing Merkle roots of synaptic state transitions and spike attestation receipts to Solana devnet targets.
- [x] **REQ-HW-010**: End-to-End Multi-Substrate & Neuromorphic Compute Verification Drill Simulator (`HardwareNeuromorphicDrillSimulator`) verifying substrate kernel compilation, energy-aware workload routing, LIF spike propagation, STDP weight adaptation, and Solana devnet anchoring.
- [x] **REQ-HW-011**: Neuromorphic REST API endpoints under `/v1/neuromorphic/*` and `/v1/hardware/drill/simulate` exposing spike event ingestion, mesh step simulation, synaptic ledger receipts, and drill executions.
