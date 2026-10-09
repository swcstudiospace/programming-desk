import pytest
from desk_gateway.neural_routing import (
    CircuitState,
    DeskCapabilityProfile,
    IntentVectorizer,
    NeuralRoutingEngine,
    RoutingCircuitBreaker,
)


def test_intent_vectorizer_basic():
    text = "Optimize PostgreSQL queries and substrate gateway concurrency under high database load."
    intent = IntentVectorizer.vectorize(
        task_text=text,
        required_tools=["sql_query", "db_migrate"],
        max_latency_budget_ms=300.0,
        max_cost_budget=0.04,
    )
    assert intent.domain_weights["systems_backend"] > 0.0
    assert "sql_query" in intent.required_tools
    assert intent.max_latency_budget_ms == 300.0
    assert len(intent.semantic_embedding) == 8


def test_neural_routing_circuit_breaker():
    cb = RoutingCircuitBreaker(failure_threshold=2, recovery_time_seconds=1.0)
    assert cb.get_state("desk-a") == CircuitState.HEALTHY

    # Record 1 failure -> DEGRADED
    st1 = cb.record_probe("desk-a", success=False, latency_ms=100.0)
    assert st1 == CircuitState.DEGRADED
    assert cb.get_state("desk-a") == CircuitState.DEGRADED

    # Record 2nd failure -> OPEN
    st2 = cb.record_probe("desk-a", success=False, latency_ms=100.0)
    assert st2 == CircuitState.OPEN
    assert cb.get_state("desk-a") == CircuitState.OPEN


def test_neural_routing_engine_score_and_dispatch():
    engine = NeuralRoutingEngine(signing_secret="test-secret")
    desk_sys = DeskCapabilityProfile(
        desk_id="desk-systems",
        seat_ids=["systems-seat-1", "systems-seat-2"],
        domains=["systems_backend", "infrastructure"],
        supported_tools=["sql_query", "bash_exec"],
        capacity_limit=50,
        active_load=5,
        base_latency_ms=20.0,
        cost_per_1k_tokens=0.001,
    )
    desk_web = DeskCapabilityProfile(
        desk_id="desk-web",
        seat_ids=["web-seat-1"],
        domains=["web_edge"],
        supported_tools=["render_dom"],
        capacity_limit=50,
        active_load=20,
        base_latency_ms=60.0,
        cost_per_1k_tokens=0.005,
    )
    engine.register_desk(desk_sys)
    engine.register_desk(desk_web)

    receipt, chosen = engine.route_task(
        task_id="task-101",
        task_text="Run database query and optimize indexing for backend latency",
        required_tools=["sql_query"],
    )

    assert chosen is not None
    assert chosen.desk_id == "desk-systems"
    assert receipt.selected_desk_id == "desk-systems"
    assert receipt.selected_seat_id in desk_sys.seat_ids
    assert receipt.composite_score > 0.0
    assert receipt.signature != ""


def test_neural_routing_circuit_breaker_failover():
    engine = NeuralRoutingEngine(signing_secret="test-secret")
    desk_sys = DeskCapabilityProfile(
        desk_id="desk-sys-primary",
        seat_ids=["seat-sys-1"],
        domains=["systems_backend"],
        supported_tools=["sql_query"],
    )
    desk_sys_sec = DeskCapabilityProfile(
        desk_id="desk-sys-secondary",
        seat_ids=["seat-sys-2"],
        domains=["systems_backend"],
        supported_tools=["sql_query"],
    )
    engine.register_desk(desk_sys)
    engine.register_desk(desk_sys_sec)

    # Trip primary circuit breaker
    engine.circuit_breaker.record_probe("desk-sys-primary", success=False, latency_ms=2000.0)
    engine.circuit_breaker.record_probe("desk-sys-primary", success=False, latency_ms=2000.0)
    engine.circuit_breaker.record_probe("desk-sys-primary", success=False, latency_ms=2000.0)
    assert engine.circuit_breaker.get_state("desk-sys-primary") == CircuitState.OPEN

    receipt, chosen = engine.route_task(
        task_id="task-failover-1",
        task_text="Run postgres migration query",
        required_tools=["sql_query"],
    )

    assert chosen is not None
    assert chosen.desk_id == "desk-sys-secondary"
    assert receipt.selected_desk_id == "desk-sys-secondary"


def test_neural_routing_context_envelope_verification():
    engine = NeuralRoutingEngine(signing_secret="test-secret")
    envelope = engine.create_context_envelope(
        task_id="task-env-1",
        source_desk_id="desk-origin",
        target_desk_id="desk-target",
        target_seat_id="seat-target-0",
        conversation_state={"messages": [{"role": "user", "content": "hello"}]},
        sensory_context={"embedding_dim": 8},
    )

    assert envelope.envelope_id.startswith("env-")
    assert engine.verify_envelope(envelope) is True

    # Tamper with envelope
    envelope.source_desk_id = "desk-tampered"
    assert engine.verify_envelope(envelope) is False
