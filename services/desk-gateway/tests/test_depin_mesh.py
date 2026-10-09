"""Unit tests for Quantum-Safe DePIN & Verifiable Resource Mesh (Phase 63)."""

import pytest

from desk_gateway.depin_mesh import (
    DePINAnchorExporter,
    DePINLedgerReceipt,
    DePINResourceLedger,
    PhysicalResourceNode,
    PhysicalResourceType,
    ProofOfPhysicalWork,
    ResourceLease,
    SwarmImmuneDePINDrillSimulator,
    VerifiableResourceOrchestrator,
)


def test_resource_orchestrator_initialization_and_node_registration():
    orchestrator = VerifiableResourceOrchestrator()
    assert len(orchestrator.nodes) >= 4

    custom_node = PhysicalResourceNode(
        node_id="depin-edge-custom-0",
        resource_type=PhysicalResourceType.EDGE_COMPUTE_POW,
        region="us-central",
        capacity_units=300.0,
        available_units=300.0,
        reputation_score=0.99,
    )
    orchestrator.register_node(custom_node)
    assert "depin-edge-custom-0" in orchestrator.nodes


def test_resource_leasing():
    orchestrator = VerifiableResourceOrchestrator()
    initial_avail = orchestrator.nodes["depin-us-east-gpu-0"].available_units

    lease = orchestrator.allocate_lease(
        consumer_seat="bot-01-systems-backend",
        resource_type=PhysicalResourceType.GPU_CLUSTER,
        required_units=150.0,
        duration_seconds=3600.0,
    )
    assert lease is not None
    assert lease.consumer_seat == "bot-01-systems-backend"
    assert lease.allocated_units == 150.0
    assert orchestrator.nodes["depin-us-east-gpu-0"].available_units == initial_avail - 150.0

    # Over-allocation fails
    huge_lease = orchestrator.allocate_lease(
        consumer_seat="bot-01-systems-backend",
        resource_type=PhysicalResourceType.GPU_CLUSTER,
        required_units=999999.0,
    )
    assert huge_lease is None


def test_proof_of_physical_work_attestation_and_verification():
    orchestrator = VerifiableResourceOrchestrator()
    popw = orchestrator.generate_proof_of_physical_work(
        node_id="depin-us-east-gpu-0",
        work_units=100.0,
        workload_payload="RESNET50_SYNTHETIC_FORWARD_PASS",
        elapsed_ms=42.5,
    )
    assert popw.proof_id.startswith("popw-")
    assert orchestrator.verify_popw(popw) is True

    # Tampered proof
    tampered = ProofOfPhysicalWork(
        proof_id=popw.proof_id,
        node_id=popw.node_id,
        resource_type=popw.resource_type,
        work_units_completed=999.0,  # tampered
        workload_digest=popw.workload_digest,
        elapsed_ms=popw.elapsed_ms,
        attestation_sig=popw.attestation_sig,
    )
    assert orchestrator.verify_popw(tampered) is False


def test_depin_resource_ledger_and_merkle_root():
    ledger = DePINResourceLedger()
    rcpt1 = ledger.append_event("LEASE_ALLOCATION", {"lease_id": "l-1", "units": 100})
    rcpt2 = ledger.append_event("POPW_VERIFIED", {"proof_id": "p-1", "units": 100})

    assert len(ledger.receipts) == 2
    root = ledger.compute_merkle_root()
    assert isinstance(root, str)
    assert len(root) == 64


def test_depin_solana_devnet_anchor_export():
    ledger = DePINResourceLedger()
    ledger.append_event("LEASE_ALLOCATION", {"lease_id": "l-1"})
    exporter = DePINAnchorExporter()
    anchor = exporter.export_commitment(ledger)

    assert anchor["status"] == "CONFIRMED_ON_SOLANA_DEVNET"
    assert anchor["leaf_count"] == 1
    assert "transaction_signature" in anchor


def test_swarm_immune_depin_drill_simulator():
    drill = SwarmImmuneDePINDrillSimulator.run_drill()
    assert drill["drill_status"] == "ALL_CHECKS_PASSED"
    assert drill["antibody_distribution_and_sync"]["status"] == "PASSED"
    assert drill["antifragility_and_genetic_evolution"]["status"] == "PASSED"
    assert drill["runtime_reconstitution"]["status"] == "PASSED"
    assert drill["depin_resource_leasing_and_popw"]["status"] == "PASSED"
    assert drill["depin_ledger_and_solana_anchor"]["status"] == "PASSED"
