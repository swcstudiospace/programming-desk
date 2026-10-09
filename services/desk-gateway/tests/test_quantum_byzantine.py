"""Test suite for Quantum Network Byzantine Agreement & SAGIN Quorum Routing (Milestone v7.1)."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.quantum_byzantine_mesh import (
    ByzantineConsensusResult,
    ConsensusStatus,
    NodeType,
    QuantumByzantineCoordinator,
    QuantumPseudoSignatureEngine,
    SAGINNode,
    SAGINTopologyRouter,
)
from desk_gateway.quantum_byzantine_anchoring import (
    QuantumByzantineMerkleLedger,
    QuantumByzantineReceipt,
    QuantumByzantineSolanaAnchorExporter,
    QuantumByzantineVerificationDrill,
)
from desk_gateway.server import build_app


def test_sagin_topology_routing() -> None:
    router = SAGINTopologyRouter()
    assert len(router.nodes) == 4
    assert len(router.links) == 12  # 6 bidirectional pairs

    path, fidelity, latency = router.compute_shortest_quantum_path("ground-01", "ground-02")
    assert len(path) >= 2
    assert path[0] == "ground-01"
    assert path[-1] == "ground-02"
    assert 0.0 < fidelity <= 1.0
    assert latency > 0.0

    # Self path
    self_path, self_fid, self_lat = router.compute_shortest_quantum_path("ground-01", "ground-01")
    assert self_path == ["ground-01"]
    assert self_fid == 1.0
    assert self_lat == 0.0


def test_quantum_pseudo_signatures() -> None:
    engine = QuantumPseudoSignatureEngine(key_length=32)
    keys = engine.generate_shared_entangled_pairs(num_nodes=3)
    assert "node-00" in keys
    assert "node-01" in keys

    # Direct signature from node-00 to node-01
    sig = engine.sign_proposal("node-00", 1, keys["node-00"]["node-01"])
    assert sig.signer_id == "node-00"
    assert sig.measurement_basis == "Z"
    assert len(sig.outcomes) == 32

    # Verify matching key
    assert engine.verify_pseudo_signature(sig, keys["node-01"]["node-00"], error_threshold=0.15)

    # Tampered key should fail verification
    inverted_key = [1 - b for b in keys["node-01"]["node-00"]]
    assert not engine.verify_pseudo_signature(sig, inverted_key, error_threshold=0.15)


def test_honest_byzantine_consensus() -> None:
    coord = QuantumByzantineCoordinator()
    nodes = ["ground-01", "ground-02", "haps-01", "leo-sat-01"]
    res = coord.run_consensus_round(
        round_id="test-round-1",
        node_ids=nodes,
        leader_id="ground-01",
        leader_proposed_value=1,
        byzantine_node_ids=[],
        inject_split_state_cheat=False,
    )
    assert res.status == ConsensusStatus.AGREED
    assert res.agreed_value == 1
    assert res.quorum_size == 4
    assert len(res.byzantine_nodes_detected) == 0
    assert res.quorum_fidelity > 0.80
    assert res.routing_hops >= 1


def test_malicious_split_state_cheat_detection() -> None:
    coord = QuantumByzantineCoordinator()
    nodes = ["ground-01", "ground-02", "haps-01", "leo-sat-01"]
    res = coord.run_consensus_round(
        round_id="test-round-cheat",
        node_ids=nodes,
        leader_id="ground-01",
        leader_proposed_value=1,
        byzantine_node_ids=["ground-01"],
        inject_split_state_cheat=True,
    )
    assert res.status == ConsensusStatus.CHEAT_DETECTED
    assert "ground-01" in res.byzantine_nodes_detected
    assert res.agreed_value is None


def test_quantum_byzantine_merkle_ledger() -> None:
    ledger = QuantumByzantineMerkleLedger()
    rcpt1 = QuantumByzantineReceipt(
        receipt_id="r1",
        round_id="rnd-1",
        status="AGREED",
        total_nodes=4,
        quorum_size=4,
        agreed_value=1,
        byzantine_count=0,
        quorum_fidelity=0.95,
        routing_hops=2,
        fault_bound_satisfied=True,
    )
    rcpt2 = QuantumByzantineReceipt(
        receipt_id="r2",
        round_id="rnd-2",
        status="CHEAT_DETECTED",
        total_nodes=4,
        quorum_size=3,
        agreed_value=None,
        byzantine_count=1,
        quorum_fidelity=0.91,
        routing_hops=2,
        fault_bound_satisfied=True,
    )
    ledger.append_receipt(rcpt1)
    ledger.append_receipt(rcpt2)

    root = ledger.get_merkle_root()
    assert len(root) == 64

    proof0 = ledger.get_proof(0)
    assert QuantumByzantineMerkleLedger.verify_proof(rcpt1.compute_hash(), proof0, root)

    proof1 = ledger.get_proof(1)
    assert QuantumByzantineMerkleLedger.verify_proof(rcpt2.compute_hash(), proof1, root)


def test_solana_anchor_exporter() -> None:
    ledger = QuantumByzantineMerkleLedger()
    rcpt = QuantumByzantineReceipt(
        receipt_id="r-anchor",
        round_id="rnd-anchor",
        status="AGREED",
        total_nodes=4,
        quorum_size=4,
        agreed_value=1,
        byzantine_count=0,
        quorum_fidelity=0.95,
        routing_hops=2,
        fault_bound_satisfied=True,
    )
    ledger.append_receipt(rcpt)
    root = ledger.get_merkle_root()
    proof = ledger.get_proof(0)

    payload = QuantumByzantineSolanaAnchorExporter.generate_instruction_payload(
        merkle_root=root,
        receipt=rcpt,
        proof=proof,
    )
    assert payload["program_id"] == QuantumByzantineSolanaAnchorExporter.PROGRAM_ID
    assert payload["instruction"] == "record_byzantine_consensus_receipt"
    assert payload["parameters"]["round_id"] == "rnd-anchor"
    assert payload["parameters"]["agreed_value"] == 1

    prog = QuantumByzantineSolanaAnchorExporter.generate_anchor_program()
    assert "pub mod quantum_byzantine_consensus" in prog
    assert "FaultToleranceBoundExceeded" in prog


def test_verification_drill() -> None:
    drill = QuantumByzantineVerificationDrill()
    result = drill.run_all_stages()
    assert result["all_passed"] is True
    assert result["stages"]["stage1_sagin_routing"]["passed"] is True
    assert result["stages"]["stage2_pseudo_signature"]["passed"] is True
    assert result["stages"]["stage3_honest_consensus"]["passed"] is True
    assert result["stages"]["stage4_cheat_detection"]["passed"] is True
    assert result["stages"]["stage5_anchor_merkle"]["passed"] is True


def test_server_routes_quantum_byzantine() -> None:
    app, _ = build_app()
    client = TestClient(app)

    # 1. Route find
    resp = client.post("/v1/quantum/byzantine/route", json={"source": "ground-01", "target": "ground-02"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["path"]) >= 2
    assert data["fidelity"] > 0.0

    # 2. Consensus run (honest)
    resp = client.post("/v1/quantum/byzantine/consensus/run", json={
        "round_id": "test-api-round-1",
        "nodes": ["ground-01", "ground-02", "haps-01", "leo-sat-01"],
        "leader": "ground-01",
        "proposal": 1,
        "inject_split_state_cheat": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["consensus"]["status"] == "AGREED"
    assert data["receipt"]["agreed_value"] == 1
    assert len(data["merkle_root"]) == 64

    # 3. Consensus run (cheat detection)
    resp = client.post("/v1/quantum/byzantine/consensus/run", json={
        "round_id": "test-api-round-cheat",
        "nodes": ["ground-01", "ground-02", "haps-01", "leo-sat-01"],
        "leader": "ground-01",
        "proposal": 1,
        "byzantine_nodes": ["ground-01"],
        "inject_split_state_cheat": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["consensus"]["status"] == "CHEAT_DETECTED"
    assert "ground-01" in data["consensus"]["byzantine_nodes_detected"]

    # 4. Anchor export
    resp = client.post("/v1/quantum/byzantine/anchor/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "program" in data
    assert data["anchor"]["instruction"] == "record_byzantine_consensus_receipt"

    # 5. Drill simulate
    resp = client.post("/v1/quantum/byzantine/drill/simulate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["drill"]["all_passed"] is True
