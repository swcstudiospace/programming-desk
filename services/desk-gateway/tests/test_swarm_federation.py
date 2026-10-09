"""Unit tests for Phase 47: Self-Synthesizing Capability Federation & Autonomous Execution Verification."""

import pytest
from desk_gateway.swarm_orchestration import (
    CrossDeskWorkflowCompiler,
    WorkflowExecutionEngine,
    TaskPriority,
)
from desk_gateway.swarm_federation import (
    FederatedCapability,
    CapabilityFederationBroker,
    WorkflowReceiptLedger,
    WorkflowAnchorExporter,
    WorkflowFailureSynthesizer,
    SwarmOrchestrationDrillSimulator,
)


def test_capability_federation_broker():
    broker = CapabilityFederationBroker()

    c1 = FederatedCapability(
        capability_name="code_linter",
        desk_id="desk-alpha",
        seat_id="quality",
        schema_contract={},
        health_score=0.9,
        latency_ms=25.0,
    )
    c2 = FederatedCapability(
        capability_name="code_linter",
        desk_id="desk-beta",
        seat_id="quality",
        schema_contract={},
        health_score=0.99,
        latency_ms=10.0,
    )

    broker.register_capability(c1)
    broker.register_capability(c2)

    best = broker.discover("code_linter")
    assert best is not None
    assert best.desk_id == "desk-beta"
    assert len(broker.list_capabilities()) == 2


def test_workflow_receipt_ledger_and_anchor_export():
    compiler = CrossDeskWorkflowCompiler()
    dag = compiler.compile({
        "workflow_id": "receipt-test-wf",
        "name": "Receipt Test",
        "tasks": [{"task_id": "step1", "assigned_seat": "lead"}],
    })
    dag.tasks["step1"].output_data = {"verdict": "CLEAN"}

    ledger = WorkflowReceiptLedger(signing_secret="test-secret")
    receipt = ledger.record_execution(dag, duration_ms=12.5)

    assert receipt.workflow_id == "receipt-test-wf"
    assert receipt.task_count == 1
    assert "lead" in receipt.seat_signatures
    assert ledger.verify_receipt(receipt) is True

    exporter = WorkflowAnchorExporter()
    anchor = exporter.export_anchor(receipt)
    assert anchor["status"] == "CONFIRMED"
    assert "solana_devnet" in anchor["target"]


def test_workflow_failure_synthesizer_and_drill():
    compiler = CrossDeskWorkflowCompiler()
    dag = compiler.compile({
        "workflow_id": "failure-wf",
        "name": "Failure Recovery Test",
        "tasks": [
            {"task_id": "step_main", "assigned_seat": "lead"},
            {"task_id": "step_dep", "assigned_seat": "web", "dependencies": ["step_main"]},
        ],
    })

    # Synthesize fallback
    healed = WorkflowFailureSynthesizer.synthesize_fallback_dag(dag, "step_main")
    assert "step_main-fallback" in healed.tasks
    assert healed.tasks["step_dep"].dependencies == ["step_main-fallback"]

    # Drill simulator
    drill = SwarmOrchestrationDrillSimulator.run_swarm_orchestration_drill()
    assert drill["status"] == "PASS"
    for case_name, res in drill["test_cases"].items():
        assert res["passed"] is True, f"Failed case {case_name}"
