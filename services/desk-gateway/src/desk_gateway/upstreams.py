"""Clients for everything the gateway talks to. Every method returns plain dicts and never raises
past its boundary: reads come back as {"error": <code>, "reason": ...} so a tool can fail open,
writes come back the same way so a tool can fail closed. Secrets never appear in return values.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shlex
import signal
import time
from typing import Any

import httpx

from desk_gateway.config import Settings
from desk_gateway.redact import redact_text, redact_value

logger = logging.getLogger("desk_gateway.upstreams")

NOT_CONFIGURED = "not_configured"
UPSTREAM_ERROR = "upstream_error"
UPSTREAM_TIMEOUT = "upstream_timeout"

READ_ONLY_SQL = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|vacuum|call|do|merge|set\s+role)\b",
    re.IGNORECASE,
)


def not_configured(what: str) -> dict[str, Any]:
    return {"error": NOT_CONFIGURED, "reason": f"{what} is not configured on the gateway; record this under unverified"}


_SQL_LITERAL_OR_COMMENT = re.compile(
    r"'(?:[^']|'')*'"       # single-quoted literal, '' as the escape
    r'|"(?:[^"]|"")*"'      # double-quoted identifier
    r"|--[^\n]*"            # line comment
    r"|/\*.*?\*/",          # block comment
    re.DOTALL,
)


def _sql_code_only(sql: str) -> str:
    """`sql` with literals and comments blanked, so keyword scanning sees operations only.

    Scanning the raw text rejects ordinary reads: SELECT 'delete', or a LIKE '%create%'
    filter, matches the write-keyword pattern inside its own quotes. Blanking rather than
    deleting preserves offsets and cannot join two tokens into a third.
    """
    return _SQL_LITERAL_OR_COMMENT.sub(lambda m: " " * len(m.group()), sql)


def read_only_sql(sql: str) -> str | None:
    code = _sql_code_only(sql)
    if not READ_ONLY_SQL.match(code.lstrip()):
        return "only SELECT or WITH statements are accepted"
    if FORBIDDEN_SQL.search(code):
        return "statement contains a write keyword"
    if ";" in code.strip().rstrip(";"):
        return "one statement per call"
    return None


async def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"text": redact_text(resp.text[:2000])}


class HttpUpstream:
    def __init__(self, name: str, base_url: str, headers: dict[str, str] | None = None, timeout: float = 15.0) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            return not_configured(self.name)
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = {**self.headers, **(kwargs.pop("headers", None) or {})}
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                resp = await client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            return {"error": UPSTREAM_TIMEOUT, "reason": f"{self.name} did not answer within {self.timeout:.0f}s"}
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"{self.name}: {redact_text(str(exc))[:300]}"}
        body = await _json(resp)
        if resp.status_code >= 400:
            return {
                "error": UPSTREAM_ERROR,
                "reason": f"{self.name} returned HTTP {resp.status_code}",
                "status": resp.status_code,
                "body": redact_value(body) if isinstance(body, (dict, list)) else body,
            }
        return {"ok": True, "status": resp.status_code, "body": redact_value(body)}


class Substrate:
    """substrate-mcp on the VPS loopback: plain HTTP for brief/events, MCP for the rest."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "substrate",
            settings.substrate_url,
            headers={"Authorization": f"Bearer {settings.substrate_token}"} if settings.substrate_token else {},
            timeout=6.0,
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.substrate_url and self.settings.substrate_token)

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/healthz")

    async def brief(self, *, repo: str | None, graph_id: str | None) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        payload = {k: v for k, v in {"repo": repo, "graph_id": graph_id, "surface": "grok-bot"}.items() if v}
        try:
            async with httpx.AsyncClient(timeout=6.0, headers=self.http.headers) as client:
                resp = await client.post(f"{self.http.base_url}/brief", json=payload)
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"substrate: {redact_text(str(exc))[:300]}"}
        if resp.status_code >= 400:
            return {"error": UPSTREAM_ERROR, "reason": f"substrate returned HTTP {resp.status_code}"}
        return {"ok": True, "brief": redact_text(resp.text[:20000])}

    async def emit(self, event: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        return await self.http.request("POST", "/events", json={"surface": "grok-bot", **event})

    async def call_tool(self, name: str, arguments: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
        if not self.configured:
            return not_configured("substrate")
        from mcp.client.client import Client
        from mcp.client.streamable_http import streamable_http_client

        try:
            async with asyncio.timeout(timeout):
                http_client = httpx.AsyncClient(headers=self.http.headers, timeout=timeout)
                async with http_client:
                    transport = streamable_http_client(f"{self.http.base_url}/mcp", http_client=http_client)
                    async with Client(transport, read_timeout_seconds=timeout) as client:
                        result = await client.call_tool(name, arguments)
        except TimeoutError:
            return {"error": UPSTREAM_TIMEOUT, "reason": f"substrate {name} did not answer within {timeout:.0f}s"}
        except Exception as exc:  # the MCP client raises many shapes; none of them may reach a Bot raw
            return {"error": UPSTREAM_ERROR, "reason": f"substrate {name}: {redact_text(str(exc))[:300]}"}
        content: list[Any] = []
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text is None:
                continue
            try:
                content.append(json.loads(text))
            except ValueError:
                content.append(redact_text(text))
        out: dict[str, Any] = {"ok": not result.is_error, "content": redact_value(content)}
        if result.structured_content is not None:
            out["structured"] = redact_value(result.structured_content)
        if result.is_error:
            out["error"] = UPSTREAM_ERROR
            out["reason"] = f"substrate {name} reported an error"
        return out


class AgentBus:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "agent-bus",
            settings.agent_bus_url if settings.agent_bus_token else "",
            headers={"Authorization": f"Bearer {settings.agent_bus_token}"} if settings.agent_bus_token else {},
            timeout=10.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/health")

    async def start_job(self, runtime: str, goal: str, provider: str | None, idempotency_key: str | None) -> dict[str, Any]:
        body = {"runtime": runtime, "goal": goal}
        if provider:
            body["provider"] = provider
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        return await self.http.request("POST", "/v1/jobs", json=body)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/v1/jobs/{job_id}")

    async def wait_job(self, job_id: str, timeout_sec: int, poll_sec: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, Any] = {}
        while True:
            last = await self.get_job(job_id)
            status = (last.get("body") or {}).get("status") if last.get("ok") else None
            if last.get("error") or status in {"completed", "failed", "error"}:
                return last
            if time.monotonic() >= deadline:
                return {**last, "timed_out": True}
            await asyncio.sleep(poll_sec)


class Greptime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        auth = (settings.greptime_user, settings.greptime_password) if settings.greptime_user else None
        self.auth = auth

    @property
    def configured(self) -> bool:
        return bool(self.settings.greptime_url)

    async def sql(self, sql: str, limit: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("greptime")
        problem = read_only_sql(sql)
        if problem:
            return {"error": "invalid_sql", "reason": problem}
        query = f"SELECT * FROM ({sql.rstrip(';')}) AS q LIMIT {int(limit)}"
        try:
            async with httpx.AsyncClient(timeout=10.0, auth=self.auth) as client:
                resp = await client.post(
                    f"{self.settings.greptime_url}/v1/sql",
                    params={"db": self.settings.greptime_db},
                    data={"sql": query},
                )
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"greptime: {redact_text(str(exc))[:300]}"}
        body = await _json(resp)
        if resp.status_code >= 400:
            return {"error": UPSTREAM_ERROR, "reason": f"greptime returned HTTP {resp.status_code}", "body": redact_value(body)}
        return {"ok": True, "body": redact_value(body)}

    async def health(self) -> dict[str, Any]:
        if not self.configured:
            return not_configured("greptime")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.settings.greptime_url}/health")
        except httpx.HTTPError as exc:
            return {"error": UPSTREAM_ERROR, "reason": redact_text(str(exc))[:200]}
        return {"ok": resp.status_code < 400, "status": resp.status_code}


class Timescale:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.pg_url

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def query(self, sql: str, limit: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("timescale")
        problem = read_only_sql(sql)
        if problem:
            return {"error": "invalid_sql", "reason": problem}
        try:
            import psycopg
        except ImportError:
            return {"error": NOT_CONFIGURED, "reason": "psycopg is not installed on the gateway (extra: timescale)"}

        def run() -> dict[str, Any]:
            with psycopg.connect(self.url, connect_timeout=5, options="-c default_transaction_read_only=on") as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM ({sql.rstrip(';')}) AS q LIMIT %s", (int(limit),))
                    cols = [d.name for d in cur.description or []]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"ok": True, "columns": cols, "rows": redact_value(json.loads(json.dumps(rows, default=str)))}

        try:
            return await asyncio.to_thread(run)
        except Exception as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"timescale: {redact_text(str(exc))[:300]}"}

    async def health(self) -> dict[str, Any]:
        result = await self.query("SELECT 1 AS ok", 1)
        return {"ok": bool(result.get("ok")), **({} if result.get("ok") else result)}


