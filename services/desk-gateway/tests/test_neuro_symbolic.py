"""Unit tests for Neuro-Symbolic Logic Graph & First-Order Predicate Synthesis (Phase 56)."""

import pytest

from desk_gateway.neuro_symbolic import (
    ConceptNode,
    FirstOrderLogicEngine,
    LogicalInvariantChecker,
    NeuroSymbolicGraph,
    Predicate,
    RelationEdge,
    RuleExtractionEngine,
    SymbolicRule,
)


def test_predicate_grounding_and_unification():
    p1 = Predicate(name="parent", args=("?x", "Bob"))
    p2 = Predicate(name="parent", args=("Alice", "Bob"))
    bindings = p1.unify(p2, {})
    assert bindings is not None
    assert bindings["?x"] == "Alice"

    # Incompatible predicate name or arity
    p3 = Predicate(name="sibling", args=("Alice", "Bob"))
    assert p1.unify(p3, {}) is None


def test_first_order_logic_forward_chaining():
    engine = FirstOrderLogicEngine()

    # Facts: parent(Alice, Bob), parent(Bob, Charlie)
    engine.add_fact(Predicate(name="parent", args=("Alice", "Bob")))
    engine.add_fact(Predicate(name="parent", args=("Bob", "Charlie")))

    # Rule: parent(?x, ?y) AND parent(?y, ?z) -> grandparent(?x, ?z)
    rule = SymbolicRule(
        rule_id="r_gp",
        antecedents=[
            Predicate(name="parent", args=("?x", "?y")),
            Predicate(name="parent", args=("?y", "?z")),
        ],
        consequent=Predicate(name="grandparent", args=("?x", "?z")),
    )
    engine.add_rule(rule)

    inferred = engine.evaluate_forward_chaining()
    assert len(inferred) == 1
    assert inferred[0].name == "grandparent"
    assert inferred[0].args == ("Alice", "Charlie")

    # Query
    q = Predicate(name="grandparent", args=("Alice", "?who"))
    results = engine.query(q)
    assert len(results) == 1
    assert results[0]["?who"] == "Charlie"


def test_neuro_symbolic_knowledge_graph():
    graph = NeuroSymbolicGraph(embedding_dimension=3)

    c1 = graph.add_concept("node-agent-1", "LeadAgent", "agent", embedding=[1.0, 0.0, 0.0])
    c2 = graph.add_concept("node-tool-1", "DeployTool", "tool", embedding=[0.9, 0.1, 0.0])
    c3 = graph.add_concept("node-db-1", "MainDB", "database", embedding=[0.0, 1.0, 0.0])

    assert c1.node_id == "node-agent-1"
    assert "node-tool-1" in graph.nodes

    # Query similarity
    matches = graph.query_similarity([1.0, 0.05, 0.0], top_k=2)
    assert len(matches) == 2
    # LeadAgent and DeployTool should be top matches
    top_ids = [m[0].node_id for m in matches]
    assert "node-agent-1" in top_ids
    assert "node-tool-1" in top_ids


def test_logical_invariant_checker():
    engine = FirstOrderLogicEngine()
    checker = LogicalInvariantChecker(engine)

    # Invariant: Any seat with privilege("guest") executing delete_database() is a violation
    checker.register_safety_invariant(
        name="NO_GUEST_DELETION",
        forbidden_predicate=Predicate(name="delete_operation", args=("?seat", "production")),
        description="Guest seat cannot delete production resources",
    )

    # Safe facts
    safe_violations = checker.check_invariants(
        candidate_action="read_stats",
        candidate_facts=[Predicate(name="read_operation", args=("seat_guest", "stats"))],
    )
    assert len(safe_violations) == 0

    # Unsafe facts violating invariant
    violations = checker.check_invariants(
        candidate_action="delete_all",
        candidate_facts=[Predicate(name="delete_operation", args=("seat_guest", "production"))],
    )
    assert len(violations) == 1
    assert violations[0].invariant_name == "NO_GUEST_DELETION"
    assert violations[0].violating_bindings["?seat"] == "seat_guest"


def test_rule_extraction_engine():
    extractor = RuleExtractionEngine()
    # Record recurring pattern: tool_latency_high -> trigger_drain
    for _ in range(3):
        extractor.record_observation(
            context_predicates=[Predicate(name="tool_latency_high", args=("seat_alpha",))],
            outcome_predicate=Predicate(name="trigger_drain", args=("seat_alpha",)),
        )

    rules = extractor.extract_rules(min_support=2, min_confidence=0.8)
    assert len(rules) >= 1
    assert rules[0].consequent.name == "trigger_drain"
    assert rules[0].antecedents[0].name == "tool_latency_high"
