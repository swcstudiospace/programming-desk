"""LEAD-only tools: intake, graph state, Lane B agent bus, roster status."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from desk_gateway.config import SEAT_LABEL, SEATS
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import NOT_CONFIGURED

GITHUB_ISSUE = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/issues/(\d+)$")

# How far before the first attempt a recovery lookup starts reading; see _lookup_since.
ACK_LOOKUP_SKEW_SEC = 86400.0

# One lock per intake+ack, with a use count so the entries do not outlive their acks.
_ACK_LOCKS: dict[str, asyncio.Lock] = {}
_ACK_LOCK_USERS: dict[str, int] = {}


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

    That ordering makes the reply the thing a retry can duplicate, so it is delivered at most
    once per ack: see _reply_once.
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
        notify, fail = await _reply_once(svc, record, args, callback)
        if fail is not None:
            return fail

    updated = svc.store.intake_ack(args["intake_id"], ack)
    if updated is None:
        return failure(
            "not_found",
            f"intake {args['intake_id']} was gone before it could be advanced to {args['status']}",
            notify=notify,
        )
    return {"ok": True, "intake": updated, "notify": notify}


async def _reply_once(
    svc: Any, record: dict[str, Any], args: dict[str, Any], callback: tuple[str, str, int]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Post the origin reply at most once per ack, whatever fails after it.

    Returns (notify, failure-or-None). The reply has to precede the store advance, so the
    retry a failed advance asks for arrives with the comment already on the issue — and
    nothing in the record said so, so the retry posted a second identical comment.

    The guard is a write-ahead delivery marker plus the same marker embedded in the comment:

    * nothing recorded — record `attempted`, then post. The post is only reached once that
      record is durable, so no outcome can lose the fact that a comment may exist. If the
      write itself fails, nothing was posted and there is nothing to duplicate.
    * `attempted` — an earlier call posted, or died trying, and the issue is the record of
      which. Found means it was delivered; genuinely absent means the post never landed and
      may go out again. Unknown — a lookup that errored, one that could not read far enough,
      or a gateway with no GitHub token left to ask with — must neither post nor advance: the
      reply may be on the issue, which makes posting a duplicate, and it may not be, which
      makes advancing a claim that a requester was told something nobody told them.
    * `delivered` — skip the post; the caller still finishes the advance.

    Keyed on the ack's content, so a retry of the same ack is suppressed while a deliberately
    different ack (a later status, a new message) is a new reply.

    All of it runs under a per-ack lock, and the record is re-read inside that lock. Two acks
    for the same reply in flight together would otherwise both read a state from before either
    had posted — the second one's lookup finding nothing because the first one's comment had
    not landed yet — and both would post. The lock is process-local, which is the same scope
    the store's own writes are serialised in.
    """
    link, repo, number = callback
    key, marker = _delivery_marker(args)
    intake_id = record["intake_id"]

    async with _ack_lock(f"{intake_id}:{key}"):
        # Re-read: a concurrent ack for this same reply may have posted it while this call
        # waited for the lock, and the record read before the lock would not say so.
        current = svc.store.intake_get(intake_id) or record
        entry = svc.store.intake_delivery_get(current, key)
        prior = entry.get("state")

        if prior == "delivered":
            return {"delivered": True, "reason": "the reply for this ack was already posted",
                    "target": link, "posted": False}, None

        if prior == "attempted":
            seen = await svc.github.find_issue_comment(
                repo, number, marker, since=_lookup_since(entry.get("first_at"))
            )
            if seen.get("found"):
                svc.store.intake_delivery(intake_id, key, "delivered")
                return {"delivered": True, "reason": "an earlier call already posted this reply",
                        "target": link, "posted": False}, None
            if seen.get("error") or not seen.get("complete"):
                reason = seen.get("reason") or f"the thread on {link} could not be read far enough"
                notify = {"delivered": False, "reason": reason, "target": link,
                          "error": seen.get("error"), "posted": False}
                return notify, failure(
                    "notify_unknown",
                    f"an earlier desk_intake_ack posted, or tried to post, the reply to {link}, and "
                    f"whether it landed cannot be read back: {reason}. Posting again could duplicate "
                    f"it and advancing could claim a reply nobody received, so intake {intake_id} "
                    f"stays {current.get('state')} rather than {args['status']}; check {link} and "
                    "ack again once GitHub can be read.",
                    intake=current,
                    notify=notify,
                )
        else:
            svc.store.intake_delivery(intake_id, key, "attempted")

        result = await svc.github.comment_on_issue(repo, number, _ack_comment(args, marker))
        notify = {"delivered": bool(result.get("ok")), "reason": result.get("reason"),
                  "target": link, "error": result.get("error"), "posted": bool(result.get("ok"))}
        if notify["delivered"]:
            svc.store.intake_delivery(intake_id, key, "delivered")
            return notify, None
        if notify.get("error") == NOT_CONFIGURED:
            # Nothing was sent and nothing can be, so an attempt marker would be a lie: it
            # would send a later ack looking for a comment that was never written, and strand
            # the intake if that lookup could not answer. Neither branch above matches this
            # state, so an ack on a gateway that has since been given a token starts over.
            svc.store.intake_delivery(intake_id, key, "unconfigured")
            return notify, None
        return notify, failure(
            "notify_failed",
            f"the reply to {link} was not posted: "
            f"{notify.get('reason') or notify.get('error') or 'unknown error'}. "
            f"The requester has not been told, so intake {intake_id} stays "
            f"{current.get('state')} rather than {args['status']}; call desk_intake_ack again.",
            intake=current,
            notify=notify,
        )