class Dragonfly:
    def __init__(self, settings: Settings) -> None:
        self.url = settings.dragonfly_url

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def command(self, action: str, key: str, value: str | None, ttl_sec: int) -> dict[str, Any]:
        if not self.configured:
            return not_configured("dragonfly")
        try:
            import redis.asyncio as redis
        except ImportError:
            return {"error": NOT_CONFIGURED, "reason": "redis is not installed on the gateway (extra: dragonfly)"}
        try:
            client = redis.from_url(self.url, socket_timeout=4, socket_connect_timeout=4, decode_responses=True)
            try:
                if action == "get":
                    return {"ok": True, "value": await client.get(key)}
                if action == "set":
                    await client.set(key, value or "", ex=int(ttl_sec))
                    return {"ok": True}
                if action == "del":
                    return {"ok": True, "deleted": int(await client.delete(key))}
                if action == "ping":
                    return {"ok": bool(await client.ping())}
            finally:
                await client.aclose()
        except Exception as exc:
            return {"error": UPSTREAM_ERROR, "reason": f"dragonfly: {redact_text(str(exc))[:300]}"}
        return {"error": "invalid_action", "reason": action}

    async def health(self) -> dict[str, Any]:
        return await self.command("ping", "health", None, 1)


class Hindsight:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "hindsight",
            settings.hindsight_url if settings.hindsight_api_key else "",
            headers={"Authorization": f"Bearer {settings.hindsight_api_key}"} if settings.hindsight_api_key else {},
            timeout=10.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/health")

    async def retain(self, bank: str, content: str, tags: list[str], context: str | None) -> dict[str, Any]:
        item: dict[str, Any] = {"content": redact_text(content), "tags": tags}
        if context:
            item["context"] = redact_text(context)
        return await self.http.request("POST", f"/v1/default/banks/{bank}/memories", json={"items": [item]})

    async def recall(self, bank: str, query: str, max_results: int) -> dict[str, Any]:
        body = {"query": query, "budget": "mid", "max_tokens": min(4096, 400 * max_results)}
        return await self.http.request("POST", f"/v1/default/banks/{bank}/memories/recall", json=body)


