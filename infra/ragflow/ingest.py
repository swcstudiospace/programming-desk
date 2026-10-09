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
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Selection, names and meta_fields are the VPS seeder's, so desk_docs_search
# keeps resolving the same datasets. Caps from a full reseed are not applied
# to a push diff.
MAX_BYTES = 400_000
UPLOAD_BATCH = 20
PARSE_BATCH = 50
DOC_EXT = {".md", ".mdx", ".markdown", ".rst"}
TEXTLIKE_EXT = {".yaml", ".yml", ".json", ".xml", ".toml", ".txt", ".example"}
EXCLUDE_DIRS = {
    ".git", "node_modules", "vendor", "vendored", "third_party", "dist", "build",
    "target", "out", ".venv", "venv", "__pycache__", ".next", ".turbo", "coverage",
    ".cache", "fixtures", "__snapshots__", "site-packages", "bower_components",
    ".pnpm-store", "__MACOSX", "generated",
}
HIDDEN_DIR_OK = {".cursor", ".claude", ".receipts", ".github", ".agents", ".grok", ".planning"}
EXCLUDE_NAME = re.compile(
    r"(^\.env(?!\.example$)|secret|credential|private[-_]?key|\.pem$|\.key$|id_rsa|"
    r"lock\.(json|yaml)$|\.lock$|-lock\.|^LICENSE|^CHANGELOG)",
    re.I,
)
SECRET_PAT = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bghp_[A-Za-z0-9]{30,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{30,}|\bxox[abpr]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b|"
    r"\bxai-[A-Za-z0-9]{20,}|\bragflow-[A-Za-z0-9]{20,}|"
    r"postgres(ql)?://[^\s:@/]+:[^\s@/]{6,}@|redis://[^\s:@/]*:[^\s@/]{8,}@)"
)
AGENT_SKILLS = "agent-skills"
PRODUCT_DOCS = "product-docs"
# dataset -> (product, extra include globs), from the seeder REPOS table.
REPO_RULES: dict[str, tuple[bool, tuple[str, ...]]] = {
    "programming-desk": (False, (".receipts/**/*.json", "ownership.yaml", "openapi.yaml", "contracts/**", "prompts/**", "ci/**/*.yml", "ci/**/*.yaml")),
    "agent-substrate": (False, (".env.example", "packages/*/README.md")),
    "claude-ultrathink": (True, ("prompts/**", "commands/**/*.md", "agents/**/*.md")),
    "agent-swarm": (True, ("prompts/**", "agents/**/*.md")),
    "omes-bot": (True, ()),
    "grok-cloud-sessions": (True, ()),
    "hermes-bot": (True, ()),
    "ultrathink": (True, ()),
    "ship-desk": (True, ()),
    "recruitment-desk": (True, ()),
    "aimeecodes": (True, ()),
    "spectrumwebco-marketing": (True, ()),
    "grokrouter": (True, ()),
    "motion-playbook": (True, ()),
    "plugin": (True, ()),
    "clippyos": (True, ()),
    "desklanes": (True, ()),
    "kanbanos": (True, ()),
}

_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")
_ZEROS = re.compile(r"^0+$")
_SAFE_REV = re.compile(r"[A-Za-z0-9._/-]+")


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
    branch: str = ""
    slug: str = ""
    url: str = ""
    content: bytes | None = field(default=None, repr=False)


def _parts(path: str) -> list[str]:
    return [part for part in path.replace("\\", "/").split("/") if part not in ("", ".")]


def secret_filename(path: str) -> bool:
    return bool(EXCLUDE_NAME.search(Path(path).name))


def _extra_match(repo: str, path: str) -> bool:
    _product, globs = REPO_RULES.get(repo, (False, ()))
    return any(fnmatch(path, pattern) for pattern in globs)


