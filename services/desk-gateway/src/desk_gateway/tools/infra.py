"""INFRA tools: Railway, tailnet, VPS units, data-plane health."""

from __future__ import annotations

import json
from typing import Any

from desk_gateway.tools import ToolContext, failure
from desk_gateway.upstreams import run_command

DEFAULT_UNITS = ["substrate-mcp", "substrate-host", "substrate-dispatcher", "desk-gateway", "vps-agent-bus", "grok-claude-cloud-connector"]
FORWARDER_PORTS = {
    "ultrathink-production-tailscale-forwarder": [4000, 4001, 4003, 5432, 6379],
    "agent-substrate-production-tailscale-forwarder": [8888, 9380, 80],
}


def _projects(ctx: ToolContext, which: str) -> list[str]:
    names = ["ultrathink", "agent-substrate"] if which == "all" else [which]
    return [n for n in names if ctx.services.railway.project_id(n)]


def _default_environment_id(environments: list[dict[str, Any]]) -> str | None:
    """The environment every unqualified Railway call means: production, else the first listed.

    One rule, used by railway_status when it scopes latest_deployment and by _find_service
    when it picks the environment to read variables from or redeploy into, so the deployment
    reported as current and the environment acted on are always the same one.
    """
    prod = next((e for e in environments if e.get("name") == "production"), None)
    chosen = prod or (environments[0] if environments else {})
    return chosen.get("id")


def _env_deployment(by_env: dict[str, Any], environment_id: str | None) -> dict[str, Any] | None:
    """The deployment in one environment, and nothing when that environment has none.

    Never another environment's: "the service's latest deployment" across environments is not
    a thing, and the first instance the API happened to return could be staging while the
    caller — logs, a redeploy check — meant production.
    """
    if environment_id:
        return by_env.get(environment_id)
    if len(by_env) == 1:
        return next(iter(by_env.values()))
    return None


async def railway_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return {"projects": [], **failure("not_configured", "Railway API token is not configured on the gateway")}
    out = []
    for name in _projects(ctx, args.get("project", "all")):
        result = await railway.project_status(name)
        if result.get("error"):
            out.append({"project": name, **result})
            continue
        project = ((result.get("body") or {}).get("data") or {}).get("project") or {}
        environments = [(e.get("node") or {}) for e in ((project.get("environments") or {}).get("edges") or [])]
        default_env = _default_environment_id(environments)
        services = []
        for edge in (project.get("services") or {}).get("edges") or []:
            node = edge.get("node") or {}
            instances = [(e.get("node") or {}) for e in ((node.get("serviceInstances") or {}).get("edges") or [])]
            # Per environment: "the service's current deployment" is only a well-defined thing
            # within one environment, and a redeploy names one.
            by_env = {i["environmentId"]: i["latestDeployment"] for i in instances if i.get("environmentId") and i.get("latestDeployment")}
            latest = _env_deployment(by_env, default_env)
            services.append({
                "id": node.get("id"),
                "name": node.get("name"),
                # Scoped, and says which environment it is scoped to: an unqualified
                # latest_deployment was whichever instance the API listed first, so a consumer
                # falling back to it could read logs from, or reason about, another environment.
                "latest_deployment": latest,
                "environment_id": default_env,
                "deployments": by_env,
            })
        out.append({"project": name, "id": project.get("id"), "services": services, "environments": environments})
    if not out:
        return {"projects": [], **failure("not_configured", "no Railway project ids configured")}
    return {"projects": out}


async def _find_service(ctx: ToolContext, project: str, service_name: str) -> dict[str, Any] | None:
    """One service, the environment an unqualified call means, and that environment's deployment."""
    status = await railway_status(ctx, {"project": project})
    for p in status.get("projects") or []:
        for s in p.get("services") or []:
            if s.get("name") == service_name:
                environment_id = _default_environment_id(p.get("environments") or [])
                return {
                    "project_id": p.get("id"),
                    "service": s,
                    "environment_id": environment_id,
                    "deployment": _env_deployment(s.get("deployments") or {}, environment_id),
                }
    return None


async def railway_logs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return {"lines": [], **failure("not_configured", "Railway API token is not configured on the gateway")}
    deployment_id = args.get("deployment_id")
    environment_id = None
    if not deployment_id:
        # The fallback names one environment's deployment, not whichever the API listed first:
        # logs read from the wrong environment are worse than no logs, because they look right.
        found = await _find_service(ctx, args["project"], args["service"])
        if not found:
            return {"lines": [], **failure("not_found", f"service {args['service']} not found in {args['project']}")}
        environment_id = found["environment_id"]
        deployment_id = (found["deployment"] or {}).get("id")
        if not deployment_id:
            return {"lines": [], **failure(
                "not_found",
                f"{args['service']} has no deployment in environment {environment_id or 'unknown'}; "
                "pass deployment_id to read another environment's logs",
            )}
    result = await railway.logs(deployment_id, int(args.get("lines", 100)))
    if result.get("error"):
        return {"lines": [], **result}
    logs = ((result.get("body") or {}).get("data") or {}).get("deploymentLogs") or []
    return {"deployment_id": deployment_id, "environment_id": environment_id, "lines": logs}


