"""SYSTEMS tools (the LSP diagnostics tool is shared with WEB)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from desk_gateway.redact import contains_secret, redact_text
from desk_gateway.repo import safe_path
from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import run_command

TIER1 = {"tsjs": (".ts", ".tsx", ".js", ".jsx"), "python": (".py",), "go": (".go",)}


async def index_query(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    result = await ctx.services.timescale.query(args["sql"], int(args.get("limit", 100)))
    if result.get("error"):
        return {"rows": [], **result}
    return result


async def events_query(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    result = await ctx.services.greptime.sql(args["sql"], int(args.get("limit", 100)))
    if result.get("error"):
        return {"rows": [], **result}
    return result


async def cache(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    key = f"{ctx.short}:{args['key']}"
    if args["action"] == "set" and args.get("value") and contains_secret(args["value"]):
        return failure("secret_refused", "cache values may not contain credentials")
    return await ctx.services.dragonfly.command(args["action"], key, args.get("value"), int(args.get("ttl_sec", 3600)))


def _language_for(path: str, language: str | None) -> str | None:
    if language:
        return language
    for lang, exts in TIER1.items():
        if path.endswith(exts):
            return lang
    if path.endswith(".rs"):
        return "rust"
    return None


async def lsp_diagnostics(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if not safe_path(args["path"]):
        return failure("invalid_args", "path must be repo-relative")
    language = _language_for(args["path"], args.get("language"))
    if language not in TIER1:
        return failure("language_not_tier1", f"{language or 'unknown'} is not a Tier-1 language (tsjs, python, go)")
    repo = ctx.services.repo
    broker = repo.dir / "infra" / "unified-lsp-broker" / "broker.py"
    if not broker.is_file():
        return failure("not_configured", "unified LSP broker is not present in the checkout")
    state_dir = Path(os.environ.get("ULSP_STATE_DIR", "/var/lib/desk-gateway/ulsp"))
    state_dir.mkdir(parents=True, exist_ok=True)
    request = json.dumps({"id": 1, "method": "diagnostics", "params": {"path": args["path"], "language": language}})
    result = await run_command(["python3", str(broker), "--state-dir", str(state_dir), "rpc"], cwd=str(repo.dir), timeout=19, input_text=request)
    if result["exit_code"] != 0:
        return failure("upstream_error", f"broker exit {result['exit_code']}: {result['stderr'][-200:]}")
    try:
        return {"ok": True, "diagnostics": json.loads(result["stdout"] or "{}")}
    except ValueError:
        return {"ok": True, "raw": result["stdout"][-4000:]}


async def contract_propose(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if contains_secret(args["body"]):
        return failure("secret_refused", "proposal body contains a credential shape")
    # The roster pattern for `surface` allows '.' and '/', so it accepts
    # contracts/../../../etc/passwd. The path is joined onto the export tree and written
    # before any gate runs, and the unit runs as root — so without this the tool is an
    # arbitrary root-owned file write. safe_path is the same guard every other repo-path
    # tool here uses; it refuses '..' and a leading '/'.
    if not safe_path(args["surface"]):
        return failure("invalid_surface", "surface must be a relative path with no '..' segment")
    repo = ctx.services.repo
    if not repo.available:
        return failure("not_configured", "repo checkout is not available to the gateway")
    change = args["change_id"]
    branch = f"{ctx.bot_id}/contract-{change}"
    tree = await repo.export(repo.main_ref)
    if tree is None:
        return failure("upstream_error", "could not export origin/main")
    try:
        surface = Path(args["surface"])
        target = tree / surface
        # Belt and braces behind safe_path: resolve and require the result to stay inside
        # the export tree, so a symlink in the tree cannot redirect the write either.
        if not target.resolve().is_relative_to(tree.resolve()):
            return failure("invalid_surface", "surface resolves outside the proposal tree")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["body"], encoding="utf-8")
        proposal = {
            "change_id": change,
            "proposed_by": ctx.bot_id,
            "surface": args["surface"],
            "breaking": bool(args["breaking"]),
            "version": args["version"],
            "summary": args["summary"],
            "migration_note": args.get("migration_note"),
            "consumers_required": args["consumers_required"],
            "acknowledgements": [],
        }
        changes = tree / "contracts" / "changes"
        changes.mkdir(parents=True, exist_ok=True)
        (changes / f"{change}.yaml").write_text(_yaml(proposal), encoding="utf-8")
        gate = await repo.run_gate("check_secrets.py", ["--files", str(target), str(changes / f"{change}.yaml")], cwd=tree)
        if gate["exit_code"] != 0:
            return failure("gate_failed", "G-3 rejected the proposal", detail=gate["stdout"][-500:])
        bundle = {
            "branch": branch,
            "files": {str(surface): args["body"], f"contracts/changes/{change}.yaml": _yaml(proposal)},
            "pr_title": f"contract: {change} ({'breaking' if args['breaking'] else 'additive'})",
            "pr_body": (
                f"## Contract change `{change}`\n\n{args['summary']}\n\n"
                f"- surface: `{args['surface']}`\n- version: {args['version']}\n- breaking: {args['breaking']}\n"
                f"- consumers required: {', '.join(args['consumers_required'])}\n\n"
                "Consumers acknowledge with `desk_contract_ack`. QUALITY merges after G-4."
            ),
        }
    finally:
        import shutil

        shutil.rmtree(tree, ignore_errors=True)
    push = await _push_bundle(ctx, bundle)
    return {"ok": True, "proposal": proposal, "branch": branch, "push": push}


async def _push_bundle(ctx: ToolContext, bundle: dict[str, Any]) -> dict[str, Any]:
    """Create the branch with the proposal files in a scratch clone and open a draft PR with gh.
    Without gh or a writable remote the bundle is returned for the seat to commit itself."""
    repo = ctx.services.repo
    scratch = Path(tempfile.mkdtemp(prefix="desk-contract-"))
    try:
        clone = await run_command(["git", "clone", "--quiet", "--depth", "1", "--branch", repo.branch, str(repo.dir), str(scratch / "wt")], timeout=60)
        if clone["exit_code"] != 0:
            return {"pushed": False, "reason": "scratch clone failed", "bundle": bundle}
        wt = scratch / "wt"
        await run_command(["git", "checkout", "-q", "-b", bundle["branch"]], cwd=str(wt))
        for rel, text in bundle["files"].items():
            path = wt / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        await run_command(["git", "add", *bundle["files"].keys()], cwd=str(wt))
        commit = await run_command(
            ["git", "-c", "user.name=desk-gateway", "-c", "user.email=desk-gateway@swcstudio.space", "commit", "-q", "-m", bundle["pr_title"]],
            cwd=str(wt),
        )
        if commit["exit_code"] != 0:
            return {"pushed": False, "reason": redact_text(commit["stderr"][-200:]), "bundle": bundle}
        remote = await run_command(["git", "-C", str(repo.dir), "remote", "get-url", repo.remote])
        if remote["exit_code"] != 0:
            return {"pushed": False, "reason": "no remote", "bundle": bundle}
        await run_command(["git", "remote", "set-url", "origin", remote["stdout"].strip()], cwd=str(wt))
        push = await run_command(["git", "push", "-q", "-u", "origin", bundle["branch"]], cwd=str(wt), timeout=60)
        if push["exit_code"] != 0:
            return {"pushed": False, "reason": redact_text(push["stderr"][-200:]), "bundle": bundle}
        pr = await run_command(
            ["gh", "pr", "create", "--draft", "--base", repo.branch, "--head", bundle["branch"], "--title", bundle["pr_title"], "--body", bundle["pr_body"]],
            cwd=str(wt),
            timeout=60,
        )
        return {"pushed": True, "branch": bundle["branch"], "pr": pr["stdout"].strip() if pr["exit_code"] == 0 else None, "pr_error": None if pr["exit_code"] == 0 else redact_text(pr["stderr"][-200:])}
    finally:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)


def _yaml(doc: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


async def design_artifact_get(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    text = await ctx.services.repo.show(args["path"])
    if text is None:
        return failure("not_found", f"{args['path']} is not on origin/main")
    return {"path": args["path"], "content": text[:60000], "truncated": len(text) > 60000}


async def graph_heartbeat(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Renew a lease this seat already holds, via the substrate's graph_heartbeat (SPE-4792,
    agent-substrate packages/mcp-server lease.ts). lease_id must be the one graph_claim
    (lead.graph_state, action: claim) returned — it is what proves the holder. The substrate
    answers ok:false with reason lost, expired or unheld for a lease this call no longer holds;
    that is a normal response, not a transport failure, so it is passed through under
    `substrate` rather than mapped onto `error`."""
    payload: dict[str, Any] = {
        "graph_id": args["graph_id"],
        "node_id": args["node_id"],
        "lease_id": args["lease_id"],
    }
    if args.get("ttl_seconds") is not None:
        payload["ttl_seconds"] = args["ttl_seconds"]
    result = await ctx.services.substrate.call_tool("graph_heartbeat", payload, timeout=10)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "graph_heartbeat failed"), detail=result.get("content"))
    return {"ok": True, "substrate": result.get("content")}


async def drift_scan(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Read-only coord_drift_scan(repo) snapshot (SPE-4792, agent-substrate drift.ts): one call,
    one checked_at, every finding typed by the DriftKind enum. Reports only — never claims,
    releases or alters anything. Empty findings is not the same as agreement: a snapshot whose
    `unavailable` list is non-empty means a plane could not be read, and that is the caller's to
    weigh, not something this backend resolves on their behalf."""
    payload: dict[str, Any] = {"repo": args["repo"]}
    for key in ("path", "git_tip", "branch", "idle_seconds", "limit", "format"):
        if args.get(key) is not None:
            payload[key] = args[key]
    result = await ctx.services.substrate.call_tool("coord_drift_scan", payload, timeout=10)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "coord_drift_scan failed"), detail=result.get("content"))
    return {"ok": True, "substrate": result.get("content")}
