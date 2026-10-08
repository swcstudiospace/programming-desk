"""Tests for LLM Tier Routing, Dynamic Fallback, Prompt Cache Optimization & FinOps Verification."""

import pytest
from starlette.testclient import TestClient

from desk_gateway.finops import SpendCircuitBreaker, TokenLedger
from desk_gateway.tier_routing import (
    ClassificationResult,
    ComplexityClassifier,
    FallbackCascadeManager,
    FallbackDecision,
    FallbackReason,
    FinOpsVerifier,
    LLMTier,
    PromptCacheOptimizer,
    TierBenchmarkMonitor,
)
from desk_gateway.server import build_app


def test_complexity_classifier_thresholds():
    classifier = ComplexityClassifier()

    # 1. Tier 1: Fast / routine task
    t1 = classifier.classify("What is the current status?")
    assert t1.tier == LLMTier.TIER_1_FAST
    assert t1.recommended_model in ("gpt-4o-mini", "claude-3-5-haiku")

    # 2. Tier 2: Standard coding / schema / unit test
    t2 = classifier.classify("def implement_endpoint(request): pass # implement pytest suite")
    assert t2.tier == LLMTier.TIER_2_STANDARD
    assert t2.recommended_model in ("claude-3-5-sonnet", "grok-2", "gpt-4o")

    # 3. Tier 3: Reasoning / formal verification / distributed consensus
    t3 = classifier.classify("prove formal verification of raft consensus state machine and asymptotic bounds")
    assert t3.tier == LLMTier.TIER_3_REASONING
    assert t3.recommended_model in ("deepseek-reasoner", "claude-3-5-sonnet")

    # Explicit tier override
    explicit = classifier.classify("hello", explicit_tier="tier_3_reasoning")
    assert explicit.tier == LLMTier.TIER_3_REASONING


def test_fallback_cascade_resolution():
    classifier = ComplexityClassifier()
    cb = SpendCircuitBreaker(TokenLedger())
    cascade = FallbackCascadeManager(classifier=classifier, circuit_breaker=cb)

    # Cross-provider on 429
    f_429 = cascade.resolve_fallback(
        current_model="claude-3-5-sonnet",
        current_tier=LLMTier.TIER_2_STANDARD,
        reason=FallbackReason.RATE_LIMIT_429,
    )
    assert f_429.original_model == "claude-3-5-sonnet"
    assert f_429.fallback_model != "claude-3-5-sonnet"
    assert f_429.fallback_tier == LLMTier.TIER_2_STANDARD
    assert f_429.strategy == "cross_provider"

    # Budget exhaustion degradation
    f_budget = cascade.resolve_fallback(
        current_model="deepseek-reasoner",
        current_tier=LLMTier.TIER_3_REASONING,
        reason=FallbackReason.BUDGET_EXHAUSTED,
    )
    assert f_budget.fallback_tier == LLMTier.TIER_1_FAST
    assert f_budget.fallback_model == "gpt-4o-mini"
    assert f_budget.strategy == "budget_degrade"


def test_prompt_cache_optimizer_hit_rates():
    optimizer = PromptCacheOptimizer(min_prefix_chars=50)

    system_prefix = "System: You are an autonomous software engineering assistant for Programming Desk."
    context = "Context: Project repo contracts and schemas."

    # Call 1 (first appearance)
    res1 = optimizer.optimize_prompt(system_prefix, context, "List tools available.")
    assert res1.cache_eligible is True
    assert res1.prefix_tokens > 0

    # Call 2, 3, 4 with identical prefix -> recurring hits
    res2 = optimizer.optimize_prompt(system_prefix, context, "Run tests.")
    res3 = optimizer.optimize_prompt(system_prefix, context, "Verify audit ledger.")
    res4 = optimizer.optimize_prompt(system_prefix, context, "Check edge router.")

    stats = optimizer.get_stats()
    assert stats["total_requests"] == 4
    assert stats["cache_hits"] == 3
    # Hit rate is 3/4 = 0.75 (>60% requirement in REQ-TIER-003)
    assert stats["hit_rate"] >= 0.60
    assert res4.estimated_hit_rate >= 0.60


