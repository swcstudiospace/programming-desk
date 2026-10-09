#!/usr/bin/env python3
"""Incremental RAGFlow ingest for one git push.

Stdlib only. Names, datasets and meta_fields follow the desk seeder:

- dataset name is the repo name
- document name is ``repo__path`` with slashes written as ``__``
- non-doc types get a ``.txt`` suffix
- meta_fields are repo, path, commit, url, content_sha256
- SKILL.md and agent files also go to ``agent-skills``
- README and docs of the product repos also go to ``product-docs``

Empty ``RAGFLOW_URL`` or ``RAGFLOW_API_KEY`` prints a notice and exits 0.
``pull_request`` events exit 0 without reading the tree. ``--dry-run`` prints
the plan and does not call RAGFlow. The key and file contents are never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MAX_BYTES = 400 * 1024
PARSE_BATCH = 16
DOC_EXTENSIONS = {
    ".md", ".mdx", ".markdown", ".txt", ".rst", ".adoc", ".asciidoc",
    ".html", ".htm", ".pdf", ".docx", ".csv", ".org",
}
TEXT_EXTENSIONS = {
    ".py", ".pyi", ".yml", ".yaml", ".json", ".toml", ".xml", ".sh", ".bash",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".sql", ".tf",
    ".hujson", ".css", ".ini", ".cfg", ".conf", ".service", ".timer",
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".gz", ".tgz",
    ".woff", ".woff2", ".ttf", ".mp4", ".mp3", ".jar", ".apk", ".so", ".dylib",
    ".dll", ".lock", ".pyc", ".wasm",
}
EXCLUDED_DIRS = {
    ".git", "node_modules", ".receipts", "vendor", "dist", "build",
    "__pycache__", ".venv", "venv", ".pytest_cache", "coverage", ".next",
    "target", ".tox", ".gradle", "Pods", ".terraform", "transcripts",
    ".idea", ".vscode",
}
EXCLUDED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "cargo.lock",
    "go.sum", "poetry.lock",
}
SECRET_FILENAMES = {
    ".env", ".netrc", ".npmrc", ".pypirc", ".pgpass",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    "credentials.json", "secrets.json", "service-account.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx", ".keystore", ".jks", ".p8")
PRODUCT_REPOS = {
    "kanbanos", "kanban-os", "desklanes", "desk-lanes", "clippyos", "auctioning",
}
AGENT_SKILLS = "agent-skills"
PRODUCT_DOCS = "product-docs"
# Extra include globs, assumed from the four repos' doc trees. uploads/seed.py
# was not in this workspace, so these are the trees the use case names rather
# than a byte copy of the VPS script.
REPO_EXTRA_GLOBS = {
    "programming-desk": ("prompts/**", "prompts-assembled/**", "contracts/**", "skills/**", "docs/**"),
    "agent-substrate": ("docs/**", "packages/**", ".planning/**"),
    "agent-swarm": (".cursor/agents/**", "skills/**", "docs/**", "swarm/**"),
    "claude-ultrathink": ("docs/**", "plugins/**", "skills/**", ".claude/**"),
}
SHARED_EXTRA_NAMES = {"Dockerfile", "Makefile", "LICENSE", "justfile", "Containerfile"}

_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")
_ZEROS = re.compile(r"^0+$")


class IngestError(Exception):
    """A git or RAGFlow failure that should exit non-zero."""


@dataclass
class Action:
    kind: str
    path: str
    dataset: str = ""
    document: str = ""
    sha256: str = ""
    nbytes: int = 0
    commit: str = ""
    url: str = ""
    content: bytes | None = field(default=None, repr=False)


def _pem_prefix() -> bytes:
    # Built in two parts so this source line is not itself a key block.
    return b"-----BEGIN " + b"PRIVATE KEY-----"


def credential_shaped(data: bytes) -> bool:
    """True when the bytes look like a credential. The match is not returned."""
    if _pem_prefix() in data:
        return True
    if re.search(br"(?:AKIA|ASIA)[0-9A-Z]{16}", data):
        return True
    if re.search(br"gh[pousr]_[A-Za-z0-9]{20,}", data):
        return True
    if re.search(br"github_pat_[A-Za-z0-9_]{20,}", data):
        return True
    if re.search(br"xox[baprs]-[A-Za-z0-9\-]{10,}", data):
        return True
    if re.search(br"sk-(?:proj-|ant-)?[A-Za-z0-9\-_]{20,}", data):
        return True
    if re.search(br"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", data):
        return True
    if re.search(br"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)://[^:\s/]+:[^@\s/]+@", data):
        return True
    return False


def secret_filename(path: str) -> bool:
    name = Path(path).name.lower()
    if name in SECRET_FILENAMES:
        return True
    if name.startswith(".env.") and not name.endswith((".example", ".sample", ".template")):
        return True
    if name.endswith(SECRET_SUFFIXES):
        return True
    if any(part in name for part in ("secret", "credential", "password")) and name.endswith(
        (".json", ".yml", ".yaml", ".txt", ".env", ".xml", ".ini")
    ):
        return True
    return False


def _parts(path: str) -> list[str]:
    return [part for part in path.replace("\\", "/").split("/") if part not in ("", ".")]


def excluded_path(path: str) -> bool:
    parts = _parts(path)
    if not parts:
        return True
    if parts[-1].lower() in EXCLUDED_FILES:
        return True
    return any(part in EXCLUDED_DIRS for part in parts[:-1])


def _extra_match(repo: str, path: str) -> bool:
    name = Path(path).name
    if name in SHARED_EXTRA_NAMES:
        return True
    for pattern in REPO_EXTRA_GLOBS.get(repo, ()):
        if fnmatch(path, pattern):
            return True
    return False


def selected_path(repo: str, path: str) -> bool:
    """True when the seeder would consider this path a document."""
    if excluded_path(path) or secret_filename(path):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return False
    if suffix in DOC_EXTENSIONS or suffix in TEXT_EXTENSIONS:
        return True
    return _extra_match(repo, path)


def is_agent_file(path: str) -> bool:
    if Path(path).name == "SKILL.md":
        return True
    parts = _parts(path)
    for index, part in enumerate(parts[:-1]):
        nxt = parts[index + 1]
        if part in {".cursor", ".claude", ".codex"} and nxt == "agents":
            return True
    return False


def is_product_doc(path: str) -> bool:
    name = Path(path).name.lower()
    if name.startswith("readme."):
        return True
    return "docs" in _parts(path)


def datasets_for(repo: str, path: str) -> list[str]:
    names = [repo]
    if is_agent_file(path):
        names.append(AGENT_SKILLS)
    if repo.lower() in PRODUCT_REPOS and is_product_doc(path):
        names.append(PRODUCT_DOCS)
    return names


def document_name(repo: str, path: str) -> str:
    normalized = "/".join(_parts(path))
    stem = f"{repo}__{normalized.replace('/', '__')}"
    suffix = Path(normalized).suffix.lower()
    if suffix in DOC_EXTENSIONS:
        return stem
    return stem + ".txt"


def blob_url(github_base: str, repo: str, commit: str, path: str) -> str:
    quoted = "/".join(quote(part) for part in _parts(path))
    if "/" in repo:
        return f"https://github.com/{repo}/blob/{commit}/{quoted}"
    base = github_base.rstrip("/")
    return f"{base}/{repo}/blob/{commit}/{quoted}"


def parse_name_status(text: str) -> list[tuple[str, str]]:
    """Parse ``git diff --name-status`` text into (status, path) pairs.

    Status is ``A``, ``M`` or ``D``. A rename is a delete of the old path and
    an add of the new path. A copy is an add of the new path.
    """
    changes: list[tuple[str, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        cols = raw.split("\t")
        code = cols[0][:1]
        if code in {"R", "C"} and len(cols) >= 3:
            if code == "R":
                changes.append(("D", cols[1]))
            changes.append(("A", cols[2]))
        elif code == "D" and len(cols) >= 2:
            changes.append(("D", cols[1]))
        elif code in {"A", "M", "T"} and len(cols) >= 2:
            changes.append(("A" if code == "A" else "M", cols[1]))
    return changes


def parse_name_status_z(blob: bytes) -> list[tuple[str, str]]:
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    changes: list[tuple[str, str]] = []
    index = 0
    while index < len(parts):
        status = parts[index].decode("utf-8", "surrogateescape")
        index += 1
        code = status[:1]
        if code in {"R", "C"}:
            if index + 1 >= len(parts):
                break
            old = parts[index].decode("utf-8", "surrogateescape")
            new = parts[index + 1].decode("utf-8", "surrogateescape")
            index += 2
            if code == "R":
                changes.append(("D", old))
            changes.append(("A", new))
            continue
        if index >= len(parts):
            break
        path = parts[index].decode("utf-8", "surrogateescape")
        index += 1
        if code == "D":
            changes.append(("D", path))
        elif code in {"A", "M", "T"}:
            changes.append(("A" if code == "A" else "M", path))
    return changes


def _git(root: Path, args: list[str], *, text: bool = False) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        raise IngestError(f"git {' '.join(args)} failed: {detail}") from exc
    if text:
        return result.stdout.decode("utf-8", "surrogateescape")
    return result.stdout


def _valid_rev(value: str) -> bool:
    return bool(_SHA.fullmatch(value)) and not _ZEROS.fullmatch(value)


def changed_paths(root: Path, before: str, after: str) -> list[tuple[str, str]]:
    """Added, modified, renamed and deleted paths between two commits.

    An all-zero or missing ``before`` lists every file at ``after``.
    """
    if not before or _ZEROS.fullmatch(before) or not _valid_rev(before):
        rev = after if _valid_rev(after) else "HEAD"
        blob = _git(root, ["ls-tree", "-r", "-z", "--name-only", rev])
        assert isinstance(blob, bytes)
        return [("A", part.decode("utf-8", "surrogateescape")) for part in blob.split(b"\0") if part]
    if not _valid_rev(after):
        raise IngestError("after must be a commit sha when before is a commit sha")
    blob = _git(root, ["diff", "--name-status", "-z", "-M", before, after])
    assert isinstance(blob, bytes)
    return parse_name_status_z(blob)


def _blob_size(root: Path, rev: str, path: str) -> int:
    raw = _git(root, ["cat-file", "-s", f"{rev}:{path}"], text=True)
    assert isinstance(raw, str)
    return int(raw.strip() or "0")


def _blob_bytes(root: Path, rev: str, path: str) -> bytes:
    raw = _git(root, ["show", f"{rev}:{path}"])
    assert isinstance(raw, bytes)
    return raw


def build_plan(
    root: Path,
    repo: str,
    before: str,
    after: str,
    *,
    github_base: str,
) -> list[Action]:
    rev = after if _valid_rev(after) else "HEAD"
    commit = after if _valid_rev(after) else _git(root, ["rev-parse", "HEAD"], text=True)
    if isinstance(commit, bytes):
        commit = commit.decode()
    commit = str(commit).strip()
    actions: list[Action] = []
    for status, path in changed_paths(root, before, after):
        if status == "D":
            if not selected_path(repo, path):
                continue
            name = document_name(repo, path)
            for dataset in datasets_for(repo, path):
                actions.append(Action("delete", path, dataset, name, commit=commit))
            continue
        if secret_filename(path):
            actions.append(Action("skip-secret", path))
            continue
        if not selected_path(repo, path):
            actions.append(Action("skip-type", path))
            continue
        try:
            nbytes = _blob_size(root, rev, path)
        except IngestError:
            actions.append(Action("skip-missing", path))
            continue
        if nbytes > MAX_BYTES:
            actions.append(Action("skip-size", path, nbytes=nbytes))
            continue
        try:
            content = _blob_bytes(root, rev, path)
        except IngestError:
            actions.append(Action("skip-missing", path))
            continue
        if credential_shaped(content):
            actions.append(Action("skip-credential", path, nbytes=nbytes))
            continue
        digest = hashlib.sha256(content).hexdigest()
        name = document_name(repo, path)
        url = blob_url(github_base, repo, commit, path)
        for dataset in datasets_for(repo, path):
            actions.append(
                Action(
                    "upsert", path, dataset, name, digest, nbytes, commit, url, content,
                )
            )
    return actions


def format_plan(actions: Iterable[Action]) -> str:
    lines: list[str] = []
    for action in actions:
        if action.kind == "upsert":
            lines.append(
                "plan upsert "
                f"dataset={action.dataset} document={action.document} "
                f"path={action.path} sha256={action.sha256}"
            )
        elif action.kind == "delete":
            lines.append(
                f"plan delete dataset={action.dataset} document={action.document} path={action.path}"
            )
        elif action.kind == "skip-size":
            lines.append(f"plan skip-size path={action.path} bytes={action.nbytes}")
        else:
            lines.append(f"plan {action.kind} path={action.path}")
    return "\n".join(lines)


def _redact(text: str, secret: str) -> str:
    if secret:
        text = text.replace(secret, "[redacted]")
    return text[:300]


class RagflowClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._datasets: dict[str, str] = {}

    def _request(self, method: str, path: str, *, query: dict | None = None, payload: bytes | None = None,
                 headers: dict[str, str] | None = None) -> dict:
        url = self.base_url + path
        if query:
            url = url + "?" + urlencode(query)
        req_headers = {"Authorization": f"Bearer {self.api_key}"}
        if headers:
            req_headers.update(headers)
        request = Request(url, data=payload, headers=req_headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise IngestError(
                f"RAGFlow {method} {path} returned HTTP {exc.code}: {_redact(body, self.api_key)}"
            ) from exc
        except URLError as exc:
            raise IngestError(f"RAGFlow {method} {path} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestError(f"RAGFlow {method} {path} returned non-JSON") from exc
        if isinstance(body, dict) and body.get("code") not in (None, 0):
            message = body.get("message") or body.get("msg") or "error"
            raise IngestError(f"RAGFlow {method} {path} code {body.get('code')}: {_redact(str(message), self.api_key)}")
        return body if isinstance(body, dict) else {}

    def dataset_id(self, name: str) -> str:
        cached = self._datasets.get(name)
        if cached:
            return cached
        body = self._request("GET", "/api/v1/datasets", query={"page": 1, "page_size": 100, "name": name})
        data = body.get("data")
        rows = data if isinstance(data, list) else []
        if isinstance(data, dict):
            rows = data.get("docs") or data.get("datasets") or []
        for row in rows:
            if isinstance(row, dict) and row.get("name") == name and row.get("id"):
                self._datasets[name] = str(row["id"])
                return self._datasets[name]
        created = self._request(
            "POST",
            "/api/v1/datasets",
            payload=json.dumps({"name": name}).encode(),
            headers={"Content-Type": "application/json"},
        )
        created_row = created.get("data") if isinstance(created.get("data"), dict) else {}
        dataset_id = str(created_row.get("id") or "")
        if not dataset_id:
            raise IngestError(f"RAGFlow created dataset {name} without an id")
        self._datasets[name] = dataset_id
        return dataset_id

    def documents(self, dataset_id: str, keywords: str) -> list[dict]:
        found: list[dict] = []
        page = 1
        while page <= 50:
            body = self._request(
                "GET",
                f"/api/v1/datasets/{dataset_id}/documents",
                query={"page": page, "page_size": 100, "keywords": keywords},
            )
            data = body.get("data")
            if isinstance(data, list):
                docs = [row for row in data if isinstance(row, dict)]
                total = None
            elif isinstance(data, dict):
                docs = [row for row in (data.get("docs") or []) if isinstance(row, dict)]
                total = data.get("total")
            else:
                docs = []
                total = None
            found.extend(docs)
            if not docs or len(docs) < 100:
                break
            if isinstance(total, int) and len(found) >= total:
                break
            page += 1
        return found

    def upload(self, dataset_id: str, filename: str, content: bytes) -> str:
        boundary = "----ragflow" + uuid.uuid4().hex
        safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
        preamble = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        payload = preamble + content + f"\r\n--{boundary}--\r\n".encode()
        body = self._request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/documents",
            payload=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        data = body.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("id"):
            return str(data[0]["id"])
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        raise IngestError("RAGFlow upload returned no document id")

    def set_meta(self, dataset_id: str, document_id: str, name: str, meta: dict) -> None:
        self._request(
            "PUT",
            f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
            payload=json.dumps({"name": name, "meta_fields": meta}).encode(),
            headers={"Content-Type": "application/json"},
        )

    def delete(self, dataset_id: str, document_ids: list[str]) -> None:
        if not document_ids:
            return
        self._request(
            "DELETE",
            f"/api/v1/datasets/{dataset_id}/documents",
            payload=json.dumps({"ids": document_ids}).encode(),
            headers={"Content-Type": "application/json"},
        )

    def parse(self, dataset_id: str, document_ids: list[str]) -> None:
        if not document_ids:
            return
        self._request(
            "POST",
            f"/api/v1/datasets/{dataset_id}/chunks",
            payload=json.dumps({"document_ids": document_ids}).encode(),
            headers={"Content-Type": "application/json"},
        )


def _matches(docs: list[dict], name: str, path: str, repo: str) -> list[dict]:
    hits = []
    for doc in docs:
        meta = doc.get("meta_fields") or {}
        if not isinstance(meta, dict):
            meta = {}
        if doc.get("name") == name or (meta.get("path") == path and meta.get("repo") == repo):
            hits.append(doc)
    return hits


def execute(actions: list[Action], client: RagflowClient, repo: str, batch_size: int = PARSE_BATCH) -> None:
    pending: dict[str, list[str]] = {}

    def flush(dataset: str, force: bool = False) -> None:
        ids = pending.get(dataset) or []
        if not ids:
            return
        if not force and len(ids) < batch_size:
            return
        dataset_id = client.dataset_id(dataset)
        client.parse(dataset_id, ids)
        pending[dataset] = []

    for action in actions:
        if action.kind == "delete":
            dataset_id = client.dataset_id(action.dataset)
            docs = _matches(client.documents(dataset_id, action.document), action.document, action.path, repo)
            client.delete(dataset_id, [str(doc["id"]) for doc in docs if doc.get("id")])
            continue
        if action.kind != "upsert":
            continue
        dataset_id = client.dataset_id(action.dataset)
        existing = _matches(client.documents(dataset_id, action.document), action.document, action.path, repo)
        if any(str((doc.get("meta_fields") or {}).get("content_sha256")) == action.sha256 for doc in existing):
            print(
                f"plan skip-unchanged dataset={action.dataset} document={action.document} path={action.path}",
                flush=True,
            )
            continue
        if action.content is None:
            raise IngestError(f"missing content for {action.path}")
        new_id = client.upload(dataset_id, action.document, action.content)
        client.set_meta(
            dataset_id,
            new_id,
            action.document,
            {
                "repo": repo,
                "path": action.path,
                "commit": action.commit,
                "url": action.url,
                "content_sha256": action.sha256,
            },
        )
        old_ids = [str(doc["id"]) for doc in existing if doc.get("id") and str(doc["id"]) != new_id]
        client.delete(dataset_id, old_ids)
        pending.setdefault(action.dataset, []).append(new_id)
        flush(action.dataset)
        print(
            f"plan upsert dataset={action.dataset} document={action.document} path={action.path} sha256={action.sha256}",
            flush=True,
        )
    for dataset in list(pending):
        flush(dataset, force=True)


def secrets_present(url: str, key: str) -> bool:
    return bool(url.strip()) and bool(key.strip())


def run(argv: list[str] | None = None, *, client_factory=RagflowClient) -> int:
    parser = argparse.ArgumentParser(description="Ingest one git push into RAGFlow")
    parser.add_argument("--repo", required=True, help="Dataset name. Usually the GitHub repo name.")
    parser.add_argument("--root", default=".", help="Git working tree to read")
    parser.add_argument("--before", default="", help="Push before SHA. All zeros lists the whole tree.")
    parser.add_argument("--after", default="", help="Push after SHA")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and do not call RAGFlow")
    parser.add_argument("--github-base", default="https://github.com/swcstudiospace")
    parser.add_argument("--batch-size", type=int, default=PARSE_BATCH)
    args = parser.parse_args(argv)

    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        print("ragflow-ingest: pull_request events do not ingest; skipping")
        return 0

    root = Path(args.root).resolve()
    try:
        actions = build_plan(
            root, args.repo, args.before, args.after, github_base=args.github_base,
        )
    except IngestError as exc:
        print(f"ragflow-ingest: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        rendered = format_plan(actions)
        if rendered:
            print(rendered)
        else:
            print("ragflow-ingest: no documents to ingest")
        return 0

    url = os.environ.get("RAGFLOW_URL", "")
    key = os.environ.get("RAGFLOW_API_KEY", "")
    if not secrets_present(url, key):
        print("ragflow-ingest: RAGFLOW_URL or RAGFLOW_API_KEY is empty; skipping ingest")
        return 0

    if not any(action.kind in {"upsert", "delete"} for action in actions):
        print("ragflow-ingest: no documents to ingest")
        return 0

    try:
        execute(actions, client_factory(url, key), args.repo, batch_size=max(1, args.batch_size))
    except IngestError as exc:
        print(f"ragflow-ingest: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
