"""The eight core tools every seat carries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from desk_gateway import __version__
from desk_gateway.config import (
    DEFAULT_RAGFLOW_DATASETS,
    DOCS_LOOKUP_BUDGET_SEC,
    DOCS_RETRIEVAL_BUDGET_SEC,
    MAX_LIVE_TOOLS,
    RECALL_BANK_TIMEOUT_SEC,
    SEAT_LABEL,
    SEATS,
    TOOL_DEADLINE_SEC,
)
from desk_gateway.redact import contains_secret, redact_text
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import is_unknown_dataset, not_configured

logger = logging.getLogger(__name__)

BRIEF_TTL_SEC = 300
_brief_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def brief(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    key = f"{ctx.short}:{args.get('graph_id') or ''}:{args.get('task_id') or ''}"
    now = time.time()
    if not args.get("refresh"):
        cached = _brief_cache.get(key)
        if cached and now - cached[0] < BRIEF_TTL_SEC:
            return {**cached[1], "cached": True}
    svc = ctx.services
    # The brief costs the slower of the two calls, not the sum.
    substrate_result, recall_result = await asyncio.gather(
        svc.substrate.brief(repo=None, graph_id=args.get("graph_id")),
        memory_recall(ctx, {"query": args.get("task_id") or args.get("graph_id") or "current work", "limit": 5, "include_shared": True}),
        return_exceptions=True,
    )
    if isinstance(substrate_result, BaseException):
        substrate = {"error": "upstream_error", "reason": redact_text(str(substrate_result))[:300], "plane": "substrate"}
    else:
        substrate = substrate_result
    if isinstance(recall_result, BaseException):
        recall = {"banks": [], "results": [], "error": "upstream_error", "reason": redact_text(str(recall_result))[:300], "plane": "hindsight"}
    else:
        recall = recall_result
    intake = svc.store.intake_counts() if ctx.short == "lead" else None
    packs = svc.store.pack_records(ctx.short)
    result = {
        "seat": SEAT_LABEL[ctx.short],
        "generated_at": now,
        "substrate": substrate,
        "recall": recall,
        "loaded_packs": packs,
        "intake_queue": intake,
        "reminders": [
            "Run desk_ownership_resolve before the first edit.",
            "A completion claim needs a receipt that passes desk_receipt_check.",
        ],
    }
    if not substrate.get("error"):
        _brief_cache[key] = (now, result)
    svc.store.touch_seat(ctx.short)
    return result


def _docs_budgets(settings: Any) -> tuple[float, float]:
    lookup = max(0.0, float(getattr(settings, "docs_lookup_budget_sec", DOCS_LOOKUP_BUDGET_SEC)))
    retrieval = max(0.0, float(getattr(settings, "docs_retrieval_budget_sec", DOCS_RETRIEVAL_BUDGET_SEC)))
    # Stay inside the tool wrapper's deadline so a slow phase is named ragflow,
    # not reported as the outer "deadline" error.
    slack = min(0.5, TOOL_DEADLINE_SEC * 0.05) if TOOL_DEADLINE_SEC > 0 else 0.0
    ceiling = max(0.0, TOOL_DEADLINE_SEC - slack)
    if lookup > ceiling:
        lookup = ceiling
    remaining = max(0.0, ceiling - lookup)
    if retrieval > remaining:
        retrieval = remaining
    return lookup, retrieval


def _wanted_datasets(settings: Any, args: dict[str, Any]) -> list[str]:
    configured = getattr(settings, "ragflow_datasets", None)
    names = list(configured) if configured else list(DEFAULT_RAGFLOW_DATASETS)
    repo = args.get("repo")
    if isinstance(repo, str) and repo:
        short = repo.split("/")[-1]
        if short and short not in names:
            names.append(short)
    return names


def _ragflow_timeout(phase: str, budget: float) -> dict[str, Any]:
    return {
        "results": [],
        "error": "upstream_timeout",
        "reason": f"ragflow {phase} exceeded {budget:g}s budget",
        "plane": "ragflow",
    }


def _is_ragflow_budget(result: dict[str, Any]) -> bool:
    return result.get("plane") == "ragflow" and result.get("results") == [] and "exceeded" in str(result.get("reason") or "")


async def _within(deadline: float, coro: Any, phase: str, budget: float) -> dict[str, Any]:
    left = deadline - asyncio.get_running_loop().time()
    if left <= 0:
        if asyncio.iscoroutine(coro):
            coro.close()
        return _ragflow_timeout(phase, budget)
    try:
        return await asyncio.wait_for(coro, left)
    except TimeoutError:
        return _ragflow_timeout(phase, budget)


def _chunks(hit: dict[str, Any]) -> list[dict[str, Any]]:
    body = hit.get("body") or {}
    data = body.get("data") if isinstance(body, dict) else None
    chunks = data.get("chunks") if isinstance(data, dict) else None
    return [
        {
            "content": redact_text(str(c.get("content") or c.get("content_with_weight") or ""))[:1500],
            "document": c.get("document_keyword") or c.get("docnm_kwd"),
            "dataset_id": c.get("dataset_id") or c.get("kb_id"),
            "score": c.get("similarity"),
        }
        for c in (chunks or [])
        if isinstance(c, dict)
    ]


async def docs_search(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    if not svc.ragflow.http.configured:
        # Phase 25 adds substrate docs_search. Until then an unconfigured RAGflow
        # is not_configured, not an upstream error from a tool the substrate lacks.
        return {
            "results": [],
            "error": "not_configured",
            "state": "not_configured",
            "reason": "ragflow is not configured on the gateway; substrate docs_search is not available until Phase 25",
        }
    settings = svc.settings
    lookup_budget, retrieval_budget = _docs_budgets(settings)
    names = _wanted_datasets(settings, args)
    loop = asyncio.get_running_loop()
    slack = min(0.5, TOOL_DEADLINE_SEC * 0.05) if TOOL_DEADLINE_SEC > 0 else 0.0
    outer_end = loop.time() + max(0.0, TOOL_DEADLINE_SEC - slack)
    lookup_started = loop.time()
    lookup_deadline = min(lookup_started + lookup_budget, outer_end)

    resolved = await _within(lookup_deadline, svc.ragflow.resolve_dataset_ids(names), "dataset lookup", lookup_budget)
    unused_lookup = max(0.0, lookup_budget - (loop.time() - lookup_started))
    if _is_ragflow_budget(resolved):
        return resolved
    if resolved.get("error"):
        return {"results": [], **resolved, "plane": "ragflow"}

    def _empty(missing: list[str]) -> dict[str, Any]:
        return {
            "results": [],
            "reason": "no matching datasets in RAGFlow",
            "wanted": names,
            "missing_datasets": missing,
            "plane": "ragflow",
        }

    ids = list(resolved.get("ids") or [])
    missing = list(resolved.get("missing") or [])
    if not ids:
        return _empty(missing)

    limit = args.get("limit", 8)
    retrieval_started = loop.time()
    retrieval_deadline = min(retrieval_started + retrieval_budget, outer_end)
    hit = await _within(retrieval_deadline, svc.ragflow.retrieve(args["query"], ids, limit), "retrieval", retrieval_budget)
    unused_retrieval = max(0.0, retrieval_budget - (loop.time() - retrieval_started))
    if not _is_ragflow_budget(hit) and is_unknown_dataset(hit):
        # Retrieval time does not consume the lookup allowance. The refresh gets
        # whatever lookup budget was left when the first list finished.
        refresh_allowance = min(unused_lookup, max(0.0, outer_end - loop.time()))
        resolved = await _within(
            loop.time() + refresh_allowance,
            svc.ragflow.resolve_dataset_ids(names, refresh=True),
            "dataset lookup",
            lookup_budget,
        )
        if _is_ragflow_budget(resolved):
            return resolved
        if resolved.get("error"):
            return {"results": [], **resolved, "plane": "ragflow"}
        ids = list(resolved.get("ids") or [])
        missing = list(resolved.get("missing") or [])
        if not ids:
            return _empty(missing)
        retry_allowance = min(unused_retrieval, max(0.0, outer_end - loop.time()))
        hit = await _within(
            loop.time() + retry_allowance,
            svc.ragflow.retrieve(args["query"], ids, limit),
            "retrieval",
            retrieval_budget,
        )
    if _is_ragflow_budget(hit):
        return hit
    if hit.get("error"):
        return {"results": [], **hit, "plane": "ragflow"}
    reply: dict[str, Any] = {
        "results": _chunks(hit),
        "source": "ragflow",
        "note": "a chunk is not a repository fact until the file is opened",
    }
    if missing:
        reply["missing_datasets"] = missing
    return reply


def _plane_verdict(plane: str, result: dict[str, Any]) -> dict[str, Any]:
    """One plane's retain outcome. Shape is stable for the later Hindsight-via-substrate route."""
    error = result.get("error")
    if error == "memory_denied":
        return {
            "plane": plane,
            "state": "denied",
            "reason": result.get("reason"),
            "writer": result.get("writer"),
        }
    if error == "not_configured":
        return {"plane": plane, "state": "not_configured", "reason": result.get("reason")}
    if error:
        return {"plane": plane, "state": "error", "reason": result.get("reason") or error}
    return {"plane": plane, "state": "stored", "reason": None}


