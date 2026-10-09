"""Tool backends. `contracts/tool-rosters/*.yaml` names each backend as `<module>.<function>`;
`dispatch()` resolves that name to a coroutine `fn(ctx, args) -> dict`."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from desk_gateway.audit import Audit
from desk_gateway.config import Settings
from desk_gateway.live import LiveDesk
from desk_gateway.repo import Repo
from desk_gateway.rosters import Rosters, SeatRoster, ToolSpec
from desk_gateway.store import Store
from desk_gateway.upstreams import (
    AgentBus,
    AppStoreConnect,
    Dragonfly,
    GitHub,
    Greptile,
    Greptime,
    Hindsight,
    PlayConsole,
    Railway,
    RAGFlow,
    Substrate,
    Timescale,
    Vercel,
)


@dataclass
class Services:
    settings: Settings
    store: Store
    rosters: Rosters
    repo: Repo
    substrate: Substrate
    audit: Audit
    live: LiveDesk
    agent_bus: AgentBus
    greptime: Greptime
    timescale: Timescale
    dragonfly: Dragonfly
    hindsight: Hindsight
    ragflow: RAGFlow
    railway: Railway
    vercel: Vercel
    greptile: Greptile
    github: GitHub
    play: PlayConsole
    asc: AppStoreConnect

    @classmethod
    def build(cls, settings: Settings, store: Store, rosters: Rosters) -> Services:
        substrate = Substrate(settings)
        return cls(
            settings=settings,
            store=store,
            rosters=rosters,
            repo=Repo(settings),
            substrate=substrate,
            audit=Audit(store, substrate),
            live=LiveDesk(store),
            agent_bus=AgentBus(settings),
            greptime=Greptime(settings),
            timescale=Timescale(settings),
            dragonfly=Dragonfly(settings),
            hindsight=Hindsight(settings),
            ragflow=RAGFlow(settings),
            railway=Railway(settings),
            vercel=Vercel(settings),
            greptile=Greptile(settings),
            github=GitHub(settings),
            play=PlayConsole(settings),
            asc=AppStoreConnect(settings),
        )

    async def aclose(self) -> None:
        """Close pooled HTTP clients. Safe when a client was never opened."""
        closers = []
        seen: set[int] = set()
        for name in (
            "substrate",
            "agent_bus",
            "greptime",
            "timescale",
            "hindsight",
            "ragflow",
            "railway",
            "vercel",
            "greptile",
            "github",
            "play",
            "asc",
        ):
            obj = getattr(self, name, None)
            http = getattr(obj, "http", None) if obj is not None else None
            close = getattr(http, "aclose", None)
            if close is None or id(http) in seen:
                continue
            seen.add(id(http))
            closers.append(close())
        if closers:
            await asyncio.gather(*closers)


@dataclass
class ToolContext:
    services: Services
    seat: SeatRoster
    spec: ToolSpec

    @property
    def short(self) -> str:
        return self.seat.short

    @property
    def bot_id(self) -> str:
        return self.seat.bot_id


ToolFn = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


def resolve(backend: str) -> ToolFn:
    module_name, _, func = backend.partition(".")
    module = importlib.import_module(f"desk_gateway.tools.{module_name}")
    fn = getattr(module, func, None)
    if fn is None:
        raise LookupError(backend)
    return fn


def failure(code: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"error": code, "reason": reason, **extra}


def unwrap_content(result: dict[str, Any]) -> Any:
    """The first parsed JSON block of a Substrate.call_tool result, or the raw content if it
    was not a list. Call only after result.get("error") has already been checked: a
    transport-level failure has no content worth unwrapping."""
    content = result.get("content")
    return content[0] if isinstance(content, list) and content else content