def selected_path(repo: str, path: str) -> bool:
    """Seeder ``wanted()``: doc types, text-like files under docs/prompts/contracts, extra globs."""
    parts = _parts(path)
    if not parts:
        return False
    if any(part in EXCLUDE_DIRS for part in parts[:-1]) or secret_filename(path):
        return False
    if any(part.startswith(".") and part not in HIDDEN_DIR_OK for part in parts[:-1]):
        return False
    suffix = Path(path).suffix.lower()
    if suffix in DOC_EXT:
        return True
    textlike = suffix in TEXTLIKE_EXT or Path(path).name == ".env.example"
    if _extra_match(repo, path) and (textlike or suffix in DOC_EXT):
        return True
    if parts[0] in {"docs", "prompts", "contracts"} and suffix in TEXTLIKE_EXT:
        return True
    return False


def is_skill(path: str) -> bool:
    parts = _parts(path)
    name = parts[-1] if parts else ""
    if name in {"SKILL.md", "AGENTS.md", "CLAUDE.md", "GROK.md"}:
        return True
    return (
        len(parts) >= 2
        and parts[-2] == "agents"
        and Path(name).suffix == ".md"
        and any(part in parts for part in (".cursor", ".claude", ".grok", "agents"))
    )


def is_product_doc(path: str) -> bool:
    lowered = path.lower()
    parts = _parts(path)
    if lowered in {"readme.md", "architecture.md"}:
        return True
    return bool(parts) and parts[0] == "docs" and Path(path).suffix.lower() in DOC_EXT


def datasets_for(repo: str, path: str) -> list[str]:
    names = [repo]
    if is_skill(path):
        names.append(AGENT_SKILLS)
    product, _globs = REPO_RULES.get(repo, (False, ()))
    if product and is_product_doc(path):
        names.append(PRODUCT_DOCS)
    return names


def document_name(repo: str, path: str) -> str:
    normalized = "/".join(_parts(path))
    name = f"{repo}__{normalized.replace('/', '__')}"
    if Path(normalized).suffix.lower() not in DOC_EXT | {".txt"}:
        name += ".txt"
    return name


def content_token(data: bytes) -> str:
    """First 16 hex chars, the width the seeder stores in meta_fields."""
    return hashlib.sha256(data).hexdigest()[:16]


def short_commit(sha: str) -> str:
    return sha[:12]


def blob_url(slug: str, commit: str, path: str) -> str:
    return f"https://github.com/{slug}/blob/{short_commit(commit)}/{path}"


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


def _usable_rev(value: str) -> bool:
    """A commit-ish that is safe to pass to git.

    Accepts a SHA or a single ref such as ``origin/main``. Rejects option
    injection, ranges, and the all-zero placeholder GitHub uses when the
    before commit does not exist.
    """
    if not value or _ZEROS.fullmatch(value):
        return False
    if value.startswith("-") or ".." in value or "@{" in value or "\\" in value:
        return False
    return bool(_SAFE_REV.fullmatch(value))


def changed_paths(root: Path, before: str, after: str) -> list[tuple[str, str]]:
    """Added, modified, renamed and deleted paths between two commits.

    An all-zero or missing ``before`` lists every file at ``after``.
    """
    if not _usable_rev(before):
        rev = after if _usable_rev(after) else "HEAD"
        blob = _git(root, ["ls-tree", "-r", "-z", "--name-only", rev])
        assert isinstance(blob, bytes)
        return [("A", part.decode("utf-8", "surrogateescape")) for part in blob.split(b"\0") if part]
    if not _usable_rev(after):
        raise IngestError("after must be a commit or ref when before is set")
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


def credential_shaped(data: bytes) -> bool:
    """True when the bytes match the seeder's credential pattern. The match is not returned."""
    return SECRET_PAT.search(data.decode("utf-8", errors="ignore")) is not None