class RAGFlow:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "ragflow",
            settings.ragflow_url if settings.ragflow_api_key else "",
            headers={"Authorization": f"Bearer {settings.ragflow_api_key}"} if settings.ragflow_api_key else {},
            timeout=12.0,
        )

    async def health(self) -> dict[str, Any]:
        return await self.http.request("GET", "/api/v1/datasets", params={"page": 1, "page_size": 1})

    async def datasets(self) -> dict[str, Any]:
        return await self.http.request("GET", "/api/v1/datasets", params={"page": 1, "page_size": 100})

    async def retrieve(self, question: str, dataset_ids: list[str], top_k: int) -> dict[str, Any]:
        body = {"question": question, "dataset_ids": dataset_ids, "top_k": top_k, "page_size": top_k}
        return await self.http.request("POST", "/api/v1/retrieval", json=body)


RAILWAY_GRAPHQL = "https://backboard.railway.com/graphql/v2"


class Railway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "railway",
            RAILWAY_GRAPHQL if settings.railway_api_token else "",
            headers={"Authorization": f"Bearer {settings.railway_api_token}"} if settings.railway_api_token else {},
            timeout=15.0,
        )

    def project_id(self, name: str) -> str | None:
        return self.settings.railway_projects.get(name)

    async def gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        result = await self.http.request("POST", "", json={"query": query, "variables": variables})
        if result.get("ok") and isinstance(result.get("body"), dict) and result["body"].get("errors"):
            return {"error": UPSTREAM_ERROR, "reason": "railway graphql errors", "body": result["body"]["errors"]}
        return result

    async def project_status(self, name: str) -> dict[str, Any]:
        pid = self.project_id(name)
        if not pid:
            return not_configured(f"railway project {name}")
        query = """
        query Project($id: String!) {
          project(id: $id) { id name
            services { edges { node { id name
              serviceInstances { edges { node { environmentId latestDeployment { id status createdAt } } } } } } }
            environments { edges { node { id name } } } } }
        """
        result = await self.gql(query, {"id": pid})
        return result

    async def logs(self, deployment_id: str, lines: int) -> dict[str, Any]:
        query = "query Logs($id: String!, $limit: Int) { deploymentLogs(deploymentId: $id, limit: $limit) { timestamp message severity } }"
        return await self.gql(query, {"id": deployment_id, "limit": lines})

    async def variable_names(self, project_id: str, environment_id: str, service_id: str) -> dict[str, Any]:
        query = "query Vars($p: String!, $e: String!, $s: String) { variables(projectId: $p, environmentId: $e, serviceId: $s) }"
        result = await self.gql(query, {"p": project_id, "e": environment_id, "s": service_id})
        if result.get("ok"):
            data = (result.get("body") or {}).get("data") or {}
            names = sorted((data.get("variables") or {}).keys())
            return {"ok": True, "names": names}
        return result

    async def redeploy(self, service_id: str, environment_id: str) -> dict[str, Any]:
        query = "mutation Redeploy($s: String!, $e: String!) { serviceInstanceRedeploy(serviceId: $s, environmentId: $e) }"
        return await self.gql(query, {"s": service_id, "e": environment_id})


