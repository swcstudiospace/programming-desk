#!/usr/bin/env python3
"""Tier-1 broker proof: install-on-demand, diagnostics, isolation, loopback WS.

Fixture workspace (ASSUMPTION, chosen this run):
  infra/unified-lsp-broker/fixtures/{tsjs/sample.ts,tsjs/sample.js,python/sample.py,go/sample.go}

The language server under test is the in-repo fixture, not typescript-language-server,
pyright-langserver, or gopls. Production install plans are printed and not executed.
"""

from __future__ import annotations

import atexit
import base64
import json
import os
import shlex
import shutil
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
    proc = run_broker(["--state-dir", str(state), "stop"], timeout=30)
    if proc.returncode != 0:
        raise SystemExit(f"stop failed code={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")


def ws_open(host: str, port: int, origin: str | None, presented: str | None) -> tuple[socket.socket, bytes]:
    sock = socket.create_connection((host, port), timeout=5)
    sock.settimeout(5)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    extra = ""
    if origin is not None:
        extra += f"Origin: {origin}\r\n"
    if presented is not None:
        extra += f"X-ULSP-WS-Token: {presented}\r\n"
    request = (
        f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
        f"{extra}\r\n"
    )
    sock.sendall(request.encode("ascii"))
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    status = data.split(b"\r\n", 1)[0]
    return sock, status


def ws_call(host: str, port: int, payload: dict, origin: str, presented: str) -> dict:
    sock, status = ws_open(host, port, origin, presented)
    try:
        expect(b" 101 " in status, f"websocket handshake failed: {status!r}")
        body = json.dumps(payload).encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        header = bytearray([0x81, 0x80 | len(body)])
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


def ws_status(host: str, port: int, origin: str | None, presented: str | None) -> bytes:
    sock, status = ws_open(host, port, origin, presented)
    sock.close()
    return status


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


_TEMPS: list[Path] = []


def scratch(prefix: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMPS.append(path)
    return path


def _cleanup_temps() -> None:
    for path in _TEMPS:
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_cleanup_temps)


HUNG_LS = """import json, sys

def read_exact(n):
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def read_message():
    headers = []
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\\r\\n", b"\\n"):
            break
        headers.append(line)
    length = None
    for line in headers:
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    if length is None:
        return None
    body = read_exact(length)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))

def write_message(payload):
    data = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\\r\\n\\r\\n".encode("ascii") + data)
    sys.stdout.buffer.flush()

while True:
    msg = read_message()
    if msg is None:
        break
    if msg.get("method") == "initialize" and "id" in msg:
        write_message({"jsonrpc": "2.0", "id": msg["id"], "result": {"capabilities": {}}})
"""