def build_plan(
    root: Path,
    repo: str,
    before: str,
    after: str,
    *,
    slug: str,
    branch: str,
) -> list[Action]:
    rev = after if _usable_rev(after) else "HEAD"
    commit = _git(root, ["rev-parse", "--verify", f"{rev}^{{commit}}"], text=True)
    if isinstance(commit, bytes):
        commit = commit.decode()
    commit = short_commit(str(commit).strip())
    actions: list[Action] = []
    for status, path in changed_paths(root, before, after):
        if status == "D":
            if not selected_path(repo, path):
                continue
            name = document_name(repo, path)
            for dataset in datasets_for(repo, path):
                actions.append(Action("delete", path, dataset, name, commit=commit, branch=branch, slug=slug))
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
        if nbytes == 0 or nbytes > MAX_BYTES:
            kind = "skip-empty" if nbytes == 0 else "skip-size"
            actions.append(Action(kind, path, nbytes=nbytes))
            actions.extend(_retire(repo, path, commit, branch, slug))
            continue
        try:
            content = _blob_bytes(root, rev, path)
        except IngestError:
            actions.append(Action("skip-missing", path))
            continue
        if b"\x00" in content[:4096]:
            actions.append(Action("skip-binary", path, nbytes=nbytes))
            actions.extend(_retire(repo, path, commit, branch, slug))
            continue
        if credential_shaped(content):
            actions.append(Action("skip-credential", path, nbytes=nbytes))
            continue
        digest = content_token(content)
        name = document_name(repo, path)
        url = blob_url(slug, commit, path)
        for dataset in datasets_for(repo, path):
            actions.append(
                Action(
                    "upsert", path, dataset, name, digest, nbytes, commit, branch, slug, url, content,
                )
            )
    return actions


def _retire(repo: str, path: str, commit: str, branch: str, slug: str) -> list[Action]:
    """Drop a previously indexed document when the path is no longer ingestible."""
    name = document_name(repo, path)
    return [
        Action("delete", path, dataset, name, commit=commit, branch=branch, slug=slug)
        for dataset in datasets_for(repo, path)
    ]


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


