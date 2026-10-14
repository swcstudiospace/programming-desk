"""Tick behaviour: success, nothing held, upstream down or 401, partial failure."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from desk_lease_heartbeat.cli import main
from desk_lease_heartbeat.renew import run_renew

GRAPH = "ut-spe12499-0123abcd"
TOKEN = "test-token"
LEASE_A = "lease-a"
LEASE_B = "lease-b"


def _held(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"leases": rows}) + "\n", encoding="utf-8")


def _row(node_id: str, lease_id: str, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {"graph_id": GRAPH, "node_id": node_id, "lease_id": lease_id}
    body.update(extra)
    return body


def _env(tmp: Path, url: str, **extra: str) -> dict[str, str]:
    env = {
        "LEASE_SEAT": "bot-01-systems-backend",
        "LEASE_HOLDER_ID": "host-a",
        "LEASE_ENDPOINT_URL": url,
        "LEASE_ENDPOINT_TOKEN": TOKEN,
        "LEASE_STATE_DIR": str(tmp),
        "LEASE_TTL_S": "900",
        "LEASE_TIMEOUT_S": "2",
        "LEASE_LOG_LEVEL": "info",
    }
    env.update(extra)
    return env


class _Server:
    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}/mcp"

    def __enter__(self) -> _Server:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _ok_body() -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"isError": False, "content": [{"type": "text", "text": '{"ok": true}'}]},
        }
    ).encode()


def test_renew_success(tmp_path: Path, capsys: Any) -> None:
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            seen.append({"auth": self.headers.get("Authorization"), "body": json.loads(raw)})
            payload = _ok_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    held = tmp_path / "held.json"
    _held(held, [_row("n1", LEASE_A)])
    with _Server(Handler) as server:
        code = run_renew(
            environ=_env(tmp_path, server.url, LEASE_INTERVAL_S="60", LEASE_JITTER_S="5")
        )
    err = capsys.readouterr().err
    assert code == 0
    assert seen[0]["auth"] == f"Bearer {TOKEN}"
    call = seen[0]["body"]
    assert call["method"] == "tools/call"
    assert call["params"]["name"] == "graph_heartbeat"
    assert call["params"]["arguments"] == {
        "graph_id": GRAPH,
        "node_id": "n1",
        "lease_id": LEASE_A,
        "ttl_seconds": 900,
    }
    assert (tmp_path / "last-renewal").is_file()
    assert "renewed 1 lease(s)" in err
    assert LEASE_A not in err
    assert TOKEN not in err


def test_renew_success_over_sse(tmp_path: Path) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            payload = b"data: " + _ok_body() + b"\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    _held(tmp_path / "held.json", [_row("n2", LEASE_A)])
    with _Server(Handler) as server:
        assert run_renew(environ=_env(tmp_path, server.url)) == 0


def test_nothing_held_does_not_call_upstream(tmp_path: Path, capsys: Any) -> None:
    url = f"http://127.0.0.1:{_closed_port()}/mcp"
    code = run_renew(environ=_env(tmp_path, url))
    err = capsys.readouterr().err
    assert code == 0
    assert "nothing held" in err

    _held(tmp_path / "held.json", [])
    assert run_renew(environ=_env(tmp_path, url)) == 0


def test_upstream_not_configured(tmp_path: Path, capsys: Any) -> None:
    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    env = _env(tmp_path, "http://127.0.0.1:9/mcp", LEASE_ENDPOINT_TOKEN="")
    code = run_renew(environ=env)
    err = capsys.readouterr().err
    assert code == 0
    assert "upstream not configured" in err
    assert json.loads((tmp_path / "held.json").read_text())["leases"][0]["lease_id"] == LEASE_A


def test_upstream_down(tmp_path: Path, capsys: Any) -> None:
    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    url = f"http://127.0.0.1:{_closed_port()}/mcp"
    code = run_renew(environ=_env(tmp_path, url))
    err = capsys.readouterr().err
    assert code == 3
    assert "renew failed" in err
    assert TOKEN not in err
    assert LEASE_A not in err


def test_upstream_401_redacts_echoed_token(tmp_path: Path, capsys: Any) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            echoed = self.headers.get("Authorization", "")
            payload = json.dumps({"error": "unauthorized", "echo": echoed}).encode()
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    with _Server(Handler) as server:
        code = run_renew(environ=_env(tmp_path, server.url))
    err = capsys.readouterr().err
    assert code == 2
    assert "HTTP 401" in err
    assert "Bearer [redacted]" in err
    assert TOKEN not in err
    assert LEASE_A not in err


def test_partial_failure(tmp_path: Path, capsys: Any) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            node = body["params"]["arguments"]["node_id"]
            if node == "n1":
                payload, status = _ok_body(), 200
            else:
                payload, status = b'{"error":"nope"}', 500
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    _held(tmp_path / "held.json", [_row("n1", LEASE_A), _row("n2", LEASE_B)])
    with _Server(Handler) as server:
        code = run_renew(environ=_env(tmp_path, server.url))
    err = capsys.readouterr().err
    assert code == 1
    remaining = json.loads((tmp_path / "held.json").read_text())["leases"]
    assert [row["node_id"] for row in remaining] == ["n1", "n2"]
    assert not (tmp_path / "last-renewal").exists()
    assert LEASE_A not in err and LEASE_B not in err and TOKEN not in err


def test_rejected_lease_is_dropped_and_exits_0(tmp_path: Path, capsys: Any) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            text = json.dumps({"ok": False, "reason": "expired", "lease_id": LEASE_A})
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}]}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    with _Server(Handler) as server:
        code = run_renew(environ=_env(tmp_path, server.url))
    err = capsys.readouterr().err
    assert code == 0
    assert json.loads((tmp_path / "held.json").read_text())["leases"] == []
    assert "expired" in err
    assert LEASE_A not in err


def test_env_file_token_is_sent_literally(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            seen.append(self.headers.get("Authorization", ""))
            payload = _ok_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    for key in list(os.environ):
        if key.startswith("LEASE_"):
            monkeypatch.delenv(key, raising=False)
    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    env_file = tmp_path / "heartbeat.env"
    with _Server(Handler) as server:
        env_file.write_text(
            "\n".join(
                [
                    "LEASE_SEAT=bot-01-systems-backend",
                    "LEASE_HOLDER_ID=host-a",
                    f"LEASE_ENDPOINT_URL={server.url}",
                    "LEASE_ENDPOINT_TOKEN='pa$$word'",
                    f"LEASE_STATE_DIR={tmp_path}",
                    "LEASE_TIMEOUT_S=2",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        code = main(["renew", "--env-file", str(env_file)])
    err = capsys.readouterr().err
    assert code == 0
    assert seen == ["Bearer pa$$word"]
    assert "pa$$word" not in err


def test_module_entrypoint_exits_with_the_tick_code(tmp_path: Path) -> None:
    import subprocess
    import sys

    env = {key: value for key, value in os.environ.items() if not key.startswith("LEASE_")}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    env["LEASE_STATE_DIR"] = str(tmp_path)
    nothing = subprocess.run(
        [sys.executable, "-m", "desk_lease_heartbeat", "renew"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert nothing.returncode == 0
    assert "nothing held" in nothing.stderr

    _held(tmp_path / "held.json", [_row("n1", LEASE_A)])
    env["LEASE_ENDPOINT_URL"] = f"http://127.0.0.1:{_closed_port()}/mcp"
    env["LEASE_ENDPOINT_TOKEN"] = TOKEN
    env["LEASE_TIMEOUT_S"] = "1"
    down = subprocess.run(
        [sys.executable, "-m", "desk_lease_heartbeat", "renew"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert down.returncode == 3
    assert TOKEN not in down.stderr
    assert LEASE_A not in down.stderr


def test_cadence_invariant_rejects_a_budget_the_ttl_cannot_cover(tmp_path: Path, capsys: Any) -> None:
    env = _env(
        tmp_path,
        "http://127.0.0.1:9/mcp",
        LEASE_TTL_S="90",
        LEASE_INTERVAL_S="60",
        LEASE_JITTER_S="5",
        LEASE_TIMEOUT_S="30",
    )
    code = run_renew(environ=env)
    err = capsys.readouterr().err
    assert code == 6
    assert "LEASE_TTL_S/3" in err


def test_overall_timeout_is_one_budget_for_the_tick(tmp_path: Path) -> None:
    started: list[float] = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            started.append(time.monotonic())
            release.wait(timeout=5)
            payload = _ok_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    _held(tmp_path / "held.json", [_row("n1", LEASE_A), _row("n2", LEASE_B)])
    with _Server(Handler) as server:
        began = time.monotonic()
        code = run_renew(environ=_env(tmp_path, server.url, LEASE_TIMEOUT_S="1"))
        elapsed = time.monotonic() - began
        release.set()
    # Two leases each given their own 1s budget would take about 2s against a
    # handler that blocks. One shared budget returns after the first call.
    assert code == 3
    assert elapsed < 1.8


def test_malformed_held_file_is_a_real_failure(tmp_path: Path) -> None:
    (tmp_path / "held.json").write_text("{", encoding="utf-8")
    code = run_renew(environ=_env(tmp_path, "http://127.0.0.1:9/mcp"))
    assert code == 6