class Vercel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = HttpUpstream(
            "vercel",
            "https://api.vercel.com" if settings.vercel_token else "",
            headers={"Authorization": f"Bearer {settings.vercel_token}"} if settings.vercel_token else {},
            timeout=15.0,
        )

    def allowed(self, project: str) -> bool:
        return project in self.settings.vercel_projects

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(extra or {})
        if self.settings.vercel_team_id:
            params["teamId"] = self.settings.vercel_team_id
        return params

    async def deployments(self, project: str, limit: int) -> dict[str, Any]:
        return await self.http.request("GET", "/v6/deployments", params=self._params({"app": project, "limit": limit}))

    async def deployment(self, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/v13/deployments/{deployment_id}", params=self._params())

    async def promote(self, project: str, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/v10/projects/{project}/promote/{deployment_id}", params=self._params())

    async def rollback(self, project: str, deployment_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/v9/projects/{project}/rollback/{deployment_id}", params=self._params())


class Greptile:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        headers = {}
        if settings.greptile_api_key:
            headers["Authorization"] = f"Bearer {settings.greptile_api_key}"
        if settings.greptile_github_token:
            headers["X-GitHub-Token"] = settings.greptile_github_token
        self.http = HttpUpstream("greptile", "https://api.greptile.com/v2" if settings.greptile_api_key else "", headers=headers)

    async def trigger(self, repo: str, pr_number: int) -> dict[str, Any]:
        return await self.http.request("POST", "/reviews", json={"repository": repo, "remote": "github", "prNumber": pr_number})

    async def get(self, review_id: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/reviews/{review_id}")

    async def comments(self, repo: str, pr_number: int) -> dict[str, Any]:
        return await self.http.request("GET", "/reviews", params={"repository": repo, "prNumber": pr_number})


class GitHub:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "github",
            "https://api.github.com" if settings.github_token else "",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if settings.github_token
            else {},
            timeout=15.0,
        )

    async def comment_on_issue(self, repo: str, number: int, body: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/repos/{repo}/issues/{number}/comments", json={"body": body})

    async def find_issue_comment(self, repo: str, number: int, marker: str, *, max_pages: int = 5) -> dict[str, Any]:
        """Whether a comment carrying `marker` is already on the issue.

        `complete` is the honest part: the thread is walked oldest-first in pages, and a
        `found: false` that ran out of page budget is not evidence of absence. A caller using
        this to decide whether it already posted something must not post on `complete: false`.
        """
        for page in range(1, max_pages + 1):
            result = await self.http.request(
                "GET", f"/repos/{repo}/issues/{number}/comments", params={"per_page": 100, "page": page}
            )
            if not result.get("ok"):
                return result
            comments = result.get("body")
            if not isinstance(comments, list):
                return {"error": UPSTREAM_ERROR, "reason": "github returned no comment list for the issue"}
            for comment in comments:
                if isinstance(comment, dict) and marker in (comment.get("body") or ""):
                    return {"ok": True, "found": True, "complete": True}
            if len(comments) < 100:
                return {"ok": True, "found": False, "complete": True}
        return {"ok": True, "found": False, "complete": False}


class PlayConsole:
    def __init__(self, settings: Settings) -> None:
        self.http = HttpUpstream(
            "play-console",
            "https://androidpublisher.googleapis.com/androidpublisher/v3" if settings.play_access_token else "",
            headers={"Authorization": f"Bearer {settings.play_access_token}"} if settings.play_access_token else {},
            timeout=15.0,
        )

    async def edit(self, package_name: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/applications/{package_name}/edits", json={})

    async def track(self, package_name: str, edit_id: str, track: str) -> dict[str, Any]:
        return await self.http.request("GET", f"/applications/{package_name}/edits/{edit_id}/tracks/{track}")

    async def update_track(self, package_name: str, edit_id: str, track: str, body: dict[str, Any]) -> dict[str, Any]:
        return await self.http.request("PUT", f"/applications/{package_name}/edits/{edit_id}/tracks/{track}", json=body)

    async def commit(self, package_name: str, edit_id: str) -> dict[str, Any]:
        return await self.http.request("POST", f"/applications/{package_name}/edits/{edit_id}:commit", json={})


class AppStoreConnect:
    """ASC needs an ES256 JWT minted from the .p8 key. The gateway mints one per call when
    PyJWT is installed; without it the tools report not_configured rather than guessing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.asc_key_id and s.asc_issuer_id and s.asc_private_key_path)

    def _token(self) -> str | None:
        if not self.configured:
            return None
        try:
            import jwt
        except ImportError:
            return None
        try:
            key = open(self.settings.asc_private_key_path, encoding="utf-8").read()
        except OSError:
            return None
        now = int(time.time())
        return jwt.encode(
            {"iss": self.settings.asc_issuer_id, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"},
            key,
            algorithm="ES256",
            headers={"kid": self.settings.asc_key_id},
        )

    def client(self) -> HttpUpstream:
        token = self._token()
        return HttpUpstream(
            "app-store-connect",
            "https://api.appstoreconnect.apple.com/v1" if token else "",
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=15.0,
        )


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """Stop a child and reap it, so it cannot outlive the call that started it.

    Signals the whole process group, because the commands here start their own children: a
    gate runs git, and killing only the gate leaves git behind holding an index lock. TERM
    first so git can drop that lock, then KILL. The group exists because run_command starts
    each child in its own session.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):   # gone, or not ours to signal
            with contextlib.suppress(ProcessLookupError):
                proc.kill() if sig == signal.SIGKILL else proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 3)
            return
        except asyncio.TimeoutError:    # still there: fall through to KILL, then give up
            continue


async def run_command(
    argv: list[str],
    *,
    cwd: str | None = None,
    timeout: float = 15.0,
    input_text: str | None = None,
    max_out: int = 6000,
    run_as: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Run a command and return its exit code and (redacted) output.

    `run_as` is a (uid, gid) the child is dropped to before exec. Dropping needs the gateway
    to be root, so a failure to apply it is reported as a failed command rather than ignored:
    a gate that was meant to run unprivileged must not quietly run as root instead.
    """
    creds: dict[str, Any] = {"user": run_as[0], "group": run_as[1], "extra_groups": []} if run_as else {}
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if input_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # its own process group, so a timeout can kill the tree
            **creds,
        )
    except FileNotFoundError:
        return {"exit_code": 127, "stdout": "", "stderr": f"{argv[0]}: not found", "cmd": shlex.join(argv)}
    except (PermissionError, OSError, ValueError) as exc:
        detail = f" as uid {run_as[0]}" if run_as else ""
        return {"exit_code": 126, "stdout": "", "stderr": f"{argv[0]}: could not start{detail}: {redact_text(str(exc))[:200]}", "cmd": shlex.join(argv)}
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input_text.encode() if input_text is not None else None), timeout
        )
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        # wait_for only stops waiting; the child keeps running. Gate and git commands here
        # can be slow, and the unit runs as root, so an unreaped child per timeout
        # accumulates processes holding the export tree open. Kill and reap before
        # returning, and re-raise a cancellation rather than reporting it as a timeout.
        await _terminate(proc)
        if isinstance(exc, asyncio.CancelledError):
            raise
        return {"exit_code": 124, "stdout": "", "stderr": f"timed out after {timeout:.0f}s", "cmd": shlex.join(argv)}
    return {
        "exit_code": proc.returncode,
        "stdout": redact_text(out.decode(errors="replace")[-max_out:]),
        "stderr": redact_text(err.decode(errors="replace")[-3000:]),
        "cmd": shlex.join(argv),
    }
