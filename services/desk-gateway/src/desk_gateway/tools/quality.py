"""QUALITY tools: gates, Greptile, receipt approval, waivers, contract acks, supply chain, secrets.
The contract ack tool is also served to build seats from their own rosters."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from desk_gateway.redact import redact_text
from desk_gateway.repo import safe_path, safe_ref
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import run_command

LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "uv.lock", "poetry.lock", "Cargo.lock", "Package.resolved", "gradle.lockfile", "requirements.txt", "deno.lock")


async def gates_run(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    if not (safe_ref(args["ref"]) and safe_ref(args.get("base") or "origin/main")):
        return failure("invalid_args", "ref or base is not a safe git ref")
    await repo.fetch()
    tree = await repo.export(args["ref"])
    if tree is None:
        return failure("not_found", f"ref {args['ref']} could not be exported")
    try:
        results: dict[str, Any] = {}
        results["G-1 manifest"] = await run_command(["python3", "ci/gates/check_ownership.py", "--validate-manifest"], cwd=str(tree), timeout=60)
        changed = await repo.diff_names(args.get("base") or repo.main_ref, args["ref"])
        if changed:
            results["G-1 ownership"] = await run_command(["python3", "ci/gates/check_ownership.py", "--bot", args["bot"], "--files", *changed], cwd=str(tree), timeout=60)
            results["G-3 secrets"] = await run_command(["python3", "ci/gates/check_secrets.py", "--files", *[c for c in changed if (tree / c).is_file()]], cwd=str(tree), timeout=120)
        if args.get("receipt_path") and (tree / args["receipt_path"]).is_file():
            results["G-2 receipt"] = await run_command(["python3", "ci/gates/check_receipt.py", "--receipt", args["receipt_path"], "--bot", args["bot"], "--strict"], cwd=str(tree), timeout=60)
            results["G-5/G-6 rollback"] = await run_command(["python3", "ci/gates/check_rollback.py", "--receipt", args["receipt_path"]], cwd=str(tree), timeout=60)
        if (tree / "ci" / "gates" / "check_desk_integrity.py").is_file():
            results["G-7 desk integrity"] = await run_command(["python3", "ci/gates/check_desk_integrity.py", "--repo", "."], cwd=str(tree), timeout=120)
        return {
            "ref": args["ref"],
            "changed_files": changed,
            "ok": all(r["exit_code"] == 0 for r in results.values()),
            "gates": {k: {"exit_code": v["exit_code"], "output": (v["stdout"] + v["stderr"])[-2500:]} for k, v in results.items()},
        }
    finally:
        shutil.rmtree(tree, ignore_errors=True)


async def greptile_review(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    greptile = ctx.services.greptile
    if not greptile.http.configured:
        return failure("not_configured", "Greptile is not configured on the gateway; merge claim stays blocked (skills/greptile-merge-gate)")
    repo = args.get("repo") or "swcstudiospace/programming-desk"
    if args["action"] == "trigger":
        result = await greptile.trigger(repo, int(args["pr_number"]))
        note = "a successful trigger means the review was queued, not that analysis finished"
    elif args["action"] == "get":
        if not args.get("review_id"):
            return failure("invalid_args", "get needs review_id")
        result = await greptile.get(args["review_id"])
        note = None
    else:
        result = await greptile.comments(repo, int(args["pr_number"]))
        note = "comments with addressed=false block the merge claim"
    if result.get("error"):
        return failure(result["error"], result.get("reason", "greptile failed"))
    return {"ok": True, "action": args["action"], "result": result.get("body"), "note": note}


async def receipt_approve(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    if not safe_ref(args["branch"]) or not safe_path(args["receipt_path"]):
        return failure("invalid_args", "branch or receipt_path is not safe")
    await repo.fetch()
    ref = f"{repo.remote}/{args['branch']}"
    text = await repo.show(args["receipt_path"], ref)
    if text is None:
        return failure("not_found", f"{args['receipt_path']} is not on {ref} (receipts are force-added: git add -f)")
    try:
        receipt = json.loads(text)
    except ValueError:
        return failure("invalid_receipt", "receipt is not valid JSON")
    if receipt.get("bot") == ctx.bot_id:
        return failure("self_approval", "QUALITY cannot approve a QUALITY receipt")
    check = await repo.receipt_check(receipt, receipt.get("bot") or "", False, args["receipt_path"])
    if not check.get("ok"):
        return failure("gate_failed", "the receipt does not pass G-2/G-3/G-5/G-6 before stamping", gates=check.get("gates"))
    receipt["approved_by"] = ctx.bot_id
    receipt["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if args.get("note"):
        receipt["approval_note"] = redact_text(args["note"])
    push = await _commit_file(ctx, args["branch"], args["receipt_path"], json.dumps(receipt, indent=2) + "\n", f"QUALITY: approve {args['receipt_path']}")
    return {"ok": bool(push.get("pushed")), "receipt_path": args["receipt_path"], "approved_by": ctx.bot_id, "push": push}


async def waiver_record(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not safe_ref(args["branch"]):
        return failure("invalid_args", "branch is not safe")
    name = f".receipts/bot-06-quality-security/greptile-waiver-pr{int(args['pr_number'])}-{int(time.time())}.json"
    waiver = {
        "task_id": f"greptile-waiver-pr{int(args['pr_number'])}",
        "bot": ctx.bot_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pr_number": int(args["pr_number"]),
        "waived_comment_ids": args["comment_ids"],
        "reason": redact_text(args["reason"]),
        "commands": [],
        "claims": [],
        "unverified": ["waiver recorded by the gateway; Greptile status at the branch tip was not re-fetched here"],
        "approved_by": "",
    }
    push = await _commit_file(ctx, args["branch"], name, json.dumps(waiver, indent=2) + "\n", f"QUALITY: Greptile waiver for PR #{int(args['pr_number'])}")
    return {"ok": bool(push.get("pushed")), "receipt_path": name, "push": push}


async def contract_ack(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not args["ack"] and len(args["note"]) < 20:
        return failure("invalid_args", "a rejection must name the blocker (note of at least 20 characters)")
    entry = ctx.services.store.record_ack(args["change_id"], ctx.bot_id, bool(args["ack"]), redact_text(args["note"]))
    return {"ok": True, "change_id": args["change_id"], "acknowledgements": entry["acknowledgements"]}


async def contract_ack_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    entry = svc.store.acks().get(args["change_id"]) or {"acknowledgements": []}
    proposal_text = await svc.repo.show(f"contracts/changes/{args['change_id']}.yaml") if svc.repo.available else None
    required: list[str] = []
    if proposal_text:
        import yaml

        try:
            required = list((yaml.safe_load(proposal_text) or {}).get("consumers_required") or [])
        except yaml.YAMLError:
            required = []
    acked = {a["bot"] for a in entry["acknowledgements"] if a.get("ack")}
    rejected = [a for a in entry["acknowledgements"] if not a.get("ack")]
    return {
        "change_id": args["change_id"],
        "consumers_required": required,
        "acknowledged": sorted(acked),
        "missing": sorted(set(required) - acked),
        "rejected": rejected,
        "complete": bool(required) and set(required) <= acked and not rejected,
    }


async def supply_chain_check(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    names = await repo.diff_names(args["base_ref"], args["head_ref"])
    lockfiles = [n for n in names if n.split("/")[-1] in LOCKFILES]
    manifests = [n for n in names if n.split("/")[-1] in ("package.json", "pyproject.toml", "Cargo.toml", "Package.swift", "build.gradle.kts", "build.gradle", "deno.json")]
    diff = await repo.diff(args["base_ref"], args["head_ref"], lockfiles + manifests) if (lockfiles or manifests) else ""
    added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    unpinned = [line.strip() for line in added if any(tok in line for tok in ('"latest"', "@latest", ": latest", "*"))][:20]
    git_deps = [line.strip() for line in added if "git+" in line or "github:" in line][:20]
    return {
        "lockfiles_changed": lockfiles,
        "manifests_changed": manifests,
        "unpinned": unpinned,
        "git_dependencies": git_deps,
        "verdict": "review" if (lockfiles or manifests) else "no dependency change",
        "unverified": ["licence and CVE lookup is not wired on the gateway yet; run the supply-chain skill's audit commands"],
    }


async def secret_scan(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    repo = ctx.services.repo
    if not repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    if not safe_ref(args["ref"]):
        return failure("invalid_args", "ref is not safe")
    await repo.fetch()
    tree = await repo.export(args["ref"])
    if tree is None:
        return failure("not_found", f"ref {args['ref']} could not be exported")
    try:
        paths = [p for p in (args.get("paths") or []) if safe_path(p) and (tree / p).is_file()]
        if not paths:
            paths = [str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file() and ".git" not in p.parts][:2000]
        result = await run_command(["python3", "ci/gates/check_secrets.py", "--files", *paths], cwd=str(tree), timeout=120)
        return {"ok": result["exit_code"] == 0, "gate": "G-3", "files": len(paths), "output": result["stdout"][-3000:]}
    finally:
        shutil.rmtree(tree, ignore_errors=True)


async def _commit_file(ctx: ToolContext, branch: str, rel_path: str, content: str, message: str) -> dict[str, Any]:
    repo = ctx.services.repo
    scratch = Path(__import__("tempfile").mkdtemp(prefix="desk-approve-"))
    try:
        remote = await run_command(["git", "-C", str(repo.dir), "remote", "get-url", repo.remote])
        if remote["exit_code"] != 0:
            return {"pushed": False, "reason": "no remote"}
        clone = await run_command(["git", "clone", "--quiet", "--depth", "1", "--branch", branch, remote["stdout"].strip(), str(scratch / "wt")], timeout=90)
        if clone["exit_code"] != 0:
            return {"pushed": False, "reason": redact_text(clone["stderr"][-200:])}
        wt = scratch / "wt"
        target = wt / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        await run_command(["git", "add", "-f", rel_path], cwd=str(wt))
        commit = await run_command(["git", "-c", "user.name=desk-gateway", "-c", "user.email=desk-gateway@swcstudio.space", "commit", "-q", "-m", message], cwd=str(wt))
        if commit["exit_code"] != 0:
            return {"pushed": False, "reason": redact_text(commit["stderr"][-200:])}
        push = await run_command(["git", "push", "-q", "origin", f"HEAD:{branch}"], cwd=str(wt), timeout=60)
        if push["exit_code"] != 0:
            return {"pushed": False, "reason": redact_text(push["stderr"][-200:])}
        sha = await run_command(["git", "rev-parse", "HEAD"], cwd=str(wt))
        return {"pushed": True, "branch": branch, "commit": sha["stdout"].strip()}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
