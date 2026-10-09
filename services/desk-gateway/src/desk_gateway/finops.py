"""FinOps token budgeting, model tariff calculation, and spend circuit breaker."""

from __future__ import annotations

import hashlib
import hmac
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


@dataclass
class SeatAllocation:
    """Seat-level daily and monthly token allowances in tokens."""
    seat_id: str
    daily_token_allowance: int
    monthly_token_allowance: int
    burst_allowance_ratio: float = 0.20  # Allows up to 20% burst over daily allowance with priority overdraft
    priority_level: int = 1              # 1=Standard, 2=Elevated, 3=Critical (e.g. Lead, Quality)


# Default seat allocation weights and allowances across 7 seats
DEFAULT_SEAT_ALLOCATIONS: Dict[str, SeatAllocation] = {
    "lead": SeatAllocation("lead", daily_token_allowance=2_000_000, monthly_token_allowance=50_000_000, burst_allowance_ratio=0.30, priority_level=3),
    "systems": SeatAllocation("systems", daily_token_allowance=1_500_000, monthly_token_allowance=35_000_000, burst_allowance_ratio=0.25, priority_level=2),
    "web": SeatAllocation("web", daily_token_allowance=1_200_000, monthly_token_allowance=30_000_000, burst_allowance_ratio=0.20, priority_level=2),
    "android": SeatAllocation("android", daily_token_allowance=1_000_000, monthly_token_allowance=25_000_000, burst_allowance_ratio=0.20, priority_level=1),
    "ios": SeatAllocation("ios", daily_token_allowance=1_000_000, monthly_token_allowance=25_000_000, burst_allowance_ratio=0.20, priority_level=1),
    "infra": SeatAllocation("infra", daily_token_allowance=1_500_000, monthly_token_allowance=35_000_000, burst_allowance_ratio=0.25, priority_level=2),
    "quality": SeatAllocation("quality", daily_token_allowance=2_000_000, monthly_token_allowance=50_000_000, burst_allowance_ratio=0.30, priority_level=3),
}


class SeatQuotaAllocationMatrix:
    """Distributes and enforces daily/monthly token allowances across the seven seats with priority burst overdrafts (REQ-FINOPS-003)."""

    def __init__(self, allocations: Optional[Dict[str, SeatAllocation]] = None):
        self.allocations: Dict[str, SeatAllocation] = allocations or dict(DEFAULT_SEAT_ALLOCATIONS)
        # Usage tracking: tenant_id -> seat_id -> period_key -> total_tokens
        self._seat_usage: Dict[str, Dict[str, Dict[str, int]]] = {}

    def configure_seat(self, allocation: SeatAllocation) -> None:
        self.allocations[allocation.seat_id] = allocation

    def get_allocation(self, seat_id: str) -> SeatAllocation:
        if seat_id in self.allocations:
            return self.allocations[seat_id]
        # Standard default for unconfigured seats
        return SeatAllocation(seat_id, daily_token_allowance=1_000_000, monthly_token_allowance=25_000_000)

    def _get_period_keys(self, now: Optional[float] = None) -> tuple[str, str]:
        t = time.gmtime(now if now is not None else time.time())
        day_key = f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        month_key = f"{t.tm_year}-{t.tm_mon:02d}"
        return day_key, month_key

    def record_usage(self, tenant_id: str, seat_id: str, total_tokens: int, now: Optional[float] = None) -> None:
        day_key, month_key = self._get_period_keys(now)
        tenant_seats = self._seat_usage.setdefault(tenant_id, {})
        seat_periods = tenant_seats.setdefault(seat_id, {})
        seat_periods[day_key] = seat_periods.get(day_key, 0) + total_tokens
        seat_periods[month_key] = seat_periods.get(month_key, 0) + total_tokens

    def evaluate_seat(self, tenant_id: str, seat_id: str, requested_tokens: int = 0, now: Optional[float] = None) -> Dict[str, Any]:
        alloc = self.get_allocation(seat_id)
        day_key, month_key = self._get_period_keys(now)
        tenant_seats = self._seat_usage.get(tenant_id, {})
        seat_periods = tenant_seats.get(seat_id, {})

        current_daily = seat_periods.get(day_key, 0)
        current_monthly = seat_periods.get(month_key, 0)

        daily_limit = alloc.daily_token_allowance
        monthly_limit = alloc.monthly_token_allowance
        max_daily_with_burst = int(daily_limit * (1.0 + alloc.burst_allowance_ratio))

        projected_daily = current_daily + requested_tokens
        projected_monthly = current_monthly + requested_tokens

        is_bursting = projected_daily > daily_limit and projected_daily <= max_daily_with_burst
        exceeded_daily = projected_daily > max_daily_with_burst
        exceeded_monthly = projected_monthly > monthly_limit

        allowed = not (exceeded_daily or exceeded_monthly)

        reason = "ok"
        if exceeded_monthly:
            reason = "monthly_allowance_exceeded"
        elif exceeded_daily:
            reason = "daily_burst_ceiling_exceeded"
        elif is_bursting:
            reason = "burst_overdraft_active"

        return {
            "tenant_id": tenant_id,
            "seat_id": seat_id,
            "priority_level": alloc.priority_level,
            "daily_allowance": daily_limit,
            "current_daily_usage": current_daily,
            "daily_burst_limit": max_daily_with_burst,
            "monthly_allowance": monthly_limit,
            "current_monthly_usage": current_monthly,
            "is_bursting": is_bursting,
            "allowed": allowed,
            "reason": reason,
        }


