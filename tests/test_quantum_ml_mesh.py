"""Unit and integration tests for Quantum Machine Learning & Parameterized Circuits (Phase 80)."""

import math
import pytest

from desk_gateway.quantum_ml_mesh import (
    ParameterizedQuantumCircuit,
    ParameterShiftOptimizer,
    QuantumNeuralNetworkClassifier,
)


def test_parameterized_quantum_circuit_forward():
    circuit = ParameterizedQuantumCircuit(n_qubits=2)
    features = [0.5, -0.2]
    weights = [0.3, 0.7, -0.4]

    z_exp = circuit.forward(features, weights)
    assert -1.0 <= z_exp <= 1.0


def test_parameter_shift_gradient_computation():
    circuit = ParameterizedQuantumCircuit(n_qubits=2)
    features = [0.4, 0.2]
    weights = [0.1, -0.5, 0.6]
    target_label = 1.0

    grads, loss = ParameterShiftOptimizer.compute_gradient(circuit, features, weights, target_label)
    assert len(grads) == 3
    assert loss >= 0.0
    # Gradients should be non-zero for non-stationary points
    assert any(abs(g) > 1e-4 for g in grads)


def test_quantum_neural_network_training_step():
    qnn = QuantumNeuralNetworkClassifier(initial_weights=[0.5, 0.5, 0.5])
    features = [0.6, -0.3]
    target = 1.0

    initial_pred = qnn.predict(features)
    initial_loss = (initial_pred - target) ** 2

    # Perform 3 training steps
    for _ in range(3):
        epoch = qnn.train_step(features, target, learning_rate=0.2)
        assert epoch.loss >= 0.0
        assert epoch.gradient_norm >= 0.0

    final_pred = qnn.predict(features)
    final_loss = (final_pred - target) ** 2
    assert final_loss < initial_loss