def main() -> int:
    env = os.environ.copy()
    env["ULSP_SPIKE_HOOKS"] = "1"
    env["ULSP_SERVER_MODE"] = "spike"
    env["PYTHONUNBUFFERED"] = "1"

    cold = scratch("ulsp-cold-")
    cold_proc = run_broker(["--state-dir", str(cold), "health"], env=env)
    cold_body = parse_stdout(cold_proc)
    expect(cold_proc.returncode == 0, f"cold health exit {cold_proc.returncode}")
    expect(cold_body["result"]["state"] == "cold", f"expected cold, got {cold_body}")

    unbound = scratch("ulsp-unbound-")
    unbound_proc = run_broker(["--state-dir", str(unbound), "start"], env=env)
    unbound_body = parse_stdout(unbound_proc)
    expect(unbound_proc.returncode != 0, "start without workspace should fail")
    expect(unbound_body["error"]["code"] == "workspace_unbound", unbound_body)

    forbidden = scratch("ulsp-ws-forbid-")
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

    work = scratch("ulsp-work-")
    shutil.copytree(FIXTURES, work, dirs_exist_ok=True)
    (work / ".env").write_text("API_KEY=abc123\n", encoding="utf-8")
    (work / "tsjs" / "leak.ts").write_text(
        "const leak = 1;\nulsp-diag: API_KEY=abc123 " + ("p" * 400) + "\n",
        encoding="utf-8",
    )
    (work / "tsjs" / "nul.ts").write_bytes(b"const nul = 1;\n\x00\n")
    (work / ".git").mkdir()
    (work / ".git" / "config").write_text("not-opened\n", encoding="utf-8")
    (work / "id_rsa").write_text("not-a-real-key\n", encoding="utf-8")
    (work / "notes.key").write_text("not-opened\n", encoding="utf-8")

    state = scratch("ulsp-broker-")
    daemon, info = start_daemon(state, work, "127.0.0.1:0", env)
    grandchild = 0
    try:
        expect(info["state"] == "ready", info)
        expect(info["ws"]["host"] == "127.0.0.1", info)
        expect(info["ws"]["port"] != 0, info)
        share = str(info.get("share") or "")
        expect(len(share) > 8, "listening line missing share")
        origin = f"http://{info['ws']['host']}:{info['ws']['port']}"

        code, missing = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code != 0 and missing["error"]["code"] == "language_server_missing", missing)

        code, other = rpc(state, "install", {"language": "rust"}, env)
        expect(code != 0 and other["error"]["code"] == "language_not_tier1", other)

        for language in ("tsjs", "python", "go"):
            code, installed = rpc(state, "install", {"language": language}, env)
            expect(code == 0 and installed["result"]["installed"] is True, installed)
            expect("bin" not in installed["result"], installed)
            blob = json.dumps(installed)
            expect("/tmp" not in blob and "/workspace" not in blob and "/home" not in blob, blob)
            code, again = rpc(state, "install", {"language": language}, env)
            expect(code == 0 and again["result"]["idempotent"] is True, again)

        go_wrapper = state / "bin" / "ulsp-ls-go"
        exec_line = next(line for line in go_wrapper.read_text(encoding="utf-8").splitlines() if line.startswith("exec "))
        pidfile = state / "go-grandchild.pid"
        go_wrapper.write_text(
            "#!/bin/sh\nsleep 300 &\n"
            f"echo $! > {shlex.quote(str(pidfile))}\n"
            f"{exec_line}\n",
            encoding="utf-8",
        )
        go_wrapper.chmod(0o755)

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
            expect(body["result"]["truncated"] is False, body)
            expect("STALE" not in json.dumps(body), body)
            public = json.dumps(body)
            expect("/tmp" not in public and "/workspace" not in public and "/home" not in public, public)
            expect("stderr" not in body["result"], body)

        many = work / "tsjs" / "many.ts"
        many.write_text("".join(f"ulsp-diag: item {index}\n" for index in range(40)), encoding="utf-8")
        code, many_body = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/many.ts"}, env)
        expect(code == 0, many_body)
        expect(many_body["result"]["truncated"] is True, many_body)
        expect(many_body["result"]["diagnostics_total"] == 40, many_body)
        expect(len(many_body["result"]["diagnostics"]) == 32, many_body)
        expect("STALE" not in json.dumps(many_body), many_body)

        wide = work / "tsjs" / "wide.ts"
        wide.write_text("".join(f"ulsp-diag: {'m' * 180}\n" for _ in range(40)), encoding="utf-8")
        code, wide_body = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/wide.ts"}, env)
        expect(code == 0, wide_body)
        expect(wide_body["result"]["diagnostics_total"] == 40, wide_body)
        expect(wide_body["result"]["truncated"] is True, wide_body)
        expect(len(wide_body["result"]["diagnostics"]) < 40, wide_body)

        big = work / "tsjs" / "big.ts"
        big.write_bytes(b"const big = 1;\n" + b"x" * 1_048_576)
        code, big_body = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/big.ts"}, env)
        expect(code != 0 and big_body["error"]["code"] == "file_too_large", big_body)
        expect(big_body["error"]["details"]["limit_bytes"] == 1_048_576, big_body)
        expect("1048576" in big_body["error"]["message"], big_body)

        second = run_broker(
            ["--state-dir", str(state), "start", "--workspace", str(work)],
            env=env,
            timeout=8,
        )
        second_body = parse_stdout(second)
        expect(second.returncode != 0, second_body)
        expect(second_body["error"]["code"] == "broker_already_running", second_body)
        code, still_up = rpc(state, "health", {}, env)
        expect(code == 0 and still_up["ok"] is True, still_up)

        expect(pidfile.exists(), "grandchild pid was not recorded")
        grandchild = int(pidfile.read_text(encoding="utf-8").strip())
        expect(_alive(grandchild), f"grandchild {grandchild} was not alive before stop")

        denied = {
            ".env": "extension_not_allowed",
            ".git/config": "extension_not_allowed",
            "id_rsa": "extension_not_allowed",
            "notes.key": "extension_not_allowed",
            "tsjs/nul.ts": "invalid_arguments",
        }
        for rel, err_code in denied.items():
            code, body = rpc(state, "diagnostics", {"language": "tsjs", "path": rel}, env)
            expect(code != 0 and body["error"]["code"] == err_code, body)
            expect("abc123" not in json.dumps(body), body)
            code, probed = rpc(state, "probe", {"language": "tsjs", "path": rel}, env)
            if rel != "tsjs/nul.ts":
                expect(code != 0 and probed["error"]["code"] == "extension_not_allowed", probed)
            expect("abc123" not in json.dumps(probed), probed)

        code, leaked = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/leak.ts"}, env)
        expect(code == 0, leaked)
        messages = [str(item.get("message", "")) for item in leaked["result"]["diagnostics"]]
        expect(any("[REDACTED]" in item for item in messages), leaked)
        expect("abc123" not in json.dumps(leaked), leaked)
        expect(all(len(item) <= 240 for item in messages), messages)

        raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        raw.settimeout(5)
        raw.connect(str(state / "broker.sock"))
        raw.sendall(b"\x00\n")
        raw_buf = b""
        while b"\n" not in raw_buf:
            chunk = raw.recv(4096)
            expect(bool(chunk), "broker dropped the NUL request")
            raw_buf += chunk
        raw.close()
        nul_body = json.loads(raw_buf.split(b"\n", 1)[0].decode("utf-8"))
        expect(nul_body["ok"] is False and nul_body["error"]["code"] == "invalid_arguments", nul_body)

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

        host = info["ws"]["host"]
        port = info["ws"]["port"]
        missing_origin = ws_status(host, port, None, share)
        expect(b" 403 " in missing_origin, missing_origin)
        foreign = ws_status(host, port, "https://evil.example", share)
        expect(b" 403 " in foreign, foreign)
        bad_share = ws_status(host, port, origin, "not-the-share")
        expect(b" 401 " in bad_share, bad_share)
        ws_body = ws_call(host, port, {"id": "ws", "method": "health", "params": {}}, origin, share)
        expect(ws_body["ok"] is True and ws_body["result"]["state"] == "degraded", ws_body)
        expect(ws_body["result"]["ws_role"] == "optional-localhost", ws_body)
        expect("share" not in ws_body["result"], "health leaked the share value")
        public_health = json.dumps(ws_body)
        expect("/tmp" not in public_health and "/workspace" not in public_health, public_health)

        oversized, upgraded = ws_open(host, port, origin, share)
        try:
            expect(b" 101 " in upgraded, upgraded)
            oversized.sendall(bytes([0x81, 0x80 | 127]) + (70_000).to_bytes(8, "big"))
            oversized.settimeout(2)
            try:
                oversized.recv(16)
            except (socket.timeout, OSError):
                pass
        finally:
            oversized.close()
        code, after_frame = rpc(state, "health", {}, env)
        expect(code == 0 and after_frame["ok"] is True, after_frame)
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
    expect(grandchild != 0 and not _alive(grandchild), f"grandchild survived stop: {grandchild}")
    prove_timeout_clamp()
    prove_budget_rejects_nonfinite()
    prove_timeout_recovers(work, env)
    prove_queue_timeout_keeps_session(work, env)
    prove_concurrent_claim(work, env)
    prove_shutdown_waits_for_diagnostics(work, env)
    prove_idle_clients_release(work, env)
    prove_trickle_releases_slot(work, env)
    prove_stop_past_five_seconds(work, env)
    prove_file_read_errors(work, env)

    print(
        "SPIKE_OK "
        f"plans={','.join(f'{k}:{v}' for k, v in plans.items())} "
        "diagnostics=ts,js,python,go isolation=python crashed, tsjs+go served "
        "ws=127.0.0.1 optional state_after_stop=stopped "
        "f1=origin f2=ext f3=redacted f4=nopath f5=grandchild f8=nul "
        "p1=trunc,limit,owner,deadline,queue p2=timeout,version,total,nan "
        "p3=lock,shutdown,idle,file,trickle,stop"
    )
    return 0


