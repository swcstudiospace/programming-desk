"""Tool packs: load/unload, and the shared implementations behind every pack's tools.
Pack tools talk to the application's own API base (PACK_<APP>_API_BASE); without one they
report not_configured."""

from __future__ import annotations

import time
from typing import Any

import httpx

from desk_gateway.config import MAX_LIVE_TOOLS
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import HttpUpstream, not_configured, read_only_sql


async def app_tools_load(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    app = args["app"]
    pack = svc.rosters.packs.get(app)
    if pack is None:
        return failure("not_found", f"no pack named {app}", available=sorted(svc.rosters.packs))
    if ctx.short not in pack.seats:
        return failure("forbidden", f"pack {app} is not declared for seat {ctx.short}")
    if args.get("unload"):
        records = svc.store.unload_pack(ctx.short, app)
        return {"ok": True, "loaded": records, "live_tools": len(svc.rosters.surface(ctx.short, [r["app"] for r in records]))}
    current = [r["app"] for r in svc.store.pack_records(ctx.short) if r["app"] != app]
    projected = len(svc.rosters.surface(ctx.short, current)) + len(pack.tools)
    if projected > MAX_LIVE_TOOLS:
        return failure("ceiling", f"loading {app} would put {projected} tools live; the ceiling is {MAX_LIVE_TOOLS}. Unload a pack first")
    records = svc.store.load_pack(ctx.short, app, args["task_id"])
    return {
        "ok": True,
        "loaded": records,
        "tools": sorted(pack.tools),
        "live_tools": len(svc.rosters.surface(ctx.short, [r["app"] for r in records])),
        "note": "the pack's tools appear on the next tools/list; if Grok Bot does not refresh, enable the pack connector at /mcp/<seat>/packs/<app>",
    }


def _api(ctx: ToolContext) -> HttpUpstream:
    app = ctx.spec.pack or ""
    base = ctx.services.settings.pack_api_bases.get(app, "")
    return HttpUpstream(f"{app} api", base, timeout=10.0, ephemeral=True)


async def api_smoke(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return not_configured(f"{ctx.spec.pack} API base")
    env = args.get("environment", "staging")
    started = time.monotonic()
    result = await api.request("GET", "/health", headers={"X-Desk-Environment": env})
    ms = round((time.monotonic() - started) * 1000, 1)
    if result.get("error"):
        return {**result, "ms": ms, "environment": env}
    return {"ok": True, "environment": env, "status": result.get("status"), "ms": ms, "body": result.get("body")}


async def supabase_query(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    problem = read_only_sql(args["sql"])
    if problem:
        return failure("invalid_sql", problem)
    api = _api(ctx)
    if not api.configured:
        return {"rows": [], **not_configured(f"{ctx.spec.pack} API base")}
    return await api.request("POST", "/desk/query", json={"sql": args["sql"], "limit": int(args.get("limit", 50))})


async def push_test(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return not_configured(f"{ctx.spec.pack} API base")
    body = {"platform": args["platform"], "device_label": args["device_label"], "title": args.get("title"), "body": args.get("body"), "test_only": True}
    result = await api.request("POST", "/desk/push-test", json=body)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "push test failed"))
    return {"ok": True, "result": result.get("body")}


async def feature_flags(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return {"flags": {}, **not_configured(f"{ctx.spec.pack} API base")}
    result = await api.request("GET", "/desk/flags", params={"environment": args.get("environment", "staging")})
    return result if result.get("error") else {"flags": result.get("body")}


async def crash_reports(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return {"groups": [], **not_configured(f"{ctx.spec.pack} API base")}
    params = {k: v for k, v in {"platform": args.get("platform"), "since_hours": args.get("since_hours", 24), "limit": args.get("limit", 10)}.items() if v is not None}
    result = await api.request("GET", "/desk/crashes", params=params)
    return result if result.get("error") else {"groups": result.get("body")}


async def scoreboard_get(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return {"lanes": [], **not_configured(f"{ctx.spec.pack} API base")}
    result = await api.request("GET", "/api/scoreboard", params={"limit": int(args.get("limit", 20))})
    return result if result.get("error") else {"lanes": result.get("body")}


async def store_listing_get(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return not_configured(f"{ctx.spec.pack} API base")
    result = await api.request("GET", "/desk/store-listing", params={"store": args["store"], "locale": args.get("locale", "en-AU")})
    return result if result.get("error") else {"listing": result.get("body")}


async def render_job_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    if not api.configured:
        return not_configured(f"{ctx.spec.pack} API base")
    try:
        result = await api.request("GET", f"/api/render-jobs/{args['job_id']}", headers={"X-Desk-Environment": args.get("environment", "staging")})
    except httpx.HTTPError as exc:
        return failure("upstream_error", type(exc).__name__)
    return result if result.get("error") else {"job": result.get("body")}