async def railway_variable_names(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return {"names": [], **failure("not_configured", "Railway API token is not configured on the gateway")}
    found = await _find_service(ctx, args["project"], args["service"])
    if not found:
        return {"names": [], **failure("not_found", "service not found")}
    return await railway.variable_names(found["project_id"], found["environment_id"], found["service"]["id"])


async def railway_redeploy(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Redeploy a service, but only if it is still on the deployment the caller looked at.

    prior_deployment_id is the caller's evidence of what it inspected before asking for the
    write. Echoing it back without checking made that evidence false: between the status read
    and this call the service can have been redeployed or rolled forward by somebody else, and
    the receipt would then claim a redeploy of a deployment that was no longer there. Compared
    within the target environment, because that is the only scope in which "current" means
    anything.

    approval_id stays separate and unverified by design — the gateway records who claimed the
    approval, it does not adjudicate it.
    """
    railway = ctx.services.railway
    if not railway.http.configured:
        return failure("not_configured", "Railway API token is not configured on the gateway")
    found = await _find_service(ctx, args["project"], args["service"])
    if not found:
        return failure("not_found", "service not found")
    environment_id = found["environment_id"]
    current_id = (found["deployment"] or {}).get("id")
    if current_id != args["prior_deployment_id"]:
        return failure(
            "stale_deployment",
            f"{args['service']} is on deployment {current_id or 'unknown'}, not the "
            f"{args['prior_deployment_id']} this call was approved against; re-read desk_railway_status "
            "and confirm the new deployment before redeploying",
            service_id=found["service"]["id"],
            environment_id=environment_id,
            current_deployment_id=current_id,
            prior_deployment_id=args["prior_deployment_id"],
        )
    result = await railway.redeploy(found["service"]["id"], environment_id)
    if result.get("error"):
        return failure(result["error"], result.get("reason", "redeploy failed"))
    return {
        "ok": True,
        "approval_id": args["approval_id"],
        "prior_deployment_id": args["prior_deployment_id"],
        "verified_prior_deployment": True,
        "environment_id": environment_id,
        "result": result.get("body"),
        "unverified": ["approval_id is recorded as given; the gateway does not verify the approval itself"],
    }


async def tailscale_status(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    status = await run_command(["tailscale", "status", "--json"], timeout=10)
    if status["exit_code"] != 0:
        return failure("not_configured", f"tailscale status failed: {status['stderr'][-200:] or status['stdout'][-200:]}")
    try:
        doc = json.loads(status["stdout"])
    except ValueError:
        return failure("upstream_error", "tailscale status returned no JSON")
    self_node = doc.get("Self") or {}
    peers = {}
    for peer in (doc.get("Peer") or {}).values():
        peers[peer.get("HostName")] = {"online": bool(peer.get("Online")), "ips": peer.get("TailscaleIPs"), "tags": peer.get("Tags"), "os": peer.get("OS")}
    forwarders = {}
    for name, ports in FORWARDER_PORTS.items():
        entry = peers.get(name)
        probes = {}
        if entry and entry["online"]:
            for port in ports:
                probe = await run_command(["timeout", "3", "bash", "-c", f"exec 3<>/dev/tcp/{name}/{port}"], timeout=5)
                probes[str(port)] = probe["exit_code"] == 0
        forwarders[name] = {"present": entry is not None, "online": bool(entry and entry["online"]), "ports": probes}
    return {"self": {"hostname": self_node.get("HostName"), "tags": self_node.get("Tags"), "ips": self_node.get("TailscaleIPs")}, "forwarders": forwarders, "peers": peers}


async def vps_units(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    units = args.get("units") or DEFAULT_UNITS
    out = {}
    for unit in units:
        result = await run_command(["systemctl", "show", unit, "--property=ActiveState,SubState,ExecMainStartTimestamp,NRestarts"], timeout=5)
        props = dict(line.split("=", 1) for line in result["stdout"].splitlines() if "=" in line)
        out[unit] = {"active": props.get("ActiveState"), "sub": props.get("SubState"), "since": props.get("ExecMainStartTimestamp"), "restarts": props.get("NRestarts")}
    return {"units": out}


async def db_health(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    svc = ctx.services
    checks = {
        "greptime": await svc.greptime.health(),
        "timescale": await svc.timescale.health(),
        "dragonfly": await svc.dragonfly.health(),
        "hindsight": await svc.hindsight.health(),
        "ragflow": await svc.ragflow.health(),
        "substrate": await svc.substrate.health(),
    }
    summary = {name: ("ok" if r.get("ok") else r.get("error", "down")) for name, r in checks.items()}
    return {"summary": summary, "checks": checks}
