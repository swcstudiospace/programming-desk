"""Unit and integration tests for Blind Quantum Computing (BQC) & MBQC Cluster States (Phase 72)."""

import math
import pytest

from desk_gateway.quantum_bqc_mesh import (
    BlindAngleSpecification,
    BlindQuantumComputingEngine,
    BrickworkClusterState,
)


def test_blind_angle_specification_and_unblinding():
    raw_angle = math.pi / 3.0
    spec = BlindAngleSpecification.create("step-1", target_qubit=0, raw_angle=raw_angle)

    assert spec.blind_key_r in {0, 1}
    expected_theta = (raw_angle + spec.blind_key_r * math.pi) % (2.0 * math.pi)
    assert spec.blind_theta == pytest.approx(expected_theta, abs=1e-5)

    # Server outcome unblinding: s = s' ^ r
    for server_outcome in (0, 1):
        unblinded = spec.unblind_outcome(server_outcome)
        assert unblinded == server_outcome ^ spec.blind_key_r


def test_brickwork_cluster_state_graph():
    cluster = BrickworkClusterState(layers=3, qubits_per_layer=4)
    info = cluster.to_dict()

    assert info["layers"] == 3
    assert info["qubits_per_layer"] == 4
    assert info["total_nodes"] == 12

    # Check horizontal connectivity (across adjacent layers)
    assert 4 in info["adjacency"][0]
    assert 0 in info["adjacency"][4]

    # Check vertical brickwork connectivity
    assert 1 in info["adjacency"][0]
    assert 0 in info["adjacency"][1]


def test_bqc_delegated_session_execution():
    engine = BlindQuantumComputingEngine()
    session_info = engine.init_bqc_session("desk-alpha", "untrusted-server", layers=2, qubits_per_layer=3)
    session_id = session_info["session_id"]

    assert session_id.startswith("bqc-")
    assert session_info["cluster_info"]["total_nodes"] == 6

    step_res = engine.execute_blind_measurement_step(
        session_id=session_id,
        target_qubit=0,
        target_angle_rad=math.pi / 4.0,
    )

    assert step_res["target_qubit"] == 0
    assert "server_received_theta" in step_res
    assert step_res["server_outcome"] in (0, 1)
    assert step_res["client_unblinded_outcome"] in (0, 1)
    assert step_res["blind_key_r_used"] in (0, 1)
