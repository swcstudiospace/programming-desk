"""Unit tests for Quantum-Classical Hybrid Mesh & VQE/QAOA Swarm Co-Processing (Milestone v5.0 - Phase 66)."""

import math
import pytest

from desk_gateway.quantum_hybrid_mesh import (
    AnsatzCircuit,
    HamiltonianOperator,
    HamiltonianTerm,
    NoiseModel,
    QAOAOptimizer,
    QuantumCircuitState,
    QuantumDecoherenceSimulator,
    QuantumGate,
    QuantumGateType,
    QuantumWorkloadScheduler,
    VQEProcessor,
)


def test_quantum_circuit_state_initialization():
    circuit = QuantumCircuitState(num_qubits=2)
    assert circuit.num_qubits == 2
    assert circuit.dim == 4
    assert circuit.state[0] == 1.0 + 0.0j
    assert circuit.state[1] == 0.0 + 0.0j
    probs = circuit.get_probabilities()
    assert probs[0] == 1.0
    assert sum(probs) == pytest.approx(1.0)


def test_bell_state_generation():
    circuit = QuantumCircuitState(num_qubits=2)
    # H on qubit 0
    circuit.apply_gate(QuantumGate(QuantumGateType.H, [0]))
    # CNOT with control=0, target=1
    circuit.apply_gate(QuantumGate(QuantumGateType.CNOT, [0, 1]))

    probs = circuit.get_probabilities()
    assert len(probs) == 4
    # Bell state |Phi+> = 1/sqrt(2) (|00> + |11>)
    assert probs[0] == pytest.approx(0.5)
    assert probs[1] == pytest.approx(0.0)
    assert probs[2] == pytest.approx(0.0)
    assert probs[3] == pytest.approx(0.5)


def test_single_qubit_rotations():
    circuit = QuantumCircuitState(num_qubits=1)
    # Ry(pi) flips |0> to |1>
    circuit.apply_gate(QuantumGate(QuantumGateType.RY, [0], parameters=[math.pi]))
    probs = circuit.get_probabilities()
    assert probs[0] == pytest.approx(0.0, abs=1e-5)
    assert probs[1] == pytest.approx(1.0, abs=1e-5)

    # Rz rotation on |0> adds phase but keeps probabilities identical
    circuit.reset()
    circuit.apply_gate(QuantumGate(QuantumGateType.RZ, [0], parameters=[math.pi / 2.0]))
    probs_z = circuit.get_probabilities()
    assert probs_z[0] == pytest.approx(1.0)


def test_hamiltonian_and_vqe_optimization():
    # Construct transverse-field Ising term: H = -1.0 * Z0 Z1 - 0.5 * X0
    h = HamiltonianOperator()
    h.add_term(-1.0, "Z Z")
    h.add_term(-0.5, "X I")

    ansatz = AnsatzCircuit(num_qubits=2, num_layers=1)
    vqe = VQEProcessor(h, ansatz)
    res = vqe.optimize(max_iterations=20, learning_rate=0.1)

    assert res["converged"] is True
    assert res["ground_state_energy"] < -1.0
    assert len(res["optimal_parameters"]) == ansatz.num_parameters


def test_qaoa_graph_partition():
    # 3-qubit line graph 0 - 1 - 2
    qaoa = QAOAOptimizer(num_qubits=3, p_steps=1)
    weights = {(0, 1): 1.0, (1, 2): 1.0}
    res = qaoa.solve_partition(weights, gammas=[0.4], betas=[0.5])

    assert len(res["optimal_bitstring"]) == 3
    assert res["optimal_probability"] > 0.0
    assert res["state_digest"] is not None


def test_decoherence_simulator():
    circuit = QuantumCircuitState(num_qubits=2)
    circuit.apply_gate(QuantumGate(QuantumGateType.H, [0]))
    circuit.apply_gate(QuantumGate(QuantumGateType.H, [1]))

    simulator = QuantumDecoherenceSimulator(depolarizing_rate=0.05, damping_rate=0.02)
    loss = simulator.apply_channel_noise(circuit, NoiseModel.DEPOLARIZING)
    assert loss == 0.05

    loss_amp = simulator.apply_channel_noise(circuit, NoiseModel.AMPLITUDE_DAMPING)
    assert loss_amp > 0.0


def test_quantum_workload_scheduler():
    scheduler = QuantumWorkloadScheduler()
    task = scheduler.dispatch_quantum_task(
        task_name="benchmark-vqe",
        circuit_type="ansatz-hea",
        num_qubits=2,
        params={"layers": 1},
    )
    assert task["task_id"].startswith("qtask-")
    assert task["status"] == "COMPLETED"
    assert len(scheduler.completed_tasks) == 1