@contextlib.asynccontextmanager
async def _ack_lock(lock_key: str) -> AsyncIterator[None]:
    """Serialise the acks that would post the same reply, and only those.

    One lock per intake+ack rather than one for the tool: acks for different intakes have
    nothing to say to each other, and holding a single lock across a GitHub round trip would
    queue all of them behind the slowest. Entries are dropped once nobody holds or wants one,
    so a long-lived gateway does not accumulate a lock per ack it has ever answered.

    Process-local, which is the same scope Store serialises its own writes in — a second
    gateway process sharing the data directory is outside what either guards, and there the
    durable marker and the lookup against the issue are what stand between a retry and a
    duplicate.
    """
    lock = _ACK_LOCKS.setdefault(lock_key, asyncio.Lock())
    _ACK_LOCK_USERS[lock_key] = _ACK_LOCK_USERS.get(lock_key, 0) + 1
    try:
        async with lock:
            yield
    finally:
        _ACK_LOCK_USERS[lock_key] -= 1
        if _ACK_LOCK_USERS[lock_key] <= 0:
            _ACK_LOCK_USERS.pop(lock_key, None)
            _ACK_LOCKS.pop(lock_key, None)


def _lookup_since(first_at: float | None) -> str | None:
    """The `since` window for a recovery lookup: shortly before the first attempt for this ack.

    Without one, the lookup reads the thread from its oldest comment and gives up after a
    bounded number of pages, so on a thread already longer than that budget it could never
    reach the reply it is looking for — and a reply that cannot be found is treated as
    unknown, which strands the intake with no way to recover by asking again.

    Widened by a day because `since` is compared against GitHub's clock rather than this
    gateway's: a window that started even slightly too late would miss the comment and read
    as proof it was never posted, which is the one mistake here that duplicates a reply.
    """
    if not first_at:
        return None
    moment = datetime.fromtimestamp(float(first_at) - ACK_LOOKUP_SKEW_SEC, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _delivery_marker(args: dict[str, Any]) -> tuple[str, str]:
    """(store key, comment marker) for one ack, derived from the ack itself.

    A digest rather than the status alone: two acks can legitimately carry the same status
    with different messages, and suppressing the second of those would lose a reply the
    requester was owed. A retry of the same call digests the same way.
    """
    body = json.dumps({k: v for k, v in args.items() if k != "intake_id"}, sort_keys=True, default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    key = f"{args['status']}:{digest}"
    return key, f"<!-- desk-intake-ack {args['intake_id']} {args['status']} {digest} -->"


def _callback(record: dict[str, Any]) -> tuple[str, str, int] | None:
    if record.get("origin") != "github":
        return None
    for link in record.get("links") or []:
        match = GITHUB_ISSUE.match(link)
        if match:
            return link, match.group(1), int(match.group(2))
    return None


def _ack_comment(args: dict[str, Any], marker: str) -> str:
    lines = [f"**Programming Desk** · LEAD · {args['status']}"]
    if args.get("graph_id"):
        lines.append(f"Graph ID: `{args['graph_id']}`")
    if args.get("message"):
        lines.append(args["message"])
    for extra in args.get("links") or []:
        lines.append(f"- {extra}")
    # The marker is what a retry looks for, so it has to survive in the posted body; an HTML
    # comment keeps it out of the rendered reply.
    lines.append(f"intake `{args['intake_id']}`\n{marker}")
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
