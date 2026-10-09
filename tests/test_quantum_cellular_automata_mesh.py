"""Unit and integration tests for Quantum Cellular Automata & Quantum Walk (Phase 86)."""

import math
import pytest

from desk_gateway.quantum_cellular_automata_mesh import (
    CoinType,
    QuantumCellularAutomaton,
    QuantumWalkEngine,
    QuantumWalkState,
)


def test_quantum_walk_engine_evolution():
    qw = QuantumWalkEngine(lattice_size=31, coin_type=CoinType.HADAMARD)
    assert qw.current_step == 0

    state1 = qw.step()
    assert state1.step == 1
    assert state1.variance > 0.0

    # Run for 5 more steps
    for _ in range(5):
        st = qw.step()

    assert st.step == 6
    # Discrete-time quantum walk spreads ballistically (variance ~ t^2), speedup ratio > 1.0
    assert st.quantum_speedup_ratio > 1.0


def test_quantum_cellular_automaton_margolus_unitarity():
    qca = QuantumCellularAutomaton(n_cells=16, coupling_theta=math.pi / 4.0)
    assert qca.step_count == 0

    res1 = qca.step()
    assert res1["step"] == 1
    assert len(res1["excitations"]) == 16
    assert abs(res1["total_excitation"] - 1.0) < 1e-4

    res2 = qca.step()
    assert res2["step"] == 2
    # Unitarity check: total probability/excitation preserved to 1.0
    assert abs(res2["total_excitation"] - 1.0) < 1e-4