async def memory_retain(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not args.get("receipt_path") and not args.get("source"):
        return failure("evidence_required", "retain needs receipt_path or source")
    if contains_secret(args["content"]):
        return failure("secret_refused", "content contains a credential shape; remove it and retry")
    svc = ctx.services
    tags = [f"seat:{ctx.short}", *(args.get("tags") or [])]
    for key in ("graph_id", "task_id", "receipt_path", "source"):
        if args.get(key):
            tags.append(f"{key}:{args[key]}")
    results: dict[str, Any] = {}
    if svc.hindsight.http.configured:
        results["hindsight"] = await svc.hindsight.retain(ctx.seat.memory_own, args["content"], tags, context=f"Programming Desk {SEAT_LABEL[ctx.short]}")
    else:
        results["hindsight"] = not_configured("hindsight")
    graph_id = args.get("graph_id")
    if graph_id:
        scope = f"graph:{graph_id}"
        kind = "decision"
    else:
        scope = "agent:grok-bot"
        kind = "fact"
    results["substrate"] = await svc.substrate.call_tool(
        "memory_write",
        {
            "scope": scope,
            "kind": kind,
            "text": f"[{ctx.seat.memory_own}] {args['content']}",
            "trust": "agent-claimed",
            "ttl": "permanent",
        },
        timeout=8,
    )
    verdicts = [_plane_verdict(plane, result) for plane, result in results.items()]
    for verdict in verdicts:
        if verdict["state"] == "stored":
            continue
        logger.warning(
            "memory plane not stored seat=%s plane=%s state=%s reason=%s writer=%s",
            ctx.short,
            verdict["plane"],
            verdict["state"],
            verdict.get("reason") or "",
            verdict.get("writer") or "",
        )
    stored = any(verdict["state"] == "stored" for verdict in verdicts)
    partial = stored and any(verdict["state"] != "stored" for verdict in verdicts)
    if not stored:
        return failure(
            "memory_unavailable",
            "no memory plane accepted the write",
            results=results,
            verdicts=verdicts,
            ok=False,
            partial=False,
        )
    return {"ok": True, "partial": partial, "bank": ctx.seat.memory_own, "results": results, "verdicts": verdicts}


def _bank_row(bank: str, hit: dict[str, Any], status: str) -> dict[str, Any]:
    http_status = hit.get("status") if isinstance(hit.get("status"), int) else None
    row = {"bank": bank, **hit, "status": status, "plane": hit.get("plane") or "hindsight"}
    if http_status is not None:
        row["http_status"] = http_status
    return row


async def memory_recall(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    banks = [ctx.seat.memory_own] + (list(ctx.seat.memory_shared) if args.get("include_shared", True) else [])
    out: dict[str, Any] = {"banks": banks, "results": []}
    if svc.hindsight.http.configured:
        timeout = float(getattr(svc.settings, "recall_bank_timeout_sec", RECALL_BANK_TIMEOUT_SEC))

        async def one(bank: str) -> dict[str, Any]:
            try:
                hit = await asyncio.wait_for(
                    svc.hindsight.recall(bank, args["query"], args.get("limit", 8)),
                    timeout,
                )
            except TimeoutError:
                return {
                    "bank": bank,
                    "status": "timeout",
                    "error": "upstream_timeout",
                    "reason": f"hindsight bank {bank} exceeded the {timeout:g}s recall budget",
                    "plane": "hindsight",
                }
            except Exception as exc:
                return {
                    "bank": bank,
                    "status": "error",
                    "error": "upstream_error",
                    "reason": redact_text(str(exc))[:300],
                    "plane": "hindsight",
                }
            if not isinstance(hit, dict):
                return {"bank": bank, "status": "error", "error": "upstream_error", "reason": "hindsight recall returned no result", "plane": "hindsight"}
            if hit.get("error"):
                status = "timeout" if hit.get("error") == "upstream_timeout" else "error"
                return _bank_row(bank, hit, status)
            return _bank_row(bank, hit, "ok")

        out["results"] = list(await asyncio.gather(*(one(bank) for bank in banks)))
        return out
    via = await svc.substrate.call_tool("memory_search", {"query": args["query"], "limit": args.get("limit", 8)}, timeout=8)
    if via.get("error"):
        out["reason"] = via.get("reason")
        out["error"] = via["error"]
    else:
        out["results"] = via.get("content") or []
        out["source"] = "substrate"
    return out


async def ownership_resolve(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    if not svc.repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    manifest_text = await svc.repo.show("ownership.yaml")
    if manifest_text is None:
        return failure("upstream_error", "ownership.yaml could not be read at origin/main")
    try:
        gate = svc.repo.gate_module("check_ownership")
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(manifest_text)
            tmp = Path(fh.name)
        try:
            manifest = gate.load_manifest(tmp)
        finally:
            tmp.unlink(missing_ok=True)
    except Exception as exc:
        return failure("upstream_error", f"ownership gate could not load: {redact_text(str(exc))[:200]}")
    results = []
    for path in args["paths"]:
        owner, contract = gate.resolve_owner(path, manifest)
        results.append(
            {
                "path": path,
                "owner": owner,
                "contract_surface": bool(contract),
                "mine": owner == ctx.bot_id,
                "unowned": owner is None,
            }
        )
    return {"results": results, "ref": await svc.repo.head_sha()}


async def receipt_check(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    if not svc.repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    receipt = args.get("receipt")
    if receipt is None and args.get("receipt_path"):
        text = await svc.repo.show(args["receipt_path"])
        if text is None:
            return failure("not_found", f"{args['receipt_path']} is not on {svc.repo.main_ref}")
        try:
            receipt = json.loads(text)
        except ValueError:
            return failure("invalid_receipt", "receipt is not valid JSON")
    if receipt is None:
        return failure("invalid_args", "receipt or receipt_path is required")
    if contains_secret(json.dumps(receipt)):
        return failure("secret_refused", "receipt contains a credential shape (PD-4); a receipt that leaks a token is a failed receipt")
    return await svc.repo.receipt_check(receipt, args["bot"], bool(args.get("strict", True)), args.get("receipt_path"))


async def event_emit(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload = args.get("payload") or {}
    if len(json.dumps(payload)) > 4096:
        return failure("payload_too_large", "payload exceeds 4 KB")
    event = {
        "kind": "note",
        "summary": f"{SEAT_LABEL[ctx.short]} {args['kind']}",
        "graph_id": args.get("graph_id"),
        "payload": {"seat": ctx.short, "event": args["kind"], "task_id": args.get("task_id"), **payload},
        "actor": "agent",
    }
    ctx.services.store.audit_append({**event, "ts_gateway": time.time()})
    # The live view is a local observer: it reflects what the seat reported even when substrate
    # rejects the event below, and a broken view must never fail the tool call.
    try:
        ctx.services.live.reported(ctx.short, args["kind"], args.get("task_id"), payload)
    except Exception:
        logger.exception("live desk update failed")
    result = await ctx.services.substrate.emit({k: v for k, v in event.items() if v is not None})
    if result.get("error"):
        return failure(result["error"], result.get("reason", "event not accepted"), local_mirror=True)
    return {"ok": True, "substrate": result.get("body")}


async def doctor(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    action = args["action"]
    store = svc.store
    if action == "register":
        if not args.get("agent_uuid") and not args.get("channel_id"):
            return failure("invalid_args", "register needs agent_uuid (any seat) or channel_id (LEAD)")
        if args.get("channel_id") and ctx.short != "lead":
            return failure("forbidden", "only LEAD registers the channel id")
        roster = store.register_seat(ctx.short, agent_uuid=args.get("agent_uuid"), channel_id=args.get("channel_id"), tool_count=len(ctx.seat.tools))
        registered = sorted(s for s, e in roster["seats"].items() if e.get("agent_uuid"))
        return {"ok": True, "registered": registered, "channel_id": roster.get("channel_id"), "missing": sorted(set(SEATS) - set(registered))}

    if action in {"install_prompt", "repair"}:
        rendered = await render_prompt(ctx)
        if rendered.get("error"):
            return rendered
        sha = rendered["sha256"]
        store.touch_seat(ctx.short, expected_prompt_sha256=sha)
        return {
            "ok": True,
            "seat": SEAT_LABEL[ctx.short],
            "sha256": sha,
            "roster_version": rendered["roster_version"],
            "prompt": rendered["prompt"],
            "install_path_hint": "/home/box/agent-data/agents/<your-uuid>/SYSTEM_PROMPT.xml",
        }

    roster = store.roster()
    seats = roster.get("seats") or {}
    mine = seats.get(ctx.short) or {}
    checks: dict[str, dict[str, Any]] = {}
    expected_sha = mine.get("expected_prompt_sha256")
    given_sha = args.get("prompt_sha256")
    checks["prompt"] = {
        "green": bool(expected_sha and given_sha and expected_sha == given_sha),
        "detail": "sha256 matches the rendered prompt" if expected_sha and given_sha and expected_sha == given_sha else ("run install_prompt, write SYSTEM_PROMPT.xml, then check with prompt_sha256" if not given_sha else "installed prompt differs from the rendered one"),
    }
    declared = await _declared_skills(ctx)
    installed = set(args.get("installed_skills") or [])
    missing_skills = sorted(s for s in declared if s not in installed) if installed else declared
    checks["skills"] = {"green": bool(installed) and not missing_skills, "declared": declared, "missing": missing_skills, "detail": "pass installed_skills (names from the / menu) to verify" if not installed else ""}
    mem = await svc.hindsight.health() if svc.hindsight.http.configured else await svc.substrate.health()
    checks["memory"] = {"green": bool(mem.get("ok")), "plane": "hindsight" if svc.hindsight.http.configured else "substrate", "detail": mem.get("reason", "")}
    live = len(svc.rosters.surface(ctx.short, store.packs_for(ctx.short)))
    base = len(ctx.seat.tools)
    checks["tools"] = {"green": 10 <= base <= 15 and live <= MAX_LIVE_TOOLS, "roster": base, "live": live, "contract": f"contracts/tool-rosters/{ctx.short}.yaml", "version": ctx.seat.version}
    checks["connector"] = {"green": True, "detail": "this call authenticated as the seat; a call on another seat's endpoint returns 403"}
    registered = sorted(s for s, e in seats.items() if e.get("agent_uuid"))
    checks["roster"] = {"green": len(registered) == 7 and bool(roster.get("channel_id")), "registered": registered, "channel_id": roster.get("channel_id"), "quality_in_channel": False}
    sub = await svc.substrate.health()
    checks["substrate"] = {"green": bool(sub.get("ok")), "detail": sub.get("reason", "")}
    green = all(c["green"] for c in checks.values())
    result = {"green": green, "seat": SEAT_LABEL[ctx.short], "gateway_version": __version__, "checks": checks}
    store.doctor_result(ctx.short, {"green": green, "checks": {k: v["green"] for k, v in checks.items()}})
    store.touch_seat(ctx.short, prompt_sha256=given_sha)
    return result


async def _declared_skills(ctx: ToolContext) -> list[str]:
    text = await ctx.services.repo.show(f"prompts/{ctx.bot_id}.xml")
    if not text:
        return []
    import re

    paths = re.findall(r'<skill path="skills/([^"]+)/SKILL\.md"', text)
    names = []
    for path in paths:
        name = path.split("/")[-1]
        if name not in names:
            names.append(name)
    for always in ("verification-receipts", "desk-doctor", "desk-bootstrap", "desk-production-loop"):
        if always not in names:
            names.append(always)
    return names


async def render_prompt(ctx: ToolContext) -> dict[str, Any]:
    """Assemble this seat's prompt for the registered roster with the repo's own assembler,
    run against an export of origin/main so the checkout is never touched."""
    import shutil
    import tempfile
    from pathlib import Path

    svc = ctx.services
    roster = svc.store.roster()
    seats = roster.get("seats") or {}
    missing = [s for s in SEATS if not (seats.get(s) or {}).get("agent_uuid")]
    if not roster.get("channel_id"):
        missing.append("channel_id")
    if missing:
        return failure("roster_incomplete", "register every seat and the channel id first", missing=missing)
    if not svc.repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    tree = await svc.repo.export(svc.repo.main_ref)
    if tree is None:
        return failure("upstream_error", f"could not export {svc.repo.main_ref}")
    try:
        version = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(roster.get("updated_at") or time.time()))
        doc = {
            "team": "registered",
            "roster_version": version,
            "desk_channel_id": roster["channel_id"],
            "gateway_url": svc.settings.gateway_url,
            "seats": {
                SEAT_LABEL[s]: {"bot_id": SEATS[s], "uuid": seats[s]["agent_uuid"], "in_channel": s != "quality"}
                for s in SEATS
            },
        }
        roster_path = Path(tempfile.mkstemp(prefix="desk-roster-", suffix=".json")[1])
        roster_path.write_text(json.dumps(doc), encoding="utf-8")
        try:
            run = await _run_bash(tree / "scripts" / "assemble-prompts.sh", roster_path, tree)
        finally:
            roster_path.unlink(missing_ok=True)
        if run["exit_code"] != 0:
            return failure("upstream_error", f"assemble-prompts failed: {run['stderr'][-300:]}")
        out = tree / "prompts-assembled" / f"{SEAT_LABEL[ctx.short]}.xml"
        if not out.is_file():
            return failure("not_found", "assembler produced no prompt for this seat")
        text = out.read_text(encoding="utf-8")
        if "{{" in text:
            return failure("upstream_error", "assembled prompt still has placeholders")
        return {"prompt": text, "sha256": hashlib.sha256(text.encode()).hexdigest(), "roster_version": version}
    finally:
        shutil.rmtree(tree, ignore_errors=True)


async def _run_bash(script: Any, roster_path: Any, cwd: Any) -> dict[str, Any]:
    from desk_gateway.upstreams import run_command

    return await run_command(["bash", str(script), "--roster", str(roster_path)], cwd=str(cwd), timeout=60)
