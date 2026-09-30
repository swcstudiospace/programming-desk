"""LEAD-only tools: intake, graph state, Lane B agent bus, roster status."""

from __future__ import annotations

import re
from typing import Any

from desk_gateway.config import SEAT_LABEL, SEATS
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import NOT_CONFIGURED

GITHUB_ISSUE = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/issues/(\d+)$")


async def intake_next(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    record = ctx.services.store.intake_next(args.get("origin"))
    if record is None:
        return {"work_order": None, "queue": ctx.services.store.intake_counts()}
    return {"work_order": record, "queue": ctx.services.store.intake_counts(), "next": "Stage 1: ORIGINAL is work_order.ask verbatim"}


async def intake_ack(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Answer an intake request, and reply on its origin when it has one.

    A reply that was attempted and failed is surfaced, because the issue is the record of an
    intake and the workflow posts no fallback comment — so the requester was never told, and
    an unqualified ok: true tells LEAD the opposite. An unconfigured gateway is different in
    kind: nothing was attempted, there is nothing to retry, and every github-origin ack would
    otherwise be unusable on a deployment without a token. That case keeps reporting the ack
    it stored, with delivered: false and the reason.

    The reply goes out *before* the record is advanced, so a failure leaves nothing to undo.
    Storing first and posting second needed the state machine this record does not have:
    the intake was already marked accepted, so calling again — which is what the failure
    tells LEAD to do — retried a reply for a request that no longer looked claimed, and the
    queue counted work as answered that nobody had been told about.
    """
    svc = ctx.services
    record = svc.store.intake_get(args["intake_id"])
    if record is None:
        return failure("not_found", f"no intake {args['intake_id']}")
    ack = {k: v for k, v in args.items() if k != "intake_id"}
    ack["by"] = ctx.bot_id

    notify: dict[str, Any] = {"delivered": False, "reason": "origin has no callback"}
    callback = _callback(record)
    if callback is not None:
        link, repo, number = callback
        result = await svc.github.comment_on_issue(repo, number, _ack_comment(args))
        notify = {"delivered": bool(result.get("ok")), "reason": result.get("reason"),
                  "target": link, "error": result.get("error")}
        if not notify["delivered"] and notify.get("error") != NOT_CONFIGURED:
            return failure(
                "notify_failed",
                f"the reply to {link} was not posted: "
                f"{notify.get('reason') or notify.get('error') or 'unknown error'}. "
                f"The requester has not been told, so intake {args['intake_id']} stays "
                f"{record.get('state')} rather than {args['status']}; call desk_intake_ack again.",
                intake=record,
                notify=notify,
            )

    updated = svc.store.intake_ack(args["intake_id"], ack)
    return {"ok": True, "intake": updated, "notify": notify}


def _callback(record: dict[str, Any]) -> tuple[str, str, int] | None:
    if record.get("origin") != "github":
        return None
    for link in record.get("links") or []:
        match = GITHUB_ISSUE.match(link)
        if match:
            return link, match.group(1), int(match.group(2))
    return None


def _ack_comment(args: dict[str, Any]) -> str:
    lines = [f"**Programming Desk** · LEAD · {args['status']}"]
    if args.get("graph_id"):
        lines.append(f"Graph ID: `{args['graph_id']}`")
    if args.get("message"):
        lines.append(args["message"])
    for extra in args.get("links") or []:
        lines.append(f"- {extra}")
    lines.append(f"intake `{args['intake_id']}`")
    return "\n\n".join(lines)


async def graph_register(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"graph_id": args["graph_id"], "repo": args["repo"], "status": "planning"}
    if args.get("nodes"):
        payload["nodes"] = [
            {k: v for k, v in {"node_id": n["node_id"], "linear_identifier": n.get("linear_id"), "state": "open"}.items() if v is not None}
            for n in args["nodes"]
        ]
    result = await ctx.services.substrate.call_tool("graph_register", payload, timeout=10)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "graph_register failed"), detail=result.get("content"))
    return {"ok": True, "graph_id": args["graph_id"], "substrate": result.get("content")}


async def graph_state(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    tool = {"claim": "graph_claim", "release": "graph_release", "complete": "graph_complete"}[args["action"]]
    session_id = f"grok-bot:{args.get('surface') or 'lead'}:{args['graph_id']}"
    payload: dict[str, Any] = {"graph_id": args["graph_id"], "node_id": args["node_id"], "session_id": session_id}
    if args["action"] == "complete":
        payload["result"] = {"summary": args.get("note") or "completed via desk gateway", "tests_pass": False}
    result = await ctx.services.substrate.call_tool(tool, payload, timeout=10)
    if result.get("error"):
        return failure(result["error"], result.get("reason", f"{tool} failed"), detail=result.get("content"))
    return {"ok": True, "action": args["action"], "substrate": result.get("content")}


async def bus_start_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    result = await ctx.services.agent_bus.start_job(args["runtime"], args["goal"], args.get("provider"), args.get("idempotency_key"))
    if result.get("error"):
        return failure(result["error"], result.get("reason", "agent bus refused the job"))
    body = result.get("body") or {}
    if isinstance(body, dict):
        body.pop("wsUrl", None)
    return {"ok": True, "job": body, "note": "Lane B: the durable output is still a branch and draft PR on GitHub"}


async def bus_wait_job(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    result = await ctx.services.agent_bus.wait_job(args["job_id"], int(args.get("timeout_sec", 180)), int(args.get("poll_sec", 2)))
    if result.get("error"):
        return failure(result["error"], result.get("reason", "agent bus unavailable"))
    return {"ok": True, "job": result.get("body"), "timed_out": bool(result.get("timed_out"))}


async def roster_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    roster = svc.store.roster()
    doctor = svc.store.doctor_results()
    seats = []
    for short in SEATS:
        entry = (roster.get("seats") or {}).get(short) or {}
        seats.append(
            {
                "seat": SEAT_LABEL[short],
                "registered": bool(entry.get("agent_uuid")),
                "last_seen": entry.get("last_seen"),
                "tool_count": len(svc.rosters.surface(short, svc.store.packs_for(short))),
                "packs": svc.store.packs_for(short),
                "doctor": doctor.get(short),
                "in_channel": short != "quality",
            }
        )
    return {
        "channel_id": roster.get("channel_id"),
        "complete": all(s["registered"] for s in seats) and bool(roster.get("channel_id")),
        "seats": seats,
        "intake_queue": svc.store.intake_counts(),
    }
