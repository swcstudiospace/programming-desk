"""Unit and integration tests for Quantum Internet Protocol Stack & Entanglement Routing (Phase 74)."""

import pytest

from desk_gateway.quantum_internet_mesh import (
    EntanglementRoutingEngine,
    QuantumConnectionManager,
    QuantumNetworkLink,
    QuantumPacket,
    QuantumProtocolLayer,
)


def test_quantum_network_link_cost():
    link = QuantumNetworkLink(
        link_id="link-1",
        node_u="desk-alpha",
        node_v="desk-beta",
        raw_fidelity=0.98,
        latency_ms=2.0,
    )
    assert link.cost > 0.0
    assert link.to_dict()["raw_fidelity"] == 0.98


def test_dijkstra_entanglement_routing():
    engine = EntanglementRoutingEngine()
    engine.add_link("desk-alpha", "hop-1", raw_fidelity=0.98, latency_ms=1.0)
    engine.add_link("hop-1", "hop-2", raw_fidelity=0.97, latency_ms=1.5)
    engine.add_link("hop-2", "desk-beta", raw_fidelity=0.98, latency_ms=1.0)
    # High-latency low-fidelity shortcut
    engine.add_link("desk-alpha", "desk-beta", raw_fidelity=0.80, latency_ms=50.0)

    path, est_fid, latency = engine.compute_shortest_entanglement_path("desk-alpha", "desk-beta")
    assert path == ["desk-alpha", "hop-1", "hop-2", "desk-beta"]
    assert est_fid > 0.85
    assert latency == 3.5


def test_quantum_packet_dispatch():
    engine = EntanglementRoutingEngine()
    engine.add_link("desk-alpha", "desk-beta", raw_fidelity=0.99, latency_ms=1.0)
    conn_mgr = QuantumConnectionManager(engine)

    pkt = conn_mgr.route_quantum_packet("desk-alpha", "desk-beta", target_fidelity=0.95)
    assert pkt.delivered is True
    assert pkt.route_path == ["desk-alpha", "desk-beta"]
    assert pkt.achieved_fidelity >= 0.95
