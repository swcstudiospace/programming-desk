"""Load the tool rosters and packs from contracts/ and turn them into per-seat surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from desk_gateway.config import MAX_LIVE_TOOLS, PACK_MAX_TOOLS, SEATS


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str
    gates: tuple[str, ...]
    description: str
    backend: str
    input_schema: dict[str, Any]
    pack: str | None = None

    @property
    def read_only(self) -> bool:
        return self.kind == "read"


@dataclass
class SeatRoster:
    short: str
    bot_id: str
    endpoint: str
    scope: str
    version: str
    memory_own: str
    memory_shared: tuple[str, ...]
    packs_allowed: bool
    tools: dict[str, ToolSpec] = field(default_factory=dict)


@dataclass
class PackSpec:
    app: str
    title: str
    version: str
    seats: tuple[str, ...]
    tools: dict[str, ToolSpec] = field(default_factory=dict)


class RosterError(ValueError):
    pass


def _tool(raw: dict[str, Any], pack: str | None = None) -> ToolSpec:
    for key in ("name", "kind", "description", "backend", "input"):
        if key not in raw:
            raise RosterError(f"tool {raw.get('name', '?')} is missing {key}")
    if raw["kind"] not in {"read", "write"}:
        raise RosterError(f"tool {raw['name']} has kind {raw['kind']!r}")
    gates = tuple(raw.get("gates") or [])
    if not set(gates) <= {"g5", "g6"}:
        raise RosterError(f"tool {raw['name']} has unknown gates {gates}")
    required = set(raw["input"].get("required") or [])
    if "g5" in gates and not {"rollback_plan", "approval_id"} <= required:
        raise RosterError(f"tool {raw['name']} is g5 but does not require rollback_plan and approval_id")
    if "g6" in gates and "approval_id" not in required:
        raise RosterError(f"tool {raw['name']} is g6 but does not require approval_id")
    return ToolSpec(
        name=raw["name"],
        kind=raw["kind"],
        gates=gates,
        description=" ".join(str(raw["description"]).split()),
        backend=raw["backend"],
        input_schema=raw["input"],
        pack=pack,
    )


class Rosters:
    def __init__(self, seats: dict[str, SeatRoster], packs: dict[str, PackSpec]) -> None:
        self.seats = seats
        self.packs = packs

    @classmethod
    def load(cls, contracts_dir: Path) -> Rosters:
        rosters_dir = contracts_dir / "tool-rosters"
        packs_dir = contracts_dir / "tool-packs"
        core_raw = yaml.safe_load((rosters_dir / "_core.yaml").read_text(encoding="utf-8"))
        core = [_tool(t) for t in core_raw.get("tools") or []]
        seats: dict[str, SeatRoster] = {}
        for path in sorted(rosters_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            short = raw["short"]
            if SEATS.get(short) != raw["seat"]:
                raise RosterError(f"{path.name}: seat {raw['seat']} does not match short {short}")
            if raw.get("endpoint") != f"/mcp/{short}":
                raise RosterError(f"{path.name}: endpoint must be /mcp/{short}")
            tools: dict[str, ToolSpec] = {}
            for spec in (core if raw.get("core") else []) + [_tool(t) for t in raw.get("tools") or []]:
                if spec.name in tools:
                    raise RosterError(f"{path.name}: duplicate tool {spec.name}")
                tools[spec.name] = spec
            if not 10 <= len(tools) <= 15:
                raise RosterError(f"{path.name}: {len(tools)} tools; the band is 10-15")
            banks = raw.get("memory_banks") or {}
            seats[short] = SeatRoster(
                short=short,
                bot_id=raw["seat"],
                endpoint=raw["endpoint"],
                scope=raw.get("scope") or f"seat:{short}",
                version=str(raw.get("version") or "0"),
                memory_own=banks.get("own") or f"pd-{short}",
                memory_shared=tuple(banks.get("shared") or ["pd-desk"]),
                packs_allowed=bool(raw.get("packs_allowed")),
                tools=tools,
            )
        missing = set(SEATS) - set(seats)
        if missing:
            raise RosterError(f"no roster for seats: {sorted(missing)}")
        packs: dict[str, PackSpec] = {}
        if packs_dir.is_dir():
            for path in sorted(packs_dir.glob("*.yaml")):
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                app = raw["app"]
                tools = {}
                for t in raw.get("tools") or []:
                    spec = _tool(t, pack=app)
                    if not spec.name.startswith(f"{app}_"):
                        raise RosterError(f"{path.name}: tool {spec.name} must be prefixed {app}_")
                    tools[spec.name] = spec
                if not 1 <= len(tools) <= PACK_MAX_TOOLS:
                    raise RosterError(f"{path.name}: {len(tools)} tools; a pack holds 1-{PACK_MAX_TOOLS}")
                packs[app] = PackSpec(
                    app=app,
                    title=str(raw.get("title") or app),
                    version=str(raw.get("version") or "0"),
                    seats=tuple(raw.get("seats") or []),
                    tools=tools,
                )
        return cls(seats, packs)

    def surface(self, short: str, loaded_packs: list[str]) -> dict[str, ToolSpec]:
        seat = self.seats[short]
        tools = dict(seat.tools)
        for app in loaded_packs:
            pack = self.packs.get(app)
            if not pack:
                continue
            for name, spec in pack.tools.items():
                if name not in tools:
                    tools[name] = spec
        if len(tools) > MAX_LIVE_TOOLS:
            raise RosterError(f"{short}: {len(tools)} live tools exceeds {MAX_LIVE_TOOLS}")
        return tools

    def pack_surface(self, short: str, app: str) -> dict[str, ToolSpec]:
        pack = self.packs.get(app)
        if not pack or short not in pack.seats:
            return {}
        return dict(pack.tools)
