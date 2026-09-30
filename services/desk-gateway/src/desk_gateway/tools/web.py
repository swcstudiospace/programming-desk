"""WEB tools: Vercel, preview evidence, bundle secret scan."""

from __future__ import annotations

import hashlib
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from desk_gateway.repo import safe_path
from desk_gateway.tools import ToolContext, failure


def _project_allowed(ctx: ToolContext, project: str) -> dict[str, Any] | None:
    if not ctx.services.vercel.http.configured:
        return failure("not_configured", "Vercel is not configured on the gateway")
    if not ctx.services.vercel.allowed(project):
        return failure("forbidden", f"{project} is not in the gateway's Vercel project allowlist")
    return None


async def vercel_deployments(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    blocked = _project_allowed(ctx, args["project"])
    if blocked:
        return {"deployments": [], **blocked}
    if args.get("deployment_id"):
        result = await ctx.services.vercel.deployment(args["deployment_id"])
        return result if result.get("error") else {"deployment": result.get("body")}
    result = await ctx.services.vercel.deployments(args["project"], int(args.get("limit", 10)))
    if result.get("error"):
        return {"deployments": [], **result}
    body = result.get("body") or {}
    items = [
        {k: d.get(k) for k in ("uid", "state", "target", "url", "created", "meta")} for d in body.get("deployments") or []
    ]
    return {"deployments": items}


async def vercel_promote(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    blocked = _project_allowed(ctx, args["project"])
    if blocked:
        return blocked
    result = await ctx.services.vercel.promote(args["project"], args["deployment_id"])
    if result.get("error"):
        return failure(result["error"], result.get("reason", "promote failed"))
    return {"ok": True, "approval_id": args["approval_id"], "result": result.get("body")}


async def vercel_rollback(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    blocked = _project_allowed(ctx, args["project"])
    if blocked:
        return blocked
    result = await ctx.services.vercel.rollback(args["project"], args["deployment_id"])
    if result.get("error"):
        return failure(result["error"], result.get("reason", "rollback failed"))
    return {"ok": True, "approval_id": args["approval_id"], "result": result.get("body")}


async def preview_check(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    url = args["url"]
    host = urlparse(url).hostname or ""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            resp = await client.get(url, headers={"User-Agent": "desk-gateway/preview-check"})
    except httpx.HTTPError as exc:
        return failure("upstream_error", f"fetch failed: {type(exc).__name__}")
    ms = (time.monotonic() - started) * 1000
    body = resp.content[:2_000_000]
    return {
        "url": url,
        "host": host,
        "status": resp.status_code,
        "expected": int(args.get("expect_status", 200)),
        "matches": resp.status_code == int(args.get("expect_status", 200)),
        "ms": round(ms, 1),
        "content_type": resp.headers.get("content-type"),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "redirect": resp.headers.get("location"),
    }


async def bundle_secret_scan(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    paths = [p for p in args["paths"] if safe_path(p)]
    if not paths:
        return failure("invalid_args", "no acceptable paths")
    missing = [p for p in paths if not (repo.dir / p).exists()]
    if missing:
        return failure("not_found", f"not in the checkout: {missing[:5]}")
    result = await repo.run_gate("check_secrets.py", ["--files", *paths], timeout=60)
    return {"ok": result["exit_code"] == 0, "gate": "G-3", "exit_code": result["exit_code"], "output": result["stdout"][-3000:]}
