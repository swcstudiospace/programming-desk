#!/usr/bin/env python3
"""Tier-1 broker proof: install-on-demand, diagnostics, isolation, loopback WS.

Fixture workspace (ASSUMPTION, chosen this run):
  infra/unified-lsp-broker/fixtures/{tsjs/sample.ts,tsjs/sample.js,python/sample.py,go/sample.go}

The language server under test is the in-repo fixture, not typescript-language-server,
pyright-langserver, or gopls. Production install plans are printed and not executed.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

BROKER = Path(__file__).resolve().parent / "broker.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PY = sys.executable


def expect(cond: bool, message: str) -> None:
    if not cond:
        raise SystemExit(message)


def run_broker(args: list[str], env: dict | None = None, timeout: float = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(BROKER), *args],
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
        check=False,
    )


def parse_stdout(proc: subprocess.CompletedProcess) -> dict:
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        raise SystemExit(f"no stdout for {proc.args}: stderr={proc.stderr!r}")
    return json.loads(line[-1])


def rpc(state: Path, method: str, params: dict | None = None, env: dict | None = None) -> tuple[int, dict]:
    request = json.dumps({"id": method, "method": method, "params": params or {}})
    proc = subprocess.run(
        [PY, str(BROKER), "--state-dir", str(state), "rpc"],
        input=request + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
        check=False,
    )
    return proc.returncode, parse_stdout(proc)


def start_daemon(state: Path, workspace: Path, ws: str | None, env: dict) -> tuple[subprocess.Popen, dict]:
    cmd = [PY, str(BROKER), "--state-dir", str(state), "start", "--workspace", str(workspace)]
    if ws:
        cmd.extend(["--ws", ws])
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    assert proc.stdout is not None
    if proc.stderr is not None:
        threading.Thread(target=proc.stderr.read, daemon=True).start()
    line = proc.stdout.readline()
    if proc.poll() is not None:
        err = proc.stderr.read() if proc.stderr is not None else ""
        raise SystemExit(f"daemon exited early code={proc.returncode} line={line!r} stderr={err!r}")
    return proc, json.loads(line)


def stop_daemon(state: Path) -> None:
    proc = run_broker(["--state-dir", str(state), "stop"], timeout=15)
    if proc.returncode != 0:
        raise SystemExit(f"stop failed code={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")


def ws_call(host: str, port: int, payload: dict) -> dict:
    sock = socket.create_connection((host, port), timeout=5)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        status = data.split(b"\r\n", 1)[0]
        expect(b" 101 " in status, f"websocket handshake failed: {status!r}")
        body = json.dumps(payload).encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        header = bytearray([0x81])
        if len(body) < 126:
            header.append(0x80 | len(body))
        else:
            header.append(0x80 | 126)
            header.extend(len(body).to_bytes(2, "big"))
        sock.sendall(bytes(header) + mask + masked)
        hdr = _recvn(sock, 2)
        opcode = hdr[0] & 0x0F
        length = hdr[1] & 0x7F
        expect(opcode == 0x1, f"unexpected websocket opcode {opcode}")
        if length == 126:
            length = int.from_bytes(_recvn(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(_recvn(sock, 8), "big")
        payload_out = _recvn(sock, length)
        return json.loads(payload_out.decode("utf-8"))
    finally:
        sock.close()


def _recvn(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise SystemExit("websocket closed early")
        buf.extend(chunk)
    return bytes(buf)


def marker_present(message: dict, needle: str) -> bool:
    diags = (message.get("result") or {}).get("diagnostics") or []
    return any(needle in str(item.get("message", "")) for item in diags)


def main() -> int:
    env = os.environ.copy()
    env["ULSP_SPIKE_HOOKS"] = "1"
    env["ULSP_SERVER_MODE"] = "spike"
    env["PYTHONUNBUFFERED"] = "1"

    cold = Path(tempfile.mkdtemp(prefix="ulsp-cold-"))
    cold_proc = run_broker(["--state-dir", str(cold), "health"], env=env)
    cold_body = parse_stdout(cold_proc)
    expect(cold_proc.returncode == 0, f"cold health exit {cold_proc.returncode}")
    expect(cold_body["result"]["state"] == "cold", f"expected cold, got {cold_body}")

    unbound = Path(tempfile.mkdtemp(prefix="ulsp-unbound-"))
    unbound_proc = run_broker(["--state-dir", str(unbound), "start"], env=env)
    unbound_body = parse_stdout(unbound_proc)
    expect(unbound_proc.returncode != 0, "start without workspace should fail")
    expect(unbound_body["error"]["code"] == "workspace_unbound", unbound_body)

    forbidden = Path(tempfile.mkdtemp(prefix="ulsp-ws-forbid-"))
    forbid_proc = run_broker(
        ["--state-dir", str(forbidden), "start", "--workspace", str(FIXTURES), "--ws", "0.0.0.0:9"],
        env=env,
    )
    forbid_body = parse_stdout(forbid_proc)
    expect(forbid_proc.returncode != 0, "non-loopback websocket should fail")
    expect(forbid_body["error"]["code"] == "ws_host_forbidden", forbid_body)
    expect(not (forbidden / "broker.pid").exists(), f"failed start wrote a pid file: {forbid_body}")

    plans = {}
    for language, command in (
        ("tsjs", "typescript-language-server"),
        ("python", "pyright-langserver"),
        ("go", "gopls"),
    ):
        proc = run_broker(["--state-dir", str(cold), "plan", "--language", language], env=env)
        body = parse_stdout(proc)
        expect(proc.returncode == 0, f"plan {language} failed: {body}")
        expect(body["result"]["executed"] is False, body)
        expect(body["result"]["production_server"]["command"] == command, body)
        plans[language] = command

    rust = run_broker(["--state-dir", str(cold), "plan", "--language", "rust"], env=env)
    rust_body = parse_stdout(rust)
    expect(rust.returncode != 0, "rust plan should fail")
    expect(rust_body["error"]["code"] == "language_not_tier1", rust_body)

    state = Path(tempfile.mkdtemp(prefix="ulsp-broker-"))
    daemon, info = start_daemon(state, FIXTURES, "127.0.0.1:0", env)
    try:
        expect(info["state"] == "ready", info)
        expect(info["ws"]["host"] == "127.0.0.1", info)
        expect(info["ws"]["port"] != 0, info)

        code, missing = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code != 0 and missing["error"]["code"] == "language_server_missing", missing)

        code, other = rpc(state, "install", {"language": "rust"}, env)
        expect(code != 0 and other["error"]["code"] == "language_not_tier1", other)

        for language in ("tsjs", "python", "go"):
            code, installed = rpc(state, "install", {"language": language}, env)
            expect(code == 0 and installed["result"]["installed"] is True, installed)
            code, again = rpc(state, "install", {"language": language}, env)
            expect(code == 0 and again["result"]["idempotent"] is True, again)

        expected = {
            ("tsjs", "tsjs/sample.ts"): "intentional spike diagnostic for tsjs",
            ("tsjs", "tsjs/sample.js"): "intentional spike diagnostic for javascript",
            ("python", "python/sample.py"): "intentional spike diagnostic for python",
            ("go", "go/sample.go"): "intentional spike diagnostic for go",
        }
        for (language, rel), needle in expected.items():
            code, body = rpc(state, "diagnostics", {"language": language, "path": rel}, env)
            expect(code == 0 and body["ok"] is True, body)
            expect(marker_present(body, needle), body)
            if rel.endswith(".js"):
                expect(body["result"]["language_id"] == "javascript", body)
            if rel.endswith(".ts"):
                expect(body["result"]["language_id"] == "typescript", body)

        code, health = rpc(state, "health", {}, env)
        expect(code == 0 and health["result"]["state"] == "serving", health)
        live_pids = [
            item["pid"]
            for item in health["result"]["sessions"].values()
            if item.get("status") == "running" and item.get("pid")
        ]
        expect(len(live_pids) >= 3, health)

        code, escape = rpc(state, "diagnostics", {"language": "go", "path": "../registry/tier1.json"}, env)
        expect(code != 0 and escape["error"]["code"] == "workspace_escape", escape)

        code, armed = rpc(state, "arm_crash", {"language": "python"}, env)
        expect(code == 0 and armed["result"]["armed"] == "python", armed)
        code, crashed = rpc(state, "diagnostics", {"language": "python", "path": "python/sample.py"}, env)
        expect(code != 0 and crashed["error"]["code"] == "language_server_failed", crashed)
        code, still_ts = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(still_ts, "intentional spike diagnostic for tsjs"), still_ts)
        code, still_go = rpc(state, "diagnostics", {"language": "go", "path": "go/sample.go"}, env)
        expect(code == 0 and marker_present(still_go, "intentional spike diagnostic for go"), still_go)
        code, degraded = rpc(state, "health", {}, env)
        expect(degraded["result"]["state"] == "degraded", degraded)
        expect(degraded["result"]["sessions"]["python"]["status"] == "failed", degraded)

        ws_body = ws_call(info["ws"]["host"], info["ws"]["port"], {"id": "ws", "method": "health", "params": {}})
        expect(ws_body["ok"] is True and ws_body["result"]["state"] == "degraded", ws_body)
        expect(ws_body["result"]["ws_role"] == "optional-localhost", ws_body)
    finally:
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()

    expect(daemon.poll() is not None, "daemon still running after stop")
    stopped = run_broker(["--state-dir", str(state), "health"], env=env)
    stopped_body = parse_stdout(stopped)
    expect(stopped_body["result"]["state"] == "stopped", stopped_body)
    deadline = time.time() + 3
    while time.time() < deadline:
        if all(not _alive(pid) for pid in live_pids):
            break
        time.sleep(0.05)
    lingering = [pid for pid in live_pids if _alive(pid)]
    expect(not lingering, f"language server pids still alive: {lingering}")

    print(
        "SPIKE_OK "
        f"plans={','.join(f'{k}:{v}' for k, v in plans.items())} "
        "diagnostics=ts,js,python,go isolation=python crashed, tsjs+go served "
        "ws=127.0.0.1 optional state_after_stop=stopped"
    )
    return 0


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
