"""Audit: every tool call becomes one redacted event, mirrored locally and sent to the substrate."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from desk_gateway.redact import redact_value
from desk_gateway.store import Store
from desk_gateway.upstreams import Substrate

logger = logging.getLogger("desk_gateway.audit")


def args_digest(arguments: dict[str, Any]) -> str:
    canonical = json.dumps(redact_value(arguments), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class Audit:
    def __init__(self, store: Store, substrate: Substrate) -> None:
        self.store = store
        self.substrate = substrate

    def tool_event(
        self,
        *,
        seat: str,
        tool: str,
        arguments: dict[str, Any],
        ok: bool,
        ms: float,
        error: str | None,
        gates: tuple[str, ...],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "seat": seat,
            "tool": tool,
            "ok": ok,
            "ms": round(ms, 1),
            "args_digest": args_digest(arguments),
        }
        if error:
            payload["error"] = error
        if gates:
            payload["gates"] = list(gates)
            payload["approval_id"] = arguments.get("approval_id")
            payload["rollback_plan"] = redact_value(arguments.get("rollback_plan"))
        event = {
            "kind": "tool.call",
            "summary": f"{seat} {tool} {'ok' if ok else 'error'}",
            "graph_id": arguments.get("graph_id"),
            "payload": payload,
            "actor": "agent",
            "ts_gateway": time.time(),
        }
        self.store.audit_append(event)
        return event

    async def send(self, event: dict[str, Any]) -> None:
        body = {k: v for k, v in event.items() if k != "ts_gateway" and v is not None}
        try:
            result = await asyncio.wait_for(self.substrate.emit(body), 6)
            if result.get("error") and result["error"] != "not_configured":
                logger.warning("audit emit failed: %s", result.get("reason"))
        except Exception as exc:
            logger.warning("audit emit failed: %s", exc)

    def fire_and_forget(self, event: dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.send(event))