def prove_timeout_clamp() -> None:
    script = (
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('ulsp_broker', 'infra/unified-lsp-broker/broker.py')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(mod)\n"
        "print(f'{mod.parse_lsp_timeout():.6f}')\n"
        "print(f'{mod.REQUEST_BUDGET_S:.6f}')\n"
        "print(f'{mod.CLIENT_RPC_DEADLINE_S:.6f}')\n"
    )
    env = os.environ.copy()
    env["ULSP_LSP_TIMEOUT_S"] = "30"
    proc = subprocess.run([PY, "-c", script], text=True, capture_output=True, env=env, timeout=10, check=False)
    expect(proc.returncode == 0, proc.stderr or proc.stdout)
    phase_s, budget_s, client_s = (float(line) for line in proc.stdout.strip().splitlines())
    expect(phase_s * 2 <= budget_s <= client_s, proc.stdout)
    expect(phase_s < 30, proc.stdout)


def prove_budget_rejects_nonfinite() -> None:
    script = (
        "import math, os, importlib.util\n"
        "spec = importlib.util.spec_from_file_location('ulsp_broker', 'infra/unified-lsp-broker/broker.py')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(mod)\n"
        "for raw in ('NaN', 'nan', 'inf', '-inf', 'Infinity'):\n"
        "    os.environ['ULSP_REQUEST_BUDGET_S'] = raw\n"
        "    budget = mod.request_budget()\n"
        "    assert math.isfinite(budget) and budget == mod.REQUEST_BUDGET_S, (raw, budget)\n"
        "print('finite')\n"
    )
    proc = subprocess.run([PY, "-c", script], text=True, capture_output=True, timeout=10, check=False)
    expect(proc.returncode == 0 and proc.stdout.strip() == "finite", proc.stderr or proc.stdout)