def _redact(text: str, *secrets: str) -> str:
    for secret in secrets:
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
                f"RAGFlow {method} {path} returned HTTP {exc.code}: "
                f"{_redact(body, self.api_key, self.base_url)}"
            ) from exc
        except URLError as exc:
            reason = _redact(str(exc.reason), self.api_key, self.base_url)
            raise IngestError(f"RAGFlow {method} {path} failed: {reason}") from exc
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestError(f"RAGFlow {method} {path} returned non-JSON") from exc
        if isinstance(body, dict) and body.get("code") not in (None, 0):
            message = body.get("message") or body.get("msg") or "error"
            raise IngestError(
                f"RAGFlow {method} {path} code {body.get('code')}: "
                f"{_redact(str(message), self.api_key, self.base_url)}"
            )
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
        # Quoted-string encoding keeps the seeder's document name, including
        # quotes. Stripping those characters made the next lookup miss.
        safe_name = quoted_filename(filename)
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

    def set_meta(self, dataset_id: str, document_id: str, meta: dict) -> None:
        self._request(
            "PUT",
            f"/api/v1/datasets/{dataset_id}/documents/{document_id}",
            payload=json.dumps({"meta_fields": meta}).encode(),
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


def quoted_filename(name: str) -> str:
    """Encode a document name as a multipart quoted-string. CR and LF cannot sit in a header."""
    cleaned = name.replace("\r", "").replace("\n", "")
    return cleaned.replace("\\", "\\\\").replace('"', '\\"')


def _candidate_names(name: str) -> set[str]:
    stripped = name.replace('"', "").replace("\r", "").replace("\n", "")
    return {name, stripped}


# List responses use names (DONE, RUNNING) and older payloads use "3" and "1".
_PARSED_RUN = {"1", "3", "RUNNING", "DONE"}


def _needs_parse(doc: dict) -> bool:
    run = doc.get("run")
    if run is None:
        return False
    return str(run).strip().upper() not in _PARSED_RUN


def _matches(docs: list[dict], name: str, path: str) -> list[dict]:
    """Exact document names match. A quote-stripped legacy name matches only the same path."""
    stripped = name.replace('"', "").replace("\r", "").replace("\n", "")
    hits = []
    for doc in docs:
        doc_name = doc.get("name")
        if doc_name == name:
            hits.append(doc)
            continue
        if stripped != name and doc_name == stripped:
            meta = doc.get("meta_fields") or {}
            if isinstance(meta, dict) and meta.get("path") == path:
                hits.append(doc)
    return hits


def _find_docs(client: RagflowClient, dataset_id: str, name: str, path: str) -> list[dict]:
    found: dict[str, dict] = {}
    for keyword in _candidate_names(name):
        for doc in client.documents(dataset_id, keyword):
            if doc.get("id"):
                found[str(doc["id"])] = doc
    return _matches(list(found.values()), name, path)


def _meta(action: Action) -> dict:
    return {
        "repo": action.slug,
        "path": action.path,
        "commit": action.commit,
        "branch": action.branch,
        "url": action.url,
        "content_sha256": action.sha256,
    }


def execute(actions: list[Action], client: RagflowClient, batch_size: int = PARSE_BATCH) -> None:
    pending: dict[str, list[str]] = {}
    upserts = [action for action in actions if action.kind == "upsert"]
    deletes = [action for action in actions if action.kind == "delete"]

    def flush(dataset: str, force: bool = False) -> None:
        ids = pending.get(dataset) or []
        if not ids:
            return
        if not force and len(ids) < batch_size:
            return
        client.parse(client.dataset_id(dataset), ids)
        pending[dataset] = []

    for action in deletes:
        dataset_id = client.dataset_id(action.dataset)
        docs = _find_docs(client, dataset_id, action.document, action.path)
        client.delete(dataset_id, [str(doc["id"]) for doc in docs if doc.get("id")])

    # Uploads stay one file at a time so the previous version is deleted only
    # after that file's upload and meta_fields call succeed. A later failure
    # still parses the documents already stored.
    try:
        for action in upserts:
            dataset_id = client.dataset_id(action.dataset)
            existing = _find_docs(client, dataset_id, action.document, action.path)
            matched = [
                doc for doc in existing
                if str((doc.get("meta_fields") or {}).get("content_sha256")) == action.sha256
            ]
            if matched:
                for doc in matched:
                    if doc.get("id") and _needs_parse(doc):
                        pending.setdefault(action.dataset, []).append(str(doc["id"]))
                flush(action.dataset)
                print(
                    f"plan skip-unchanged dataset={action.dataset} document={action.document}",
                    flush=True,
                )
                continue
            if action.content is None:
                raise IngestError(f"missing content for {action.document}")
            new_id = client.upload(dataset_id, action.document, action.content)
            client.set_meta(dataset_id, new_id, _meta(action))
            old_ids = [str(doc["id"]) for doc in existing if doc.get("id") and str(doc["id"]) != new_id]
            client.delete(dataset_id, old_ids)
            pending.setdefault(action.dataset, []).append(new_id)
            flush(action.dataset)
            print(
                f"plan upsert dataset={action.dataset} document={action.document}",
                flush=True,
            )
    finally:
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
    parser.add_argument("--repo-slug", default="", help="owner/name stored in meta_fields.repo and the blob url")
    parser.add_argument("--branch", default="", help="Branch stored in meta_fields. Defaults to GITHUB_REF_NAME or HEAD")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=PARSE_BATCH,
        help=f"documents per parse call (seeder reseed uploads in groups of {UPLOAD_BATCH}; this job uploads one file so the previous version is deleted only after that file succeeds)",
    )
    args = parser.parse_args(argv)

    if os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        print("ragflow-ingest: pull_request events do not ingest; skipping")
        return 0

    if not args.dry_run:
        url = os.environ.get("RAGFLOW_URL", "")
        key = os.environ.get("RAGFLOW_API_KEY", "")
        if not secrets_present(url, key):
            print("ragflow-ingest: RAGFLOW_URL or RAGFLOW_API_KEY is empty; skipping ingest")
            return 0

    root = Path(args.root).resolve()
    slug = args.repo_slug.strip() or f"swcstudiospace/{args.repo}"
    branch = args.branch.strip() or os.environ.get("GITHUB_REF_NAME", "").strip()
    if not branch:
        try:
            detected = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"], text=True)
            branch = str(detected).strip() if not isinstance(detected, bytes) else detected.decode().strip()
        except IngestError:
            branch = "main"
    try:
        actions = build_plan(root, args.repo, args.before, args.after, slug=slug, branch=branch)
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

    if not any(action.kind in {"upsert", "delete"} for action in actions):
        print("ragflow-ingest: no documents to ingest")
        return 0

    try:
        execute(actions, client_factory(url, key), batch_size=max(1, args.batch_size))
    except IngestError as exc:
        print(f"ragflow-ingest: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
