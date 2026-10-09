"""LLM Tier Routing, Dynamic Fallback, Prompt Cache Optimization & FinOps Verification."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from desk_gateway.finops import CircuitBreakerStatus, SpendCircuitBreaker, TokenLedger


class LLMTier(str, Enum):
    TIER_1_FAST = "tier_1_fast"
    TIER_2_STANDARD = "tier_2_standard"
    TIER_3_REASONING = "tier_3_reasoning"


DEFAULT_TIER_MODELS: Dict[LLMTier, List[str]] = {
    LLMTier.TIER_1_FAST: ["gpt-4o-mini", "claude-3-5-haiku"],
    LLMTier.TIER_2_STANDARD: ["claude-3-5-sonnet", "grok-2", "gpt-4o"],
    LLMTier.TIER_3_REASONING: ["deepseek-reasoner", "claude-3-5-sonnet"],
}

REASONING_KEYWORDS = {
    "prove", "proof", "theorem", "lemma", "formal verification", "concurrency bug",
    "deadlock", "race condition", "memory leak", "architectural synthesis",
    "distributed consensus", "raft", "paxos", "cryptographic", "asymptotic",
}

CODE_KEYWORDS = {
    "def ", "class ", "async def", "function", "refactor", "implement",
    "pytest", "unittest", "algorithm", "schema", "database", "api endpoint",
}


@dataclass
class ClassificationResult:
    tier: LLMTier
    recommended_model: str
    complexity_score: float
    reasons: List[str]
    input_tokens_estimate: int


class ComplexityClassifier:
    """Classifies task complexity to route to optimal LLM cost tiers (REQ-TIER-001)."""

    def __init__(self, tier_models: Optional[Dict[LLMTier, List[str]]] = None):
        self.tier_models = tier_models or DEFAULT_TIER_MODELS

    def estimate_tokens(self, prompt: str) -> int:
        # Rough token approximation: ~4 characters per token
        return max(1, len(prompt) // 4)

    def classify(
        self,
        prompt: str,
        context_turns: int = 0,
        explicit_tier: Optional[str] = None,
    ) -> ClassificationResult:
        if explicit_tier:
            try:
                selected_tier = LLMTier(explicit_tier)
                return ClassificationResult(
                    tier=selected_tier,
                    recommended_model=self.tier_models[selected_tier][0],
                    complexity_score=1.0 if selected_tier == LLMTier.TIER_3_REASONING else 0.5,
                    reasons=[f"Explicitly requested tier: {explicit_tier}"],
                    input_tokens_estimate=self.estimate_tokens(prompt),
                )
            except ValueError:
                pass

        prompt_lower = prompt.lower()
        tokens = self.estimate_tokens(prompt)
        reasons: List[str] = []
        score = 0.0

        # Check reasoning keywords
        reasoning_hits = [kw for kw in REASONING_KEYWORDS if kw in prompt_lower]
        if reasoning_hits:
            score += 0.5 + min(0.3, len(reasoning_hits) * 0.1)
            reasons.append(f"Reasoning keywords detected: {', '.join(reasoning_hits[:3])}")

        # Check code keywords
        code_hits = [kw for kw in CODE_KEYWORDS if kw in prompt_lower]
        if code_hits:
            score += 0.3 + min(0.2, len(code_hits) * 0.05)
            reasons.append(f"Code keywords detected: {', '.join(code_hits[:3])}")

        # Multi-turn context complexity
        if context_turns > 5:
            score += 0.25
            reasons.append(f"Deep multi-turn context: {context_turns} turns")
        elif context_turns > 2:
            score += 0.1

        # Token length impact
        if tokens > 4000:
            score += 0.35
            reasons.append(f"High token volume: ~{tokens} tokens")
        elif tokens > 1500:
            score += 0.15

        # Decision thresholds
        if score >= 0.65 or reasoning_hits:
            tier = LLMTier.TIER_3_REASONING
        elif score >= 0.3 or code_hits or tokens > 1000:
            tier = LLMTier.TIER_2_STANDARD
        else:
            tier = LLMTier.TIER_1_FAST
            reasons.append("Low complexity: routine instruction/formatting")

        return ClassificationResult(
            tier=tier,
            recommended_model=self.tier_models[tier][0],
            complexity_score=min(1.0, round(score, 3)),
            reasons=reasons,
            input_tokens_estimate=tokens,
        )


class FallbackReason(str, Enum):
    RATE_LIMIT_429 = "rate_limit_429"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    PROVIDER_ERROR_5XX = "provider_error_5xx"


@dataclass
class FallbackDecision:
    original_model: str
    original_tier: LLMTier
    fallback_model: str
    fallback_tier: LLMTier
    reason: FallbackReason
    strategy: str  # "downgrade", "cross_provider", "upgrade"


class FallbackCascadeManager:
    """Dynamic fallback cascade degrading or adapting model tiers on failure (REQ-TIER-002)."""

    def __init__(
        self,
        classifier: Optional[ComplexityClassifier] = None,
        circuit_breaker: Optional[SpendCircuitBreaker] = None,
    ):
        self.classifier = classifier or ComplexityClassifier()
        self.circuit_breaker = circuit_breaker

    def resolve_fallback(
        self,
        current_model: str,
        current_tier: LLMTier,
        reason: FallbackReason,
        tenant_id: str = "default",
    ) -> FallbackDecision:
        # If budget exhausted or circuit breaker tripped, force degrade to Tier 1 cheapest model
        if reason in (FallbackReason.BUDGET_EXHAUSTED, FallbackReason.CIRCUIT_BREAKER_TRIPPED):
            fallback_tier = LLMTier.TIER_1_FAST
            fallback_model = "gpt-4o-mini"
            return FallbackDecision(
                original_model=current_model,
                original_tier=current_tier,
                fallback_model=fallback_model,
                fallback_tier=fallback_tier,
                reason=reason,
                strategy="budget_degrade",
            )

        # On rate limit (429) or timeout or 5xx:
        # First attempt: cross-provider model in same tier
        tier_models = self.classifier.tier_models.get(current_tier, [])
        alternates_in_tier = [m for m in tier_models if m != current_model]
        if alternates_in_tier:
            return FallbackDecision(
                original_model=current_model,
                original_tier=current_tier,
                fallback_model=alternates_in_tier[0],
                fallback_tier=current_tier,
                reason=reason,
                strategy="cross_provider",
            )

        # Second attempt: downgrade to lower tier if in Tier 3 or Tier 2
        if current_tier == LLMTier.TIER_3_REASONING:
            fallback_tier = LLMTier.TIER_2_STANDARD
            fallback_model = self.classifier.tier_models[fallback_tier][0]
            strategy = "downgrade"
        elif current_tier == LLMTier.TIER_2_STANDARD:
            fallback_tier = LLMTier.TIER_1_FAST
            fallback_model = self.classifier.tier_models[fallback_tier][0]
            strategy = "downgrade"
        else:
            # Already at Tier 1, switch to second model or stay at cheapest
            fallback_tier = LLMTier.TIER_1_FAST
            fallback_model = "gpt-4o-mini" if current_model != "gpt-4o-mini" else "claude-3-5-haiku"
            strategy = "alternate_provider"

        return FallbackDecision(
            original_model=current_model,
            original_tier=current_tier,
            fallback_model=fallback_model,
            fallback_tier=fallback_tier,
            reason=reason,
            strategy=strategy,
        )


@dataclass
class CacheOptimizationResult:
    prefix_hash: str
    prefix_tokens: int
    suffix_tokens: int
    total_tokens: int
    cache_eligible: bool
    estimated_hit_rate: float
    cache_guidance: str


class PromptCacheOptimizer:
    """Detects repeated prompt prefixes to maximize caching hit rates >60% (REQ-TIER-003)."""

    def __init__(self, min_prefix_chars: int = 200):
        self.min_prefix_chars = min_prefix_chars
        self._prefix_frequencies: Dict[str, int] = {}
        self._total_requests: int = 0
        self._cache_hits: int = 0

    def optimize_prompt(
        self,
        system_prompt: str,
        context_data: str,
        dynamic_user_prompt: str,
    ) -> CacheOptimizationResult:
        self._total_requests += 1
        prefix_content = f"{system_prompt.strip()}\n---\n{context_data.strip()}".strip()
        prefix_hash = hashlib.sha256(prefix_content.encode("utf-8")).hexdigest()

        prefix_chars = len(prefix_content)
        prefix_tokens = max(1, prefix_chars // 4)
        suffix_tokens = max(1, len(dynamic_user_prompt) // 4)
        total_tokens = prefix_tokens + suffix_tokens

        is_eligible = prefix_chars >= self.min_prefix_chars
        current_freq = self._prefix_frequencies.get(prefix_hash, 0)

        if is_eligible:
            self._prefix_frequencies[prefix_hash] = current_freq + 1
            if current_freq > 0:
                self._cache_hits += 1

        # Calculate empirical or projected hit rate
        freq = self._prefix_frequencies.get(prefix_hash, 0)
        if self._total_requests > 0:
            empirical_rate = self._cache_hits / self._total_requests
        else:
            empirical_rate = 0.0

        # If prefix is recurring, projected hit rate is high
        projected_hit_rate = min(0.95, 0.4 + (0.15 * freq)) if (is_eligible and freq > 1) else (0.1 if is_eligible else 0.0)
        reported_hit_rate = round(max(empirical_rate, projected_hit_rate), 3)

        if is_eligible:
            guidance = f"Prefix cached ({prefix_tokens} tokens). Place dynamic user arguments at suffix end."
        else:
            guidance = f"Prefix too short ({prefix_chars} chars < {self.min_prefix_chars}). Not eligible for prompt cache."

        return CacheOptimizationResult(
            prefix_hash=prefix_hash,
            prefix_tokens=prefix_tokens,
            suffix_tokens=suffix_tokens,
            total_tokens=total_tokens,
            cache_eligible=is_eligible,
            estimated_hit_rate=reported_hit_rate,
            cache_guidance=guidance,
        )

    def get_stats(self) -> Dict[str, Any]:
        hit_rate = (self._cache_hits / self._total_requests) if self._total_requests > 0 else 0.0
        return {
            "total_requests": self._total_requests,
            "cache_hits": self._cache_hits,
            "hit_rate": round(hit_rate, 4),
            "unique_prefixes": len(self._prefix_frequencies),
        }


@dataclass
class TierMetric:
    model_id: str
    tier: LLMTier
    total_requests: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    total_spend_micro_dollars: int = 0
    quality_scores: List[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        return round(self.total_latency_ms / self.total_requests, 2) if self.total_requests > 0 else 0.0

    @property
    def avg_quality_score(self) -> float:
        return round(sum(self.quality_scores) / len(self.quality_scores), 3) if self.quality_scores else 0.0

    @property
    def tokens_per_dollar(self) -> float:
        # $1 = 1,000,000 uUSD. tokens_per_dollar = (total_tokens / total_spend) * 1_000_000
        if self.total_spend_micro_dollars <= 0:
            return 0.0
        return round((self.total_tokens / self.total_spend_micro_dollars) * 1_000_000, 1)


class TierBenchmarkMonitor:
    """Tracks latency, completion quality, and tokens-per-dollar across tiers (REQ-TIER-004)."""

    def __init__(self):
        self._metrics: Dict[str, TierMetric] = {}

    def _get_or_create(self, model_id: str, tier: LLMTier) -> TierMetric:
        if model_id not in self._metrics:
            self._metrics[model_id] = TierMetric(model_id=model_id, tier=tier)
        return self._metrics[model_id]

    def record_sample(
        self,
        model_id: str,
        tier: LLMTier,
        latency_ms: float,
        tokens: int,
        spend_micro_dollars: int,
        quality_score: float = 1.0,
    ) -> None:
        metric = self._get_or_create(model_id, tier)
        metric.total_requests += 1
        metric.total_latency_ms += latency_ms
        metric.total_tokens += tokens
        metric.total_spend_micro_dollars += spend_micro_dollars
        metric.quality_scores.append(quality_score)

    def get_tier_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        for model_id, m in self._metrics.items():
            summary[model_id] = {
                "tier": m.tier.value,
                "total_requests": m.total_requests,
                "avg_latency_ms": m.avg_latency_ms,
                "avg_quality_score": m.avg_quality_score,
                "total_spend_micro_dollars": m.total_spend_micro_dollars,
                "tokens_per_dollar": m.tokens_per_dollar,
            }
        return summary


class FinOpsVerifier:
    """Continuous FinOps verification test suite ensuring RPO=0, <5ms overhead, strict cutoffs (REQ-TIER-005)."""

    def __init__(
        self,
        token_ledger: TokenLedger,
        circuit_breaker: SpendCircuitBreaker,
        classifier: ComplexityClassifier,
    ):
        self.token_ledger = token_ledger
        self.circuit_breaker = circuit_breaker
        self.classifier = classifier

    def verify_all(self, tenant_id: str = "test-verify") -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # 1. Routing overhead benchmark (< 5ms target)
        prompt_sample = "def solve_concurrency_issue(lock, state): prove absence of deadlock."
        start = time.perf_counter()
        iterations = 500
        for _ in range(iterations):
            _ = self.classifier.classify(prompt_sample)
        total_time_ms = (time.perf_counter() - start) * 1000
        avg_routing_overhead_ms = total_time_ms / iterations
        overhead_ok = avg_routing_overhead_ms < 5.0
        results["routing_overhead"] = {
            "avg_ms": round(avg_routing_overhead_ms, 4),
            "threshold_ms": 5.0,
            "passed": overhead_ok,
        }

        # 2. Spend Tracking RPO = 0 (Immediate synchronous persistence)
        initial_spend = self.token_ledger.get_tenant_spend(tenant_id)
        test_rec = self.token_ledger.record_usage(
            record_id=f"verify-{time.time_ns()}",
            tenant_id=tenant_id,
            seat_id="lead",
            model_id="gpt-4o-mini",
            input_tokens=10_000,
            output_tokens=2_000,
        )
        updated_spend = self.token_ledger.get_tenant_spend(tenant_id)
        expected_spend = initial_spend + test_rec.cost_micro_dollars
        rpo_zero_ok = (updated_spend == expected_spend)
        results["rpo_zero_spend_tracking"] = {
            "initial_spend": initial_spend,
            "recorded_cost": test_rec.cost_micro_dollars,
            "updated_spend": updated_spend,
            "passed": rpo_zero_ok,
        }

        # 3. Strict Budget Cutoff Enforcement
        cutoff_tenant = f"cutoff-{time.time_ns()}"
        self.circuit_breaker.set_budget(cutoff_tenant, 100_000)  # $0.10 budget
        # Initial check should allow
        eval1 = self.circuit_breaker.evaluate(cutoff_tenant)
        allowed_before = eval1["allowed"]

        # Push past budget limit ($0.15 spend)
        self.token_ledger.record_usage(
            record_id=f"verify-trip-{time.time_ns()}",
            tenant_id=cutoff_tenant,
            seat_id="lead",
            model_id="claude-3-5-sonnet",
            input_tokens=50_000,
            output_tokens=10_000,
        )
        eval2 = self.circuit_breaker.evaluate(cutoff_tenant)
        tripped_after = (eval2["status"] == CircuitBreakerStatus.TRIPPED.value and not eval2["allowed"])
        results["strict_budget_cutoff"] = {
            "allowed_before": allowed_before,
            "tripped_after": tripped_after,
            "passed": allowed_before and tripped_after,
        }

        overall_passed = all(item.get("passed", False) for item in results.values())
        return {
            "ok": overall_passed,
            "timestamp": time.time(),
            "checks": results,
        }
