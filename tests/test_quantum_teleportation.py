"""Unit and integration tests for Inter-Cluster Quantum Teleportation (Phase 68)."""

import math
import pytest

from desk_gateway.quantum_teleportation import (
    BellPairPool,
    BellStateType,
    EntangledBellPair,
    EntanglementPurifier,
    EntanglementSwapper,
    QuantumRepeaterMesh,
    QuantumTeleportationProtocol,
)


def test_bell_pair_pool_lifecycle():
    pool = BellPairPool()
    pair = pool.create_pair("desk-alpha", "desk-beta", BellStateType.PHI_PLUS, initial_fidelity=0.98)
    assert pair.pair_id.startswith("bell-")
    assert pair.fidelity == 0.98
    assert not pair.consumed

    active = pool.list_active_pairs("desk-alpha", "desk-beta")
    assert len(active) == 1
    assert active[0].pair_id == pair.pair_id

    ok = pool.consume_pair(pair.pair_id)
    assert ok is True
    assert pair.consumed is True

    # Cannot consume twice
    ok_second = pool.consume_pair(pair.pair_id)
    assert ok_second is False
    assert len(pool.list_active_pairs("desk-alpha", "desk-beta")) == 0


def test_entanglement_purification_distillation():
    pair1 = EntangledBellPair("p1", BellStateType.PHI_PLUS, "desk-alpha", "desk-beta", fidelity=0.90)
    pair2 = EntangledBellPair("p2", BellStateType.PHI_PLUS, "desk-alpha", "desk-beta", fidelity=0.92)

    ok, purified, p_succ = EntanglementPurifier.purify(pair1, pair2)
    assert ok is True
    assert purified is not None
    assert p_succ > 0.0
    # Distillation should improve fidelity beyond the inputs
    assert purified.fidelity > 0.92
    assert pair1.consumed is True
    assert pair2.consumed is True


def test_entanglement_swapper():
    pair_ab = EntangledBellPair("p-ab", BellStateType.PHI_PLUS, "desk-alpha", "repeater-1", fidelity=0.98)
    pair_bc = EntangledBellPair("p-bc", BellStateType.PHI_PLUS, "repeater-1", "desk-gamma", fidelity=0.98)

    ok, swapped = EntanglementSwapper.swap_entanglement(pair_ab, pair_bc, bsm_error_rate=0.01)
    assert ok is True
    assert swapped is not None
    assert swapped.node_a == "desk-alpha"
    assert swapped.node_b == "desk-gamma"
    assert swapped.fidelity > 0.90
    assert pair_ab.consumed is True
    assert pair_bc.consumed is True


def test_multi_hop_repeater_mesh():
    pool = BellPairPool()
    mesh = QuantumRepeaterMesh(pool)
    mesh.register_node("node-0", "us-east")
    mesh.register_node("rep-1", "mid-atlantic")
    mesh.register_node("rep-2", "eu-west")
    mesh.register_node("node-3", "eu-central")

    route = ["node-0", "rep-1", "rep-2", "node-3"]
    ok, swapped, logs = mesh.establish_multi_hop_entanglement(route, base_fidelity=0.99, purify_hops=True)
    assert ok is True
    assert swapped is not None
    assert swapped.node_a == "node-0"
    assert swapped.node_b == "node-3"
    assert swapped.fidelity > 0.85
    assert len(logs) >= 3


def test_quantum_teleportation_protocol():
    pool = BellPairPool()
    mesh = QuantumRepeaterMesh(pool)
    proto = QuantumTeleportationProtocol(mesh)

    # Teleport state: (|0> + |1>) / sqrt(2)
    res = proto.teleport_qubit(
        source_node="alice",
        target_node="bob",
        alpha=complex(1.0, 0.0),
        beta=complex(1.0, 0.0),
    )
    assert res.success is True
    assert res.fidelity >= 0.95
    assert res.bell_measurement in [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert res.pauli_correction in ["I", "X", "Z", "XZ"]

    d = res.to_dict()
    assert d["session_id"].startswith("teleport-")
    assert d["source_node"] == "alice"
    assert d["target_node"] == "bob"