def test_tier_benchmark_monitor():
    monitor = TierBenchmarkMonitor()

    # Record Tier 1 samples
    monitor.record_sample("gpt-4o-mini", LLMTier.TIER_1_FAST, latency_ms=120.0, tokens=1000, spend_micro_dollars=200, quality_score=0.9)
    monitor.record_sample("gpt-4o-mini", LLMTier.TIER_1_FAST, latency_ms=80.0, tokens=1000, spend_micro_dollars=200, quality_score=0.95)

    # Record Tier 2 samples
    monitor.record_sample("claude-3-5-sonnet", LLMTier.TIER_2_STANDARD, latency_ms=450.0, tokens=2000, spend_micro_dollars=9000, quality_score=0.98)

    summary = monitor.get_tier_summary()
    assert "gpt-4o-mini" in summary
    assert summary["gpt-4o-mini"]["avg_latency_ms"] == 100.0
    assert summary["gpt-4o-mini"]["tokens_per_dollar"] == 5_000_000.0  # 2000 tokens for 400 uUSD -> 5M tokens per $1
    assert "claude-3-5-sonnet" in summary
    assert summary["claude-3-5-sonnet"]["avg_latency_ms"] == 450.0


def test_finops_verifier():
    ledger = TokenLedger()
    cb = SpendCircuitBreaker(ledger)
    classifier = ComplexityClassifier()
    verifier = FinOpsVerifier(ledger, cb, classifier)

    results = verifier.verify_all(tenant_id="test-verifier")
    assert results["ok"] is True
    # Overhead benchmark must be well under 5ms
    assert results["checks"]["routing_overhead"]["passed"] is True
    assert results["checks"]["routing_overhead"]["avg_ms"] < 5.0
    # Spend tracking RPO=0
    assert results["checks"]["rpo_zero_spend_tracking"]["passed"] is True
    # Strict budget cutoff
    assert results["checks"]["strict_budget_cutoff"]["passed"] is True


def test_server_tier_endpoints():
    app, _ = build_app()
    client = TestClient(app)

    # 1. Classify endpoint
    resp_classify = client.post(
        "/v1/finops/tier/classify",
        json={"prompt": "prove safety invariant of concurrent transaction graph", "context_turns": 4},
    )
    assert resp_classify.status_code == 200
    c_data = resp_classify.json()
    assert c_data["ok"] is True
    assert c_data["tier"] == LLMTier.TIER_3_REASONING.value
    assert c_data["recommended_model"] == "deepseek-reasoner"

    # 2. Fallback endpoint
    resp_fallback = client.post(
        "/v1/finops/tier/fallback",
        json={"current_model": "gpt-4o", "current_tier": "tier_2_standard", "reason": "rate_limit_429"},
    )
    assert resp_fallback.status_code == 200
    f_data = resp_fallback.json()
    assert f_data["ok"] is True
    assert f_data["original_model"] == "gpt-4o"
    assert f_data["strategy"] == "cross_provider"

    # 3. Cache optimize endpoint
    resp_cache = client.post(
        "/v1/finops/cache/optimize",
        json={
            "system_prompt": "You are an intelligent engineering assistant.",
            "context_data": "Standard repository policies and gating rules.",
            "dynamic_prompt": "Run quality verification now.",
        },
    )
    assert resp_cache.status_code == 200
    cache_data = resp_cache.json()
    assert cache_data["ok"] is True
    assert "prefix_hash" in cache_data

    # 4. Benchmark monitor endpoint
    resp_rec = client.post(
        "/v1/finops/benchmark",
        json={
            "model_id": "deepseek-reasoner",
            "tier": "tier_3_reasoning",
            "latency_ms": 1200.0,
            "tokens": 4000,
            "spend_micro_dollars": 5000,
            "quality_score": 0.99,
        },
    )
    assert resp_rec.status_code == 200
    resp_get = client.get("/v1/finops/benchmark")
    assert resp_get.status_code == 200
    b_data = resp_get.json()
    assert "deepseek-reasoner" in b_data["metrics"]

    # 5. Continuous verify endpoint
    resp_verify = client.post("/v1/finops/verify", json={"tenant_id": "test-live-run"})
    assert resp_verify.status_code == 200
    v_data = resp_verify.json()
    assert v_data["ok"] is True
    assert v_data["checks"]["routing_overhead"]["passed"] is True
    assert v_data["checks"]["routing_overhead"]["avg_ms"] < 5.0
