"""Automated dead-letter queue (DLQ) replay orchestrator with exponential backoff and poison quarantine (REQ-CHAOS-004).

Capabilities:
- Replays items from store intake DLQ with exponential backoff and jitter.
- Detects repeated execution failures (poison pill payloads).
- Quarantines poisonous payloads to a dedicated poison vault to ensure queue unblocking.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("desk_gateway.dlq_replay")


@dataclass
class ReplayResult:
    item_id: str
    success: bool
    attempts: int
    duration_sec: float
    error: str | None = None
    quarantined: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "success": self.success,
            "attempts": self.attempts,
            "duration_sec": self.duration_sec,
            "error": self.error,
            "quarantined": self.quarantined,
        }


class DLQReplayOrchestrator:
    """Orchestrates DLQ retries with exponential backoff, jitter, and poison quarantine (REQ-CHAOS-004)."""

    def __init__(
        self,
        store: Any = None,
        max_attempts: int = 3,
        base_backoff_sec: float = 0.05,
        max_backoff_sec: float = 1.0,
        jitter_factor: float = 0.2,
    ) -> None:
        self.store = store
        self.max_attempts = max_attempts
        self.base_backoff_sec = base_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.jitter_factor = jitter_factor
        self._lock = threading.RLock()
        self._poison_vault: dict[str, dict[str, Any]] = {}
        self._replay_history: list[dict[str, Any]] = []

    def calculate_backoff(self, attempt: int) -> float:
        """Compute exponential backoff with randomized jitter."""
        exponential = min(self.max_backoff_sec, self.base_backoff_sec * (2 ** attempt))
        jitter = exponential * self.jitter_factor * (random.random() * 2 - 1)
        return max(0.01, exponential + jitter)

    def quarantine_poison_pill(self, item: dict[str, Any], reason: str) -> None:
        """Move unrecoverable / corrupted payload into poison quarantine."""
        item_id = item.get("id") or f"poison-{int(time.time() * 1000)}"
        with self._lock:
            record = {
                "item": item,
                "reason": reason,
                "quarantined_at": time.time(),
            }
            self._poison_vault[item_id] = record
            logger.error("DLQ POISON PILL QUARANTINED: Item '%s': %s", item_id, reason)

            # Remove from active store DLQ if store is present
            if self.store and hasattr(self.store, "intake_dlq_remove"):
                self.store.intake_dlq_remove(item_id)

    async def replay_item(
        self,
        item: dict[str, Any],
        handler: Callable[[dict[str, Any]], Any],
    ) -> ReplayResult:
        """Replay an individual DLQ item with retry backoff and poison pill detection."""
        item_id = str(item.get("id") or "unknown")
        start_time = time.time()
        last_error = None

        for attempt in range(self.max_attempts):
            try:
                # If async handler
                if inspect.iscoroutinefunction(handler):
                    await handler(item)
                else:
                    handler(item)

                duration = time.time() - start_time
                # Remove from store DLQ upon success
                if self.store and hasattr(self.store, "intake_dlq_remove"):
                    self.store.intake_dlq_remove(item_id)

                res = ReplayResult(
                    item_id=item_id,
                    success=True,
                    attempts=attempt + 1,
                    duration_sec=duration,
                )
                with self._lock:
                    self._replay_history.append(res.to_dict())
                return res

            except Exception as exc:
                last_error = str(exc)
                logger.warning("DLQ replay attempt %d/%d for '%s' failed: %s", attempt + 1, self.max_attempts, item_id, exc)
                if attempt < self.max_attempts - 1:
                    delay = self.calculate_backoff(attempt)
                    await asyncio.sleep(delay)

        # Exceeded max attempts -> poison pill quarantine
        duration = time.time() - start_time
        self.quarantine_poison_pill(item, reason=f"Exceeded {self.max_attempts} attempts: {last_error}")

        res = ReplayResult(
            item_id=item_id,
            success=False,
            attempts=self.max_attempts,
            duration_sec=duration,
            error=last_error,
            quarantined=True,
        )
        with self._lock:
            self._replay_history.append(res.to_dict())
        return res

    async def replay_all_dlq(self, handler: Callable[[dict[str, Any]], Any]) -> list[ReplayResult]:
        """Replay all active items currently in store DLQ."""
        if not self.store or not hasattr(self.store, "intake_dlq_list"):
            return []

        dlq_items = self.store.intake_dlq_list()
        results: list[ReplayResult] = []

        for item in dlq_items:
            res = await self.replay_item(item, handler)
            results.append(res)

        return results

    def get_quarantined_items(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._poison_vault.values())

    def clear_quarantined(self) -> int:
        with self._lock:
            c = len(self._poison_vault)
            self._poison_vault.clear()
            return c
