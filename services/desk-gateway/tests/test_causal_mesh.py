"""Unit tests for Causal DAG Discovery, Do-Calculus Interventions & Counterfactual Mesh (Phase 57)."""

import pytest

from desk_gateway.causal_mesh import (
    CausalAnchorExporter,
    CausalDAG,
    CausalEdge,
    CausalProofReceipt,
    CausalVariable,
    ConstraintCausalDiscovery,
    CounterfactualSimulator,
    DoCalculusEngine,
    NeuroSymbolicCausalDrillSimulator,
)


def test_causal_dag_topological_and_cycle_rejection():
    dag = CausalDAG(dag_id="test-dag")
    dag.add_variable(CausalVariable(name="A"))
    dag.add_variable(CausalVariable(name="B"))
    dag.add_variable(CausalVariable(name="C"))

    dag.add_edge(CausalEdge(source="A", target="B", weight=1.0))
    dag.add_edge(CausalEdge(source="B", target="C", weight=2.0))

    order = dag.topological_sort()
    assert order == ["A", "B", "C"]
    assert dag.is_acyclic() is True

    # Cycle attempt should raise ValueError
    with pytest.raises(ValueError, match="directed cycle"):
        dag.add_edge(CausalEdge(source="C", target="A", weight=1.0))


def test_causal_dag_d_separation():
    # Chain: X -> Z -> Y (Z blocks path between X and Y)
    dag = CausalDAG(dag_id="chain-dag")
    dag.add_variable(CausalVariable(name="X"))
    dag.add_variable(CausalVariable(name="Z"))
    dag.add_variable(CausalVariable(name="Y"))

    dag.add_edge(CausalEdge(source="X", target="Z"))
    dag.add_edge(CausalEdge(source="Z", target="Y"))

    assert dag.is_d_separated("X", "Y", conditioning_set=set()) is False
    assert dag.is_d_separated("X", "Y", conditioning_set={"Z"}) is True


def test_constraint_causal_discovery():
    discovery = ConstraintCausalDiscovery()
    # Synthetic samples where A causes B with positive correlation
    samples = [
        {"A": 1.0, "B": 2.1, "C": 0.0},
        {"A": 2.0, "B": 4.0, "C": 0.1},
        {"A": 3.0, "B": 6.2, "C": -0.1},
        {"A": 4.0, "B": 7.9, "C": 0.05},
    ]
    dag = discovery.discover_skeleton_and_dag("discovered-test", ["A", "B", "C"], samples)
    assert dag.is_acyclic() is True
    # Edge between A and B should be formed due to strong correlation
    edge_pairs = [(e.source, e.target) for e in dag.edges]
    assert ("A", "B") in edge_pairs or ("B", "A") in edge_pairs


def test_do_calculus_intervention():
    dag = CausalDAG(dag_id="service-perf")
    dag.add_variable(CausalVariable(name="Concurrency", base_mean=10.0))
    dag.add_variable(CausalVariable(name="Latency", base_mean=5.0))
    dag.add_variable(CausalVariable(name="DropRate", base_mean=0.0))

    dag.add_edge(CausalEdge(source="Concurrency", target="Latency", weight=0.5))
    dag.add_edge(CausalEdge(source="Latency", target="DropRate", weight=0.01))

    engine = DoCalculusEngine(dag)
    res = engine.simulate_intervention(
        treatment="Latency",
        intervention_value=20.0,
        outcome="DropRate",
    )
    # Expected DropRate: 0.0 + 0.01 * 20.0 = 0.2
    assert abs(res["expected_outcome"] - 0.2) < 1e-4
    assert res["graph_mutilated"] is True


def test_counterfactual_reasoning():
    dag = CausalDAG(dag_id="cf-dag")
    dag.add_variable(CausalVariable(name="X", base_mean=0.0))
    dag.add_variable(CausalVariable(name="Y", base_mean=0.0))
    dag.add_edge(CausalEdge(source="X", target="Y", weight=2.0))

    sim = CounterfactualSimulator(dag)
    # Factual: observed X=3.0, Y=7.0 (so exogenous noise U_Y = 7.0 - 2.0*3.0 = 1.0)
    # Counterfactual: What if X was 5.0 instead?
    # Prediction: Y = 2.0 * 5.0 + 1.0 = 11.0
    res = sim.evaluate_counterfactual(
        factual_evidence={"X": 3.0, "Y": 7.0},
        counterfactual_intervention={"X": 5.0},
        target_variable="Y",
    )
    assert abs(res["counterfactual_prediction"] - 11.0) < 1e-4
    assert abs(res["inferred_noise"]["Y"] - 1.0) < 1e-4


def test_causal_anchor_exporter():
    exporter = CausalAnchorExporter()
    receipt = exporter.create_receipt("dag-01", "INTERVENTION", {"expected": 42.0})
    assert receipt.receipt_id.startswith("cpr-")

    commitment = exporter.export_causal_commitment([receipt])
    assert commitment["status"] == "CONFIRMED_ON_CHAIN"
    assert commitment["merkle_root"] is not None
    assert commitment["receipts_count"] == 1


def test_neuro_symbolic_causal_drill_simulator():
    drill = NeuroSymbolicCausalDrillSimulator.run_drill()
    assert drill["drill_status"] == "SUCCESS"
    assert drill["invariant_violation_caught"] is True
    assert drill["d_separation_verified"] is True
    assert drill["solana_commitment_root"] is not None