GENESIS_AUDIT_HASH = "0" * 64


@dataclass(frozen=True)
class ExpenditureReceipt:
    receipt_id: str
    tenant_id: str
    seat_id: str
    record_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_micro_dollars: int
    cumulative_tenant_spend: int
    timestamp: float
    prev_receipt_hash: str
    receipt_hash: str

    def to_dict(self) -> Dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)


class ExpenditureReceiptLedger:
    """Cryptographic expenditure audit receipts chaining token usage vouchers with SHA-256 state anchors (REQ-FINOPS-005)."""

    def __init__(self, secret: str = "desk-finops-receipt-anchor"):
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        # tenant_id -> list of ExpenditureReceipt
        self._chains: Dict[str, List[ExpenditureReceipt]] = {}

    @staticmethod
    def _compute_receipt_hash(
        tenant_id: str,
        seat_id: str,
        record_id: str,
        cost_micro_dollars: int,
        cumulative_tenant_spend: int,
        timestamp: float,
        prev_receipt_hash: str,
        secret: bytes,
    ) -> str:
        payload = f"{tenant_id}|{seat_id}|{record_id}|{cost_micro_dollars}|{cumulative_tenant_spend}|{timestamp:.6f}|{prev_receipt_hash}"
        return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def issue_receipt(
        self,
        tenant_id: str,
        seat_id: str,
        record_id: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        cost_micro_dollars: int,
        cumulative_tenant_spend: int,
        timestamp: Optional[float] = None,
    ) -> ExpenditureReceipt:
        ts = timestamp if timestamp is not None else time.time()
        chain = self._chains.setdefault(tenant_id, [])
        prev_hash = chain[-1].receipt_hash if chain else GENESIS_AUDIT_HASH

        receipt_hash = self._compute_receipt_hash(
            tenant_id=tenant_id,
            seat_id=seat_id,
            record_id=record_id,
            cost_micro_dollars=cost_micro_dollars,
            cumulative_tenant_spend=cumulative_tenant_spend,
            timestamp=ts,
            prev_receipt_hash=prev_hash,
            secret=self.secret,
        )

        receipt = ExpenditureReceipt(
            receipt_id=f"exp-rcpt-{tenant_id}-{len(chain) + 1}",
            tenant_id=tenant_id,
            seat_id=seat_id,
            record_id=record_id,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_micro_dollars=cost_micro_dollars,
            cumulative_tenant_spend=cumulative_tenant_spend,
            timestamp=ts,
            prev_receipt_hash=prev_hash,
            receipt_hash=receipt_hash,
        )
        chain.append(receipt)
        return receipt

    def verify_chain(self, tenant_id: str) -> Dict[str, Any]:
        """Verify the cryptographic integrity of the expenditure receipts chain."""
        chain = self._chains.get(tenant_id, [])
        if not chain:
            return {"tenant_id": tenant_id, "valid": True, "count": 0, "root_hash": GENESIS_AUDIT_HASH}

        expected_prev = GENESIS_AUDIT_HASH
        for idx, item in enumerate(chain):
            if item.prev_receipt_hash != expected_prev:
                return {
                    "tenant_id": tenant_id,
                    "valid": False,
                    "error": f"Chain broken at receipt index {idx}: expected prev {expected_prev}, found {item.prev_receipt_hash}",
                    "failed_index": idx,
                }
            recomputed = self._compute_receipt_hash(
                tenant_id=item.tenant_id,
                seat_id=item.seat_id,
                record_id=item.record_id,
                cost_micro_dollars=item.cost_micro_dollars,
                cumulative_tenant_spend=item.cumulative_tenant_spend,
                timestamp=item.timestamp,
                prev_receipt_hash=item.prev_receipt_hash,
                secret=self.secret,
            )
            if not hmac.compare_digest(recomputed, item.receipt_hash):
                return {
                    "tenant_id": tenant_id,
                    "valid": False,
                    "error": f"Hash mismatch at receipt index {idx}: recomputed {recomputed} != {item.receipt_hash}",
                    "failed_index": idx,
                }
            expected_prev = item.receipt_hash

        return {
            "tenant_id": tenant_id,
            "valid": True,
            "count": len(chain),
            "latest_receipt_hash": chain[-1].receipt_hash,
        }

    def get_chain(self, tenant_id: str) -> List[ExpenditureReceipt]:
        return list(self._chains.get(tenant_id, []))

