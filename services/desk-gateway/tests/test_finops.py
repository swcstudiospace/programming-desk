"""Tests for FinOps token budgeting, model tariff calculation, and spend circuit breaker."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.finops import (
    CircuitBreakerStatus,
    DEFAULT_TARIFFS,
    ModelTariff,
    SpendCircuitBreaker,
    TokenLedger,
)
from desk_gateway.server import build_app


def test_model_tariff_calculation():
    tariff = ModelTariff(
        model_id="test-model",
        provider="test",
        input_rate_per_m=3_000_000,    # $3.00 / 1M
        output_rate_per_m=15_000_000,  # $15.00 / 1M
        cached_input_rate_per_m=300_000,  # $0.30 / 1M
    )
    # 10,000 input tokens (with 2,000 cached) and 1,000 output tokens
    # Uncached input = 8,000 * 3 = 24,000 micro-dollars ($0.024)
    # Cached input = 2,000 * 0.3 = 600 micro-dollars ($0.0006)
    # Output = 1,000 * 15 = 15,000 micro-dollars ($0.015)
    # Total = 39,600 micro-dollars ($0.0396)
    cost = tariff.calculate_cost_micro_dollars(input_tokens=10_000, output_tokens=1_000, cached_tokens=2_000)
    assert cost == 39_600


def test_token_ledger_recording():
    ledger = TokenLedger()
    rec1 = ledger.record_usage(
        record_id="rec-1",
        tenant_id="tenant-a",
        seat_id="lead",
        model_id="claude-3-5-sonnet",
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_tokens=0,
    )
    # Sonnet: $3/M input ($3,000,000) + $15/M output for 100k ($1,500,000) = $4,500,000
    assert rec1.cost_micro_dollars == 4_500_000
    assert ledger.get_tenant_spend("tenant-a") == 4_500_000
    assert ledger.get_seat_spend("tenant-a", "lead") == 4_500_000

    rec2 = ledger.record_usage(
        record_id="rec-2",
        tenant_id="tenant-a",
        seat_id="quality",
        model_id="gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    # 4o-mini: 150k + 600k = 750,000
    assert rec2.cost_micro_dollars == 750_000
    assert ledger.get_tenant_spend("tenant-a") == 5_250_000
    assert ledger.get_seat_spend("tenant-a", "quality") == 750_000


def test_spend_circuit_breaker_thresholds():
    ledger = TokenLedger()
    cb = SpendCircuitBreaker(ledger)
    tenant = "tenant-limits"
    budget = 10_000_000  # $10.00 budget
    cb.set_budget(tenant, budget)

    # Initial: 0 spend -> NORMAL
    eval_res = cb.evaluate(tenant)
    assert eval_res["status"] == CircuitBreakerStatus.NORMAL.value
    assert eval_res["allowed"] is True

    # Under 80%: $5.00 spend -> NORMAL
    ledger._tenant_spend[tenant] = 5_000_000
    assert cb.evaluate(tenant)["status"] == CircuitBreakerStatus.NORMAL.value

    # At 80%: $8.00 spend -> WARNING
    ledger._tenant_spend[tenant] = 8_000_000
    eval_res = cb.evaluate(tenant)
    assert eval_res["status"] == CircuitBreakerStatus.WARNING.value
    assert eval_res["allowed"] is True

    # At 95%: $9.50 spend -> THROTTLED
    ledger._tenant_spend[tenant] = 9_500_000
    eval_res = cb.evaluate(tenant)
    assert eval_res["status"] == CircuitBreakerStatus.THROTTLED.value
    assert eval_res["allowed"] is True

    # At 100%: $10.00 spend -> TRIPPED
    ledger._tenant_spend[tenant] = 10_000_000
    eval_res = cb.evaluate(tenant)
    assert eval_res["status"] == CircuitBreakerStatus.TRIPPED.value
    assert eval_res["allowed"] is False
    assert cb.check_allowed(tenant) is False


def test_finops_gateway_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Set budget
    res = client.post("/v1/finops/budget", json={"tenant_id": "tenant-api", "budget_micro_dollars": 5_000_000})
    assert res.status_code == 200
    assert res.json()["budget_micro_dollars"] == 5_000_000

    # 2. Record token usage
    rec_res = client.post(
        "/v1/finops/tokens/record",
        json={
            "record_id": "rec-api-01",
            "tenant_id": "tenant-api",
            "seat_id": "lead",
            "model_id": "claude-3-5-sonnet",
            "input_tokens": 100_000,
            "output_tokens": 10_000,
            "cached_tokens": 0,
        },
    )
    assert rec_res.status_code == 200
    data = rec_res.json()
    assert data["ok"] is True
    # 100k input ($0.30 = 300,000) + 10k output ($0.15 = 150,000) = 450,000
    assert data["record"]["cost_micro_dollars"] == 450_000

    # 3. Query spend
    spend_res = client.get("/v1/finops/spend?tenant_id=tenant-api&seat_id=lead")
    assert spend_res.status_code == 200
    s_data = spend_res.json()
    assert s_data["tenant_spend_micro_dollars"] == 450_000
    assert s_data["seat_spend_micro_dollars"] == 450_000
    assert s_data["circuit_breaker"]["status"] == "normal"
