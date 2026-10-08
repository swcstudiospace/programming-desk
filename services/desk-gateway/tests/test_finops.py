"""Tests for FinOps token budgeting, model tariff calculation, and spend circuit breaker."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.finops import (
    CircuitBreakerStatus,
    DEFAULT_SEAT_ALLOCATIONS,
    DEFAULT_TARIFFS,
    ExpenditureReceipt,
    ExpenditureReceiptLedger,
    ModelTariff,
    SeatAllocation,
    SeatQuotaAllocationMatrix,
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

    # 4. Check seat quota and receipts via endpoints
    quota_res = client.get("/v1/finops/seat-quota?tenant_id=tenant-api&seat_id=lead")
    assert quota_res.status_code == 200
    assert quota_res.json()["ok"] is True
    assert quota_res.json()["seat_quota"]["allowed"] is True

    verify_res = client.get("/v1/finops/receipts/verify?tenant_id=tenant-api")
    assert verify_res.status_code == 200
    assert verify_res.json()["verification"]["valid"] is True
    assert verify_res.json()["verification"]["count"] == 1


def test_seat_quota_allocation_matrix():
    matrix = SeatQuotaAllocationMatrix()
    tenant = "tenant-seat-test"
    seat = "web"
    # Daily allowance: 1,200,000, 20% burst -> 1,440,000 ceiling

    # Normal usage
    matrix.record_usage(tenant, seat, 500_000)
    ev1 = matrix.evaluate_seat(tenant, seat)
    assert ev1["allowed"] is True
    assert ev1["is_bursting"] is False
    assert ev1["reason"] == "ok"

    # Burst overdraft usage: total 1,300,000 (> 1,200,000 but <= 1,440,000)
    matrix.record_usage(tenant, seat, 800_000)
    ev2 = matrix.evaluate_seat(tenant, seat)
    assert ev2["allowed"] is True
    assert ev2["is_bursting"] is True
    assert ev2["reason"] == "burst_overdraft_active"

    # Ceiling exceeded: total 1,500,000 (> 1,440,000)
    matrix.record_usage(tenant, seat, 200_000)
    ev3 = matrix.evaluate_seat(tenant, seat)
    assert ev3["allowed"] is False
    assert ev3["reason"] == "daily_burst_ceiling_exceeded"


def test_expenditure_receipt_ledger_integrity_and_tampering():
    ledger = ExpenditureReceiptLedger(secret="test-finops-secret")
    tenant = "tenant-tamper-check"

    # Issue three sequential receipts
    r1 = ledger.issue_receipt(tenant, "lead", "rec-1", "claude-3-5-sonnet", 1000, 100, 0, 4500, 4500)
    r2 = ledger.issue_receipt(tenant, "quality", "rec-2", "gpt-4o-mini", 2000, 200, 0, 420, 4920)
    r3 = ledger.issue_receipt(tenant, "systems", "rec-3", "deepseek-reasoner", 3000, 300, 0, 2307, 7227)

    # Verification should succeed
    res = ledger.verify_chain(tenant)
    assert res["valid"] is True
    assert res["count"] == 3
    assert res["latest_receipt_hash"] == r3.receipt_hash

    # Tampering test: alter cost in receipt 2
    chain = ledger.get_chain(tenant)
    tampered_r2 = ExpenditureReceipt(
        receipt_id=r2.receipt_id,
        tenant_id=r2.tenant_id,
        seat_id=r2.seat_id,
        record_id=r2.record_id,
        model_id=r2.model_id,
        input_tokens=r2.input_tokens,
        output_tokens=r2.output_tokens,
        cached_tokens=r2.cached_tokens,
        cost_micro_dollars=999_999,  # tampered!
        cumulative_tenant_spend=r2.cumulative_tenant_spend,
        timestamp=r2.timestamp,
        prev_receipt_hash=r2.prev_receipt_hash,
        receipt_hash=r2.receipt_hash,
    )
    ledger._chains[tenant][1] = tampered_r2

    # Verification must detect tamper
    tamper_res = ledger.verify_chain(tenant)
    assert tamper_res["valid"] is False
    assert tamper_res["failed_index"] == 1
    assert "Hash mismatch" in tamper_res["error"]

