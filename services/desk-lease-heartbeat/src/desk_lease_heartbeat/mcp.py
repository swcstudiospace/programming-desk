"""One JSON-RPC ``tools/call`` against substrate-mcp.

Same shape ``infra/lease-heartbeat/substrate-lease-reap.sh`` already uses for
``coord_reap_leases``: a single POST, JSON or SSE, no secret on the command
line. The tool here is ``graph_heartbeat``, the call ``desk_graph_state``
action ``heartbeat`` and ``coordination_graph_heartbeat`` already make.
"""

from __future__ import annotations

import json
import http.client
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from desk_lease_heartbeat.redact import redact

OutcomeKind = Literal["renewed", "rejected", "http", "unreachable", "unparseable", "tool"]

# How a tick classifies one lease. Exit codes in renew.py map from these.
EXIT_FOR: dict[OutcomeKind, int] = {
    "renewed": 0,
    "rejected": 0,
    "http": 2,
    "unreachable": 3,
    "unparseable": 4,
    "tool": 5,
}


@dataclass(frozen=True)
class CallOutcome:
    kind: OutcomeKind
    reason: str
    http_status: int | None = None


def call_graph_heartbeat(
    *,
    url: str,
    token: str,
    arguments: dict[str, object],
    timeout_s: float,
    log_bytes: int,
    secrets: list[str],
) -> CallOutcome:
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "graph_heartbeat", "arguments": arguments},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body)),
    }
    try:
        status, raw = _post(url, body, headers, timeout_s)
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        return CallOutcome("unreachable", type(exc).__name__)

    text = raw.decode("utf-8", errors="replace")
    if not 200 <= status <= 299:
        snippet = redact(text, secrets)[:log_bytes]
        return CallOutcome("http", f"HTTP {status} {snippet}".rstrip(), http_status=status)

    try:
        messages = [m for m in iter_messages(text) if isinstance(m, dict)]
    except (ValueError, json.JSONDecodeError) as exc:
        snippet = redact(text, secrets)[:log_bytes]
        return CallOutcome("unparseable", f"{exc}; {snippet}".rstrip())

    if not messages:
        snippet = redact(text, secrets)[:log_bytes]
        return CallOutcome("unparseable", f"no JSON-RPC message; {snippet}".rstrip())

    for message in messages:
        error = message.get("error")
        if error is not None:
            snippet = redact(json.dumps(error), secrets)[:log_bytes]
            return CallOutcome("tool", f"JSON-RPC error: {snippet}")
        result = message.get("result")
        if isinstance(result, dict) and result.get("isError"):
            snippet = redact(json.dumps(result), secrets)[:log_bytes]
            return CallOutcome("tool", f"isError: {snippet}")

    if not any("result" in message for message in messages):
        snippet = redact(text, secrets)[:log_bytes]
        return CallOutcome("unparseable", f"no result; {snippet}".rstrip())

    for message in messages:
        result = message.get("result")
        if not isinstance(result, dict):
            continue
        payload = _result_payload(result)
        if isinstance(payload, dict) and payload.get("ok") is False:
            reason = payload.get("reason")
            text_reason = reason if isinstance(reason, str) and reason else "unknown"
            return CallOutcome("rejected", redact(text_reason, secrets)[:200])
    return CallOutcome("renewed", "ok")


def iter_messages(text: str):
    """Yield JSON-RPC messages from a plain JSON body or an SSE stream.

    SSE follows the spec the reap wrapper documents: an event's data is all of
    its ``data:`` lines joined with newlines, dispatched at the blank line.
    ``[DONE]`` is skipped. One optional space after the colon is framing.
    """
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            yield from parsed
        else:
            yield parsed
        return

    found = False
    buf: list[str] = []

    def flush(parts: list[str]) -> object | None:
        payload = "\n".join(parts)
        if payload and payload != "[DONE]":
            return json.loads(payload)
        return None

    for line in text.splitlines():
        if line.startswith("data:"):
            chunk = line[5:]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            buf.append(chunk)
        elif line.strip() == "":
            if buf:
                msg = flush(buf)
                buf = []
                if msg is not None:
                    found = True
                    yield msg

    if buf:
        msg = flush(buf)
        if msg is not None:
            found = True
            yield msg

    if not found:
        raise ValueError("no JSON object and no SSE data: frame in response")


def _result_payload(result: dict[str, object]) -> object | None:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    content = result.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def _post(url: str, body: bytes, headers: dict[str, str], timeout_s: float) -> tuple[int, bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OSError("LEASE_ENDPOINT_URL is not an http(s) URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_cls(parsed.hostname, port, timeout=timeout_s)
    try:
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()
