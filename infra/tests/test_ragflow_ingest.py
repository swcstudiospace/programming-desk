"""Fake-server tests for incremental RAGFlow ingest."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
INGEST_PATH = REPO_ROOT / "infra" / "ragflow" / "ingest.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ragflow-ingest.yml"
CALLERS = REPO_ROOT / "infra" / "ragflow" / "callers"


def load_ingest():
    spec = importlib.util.spec_from_file_location("ragflow_ingest", INGEST_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ragflow_ingest"] = module
    spec.loader.exec_module(module)
    return module


ingest = load_ingest()


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: list[tuple[str, str, dict]] = []
        self.datasets: dict[str, str] = {}
        self.docs: dict[str, list[dict]] = {}
        self.next_id = 1


def _server(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def _body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _json(self) -> dict:
            raw = self._body()
            return json.loads(raw.decode() or "{}")

        def _send(self, payload: dict, status: int = 200) -> None:
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _record(self, method: str, path: str, detail: dict) -> None:
            with state.lock:
                state.events.append((method, path, detail))

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            parts = [part for part in parsed.path.split("/") if part]
            if parts == ["api", "v1", "datasets"]:
                name = (query.get("name") or [""])[0]
                rows = [
                    {"id": dataset_id, "name": dataset_name}
                    for dataset_name, dataset_id in state.datasets.items()
                    if not name or dataset_name == name
                ]
                self._record("GET", parsed.path, {"name": name})
                self._send({"code": 0, "data": rows})
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "datasets"] and parts[4] == "documents":
                dataset_id = parts[3]
                keywords = (query.get("keywords") or [""])[0]
                docs = [
                    doc for doc in state.docs.get(dataset_id, [])
                    if not keywords or keywords in str(doc.get("name"))
                ]
                self._record("GET", parsed.path, {"keywords": keywords})
                self._send({"code": 0, "data": {"docs": docs, "total": len(docs)}})
                return
            self._send({"code": 404, "message": "missing"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            raw = self._body()
            if parts == ["api", "v1", "datasets"]:
                name = json.loads(raw.decode())["name"]
                dataset_id = f"ds-{name}"
                state.datasets[name] = dataset_id
                state.docs.setdefault(dataset_id, [])
                self._record("POST", parsed.path, {"name": name})
                self._send({"code": 0, "data": {"id": dataset_id, "name": name}})
                return
            if len(parts) == 5 and parts[4] == "documents":
                dataset_id = parts[3]
                state.next_id += 1
                document_id = f"doc-{state.next_id}"
                state.docs.setdefault(dataset_id, []).append(
                    {"id": document_id, "name": "", "meta_fields": {}, "_bytes": len(raw)}
                )
                self._record("POST", parsed.path, {"id": document_id, "nbytes": len(raw)})
                self._send({"code": 0, "data": [{"id": document_id}]})
                return
            if len(parts) == 5 and parts[4] == "chunks":
                body = json.loads(raw.decode())
                self._record("POST", parsed.path, {"document_ids": body.get("document_ids")})
                self._send({"code": 0, "data": {}})
                return
            self._send({"code": 404, "message": "missing"}, status=404)

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            body = self._json()
            dataset_id, document_id = parts[3], parts[5]
            for doc in state.docs.get(dataset_id, []):
                if doc["id"] == document_id:
                    doc["name"] = body.get("name")
                    doc["meta_fields"] = body.get("meta_fields") or {}
            self._record("PUT", parsed.path, {"id": document_id, "meta": body.get("meta_fields")})
            self._send({"code": 0, "data": True})

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            body = self._json()
            dataset_id = parts[3]
            ids = set(body.get("ids") or [])
            state.docs[dataset_id] = [
                doc for doc in state.docs.get(dataset_id, []) if doc["id"] not in ids
            ]
            self._record("DELETE", parsed.path, {"ids": sorted(ids)})
            self._send({"code": 0, "data": True})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "ingest@example.com")
    _git(path, "config", "user.name", "ingest")
    return path


def _commit(path: Path, relative: str, content: bytes, message: str) -> str:
    target = path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _git(path, "add", "--", relative)
    _git(path, "commit", "-m", message)
    return _git(path, "rev-parse", "HEAD")


def _run(monkeypatch, root: Path, *args: str, url: str = "", key: str = "", event: str = ""):
    if url:
        monkeypatch.setenv("RAGFLOW_URL", url)
    else:
        monkeypatch.delenv("RAGFLOW_URL", raising=False)
    if key:
        monkeypatch.setenv("RAGFLOW_API_KEY", key)
    else:
        monkeypatch.delenv("RAGFLOW_API_KEY", raising=False)
    if event:
        monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    else:
        monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    code = ingest.run(
        ["--repo", "programming-desk", "--root", str(root), *args],
    )
    return code


def test_name_status_keeps_add_modify_rename_and_delete():
    text = "A\tdocs/a.md\nM\tdocs/b.md\nD\told.md\nR100\tdocs/from.md\tdocs/to.md\nC090\tdocs/src.md\tdocs/copy.md\n"
    assert ingest.parse_name_status(text) == [
        ("A", "docs/a.md"),
        ("M", "docs/b.md"),
        ("D", "old.md"),
        ("D", "docs/from.md"),
        ("A", "docs/to.md"),
        ("A", "docs/copy.md"),
    ]
    blob = b"A\0docs/a.md\0R090\0docs/from.md\0docs/to.md\0D\0old.md\0"
    assert ingest.parse_name_status_z(blob) == [
        ("A", "docs/a.md"),
        ("D", "docs/from.md"),
        ("A", "docs/to.md"),
        ("D", "old.md"),
    ]


def test_document_names_and_dataset_mapping():
    assert ingest.document_name("programming-desk", "skills/ragflow-docs/SKILL.md") == (
        "programming-desk__skills__ragflow-docs__SKILL.md"
    )
    assert ingest.document_name("programming-desk", "infra/ragflow/ingest.py") == (
        "programming-desk__infra__ragflow__ingest.py.txt"
    )
    assert ingest.datasets_for("programming-desk", "skills/ragflow-docs/SKILL.md") == [
        "programming-desk", "agent-skills",
    ]
    assert ingest.datasets_for("programming-desk", ".cursor/agents/a01.md") == [
        "programming-desk", "agent-skills",
    ]
    assert ingest.datasets_for("programming-desk", "README.md") == ["programming-desk"]
    assert ingest.datasets_for("auctioning", "README.md") == ["auctioning", "product-docs"]
    assert ingest.datasets_for("clippyos", "docs/guide.md") == ["clippyos", "product-docs"]
    assert ingest.datasets_for("agent-swarm", "docs/guide.md") == ["agent-swarm"]
    meta_keys = ("repo", "path", "commit", "url", "content_sha256")
    sample = ingest.blob_url(
        "https://github.com/swcstudiospace", "programming-desk", "abc", "docs/guide.md",
    )
    assert sample == "https://github.com/swcstudiospace/programming-desk/blob/abc/docs/guide.md"
    assert set(meta_keys) == {"repo", "path", "commit", "url", "content_sha256"}


def test_secret_name_size_and_credential_skips_do_not_print_contents(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    pem = b"-----BEGIN " + b"PRIVATE KEY-----\n" + b"MII" + (b"x" * 40) + b"\n"
    _commit(repo, "notes/leak.md", b"# notes\n" + pem, "leak")
    _commit(repo, ".env", b"TOKEN=value\n", "env")
    _commit(repo, "docs/huge.md", b"a" * (ingest.MAX_BYTES + 1), "huge")
    _commit(repo, "docs/ok.md", b"# ok\n", "ok")
    code = _run(monkeypatch, repo, "--before", "0" * 40, "--after", _git(repo, "rev-parse", "HEAD"), "--dry-run")
    captured = capsys.readouterr()
    assert code == 0
    assert "plan skip-credential path=notes/leak.md" in captured.out
    assert "plan skip-secret path=.env" in captured.out
    assert f"plan skip-size path=docs/huge.md bytes={ingest.MAX_BYTES + 1}" in captured.out
    assert "plan upsert dataset=programming-desk document=programming-desk__docs__ok.md path=docs/ok.md" in captured.out
    assert b"PRIVATE KEY" not in captured.out.encode()
    assert "TOKEN=value" not in captured.out
    assert pem.decode() not in captured.out


def test_missing_secrets_exit_zero_without_calling(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    _commit(repo, "docs/ok.md", b"# ok\n", "ok")
    state = _State()
    httpd = _server(state)
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", "HEAD",
        )
    finally:
        httpd.shutdown()
    captured = capsys.readouterr()
    assert code == 0
    assert "RAGFLOW_URL or RAGFLOW_API_KEY is empty; skipping ingest" in captured.out
    assert state.events == []


def test_pull_request_never_ingests(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    _commit(repo, "docs/ok.md", b"# ok\n", "ok")
    state = _State()
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", "HEAD",
            url=f"http://127.0.0.1:{port}", key="test-key", event="pull_request",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    assert "pull_request events do not ingest" in capsys.readouterr().out
    assert state.events == []


def test_dry_run_prints_plan_and_does_not_call(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    _commit(repo, "docs/ok.md", b"# ok\n", "ok")
    state = _State()
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", "HEAD", "--dry-run",
            url=f"http://127.0.0.1:{port}", key="test-key",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    assert "plan upsert" in capsys.readouterr().out
    assert state.events == []


def test_upsert_replaces_only_after_upload_then_parses(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    body = b"# changed\n"
    head = _commit(repo, "docs/ok.md", body, "ok")
    name = ingest.document_name("programming-desk", "docs/ok.md")
    state = _State()
    state.datasets["programming-desk"] = "ds-programming-desk"
    state.docs["ds-programming-desk"] = [{
        "id": "old-1",
        "name": name,
        "meta_fields": {
            "repo": "programming-desk",
            "path": "docs/ok.md",
            "content_sha256": "stale",
        },
    }]
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", head,
            url=f"http://127.0.0.1:{port}", key="test-key",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    methods = [(event[0], event[1], event[2]) for event in state.events]
    upload_at = next(index for index, event in enumerate(methods) if event[0] == "POST" and event[1].endswith("/documents"))
    delete_at = next(index for index, event in enumerate(methods) if event[0] == "DELETE")
    put_at = next(index for index, event in enumerate(methods) if event[0] == "PUT")
    parse_at = next(index for index, event in enumerate(methods) if event[1].endswith("/chunks"))
    assert upload_at < delete_at
    assert put_at < delete_at
    assert methods[delete_at][2]["ids"] == ["old-1"]
    assert parse_at > upload_at
    new_docs = state.docs["ds-programming-desk"]
    assert len(new_docs) == 1
    meta = new_docs[0]["meta_fields"]
    assert meta["content_sha256"] == hashlib.sha256(body).hexdigest()
    assert meta["path"] == "docs/ok.md"
    assert meta["repo"] == "programming-desk"
    assert meta["commit"] == head
    assert meta["url"].endswith(f"/programming-desk/blob/{head}/docs/ok.md")
    assert "old-1" not in methods[parse_at][2]["document_ids"]
    assert new_docs[0]["id"] in methods[parse_at][2]["document_ids"]


def test_matching_sha_skips_upload(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    body = b"# same\n"
    head = _commit(repo, "docs/ok.md", body, "ok")
    name = ingest.document_name("programming-desk", "docs/ok.md")
    state = _State()
    state.datasets["programming-desk"] = "ds-programming-desk"
    state.docs["ds-programming-desk"] = [{
        "id": "keep",
        "name": name,
        "meta_fields": {"content_sha256": hashlib.sha256(body).hexdigest(), "path": "docs/ok.md", "repo": "programming-desk"},
    }]
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", head,
            url=f"http://127.0.0.1:{port}", key="test-key",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    assert not any(event[0] in {"POST", "PUT", "DELETE"} for event in state.events)
    assert state.docs["ds-programming-desk"][0]["id"] == "keep"


def test_deleted_path_removes_the_document(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    first = _commit(repo, "docs/gone.md", b"# gone\n", "add")
    target = repo / "docs" / "gone.md"
    target.unlink()
    _git(repo, "add", "--", "docs/gone.md")
    _git(repo, "commit", "-m", "remove")
    head = _git(repo, "rev-parse", "HEAD")
    name = ingest.document_name("programming-desk", "docs/gone.md")
    state = _State()
    state.datasets["programming-desk"] = "ds-programming-desk"
    state.docs["ds-programming-desk"] = [{
        "id": "gone-1",
        "name": name,
        "meta_fields": {"path": "docs/gone.md", "repo": "programming-desk"},
    }]
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", first, "--after", head,
            url=f"http://127.0.0.1:{port}", key="test-key",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    deletes = [event for event in state.events if event[0] == "DELETE"]
    assert deletes and deletes[0][2]["ids"] == ["gone-1"]
    assert state.docs["ds-programming-desk"] == []


def test_skill_file_maps_to_agent_skills_dataset(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo")
    head = _commit(repo, "skills/demo/SKILL.md", b"# skill\n", "skill")
    state = _State()
    httpd = _server(state)
    port = httpd.server_address[1]
    try:
        code = _run(
            monkeypatch, repo, "--before", "0" * 40, "--after", head,
            url=f"http://127.0.0.1:{port}", key="test-key",
        )
    finally:
        httpd.shutdown()
    assert code == 0
    assert "programming-desk" in state.datasets
    assert "agent-skills" in state.datasets
    assert state.docs["ds-programming-desk"]
    assert state.docs["ds-agent-skills"]


def test_all_zero_before_lists_the_tree(tmp_path, capsys, monkeypatch):
    repo = _repo(tmp_path / "repo")
    _commit(repo, "docs/one.md", b"# one\n", "one")
    _commit(repo, "docs/two.md", b"# two\n", "two")
    code = _run(monkeypatch, repo, "--before", "0" * 40, "--after", "HEAD", "--dry-run")
    captured = capsys.readouterr()
    assert code == 0
    assert "path=docs/one.md" in captured.out
    assert "path=docs/two.md" in captured.out


def _triggers(document: dict) -> dict:
    # PyYAML 1.1 reads the bare key `on` as boolean true.
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict)
    return triggers


def test_workflow_and_callers_parse_and_stay_off_pull_requests():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = _triggers(workflow)
    assert "pull_request" not in triggers
    assert triggers["push"]["branches"] == ["main"]
    assert "workflow_call" in triggers
    secrets = triggers["workflow_call"]["secrets"]
    assert set(secrets) == {"RAGFLOW_URL", "RAGFLOW_API_KEY"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["ingest"]
    assert job["if"] == "github.event_name != 'pull_request'"
    assert job["runs-on"] == "ubuntu-latest"
    rendered = WORKFLOW.read_text()
    assert "echo \"$RAGFLOW_API_KEY\"" not in rendered
    assert "echo \"$RAGFLOW_URL\"" not in rendered
    assert "infra/ragflow/ingest.py" in rendered
    for caller in sorted(CALLERS.glob("*.yml")):
        doc = yaml.safe_load(caller.read_text())
        assert "pull_request" not in _triggers(doc)
        uses = doc["jobs"]["ingest"]["uses"]
        assert uses == "swcstudiospace/programming-desk/.github/workflows/ragflow-ingest.yml@main"
        assert set(doc["jobs"]["ingest"]["secrets"]) == {"RAGFLOW_URL", "RAGFLOW_API_KEY"}
        assert doc["permissions"] == {"contents": "read"}


def test_receipts_and_transcripts_are_not_selected():
    assert ingest.selected_path("programming-desk", ".receipts/bot-05-infrastructure/task.json") is False
    assert ingest.selected_path("programming-desk", "transcripts/session.json") is False
    assert ingest.selected_path("programming-desk", "docs/guide.md") is True
