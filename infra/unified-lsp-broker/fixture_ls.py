#!/usr/bin/env python3
"""Minimal LSP stdio server used by the Tier-1 spike.

Speaks Content-Length framing. On didOpen/didChange, publishes one diagnostic
per source line that contains the marker ``ulsp-diag:``. Set
``ULSP_FIXTURE_CRASH=1`` to exit on the first document sync so the broker can
prove per-language isolation.

This is not typescript-language-server, pyright, or gopls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def read_exact(stream, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def read_message(stream):
    headers: list[bytes] = []
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        headers.append(line)
    length = None
    for line in headers:
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    if length is None:
        return None
    body = read_exact(stream, length)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stream, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
    stream.flush()


def diagnostics_for(text: str, language: str) -> list[dict]:
    found: list[dict] = []
    for index, line in enumerate(text.splitlines()):
        marker = "ulsp-diag:"
        at = line.find(marker)
        if at < 0:
            continue
        message = line[at + len(marker):].strip() or "spike diagnostic"
        found.append(
            {
                "range": {
                    "start": {"line": index, "character": at},
                    "end": {"line": index, "character": len(line)},
                },
                "severity": 1,
                "source": f"ulsp-fixture-{language}",
                "message": message,
            }
        )
    return found


def publish(stream, uri: str, text: str, language: str) -> None:
    write_message(
        stream,
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": uri, "diagnostics": diagnostics_for(text, language)},
        },
    )


def text_from_did_change(params: dict) -> str | None:
    changes = params.get("contentChanges") or []
    if not changes:
        return None
    return changes[-1].get("text")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified LSP spike fixture language server")
    parser.add_argument("--language", required=True)
    args = parser.parse_args(argv)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    while True:
        message = read_message(stdin)
        if message is None:
            return 0
        method = message.get("method")
        if method == "initialize" and "id" in message:
            write_message(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "capabilities": {"textDocumentSync": 1},
                        "serverInfo": {
                            "name": f"ulsp-fixture-{args.language}",
                            "version": "0.0.1-spike",
                        },
                    },
                },
            )
            continue
        if method == "initialized":
            continue
        if method in ("textDocument/didOpen", "textDocument/didChange"):
            if os.environ.get("ULSP_FIXTURE_CRASH") == "1":
                os._exit(86)
            params = message.get("params") or {}
            if method == "textDocument/didOpen":
                doc = params.get("textDocument") or {}
                uri = doc.get("uri", "")
                text = doc.get("text", "")
            else:
                uri = params.get("textDocument", {}).get("uri", "")
                text = text_from_did_change(params) or ""
            publish(stdout, uri, text, args.language)
            continue
        if method == "shutdown" and "id" in message:
            write_message(stdout, {"jsonrpc": "2.0", "id": message["id"], "result": None})
            continue
        if method == "exit":
            return 0
        if "id" in message and method:
            write_message(stdout, {"jsonrpc": "2.0", "id": message["id"], "result": None})


if __name__ == "__main__":
    sys.exit(main())
