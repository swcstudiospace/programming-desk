"""FinOps token budgeting, model tariff calculation, and spend circuit breaker."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CircuitBreakerStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    THROTTLED = "throttled"
    TRIPPED = "tripped"


@dataclass(frozen=True)
class ModelTariff:
    """Tariff rates in micro-dollars per 1,000,000 tokens (1 USD = 1,000,000 uUSD)."""
    model_id: str
    provider: str
    input_rate_per_m: int
    output_rate_per_m: int
    cached_input_rate_per_m: int = 0

    def calculate_cost_micro_dollars(
        self, input_tokens: int, output_tokens: int, cached_tokens: int = 0
    ) -> int:
        uncached_input = max(0, input_tokens - cached_tokens)
        uncached_cost = (uncached_input * self.input_rate_per_m) // 1_000_000
        cached_cost = (cached_tokens * self.cached_input_rate_per_m) // 1_000_000
        output_cost = (output_tokens * self.output_rate_per_m) // 1_000_000
        return uncached_cost + cached_cost + output_cost


DEFAULT_TARIFFS: Dict[str, ModelTariff] = {
    # Anthropic Claude 3.5 Sonnet: $3 / M input, $15 / M output, $0.30 / M cache read
    "claude-3-5-sonnet": ModelTariff(
        model_id="claude-3-5-sonnet",
        provider="anthropic",
        input_rate_per_m=3_000_000,
        output_rate_per_m=15_000_000,
        cached_input_rate_per_m=300_000,
    ),
    # Anthropic Claude 3.5 Haiku: $0.80 / M input, $4 / M output
    "claude-3-5-haiku": ModelTariff(
        model_id="claude-3-5-haiku",
        provider="anthropic",
        input_rate_per_m=800_000,
        output_rate_per_m=4_000_000,
        cached_input_rate_per_m=80_000,
    ),
    # OpenAI GPT-4o: $2.50 / M input, $10 / M output
    "gpt-4o": ModelTariff(
        model_id="gpt-4o",
        provider="openai",
        input_rate_per_m=2_500_000,
        output_rate_per_m=10_000_000,
        cached_input_rate_per_m=1_250_000,
    ),
    # OpenAI GPT-4o-mini: $0.15 / M input, $0.60 / M output
    "gpt-4o-mini": ModelTariff(
        model_id="gpt-4o-mini",
        provider="openai",
        input_rate_per_m=150_000,
        output_rate_per_m=600_000,
        cached_input_rate_per_m=75_000,
    ),
    # Grok 2: $2.00 / M input, $10 / M output
    "grok-2": ModelTariff(
        model_id="grok-2",
        provider="xai",
        input_rate_per_m=2_000_000,
        output_rate_per_m=10_000_000,
        cached_input_rate_per_m=200_000,
    ),
    # DeepSeek Reasoner / Chat: $0.55 / M input, $2.19 / M output
    "deepseek-reasoner": ModelTariff(
        model_id="deepseek-reasoner",
        provider="deepseek",
        input_rate_per_m=550_000,
        output_rate_per_m=2_190_000,
        cached_input_rate_per_m=140_000,
    ),
}


@dataclass
class TokenUsageRecord:
    record_id: str
    tenant_id: str
    seat_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_micro_dollars: int
    timestamp: float = field(default_factory=time.time)


class TokenLedger:
    """In-memory rolling token usage ledger with multi-model cost translation."""

    def __init__(self, tariffs: Optional[Dict[str, ModelTariff]] = None):
        self.tariffs: Dict[str, ModelTariff] = tariffs or dict(DEFAULT_TARIFFS)
        self.records: List[TokenUsageRecord] = []
        self._tenant_spend: Dict[str, int] = {}
        self._seat_spend: Dict[str, int] = {}

    def register_tariff(self, tariff: ModelTariff) -> None:
        self.tariffs[tariff.model_id] = tariff

    def record_usage(
        self,
        record_id: str,
        tenant_id: str,
        seat_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> TokenUsageRecord:
        tariff = self.tariffs.get(model_id)
        if not tariff:
            # Fallback default: $1.00 / M input, $2.00 / M output
            tariff = ModelTariff(model_id, "unknown", 1_000_000, 2_000_000)

        cost = tariff.calculate_cost_micro_dollars(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )

        record = TokenUsageRecord(
            record_id=record_id,
            tenant_id=tenant_id,
            seat_id=seat_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_micro_dollars=cost,
        )
        self.records.append(record)
        self._tenant_spend[tenant_id] = self._tenant_spend.get(tenant_id, 0) + cost
        seat_key = f"{tenant_id}:{seat_id}"
        self._seat_spend[seat_key] = self._seat_spend.get(seat_key, 0) + cost
        return record

    def get_tenant_spend(self, tenant_id: str) -> int:
        return self._tenant_spend.get(tenant_id, 0)

    def get_seat_spend(self, tenant_id: str, seat_id: str) -> int:
        return self._seat_spend.get(f"{tenant_id}:{seat_id}", 0)


class SpendCircuitBreaker:
    """Graduated spend limits and circuit breaker policy."""

    def __init__(self, ledger: TokenLedger):
        self.ledger = ledger
        self.tenant_budgets: Dict[str, int] = {}  # tenant_id -> budget in micro-dollars
        self.warning_threshold_ratio: float = 0.80
        self.throttle_threshold_ratio: float = 0.95
        self.trip_threshold_ratio: float = 1.00

    def set_budget(self, tenant_id: str, budget_micro_dollars: int) -> None:
        self.tenant_budgets[tenant_id] = budget_micro_dollars

    def evaluate(self, tenant_id: str) -> Dict[str, Any]:
        budget = self.tenant_budgets.get(tenant_id)
        current_spend = self.ledger.get_tenant_spend(tenant_id)

        if budget is None or budget <= 0:
            return {
                "tenant_id": tenant_id,
                "budget_micro_dollars": None,
                "current_spend_micro_dollars": current_spend,
                "usage_ratio": 0.0,
                "status": CircuitBreakerStatus.NORMAL.value,
                "allowed": True,
            }

        ratio = current_spend / budget

        if ratio >= self.trip_threshold_ratio:
            status = CircuitBreakerStatus.TRIPPED
            allowed = False
        elif ratio >= self.throttle_threshold_ratio:
            status = CircuitBreakerStatus.THROTTLED
            allowed = True
        elif ratio >= self.warning_threshold_ratio:
            status = CircuitBreakerStatus.WARNING
            allowed = True
        else:
            status = CircuitBreakerStatus.NORMAL
            allowed = True

        return {
            "tenant_id": tenant_id,
            "budget_micro_dollars": budget,
            "current_spend_micro_dollars": current_spend,
            "usage_ratio": round(ratio, 4),
            "status": status.value,
            "allowed": allowed,
        }

    def check_allowed(self, tenant_id: str) -> bool:
        eval_result = self.evaluate(tenant_id)
        return eval_result["allowed"]
