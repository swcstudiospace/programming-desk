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
        services = []
        for edge in (project.get("services") or {}).get("edges") or []:
            node = edge.get("node") or {}
            instances = [(e.get("node") or {}) for e in ((node.get("serviceInstances") or {}).get("edges") or [])]
            latest = next((i.get("latestDeployment") for i in instances if i.get("latestDeployment")), None)
            services.append({"id": node.get("id"), "name": node.get("name"), "latest_deployment": latest})
        out.append({"project": name, "id": project.get("id"), "services": services, "environments": [(e.get("node") or {}) for e in ((project.get("environments") or {}).get("edges") or [])]})
    if not out:
        return {"projects": [], **failure("not_configured", "no Railway project ids configured")}
    return {"projects": out}


async def _find_service(ctx: ToolContext, project: str, service_name: str) -> dict[str, Any] | None:
    status = await railway_status(ctx, {"project": project})
    for p in status.get("projects") or []:
        for s in p.get("services") or []:
            if s.get("name") == service_name:
                envs = p.get("environments") or []
                prod = next((e for e in envs if e.get("name") == "production"), envs[0] if envs else {})
                return {"project_id": p.get("id"), "service": s, "environment_id": prod.get("id")}
    return None


async def railway_logs(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return {"lines": [], **failure("not_configured", "Railway API token is not configured on the gateway")}
    deployment_id = args.get("deployment_id")
    if not deployment_id:
        found = await _find_service(ctx, args["project"], args["service"])
        if not found or not (found["service"].get("latest_deployment") or {}).get("id"):
            return {"lines": [], **failure("not_found", "service or latest deployment not found")}
        deployment_id = found["service"]["latest_deployment"]["id"]
    result = await railway.logs(deployment_id, int(args.get("lines", 100)))
    if result.get("error"):
        return {"lines": [], **result}
    logs = ((result.get("body") or {}).get("data") or {}).get("deploymentLogs") or []
    return {"deployment_id": deployment_id, "lines": logs}


async def railway_variable_names(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return {"names": [], **failure("not_configured", "Railway API token is not configured on the gateway")}
    found = await _find_service(ctx, args["project"], args["service"])
    if not found:
        return {"names": [], **failure("not_found", "service not found")}
    return await railway.variable_names(found["project_id"], found["environment_id"], found["service"]["id"])


async def railway_redeploy(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    railway = ctx.services.railway
    if not railway.http.configured:
        return failure("not_configured", "Railway API token is not configured on the gateway")
    found = await _find_service(ctx, args["project"], args["service"])
    if not found:
        return failure("not_found", "service not found")
    result = await railway.redeploy(found["service"]["id"], found["environment_id"])
    if result.get("error"):
        return failure(result["error"], result.get("reason", "redeploy failed"))
    return {"ok": True, "approval_id": args["approval_id"], "prior_deployment_id": args["prior_deployment_id"], "result": result.get("body")}


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
