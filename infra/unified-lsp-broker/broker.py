#!/usr/bin/env python3
"""Box-local Unified LSP broker (Tier-1 spike).

INFRA-owned path: infra/** last-matches over **/*.py, so this file resolves to
bot-05-infrastructure. It is not a SYSTEMS service.

Primary agent surface is the WEB MCP stdio adapter. This process is the local
broker: unix-socket RPC, language-server children, optional WebSocket bound to
loopback only. WebSocket is off unless --ws is set.

Lifecycle states: cold (not running), ready, serving, degraded, stopped.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import select
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "registry" / "tier1.json"
FIXTURE_LS = ROOT / "fixture_ls.py"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
KEEP_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "USER", "LOGNAME")
MAX_RPC_BYTES = 65_536
MAX_WS_FRAME = 65_536
MAX_FILE_BYTES = 1_048_576
MAX_DIAG_MESSAGE = 240
MAX_DIAGNOSTICS = 32
MAX_DIAG_JSON = 8_192
DENIED_PARTS = {".git", ".hg", ".svn"}
DENIED_NAMES = {"id_rsa", "id_dsa", "id_ed25519", ".env"}
DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".env"}
SECRET_ASSIGN_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|client[_-]?secret)\s*[=:]\s*)(\S+)"
)
ABS_PATH_RE = re.compile(r"/(?:tmp|home|workspace|Users|var|private|opt|usr)/\S+")


class BrokerError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class LsDied(Exception):
    pass


class Session:
    def __init__(self, language: str, proc: subprocess.Popen, restarts: int = 0) -> None:
        self.language = language
        self.proc = proc
        self.restarts = restarts
        self.opened: dict[str, int] = {}
        self.next_id = 1
        self.buf = bytearray()
        self.stderr_tail: list[bytes] = []
        self.pgid = 0


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def scrub_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ[key] for key in KEEP_ENV if key in os.environ}
    if extra:
        env.update(extra)
    return env


def redact_text(text: str) -> str:
    return SECRET_ASSIGN_RE.sub(lambda match: match.group(1) + "[REDACTED]", text)


def scrub_text(text: str) -> str:
    cleaned = ABS_PATH_RE.sub("[path]", redact_text(text))
    if cleaned.startswith("/") and cleaned != "/":
        return "[path]"
    return cleaned


def scrub_public(value):
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [scrub_public(item) for item in value]
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key in {"stderr", "bin", "fixture"}:
                continue
            cleaned[key] = scrub_public(item)
        return cleaned
    return value


def share_matches(presented: str, expected: str) -> bool:
    if not presented or not expected:
        return False
    left = presented.encode("utf-8")
    right = expected.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def assert_allowed_source(entry: dict, language: str, rel: str) -> None:
    if "\x00" in rel:
        raise BrokerError("invalid_arguments", "path contains a NUL byte")
    pure = Path(rel)
    for part in pure.parts:
        if part in DENIED_PARTS or part == ".env" or part.startswith(".env."):
            raise BrokerError(
                "extension_not_allowed",
                "path is outside the language extension allowlist",
                {"language": language},
            )
    suffix = pure.suffix.lower()
    if pure.name in DENIED_NAMES or pure.name.startswith(".env") or suffix in DENIED_SUFFIXES:
        raise BrokerError(
            "extension_not_allowed",
            "path is outside the language extension allowlist",
            {"language": language},
        )
    allowed = {item.lower() for item in entry.get("extensions") or []}
    if suffix not in allowed:
        raise BrokerError(
            "extension_not_allowed",
            "path is outside the language extension allowlist",
            {"language": language, "allowed": sorted(allowed)},
        )


def read_source(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise BrokerError(
            "file_too_large",
            f"file is {size} bytes, over the read cap of {MAX_FILE_BYTES} bytes",
            {"size_bytes": size, "limit_bytes": MAX_FILE_BYTES},
        )
    data = path.read_bytes()
    if b"\x00" in data:
        raise BrokerError("invalid_arguments", "file contains a NUL byte")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BrokerError("invalid_arguments", "file is not utf-8 text") from exc


def cap_diagnostics(diags: list) -> tuple[list, bool, int]:
    """Return capped diagnostics, whether anything was dropped or shortened, and the original count."""
    capped: list[dict] = []
    truncated = False
    total = 0
    for item in diags:
        if not isinstance(item, dict):
            continue
        total += 1
        if len(capped) >= MAX_DIAGNOSTICS:
            truncated = True
            continue
        message = scrub_text(str(item.get("message", "")))
        if len(message) > MAX_DIAG_MESSAGE:
            message = message[: MAX_DIAG_MESSAGE - 1] + "…"
            truncated = True
        entry = {
            "message": message,
            "severity": item.get("severity", 1),
            "source": scrub_text(str(item.get("source", "")))[:80],
            "range": item.get("range"),
        }
        if len(json.dumps(capped + [entry])) > MAX_DIAG_JSON:
            truncated = True
            break
        capped.append(entry)
    if total > len(capped):
        truncated = True
    return capped, truncated, total


def parse_lsp_timeout() -> float:
    raw = os.environ.get("ULSP_LSP_TIMEOUT_S", "")
    if not raw:
        return 5.0
    try:
        value = float(raw)
    except ValueError:
        return 5.0
    if value <= 0 or value > 30:
        return 5.0
    return value


def version_matches(params: dict, version: int) -> bool:
    if "version" not in params:
        return True
    return params.get("version") == version


def pid_alive(pid: int | None) -> bool:
    """True only for a live process. Zombies count as dead: the parent may not have reaped them."""
    if not pid:
        return False
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return False
    text = stat_path.read_text(encoding="utf-8")
    # comm is wrapped in parentheses and may contain spaces; state follows the last ')'.
    state = text.rsplit(")", 1)[-1].split()[0]
    return state != "Z"


def resolve_in_workspace(workspace: Path, rel: str) -> Path:
    if rel.startswith("/") or rel.startswith("~") or "\\" in rel and rel[1:3] == ":\\":
        raise BrokerError("workspace_escape", "absolute paths are not accepted")
    root = workspace.resolve()
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise BrokerError("workspace_escape", "path escapes workspace root")
    return candidate


def language_id_for(entry: dict, path: Path) -> str:
    if path.suffix in set(entry.get("javascript_extensions") or []):
        return "javascript"
    return entry["language_ids"][0]


def production_plan(language: str) -> dict:
    registry = load_registry()
    languages = registry["languages"]
    if language not in languages:
        raise BrokerError(
            "language_not_tier1",
            f"{language} is outside the Tier-1 registry",
            {"tier1": sorted(languages)},
        )
    return languages[language]["production_server"]


def pop_lsp_message(buf: bytearray) -> dict | None:
    sep = buf.find(b"\r\n\r\n")
    sep_len = 4
    if sep < 0:
        sep = buf.find(b"\n\n")
        sep_len = 2
    if sep < 0:
        return None
    header = bytes(buf[:sep]).decode("ascii", "replace")
    length = None
    for line in header.splitlines():
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    if length is None:
        raise BrokerError("language_server_failed", "language server header missing Content-Length")
    start = sep + sep_len
    if len(buf) < start + length:
        return None
    body = bytes(buf[start : start + length])
    del buf[: start + length]
    return json.loads(body.decode("utf-8"))


def write_lsp(sess: Session, payload: dict) -> None:
    if sess.proc.stdin is None:
        raise LsDied()
    data = json.dumps(payload).encode("utf-8")
    packet = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data
    try:
        sess.proc.stdin.write(packet)
        sess.proc.stdin.flush()
    except (BrokenPipeError, OSError) as exc:
        raise LsDied() from exc


def read_lsp(sess: Session, timeout: float) -> dict:
    if sess.proc.stdout is None:
        raise LsDied()
    deadline = time.monotonic() + timeout
    while True:
        extracted = pop_lsp_message(sess.buf)
        if extracted is not None:
            return extracted
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BrokerError("diagnostics_timeout", "timed out waiting for the language server")
        if sess.proc.poll() is not None and not sess.buf:
            raise LsDied()
        ready, _, _ = select.select([sess.proc.stdout], [], [], min(0.2, remaining))
        if not ready:
            if sess.proc.poll() is not None:
                raise LsDied()
            continue
        chunk = os.read(sess.proc.stdout.fileno(), 65536)
        if not chunk:
            raise LsDied()
        sess.buf.extend(chunk)


def drain_stderr(pipe, bucket: list[bytes]) -> None:
    try:
        while True:
            line = pipe.readline()
            if not line:
                return
            bucket.append(line)
            if len(bucket) > 40:
                del bucket[:-20]
    except OSError:
        return


def ok(request_id, result: dict) -> dict:
    return {"id": request_id, "ok": True, "result": scrub_public(result)}


def fail(request_id, exc: BrokerError) -> dict:
    return {
        "id": request_id,
        "ok": False,
        "error": scrub_public({"code": exc.code, "message": exc.message, "details": exc.details}),
    }


class Broker:
    def __init__(self, workspace: Path, state_dir: Path, ws_spec: str | None) -> None:
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise BrokerError("workspace_unbound", f"workspace is not a directory: {self.workspace}")
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.registry = load_registry()
        self.sessions: dict[str, Session] = {}
        self.failed: set[str] = set()
        self.crash_langs: set[str] = set()
        self.installed: dict[str, dict] = {}
        self.state = "ready"
        self.running = True
        self.ws_addr: dict | None = None
        self.ws_share: str | None = None
        self.ws_sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.lang_locks: dict[str, threading.Lock] = {}
        self.lsp_timeout = parse_lsp_timeout()
        self._load_installed()
        self._claim_socket()
        if ws_spec:
            host, port = parse_ws(ws_spec)
            self._bind_ws(host, port)

    def _claim_socket(self) -> None:
        """Bind the unix socket. A live owner keeps its socket; a dead owner is replaced."""
        sock_path = self.state_dir / "broker.sock"
        recorded = read_state(self.state_dir)
        if recorded and recorded.get("state") != "stopped" and pid_alive(recorded.get("pid")):
            raise BrokerError(
                "broker_already_running",
                "another live broker owns this state directory",
                {"pid": recorded.get("pid")},
            )
        if sock_path.exists():
            sock_path.unlink()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(sock_path))
        os.chmod(sock_path, 0o600)

    def _lang_lock(self, language: str) -> threading.Lock:
        with self.lock:
            lock = self.lang_locks.get(language)
            if lock is None:
                lock = threading.Lock()
                self.lang_locks[language] = lock
            return lock

    def _load_installed(self) -> None:
        path = self.state_dir / "installed.json"
        if path.exists():
            self.installed = json.loads(path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        (self.state_dir / "installed.json").write_text(
            json.dumps(self.installed, indent=2) + "\n", encoding="utf-8"
        )
        payload = {
            "state": self.state,
            "workspace_bound": True,
            "pid": os.getpid(),
            "ws": self.ws_addr,
            "installed": sorted(self.installed),
            "sessions": self.session_view(),
        }
        (self.state_dir / "state.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        (self.state_dir / "broker.pid").write_text(str(os.getpid()), encoding="utf-8")

    def session_view(self) -> dict:
        view: dict[str, dict] = {}
        for language, sess in self.sessions.items():
            alive = sess.proc.poll() is None
            view[language] = {
                "status": "running" if alive else "exited",
                "pid": sess.proc.pid,
                "restarts": sess.restarts,
            }
        for language in self.failed:
            view[language] = {"status": "failed", "pid": None, "restarts": 1}
        return view

    def _recompute_state(self) -> None:
        if not self.running and self.state == "stopped":
            return
        if self.failed:
            self.state = "degraded"
            return
        if any(sess.proc.poll() is None for sess in self.sessions.values()):
            self.state = "serving"
            return
        self.state = "ready"

    def _require_tier1(self, language: str) -> dict:
        languages = self.registry["languages"]
        if language not in languages:
            raise BrokerError(
                "language_not_tier1",
                f"{language} is outside the Tier-1 registry and will not be installed",
                {"tier1": sorted(languages)},
            )
        return languages[language]

    def health(self) -> dict:
        return {
            "state": self.state,
            "workspace_bound": True,
            "ws": self.ws_addr,
            "installed": sorted(self.installed),
            "sessions": self.session_view(),
            "primary_surface": "mcp-stdio",
            "ws_role": "optional-localhost",
        }

    def install(self, language: str) -> dict:
        entry = self._require_tier1(language)
        mode = os.environ.get("ULSP_SERVER_MODE", "spike")
        if mode != "spike":
            raise BrokerError(
                "install_not_executed",
                "production install is recorded in the registry and is not executed by this spike",
                {"production_server": entry["production_server"]},
            )
        bin_dir = self.state_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper = bin_dir / f"ulsp-ls-{language}"
        script = (
            "#!/bin/sh\nexec "
            + shlex.quote(sys.executable)
            + " "
            + shlex.quote(str(FIXTURE_LS))
            + " --language "
            + shlex.quote(language)
            + ' "$@"\n'
        )
        wrapper.write_text(script, encoding="utf-8")
        wrapper.chmod(0o755)
        idempotent = language in self.installed
        self.installed[language] = {"mode": "spike", "wrapper": wrapper.name}
        self._persist()
        return {
            "language": language,
            "installed": True,
            "idempotent": idempotent,
            "mode": "spike",
        }

    def plan(self, language: str) -> dict:
        entry = self._require_tier1(language)
        return {"language": language, "production_server": entry["production_server"], "executed": False}

    def probe(self, language: str, rel: str) -> dict:
        entry = self._require_tier1(language)
        if "\x00" in rel:
            raise BrokerError("invalid_arguments", "path contains a NUL byte")
        resolve_in_workspace(self.workspace, rel)
        assert_allowed_source(entry, language, rel)
        if language not in self.installed:
            raise BrokerError(
                "language_server_missing",
                f"{language} is not installed; call install before hover or definition stubs",
                {"language": language},
            )
        return {
            "language": language,
            "installed": True,
            "path": rel,
            "stub": True,
        }

    def arm_crash(self, language: str) -> dict:
        if os.environ.get("ULSP_SPIKE_HOOKS") != "1":
            raise BrokerError("spike_hooks_disabled", "arm_crash requires ULSP_SPIKE_HOOKS=1")
        self._require_tier1(language)
        self.crash_langs.add(language)
        sess = self.sessions.pop(language, None)
        if sess is not None:
            self._kill(sess)
        self.failed.discard(language)
        self._recompute_state()
        self._persist()
        return {"armed": language}

    def diagnostics(self, language: str, rel: str) -> dict:
        entry = self._require_tier1(language)
        if "\x00" in rel:
            raise BrokerError("invalid_arguments", "path contains a NUL byte")
        path = resolve_in_workspace(self.workspace, rel)
        assert_allowed_source(entry, language, rel)
        if language not in self.installed:
            raise BrokerError(
                "language_server_missing",
                f"{language} is not installed",
                {"language": language, "hint": "install"},
            )
        if not path.is_file():
            raise BrokerError("file_not_found", f"file not in workspace: {rel}")
        text = read_source(path)
        uri = path.as_uri()
        lang_id = language_id_for(entry, path)
        # The language lock covers this server's stdio. The broker lock is not held while waiting.
        with self._lang_lock(language):
            attempts = 0
            while True:
                attempts += 1
                with self.lock:
                    sess = self.sessions.get(language)
                    if sess is not None and sess.proc.poll() is None:
                        spawned = False
                    else:
                        if sess is not None:
                            self._kill(sess)
                            self.sessions.pop(language, None)
                        sess = self._spawn(language)
                        spawned = True
                if spawned:
                    try:
                        self._initialize(sess)
                    except LsDied as exc:
                        with self.lock:
                            self._kill(sess)
                            self._mark_failed(language)
                        raise BrokerError(
                            "language_server_failed",
                            f"{language} language server exited during startup",
                        ) from exc
                    except BrokerError:
                        with self.lock:
                            self._kill(sess)
                            self._mark_failed(language)
                        raise
                try:
                    diags = self._collect(sess, uri, lang_id, text)
                except BrokerError as exc:
                    if exc.code == "diagnostics_timeout":
                        with self.lock:
                            self._kill(sess)
                            self._mark_failed(language)
                    raise
                except LsDied:
                    with self.lock:
                        self._kill(sess)
                        self.sessions.pop(language, None)
                    if attempts >= 2:
                        with self.lock:
                            self._mark_failed(language)
                        raise BrokerError(
                            "language_server_failed",
                            f"{language} language server crashed; other languages stay up",
                        )
                    continue
                items, truncated, total = cap_diagnostics(diags)
                with self.lock:
                    self.failed.discard(language)
                    self._recompute_state()
                    self._persist()
                return {
                    "language": language,
                    "language_id": lang_id,
                    "path": rel,
                    "diagnostics": items,
                    "truncated": truncated,
                    "diagnostics_total": total,
                }

    def _mark_failed(self, language: str) -> None:
        self.sessions.pop(language, None)
        self.failed.add(language)
        self._recompute_state()
        self._persist()

    def _spawn(self, language: str) -> Session:
        wrapper = self.state_dir / "bin" / f"ulsp-ls-{language}"
        if not wrapper.exists():
            raise BrokerError("language_server_missing", f"{language} wrapper is missing")
        extra = {}
        if language in self.crash_langs:
            extra["ULSP_FIXTURE_CRASH"] = "1"
        proc = subprocess.Popen(
            [str(wrapper)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=scrub_env(extra),
            cwd=str(self.workspace),
            start_new_session=True,
            bufsize=0,
        )
        sess = Session(language, proc)
        try:
            sess.pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError, OSError):
            sess.pgid = proc.pid
        if proc.stderr is not None:
            threading.Thread(
                target=drain_stderr, args=(proc.stderr, sess.stderr_tail), daemon=True
            ).start()
        self.sessions[language] = sess
        return sess

    def _initialize(self, sess: Session) -> None:
        request_id = sess.next_id
        sess.next_id += 1
        root = self.workspace.as_uri()
        write_lsp(
            sess,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "rootUri": root,
                    "capabilities": {
                        "textDocument": {
                            "synchronization": {"didOpen": True, "didChange": True},
                            "publishDiagnostics": {},
                        }
                    },
                    "workspaceFolders": [{"uri": root, "name": self.workspace.name}],
                },
            },
        )
        self._wait(sess, lambda msg: msg.get("id") == request_id, self.lsp_timeout)
        write_lsp(sess, {"jsonrpc": "2.0", "method": "initialized", "params": {}})

    def _collect(self, sess: Session, uri: str, language_id: str, text: str) -> list:
        version = sess.opened.get(uri, 0) + 1
        sess.opened[uri] = version
        if version == 1:
            write_lsp(
                sess,
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": uri,
                            "languageId": language_id,
                            "version": version,
                            "text": text,
                        }
                    },
                },
            )
        else:
            write_lsp(
                sess,
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didChange",
                    "params": {
                        "textDocument": {"uri": uri, "version": version},
                        "contentChanges": [{"text": text}],
                    },
                },
            )
        message = self._wait(
            sess,
            lambda msg, expected=version: msg.get("method") == "textDocument/publishDiagnostics"
            and (msg.get("params") or {}).get("uri") == uri
            and version_matches(msg.get("params") or {}, expected),
            self.lsp_timeout,
        )
        return (message.get("params") or {}).get("diagnostics") or []

    def _wait(self, sess: Session, predicate, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrokerError("diagnostics_timeout", "timed out waiting for the language server")
            message = read_lsp(sess, remaining)
            if "id" in message and "method" in message:
                self._reply_server(sess, message)
                continue
            if predicate(message):
                return message

    def _reply_server(self, sess: Session, message: dict) -> None:
        method = message.get("method")
        if method == "workspace/configuration":
            result: object = []
        else:
            result = None
        write_lsp(sess, {"jsonrpc": "2.0", "id": message["id"], "result": result})

    def _kill(self, sess: Session) -> None:
        proc = sess.proc
        pgid = sess.pgid or 0
        # Kill the child's session, including grandchildren, even if the leader already exited.
        # Never signal the broker's own process group (killpg(0) would do that).
        if pgid and pgid != os.getpgrp():
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        elif proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return

    def _delayed_shutdown(self) -> None:
        time.sleep(0.05)
        try:
            self.finish_shutdown()
        except Exception:
            os._exit(1)

    def finish_shutdown(self) -> None:
        for sess in list(self.sessions.values()):
            self._kill(sess)
        self.sessions.clear()
        self.state = "stopped"
        self.running = False
        self._persist()
        sock_path = self.state_dir / "broker.sock"
        try:
            self.sock.close()
        except OSError:
            pass
        if sock_path.exists():
            try:
                sock_path.unlink()
            except OSError:
                pass
        if self.ws_sock is not None:
            try:
                self.ws_sock.close()
            except OSError:
                pass
        os._exit(0)

    def handle(self, request: dict) -> dict:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            return fail(request_id, BrokerError("invalid_arguments", "params must be an object"))
        try:
            if method == "diagnostics":
                result = self.diagnostics(str(params.get("language") or ""), str(params.get("path") or ""))
            else:
                with self.lock:
                    if method == "health":
                        result = self.health()
                    elif method == "install":
                        result = self.install(str(params.get("language") or ""))
                    elif method == "plan":
                        result = self.plan(str(params.get("language") or ""))
                    elif method == "probe":
                        result = self.probe(str(params.get("language") or ""), str(params.get("path") or ""))
                    elif method == "arm_crash":
                        result = self.arm_crash(str(params.get("language") or ""))
                    elif method == "shutdown":
                        result = {"state": "stopped"}
                    else:
                        raise BrokerError("unknown_method", f"unknown method {method}")
        except BrokerError as exc:
            return fail(request_id, exc)
        return ok(request_id, result)

    def serve(self) -> None:
        self.sock.listen(16)
        self._persist()
        info = {
            "event": "listening",
            "state": self.state,
            "ws": self.ws_addr,
        }
        if self.ws_share:
            info["share"] = self.ws_share
        sys.stdout.write(json.dumps(info) + "\n")
        sys.stdout.flush()
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _reject_line(self, conn: socket.socket, message: str) -> None:
        response = fail(None, BrokerError("invalid_arguments", message))
        try:
            conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except OSError:
            return

    def _client(self, conn: socket.socket) -> None:
        try:
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(65536)
                if not chunk:
                    if data:
                        self._reject_line(conn, "request is not a single JSON line")
                    return
                data += chunk
                if b"\x00" in data:
                    self._reject_line(conn, "request contains a NUL byte")
                    return
                if len(data) > MAX_RPC_BYTES:
                    self._reject_line(conn, "request exceeds the frame cap")
                    return
            line = data.split(b"\n", 1)[0]
            if b"\x00" in line:
                self._reject_line(conn, "request contains a NUL byte")
                return
            try:
                request = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._reject_line(conn, "request is not JSON")
                return
            if not isinstance(request, dict):
                self._reject_line(conn, "request must be a JSON object")
                return
            response = self.handle(request)
            conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
            if request.get("method") == "shutdown" and response.get("ok"):
                threading.Thread(target=self._delayed_shutdown, daemon=True).start()
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _bind_ws(self, host: str, port: int) -> None:
        bind_host = "127.0.0.1" if host == "localhost" else host
        family = socket.AF_INET6 if bind_host == "::1" else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, port))
        sock.listen(8)
        bound = sock.getsockname()
        bound_host = bound[0]
        if bound_host not in {"127.0.0.1", "::1"}:
            sock.close()
            raise BrokerError("ws_host_forbidden", f"refusing non-loopback bind {bound_host}")
        self.ws_sock = sock
        self.ws_addr = {"host": bound_host, "port": bound[1]}
        self.ws_share = secrets.token_urlsafe(24)
        threading.Thread(target=self._ws_loop, daemon=True).start()

    def _ws_loop(self) -> None:
        assert self.ws_sock is not None
        while self.running:
            try:
                conn, _ = self.ws_sock.accept()
            except OSError:
                return
            threading.Thread(target=self._ws_client, args=(conn,), daemon=True).start()

    def _ws_client(self, conn: socket.socket) -> None:
        try:
            host = (self.ws_addr or {}).get("host", "127.0.0.1")
            port = int((self.ws_addr or {}).get("port") or 0)
            if not ws_handshake(conn, expected_origin(str(host), port), self.ws_share or ""):
                return
            opcode, payload = read_ws_frame(conn)
            if opcode != 0x1:
                return
            request = json.loads(payload.decode("utf-8"))
            response = self.handle(request)
            write_ws_frame(conn, json.dumps(response).encode("utf-8"))
            if request.get("method") == "shutdown" and response.get("ok"):
                threading.Thread(target=self._delayed_shutdown, daemon=True).start()
        except (OSError, json.JSONDecodeError, ValueError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass


def parse_ws(spec: str) -> tuple[str, int]:
    if ":" not in spec:
        raise BrokerError("ws_host_forbidden", "ws endpoint must be host:port")
    host, port_s = spec.rsplit(":", 1)
    if host not in LOOPBACK_HOSTS:
        raise BrokerError(
            "ws_host_forbidden",
            f"WebSocket share plane refuses host {host}; loopback only",
            {"allowed": sorted(LOOPBACK_HOSTS)},
        )
    try:
        port = int(port_s)
    except ValueError as exc:
        raise BrokerError("invalid_arguments", "ws port is not an integer") from exc
    if port < 0 or port > 65535:
        raise BrokerError("invalid_arguments", "ws port out of range")
    return host, port


def expected_origin(host: str, port: int) -> str:
    if ":" in host:
        return f"http://[{host}]:{port}"
    return f"http://{host}:{port}"


def ws_reject(conn: socket.socket, status: int, reason: str) -> bool:
    body = reason.encode("ascii")
    packet = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body
    try:
        conn.sendall(packet)
    except OSError:
        return False
    return False


def ws_handshake(conn: socket.socket, origin_required: str, share: str) -> bool:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk
        if len(data) > 16384:
            return False
    headers: dict[str, str] = {}
    key = None
    for line in data.decode("iso-8859-1").split("\r\n")[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        lowered = name.strip().lower()
        headers[lowered] = value.strip()
        if lowered == "sec-websocket-key":
            key = value.strip()
    if headers.get("origin", "") != origin_required:
        return ws_reject(conn, 403, "Forbidden")
    if not share_matches(headers.get("x-ulsp-ws-token", ""), share):
        return ws_reject(conn, 401, "Unauthorized")
    if not key:
        return ws_reject(conn, 400, "Bad Request")
    accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    conn.sendall(response.encode("ascii"))
    return True


def recvn(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ValueError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def read_ws_frame(conn: socket.socket) -> tuple[int, bytes]:
    header = recvn(conn, 2)
    opcode = header[0] & 0x0F
    masked = header[1] & 0x80
    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(recvn(conn, 2), "big")
    elif length == 127:
        length = int.from_bytes(recvn(conn, 8), "big")
    if length > MAX_WS_FRAME:
        raise ValueError("websocket frame exceeds cap")
    mask = recvn(conn, 4) if masked else b""
    payload = recvn(conn, length)
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def write_ws_frame(conn: socket.socket, payload: bytes) -> None:
    length = len(payload)
    header = bytearray([0x81])
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    conn.sendall(bytes(header) + payload)


def read_state(state_dir: Path) -> dict | None:
    path = state_dir / "state.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def offline_health(state_dir: Path) -> dict:
    recorded = read_state(state_dir)
    if recorded is None:
        return {
            "state": "cold",
            "workspace": None,
            "ws": None,
            "installed": [],
            "sessions": {},
            "primary_surface": "mcp-stdio",
            "ws_role": "optional-localhost",
        }
    if recorded.get("state") == "stopped" or not pid_alive(recorded.get("pid")):
        if recorded.get("state") == "stopped":
            return recorded
        recorded["state"] = "cold"
        recorded["note"] = "pid_not_running"
        return recorded
    return recorded


def rpc_call(state_dir: Path, request: dict, timeout: float = 20) -> dict:
    sock_path = state_dir / "broker.sock"
    recorded = read_state(state_dir)
    pid = (recorded or {}).get("pid")
    if not sock_path.exists() or not pid_alive(pid):
        raise BrokerError("broker_not_running", "broker is not running", {"state": "cold" if not recorded else recorded.get("state")})
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(str(sock_path))
        conn.sendall(json.dumps(request).encode("utf-8") + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
    except (ConnectionRefusedError, FileNotFoundError, socket.timeout, OSError) as exc:
        raise BrokerError("broker_not_running", "broker socket did not answer") from exc
    finally:
        conn.close()
    if not data:
        raise BrokerError("broker_not_running", "broker closed the socket")
    return json.loads(data.split(b"\n", 1)[0].decode("utf-8"))


def emit(response: dict) -> int:
    sys.stdout.write(json.dumps(response) + "\n")
    return 0 if response.get("ok") else 2


def cmd_start(args: argparse.Namespace) -> int:
    if not args.workspace:
        response = fail(None, BrokerError("workspace_unbound", "start requires --workspace"))
        return emit(response)
    state_dir = Path(args.state_dir)
    try:
        broker = Broker(Path(args.workspace), state_dir, args.ws)
    except BrokerError as exc:
        return emit(fail(None, exc))
    broker.serve()
    return 0


def forward(args: argparse.Namespace, method: str, params: dict) -> int:
    request = {"id": method, "method": method, "params": params}
    try:
        response = rpc_call(Path(args.state_dir), request)
    except BrokerError as exc:
        return emit(fail(method, exc))
    return emit(response)


def cmd_rpc(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        return emit(fail(None, BrokerError("invalid_arguments", "rpc stdin is not JSON")))
    try:
        response = rpc_call(Path(args.state_dir), request)
    except BrokerError as exc:
        return emit(fail(request.get("id"), exc))
    return emit(response)


def cmd_stop(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    recorded = read_state(state_dir) or {}
    pid = recorded.get("pid")
    code = forward(args, "shutdown", {})
    for _ in range(50):
        if not pid_alive(pid):
            return code
        time.sleep(0.1)
    sys.stderr.write("broker did not exit after shutdown\n")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified LSP broker (Tier-1 spike)")
    parser.add_argument("--state-dir", required=True)
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--workspace")
    start.add_argument("--ws", help="optional loopback host:port, for example 127.0.0.1:0")
    start.set_defaults(func=cmd_start)

    health = sub.add_parser("health")
    health.set_defaults(func=lambda args: health_cmd(args))

    sub.add_parser("rpc").set_defaults(func=cmd_rpc)
    sub.add_parser("stop").set_defaults(func=cmd_stop)

    install = sub.add_parser("install")
    install.add_argument("--language", required=True)
    install.set_defaults(func=lambda args: forward(args, "install", {"language": args.language}))

    diagnostics = sub.add_parser("diagnostics")
    diagnostics.add_argument("--language", required=True)
    diagnostics.add_argument("--path", required=True)
    diagnostics.set_defaults(
        func=lambda args: forward(args, "diagnostics", {"language": args.language, "path": args.path})
    )

    probe = sub.add_parser("probe")
    probe.add_argument("--language", required=True)
    probe.add_argument("--path", required=True)
    probe.set_defaults(func=lambda args: forward(args, "probe", {"language": args.language, "path": args.path}))

    plan = sub.add_parser("plan")
    plan.add_argument("--language", required=True)
    plan.set_defaults(func=cmd_plan)

    arm = sub.add_parser("arm-crash")
    arm.add_argument("--language", required=True)
    arm.set_defaults(func=lambda args: forward(args, "arm_crash", {"language": args.language}))
    return parser


def health_cmd(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir)
    recorded = read_state(state_dir)
    if recorded and pid_alive(recorded.get("pid")) and (state_dir / "broker.sock").exists():
        return forward(args, "health", {})
    return emit(ok("health", offline_health(state_dir)))


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        result = {"language": args.language, "production_server": production_plan(args.language), "executed": False}
    except BrokerError as exc:
        return emit(fail("plan", exc))
    return emit(ok("plan", result))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