def prove_queue_timeout_keeps_session(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-queue-")
    env = dict(base_env)
    env["ULSP_REQUEST_BUDGET_S"] = "0.6"
    env["ULSP_SPIKE_HOOKS"] = "1"
    daemon, info = start_daemon(state, work, None, env)
    try:
        expect(info["state"] == "ready", info)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0 and installed["ok"] is True, installed)
        code, first = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(first, "intentional spike diagnostic for tsjs"), first)
        code, health = rpc(state, "health", {}, env)
        sess = health["result"]["sessions"]["tsjs"]
        pid = sess["pid"]
        expect(
            sess["status"] == "running" and isinstance(pid, int) and _alive(pid),
            f"fresh session {sess} alive={_alive(pid) if isinstance(pid, int) else None}",
        )
        (state / "spike_hold_s").write_text("0.9\n", encoding="utf-8")
        results: list[tuple[int, dict]] = []
        gate = threading.Lock()

        def one() -> None:
            item = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
            with gate:
                results.append(item)

        threads = [threading.Thread(target=one) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        expect(all(not thread.is_alive() for thread in threads), "queued diagnostics still running")
        expect(len(results) == 2, str(results))
        timed_out = [
            body
            for status, body in results
            if status != 0 and (body.get("error") or {}).get("code") == "diagnostics_timeout"
        ]
        expect(timed_out, str(results))
        code, health = rpc(state, "health", {}, env)
        sess = health["result"]["sessions"]["tsjs"]
        expect(sess["status"] == "running" and sess["pid"] == pid and _alive(pid), health)
        (state / "spike_hold_s").unlink()
        code, again = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(again, "intentional spike diagnostic for tsjs"), again)
        expect("STALE" not in json.dumps(again), again)
        code, health = rpc(state, "health", {}, env)
        expect(health["result"]["sessions"]["tsjs"]["pid"] == pid, health)
    finally:
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def prove_timeout_recovers(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-timeout-")
    env = dict(base_env)
    env["ULSP_LSP_TIMEOUT_S"] = "0.4"
    daemon, info = start_daemon(state, work, None, env)
    try:
        expect(info["state"] == "ready", info)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0 and installed["ok"] is True, installed)
        hung = state / "hung_ls.py"
        hung.write_text(HUNG_LS, encoding="utf-8")
        wrapper = state / "bin" / "ulsp-ls-tsjs"
        wrapper.write_text(
            "#!/bin/sh\nexec "
            + shlex.quote(sys.executable)
            + " "
            + shlex.quote(str(hung))
            + "\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        started = time.monotonic()
        code, timed = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        elapsed = time.monotonic() - started
        expect(code != 0 and timed["error"]["code"] == "diagnostics_timeout", timed)
        expect(elapsed < 3, f"timeout waited {elapsed:.2f}s")
        code, health = rpc(state, "health", {}, env)
        expect(health["result"]["sessions"]["tsjs"]["status"] == "failed", health)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0, installed)
        code, recovered = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(recovered, "intentional spike diagnostic for tsjs"), recovered)
        expect("STALE" not in json.dumps(recovered), recovered)
    finally:
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def prove_concurrent_claim(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-claim-")
    env = dict(base_env)
    env["ULSP_SPIKE_HOOKS"] = "1"
    env["ULSP_SPIKE_CLAIM_HOLD_S"] = "0.8"
    cmd = [PY, str(BROKER), "--state-dir", str(state), "start", "--workspace", str(work)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not (state / "broker.lock").exists():
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr is not None else ""
                raise SystemExit(f"claim holder exited early stderr={err!r}")
            time.sleep(0.02)
        expect((state / "broker.lock").exists(), "owner lock was not created")
        time.sleep(0.05)
        rival_env = dict(base_env)
        rival_env.pop("ULSP_SPIKE_CLAIM_HOLD_S", None)
        rival = run_broker(
            ["--state-dir", str(state), "start", "--workspace", str(work)],
            env=rival_env,
            timeout=8,
        )
        body = parse_stdout(rival)
        expect(rival.returncode != 0 and body["error"]["code"] == "broker_already_running", body)
        assert proc.stdout is not None
        line = proc.stdout.readline()
        info = json.loads(line)
        expect(info.get("event") == "listening", info)
        code, health = rpc(state, "health", {}, env)
        expect(code == 0 and health["ok"] is True and health["result"]["state"] == "ready", health)
    finally:
        if proc.poll() is None:
            stop = run_broker(["--state-dir", str(state), "stop"], timeout=15)
            if stop.returncode != 0:
                proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def prove_shutdown_waits_for_diagnostics(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-stop-")
    env = dict(base_env)
    env["ULSP_SPIKE_HOOKS"] = "1"
    daemon, info = start_daemon(state, work, None, env)
    try:
        expect(info["state"] == "ready", info)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0 and installed["ok"] is True, installed)
        code, first = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(first, "intentional spike diagnostic for tsjs"), first)
        (state / "spike_hold_s").write_text("0.7\n", encoding="utf-8")
        holder: dict[str, tuple[int, dict]] = {}

        def run_diag() -> None:
            holder["item"] = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)

        thread = threading.Thread(target=run_diag)
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not (state / "spike_hold_ready").exists():
            time.sleep(0.02)
        expect((state / "spike_hold_ready").exists(), "diagnostics never reached the language-lock hold")
        started = time.monotonic()
        stop_daemon(state)
        elapsed = time.monotonic() - started
        thread.join(timeout=5)
        expect(not thread.is_alive(), "diagnostics still running after stop")
        status, body = holder["item"]
        expect(status == 0 and body["ok"] is True, body)
        expect(elapsed >= 0.2, f"stop did not wait for in-flight diagnostics ({elapsed:.2f}s)")
        recorded = json.loads((state / "state.json").read_text(encoding="utf-8"))
        expect(recorded.get("state") == "stopped", recorded)
        expect(not _alive(int(recorded["pid"])), recorded)
    finally:
        if daemon.poll() is None:
            try:
                stop_daemon(state)
            except SystemExit:
                daemon.kill()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def prove_idle_clients_release(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-idle-")
    env = dict(base_env)
    env["ULSP_MAX_CLIENTS"] = "1"
    env["ULSP_CLIENT_IDLE_S"] = "0.4"
    daemon, info = start_daemon(state, work, None, env)
    idle: socket.socket | None = None
    try:
        expect(info["state"] == "ready", info)
        idle = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        idle.settimeout(2)
        idle.connect(str(state / "broker.sock"))
        extra = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        extra.settimeout(2)
        extra.connect(str(state / "broker.sock"))
        extra_data = extra.recv(16)
        extra.close()
        expect(extra_data == b"", f"over-cap connection stayed open: {extra_data!r}")
        code, blocked = rpc(state, "health", {}, env)
        expect(code != 0 and blocked["error"]["code"] == "broker_not_running", blocked)
        time.sleep(0.7)
        code, health = rpc(state, "health", {}, env)
        expect(code == 0 and health["ok"] is True and health["result"]["state"] == "ready", health)
    finally:
        if idle is not None:
            idle.close()
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def _trickle(sock: socket.socket, seconds: float, stop: threading.Event) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not stop.is_set():
        try:
            sock.sendall(b"G")
        except OSError:
            return
        time.sleep(0.1)


def prove_trickle_releases_slot(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-trickle-")
    env = dict(base_env)
    env["ULSP_MAX_CLIENTS"] = "1"
    env["ULSP_CLIENT_IDLE_S"] = "0.4"
    daemon, info = start_daemon(state, work, "127.0.0.1:0", env)
    opened: list[socket.socket] = []
    try:
        expect(info["state"] == "ready" and info.get("ws"), info)

        def past_deadline(sock: socket.socket) -> None:
            opened.append(sock)
            stop = threading.Event()
            thread = threading.Thread(target=_trickle, args=(sock, 1.2, stop))
            thread.start()
            time.sleep(0.7)
            code, health = rpc(state, "health", {}, env)
            stop.set()
            thread.join(timeout=2)
            expect(code == 0 and health["ok"] is True and health["result"]["state"] == "ready", health)

        unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix.settimeout(2)
        unix.connect(str(state / "broker.sock"))
        past_deadline(unix)
        host = info["ws"]["host"]
        port = int(info["ws"]["port"])
        web = socket.create_connection((host, port), timeout=2)
        past_deadline(web)
    finally:
        for sock in opened:
            try:
                sock.close()
            except OSError:
                pass
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def prove_stop_past_five_seconds(work: Path, base_env: dict) -> None:
    state = scratch("ulsp-stop5-")
    env = dict(base_env)
    env["ULSP_SPIKE_HOOKS"] = "1"
    daemon, info = start_daemon(state, work, None, env)
    try:
        expect(info["state"] == "ready", info)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0 and installed["ok"] is True, installed)
        code, first = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)
        expect(code == 0 and marker_present(first, "intentional spike diagnostic for tsjs"), first)
        (state / "spike_hold_s").write_text("6.0\n", encoding="utf-8")
        holder: dict[str, tuple[int, dict]] = {}

        def run_diag() -> None:
            holder["item"] = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/sample.ts"}, env)

        thread = threading.Thread(target=run_diag)
        thread.start()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not (state / "spike_hold_ready").exists():
            time.sleep(0.02)
        expect((state / "spike_hold_ready").exists(), "diagnostics never reached the long hold")
        started = time.monotonic()
        stopped = run_broker(["--state-dir", str(state), "stop"], timeout=30)
        elapsed = time.monotonic() - started
        expect(stopped.returncode == 0, f"code={stopped.returncode} out={stopped.stdout!r} err={stopped.stderr!r}")
        expect(elapsed >= 5.0, f"stop returned inside the old five-second window ({elapsed:.2f}s)")
        thread.join(timeout=5)
        expect(not thread.is_alive(), "diagnostics still running after the long stop")
        status, body = holder["item"]
        expect(status == 0 and body["ok"] is True, body)
        recorded = json.loads((state / "state.json").read_text(encoding="utf-8"))
        expect(recorded.get("state") == "stopped", recorded)
        expect(not _alive(int(recorded["pid"])), recorded)
    finally:
        if daemon.poll() is None:
            daemon.kill()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def prove_file_read_errors(work: Path, base_env: dict) -> None:
    script = (
        "import tempfile, importlib.util\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('ulsp_broker', 'infra/unified-lsp-broker/broker.py')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(mod)\n"
        "path = Path(tempfile.mkdtemp()) / 'gone.ts'\n"
        "path.write_text('const gone = 1;\\n', encoding='utf-8')\n"
        "path.unlink()\n"
        "folder = path.parent / 'dir.ts'\n"
        "folder.mkdir()\n"
        "for target in (path, folder):\n"
        "    try:\n"
        "        mod.read_source(target)\n"
        "    except mod.BrokerError as exc:\n"
        "        assert exc.code == 'file_not_found', (target, exc.code)\n"
        "    else:\n"
        "        raise SystemExit(f'read succeeded for {target}')\n"
        "print('missing')\n"
    )
    proc = subprocess.run([PY, "-c", script], text=True, capture_output=True, timeout=10, check=False)
    expect(proc.returncode == 0 and proc.stdout.strip() == "missing", proc.stderr or proc.stdout)
    state = scratch("ulsp-file-")
    env = dict(base_env)
    daemon, info = start_daemon(state, work, None, env)
    try:
        expect(info["state"] == "ready", info)
        code, installed = rpc(state, "install", {"language": "tsjs"}, env)
        expect(code == 0 and installed["ok"] is True, installed)
        missing = work / "tsjs" / "missing.ts"
        missing.write_text("const missing = 1;\n", encoding="utf-8")
        missing.unlink()
        code, body = rpc(state, "diagnostics", {"language": "tsjs", "path": "tsjs/missing.ts"}, env)
        expect(code != 0 and body["ok"] is False and body["error"]["code"] == "file_not_found", body)
        code, health = rpc(state, "health", {}, env)
        expect(code == 0 and health["ok"] is True, health)
    finally:
        if daemon.poll() is None:
            stop_daemon(state)
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()


def _alive(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    text = stat.read_text(encoding="utf-8")
    state = text.rsplit(")", 1)[-1].split()[0]
    return state != "Z"


if __name__ == "__main__":
    sys.exit(main())
