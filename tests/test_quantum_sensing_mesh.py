"""Unit and integration tests for Distributed Quantum Sensing & Clock Sync (Phase 78)."""

import math
import pytest

from desk_gateway.quantum_sensing_mesh import (
    NOONStateMetrologyResult,
    QuantumClockSyncResult,
    QuantumClockSynchronizer,
    QuantumMetrologyEstimator,
    QuantumSensorTelemetry,
    SensorType,
)


def test_noon_state_metrology_advantage():
    res = QuantumMetrologyEstimator.estimate_phase_with_noon(true_phase_rad=1.0, n_photons=16)

    assert res.n_photons == 16
    assert res.heisenberg_limit == 1.0 / 16.0
    assert res.standard_quantum_limit == 1.0 / 4.0
    assert res.heisenberg_limit < res.standard_quantum_limit
    assert res.entanglement_advantage_factor > 1.5
    assert abs(res.estimated_phase - 1.0) < 0.5


def test_quantum_clock_synchronization():
    sync = QuantumClockSynchronizer(base_fidelity=0.99)
    res = sync.synchronize_clocks("desk-alpha", "desk-beta", initial_skew_ps=150.0)

    assert res.session_id.startswith("qsync-")
    assert res.node_a == "desk-alpha"
    assert res.node_b == "desk-beta"
    assert res.sync_status == "SYNCHRONIZED_SUB_PICOSECOND"
    assert abs(res.calibrated_offset_ps - 150.0) < 0.1
    assert res.entangled_fidelity == 0.99
