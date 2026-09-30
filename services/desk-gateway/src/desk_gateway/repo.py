"""Read-only access to the programming-desk checkout on the VPS and the gate scripts in it.

Nothing here writes to the working tree of the checkout. Refs are exported into a scratch
directory with `git archive` when a gate needs a tree; the checkout itself is never switched.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from desk_gateway.config import Settings
from desk_gateway.upstreams import run_command

SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
SAFE_PATH = re.compile(r"^(?!/)(?!.*\.\.)[A-Za-z0-9._/@ -]{1,300}$")


def safe_ref(ref: str) -> bool:
    return bool(SAFE_REF.match(ref)) and not ref.startswith("-")


def safe_path(path: str) -> bool:
    return bool(SAFE_PATH.match(path))


class Repo:
    def __init__(self, settings: Settings) -> None:
        self.dir = Path(settings.repo_dir)
        self.remote = settings.repo_remote
        self.branch = settings.repo_branch

    @property
    def available(self) -> bool:
        return (self.dir / ".git").exists() or (self.dir / "ownership.yaml").exists()

    @property
    def main_ref(self) -> str:
        """origin/main in production; with no remote configured, the local ref itself
        (tests point DESK_REPO_BRANCH at HEAD of the checkout under test)."""
        return f"{self.remote}/{self.branch}" if self.remote else self.branch

    async def resolve_ref(self, ref: str | None = None) -> str:
        """The configured origin/main, or HEAD when the checkout has no such remote ref
        (a fresh clone in tests, a detached export)."""
        target = ref or self.main_ref
        if not safe_ref(target):
            return target
        probe = await run_command(["git", "rev-parse", "--verify", "--quiet", target], cwd=str(self.dir))
        if probe["exit_code"] == 0:
            return target
        return "HEAD"

    async def fetch(self) -> dict[str, Any]:
        if not self.remote:
            return {"exit_code": 0, "stdout": "", "stderr": "", "cmd": "git fetch (skipped: no remote configured)"}
        return await run_command(["git", "fetch", "--quiet", self.remote], cwd=str(self.dir), timeout=30)

    async def head_sha(self, ref: str | None = None) -> str | None:
        result = await run_command(["git", "rev-parse", await self.resolve_ref(ref)], cwd=str(self.dir))
        return result["stdout"].strip() if result["exit_code"] == 0 else None

    async def show(self, path: str, ref: str | None = None) -> str | None:
        if not safe_path(path):
            return None
        target = await self.resolve_ref(ref)
        if not safe_ref(target):
            return None
        result = await run_command(["git", "show", f"{target}:{path}"], cwd=str(self.dir), timeout=15, max_out=2_000_000)
        if result["exit_code"] != 0:
            if not ref and (self.dir / path).is_file():
                return (self.dir / path).read_text(encoding="utf-8", errors="replace")
            return None
        return result["stdout"]

    async def diff_names(self, base: str, head: str) -> list[str]:
        if not (safe_ref(base) and safe_ref(head)):
            return []
        result = await run_command(["git", "diff", "--name-only", f"{base}...{head}"], cwd=str(self.dir), timeout=20, max_out=500_000)
        return [line for line in result["stdout"].splitlines() if line.strip()] if result["exit_code"] == 0 else []

    async def diff(self, base: str, head: str, paths: list[str] | None = None) -> str:
        if not (safe_ref(base) and safe_ref(head)):
            return ""
        argv = ["git", "diff", f"{base}...{head}"]
        if paths:
            argv += ["--", *[p for p in paths if safe_path(p)]]
        result = await run_command(argv, cwd=str(self.dir), timeout=20, max_out=2_000_000)
        return result["stdout"] if result["exit_code"] == 0 else ""

    async def export(self, ref: str) -> Path | None:
        """Export a ref into a fresh scratch directory. The caller removes it."""
        if not safe_ref(ref):
            return None
        proc_out = await _archive_bytes(self.dir, await self.resolve_ref(ref))
        if proc_out is None:
            return None
        scratch = Path(tempfile.mkdtemp(prefix="desk-gate-"))
        with tarfile.open(fileobj=BytesIO(proc_out)) as tar:
            tar.extractall(scratch, filter="data")
        return scratch

    def gate_module(self, name: str) -> Any:
        path = self.dir / "ci" / "gates" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"desk_gate_{name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def ownership_manifest(self) -> Any:
        text = await self.show("ownership.yaml")
        if text is None:
            return None
        import yaml

        return yaml.safe_load(text)

    async def run_gate(self, script: str, args: list[str], cwd: Path | None = None, timeout: float = 60.0) -> dict[str, Any]:
        gate = self.dir / "ci" / "gates" / script
        return await run_command(["python3", str(gate), *args], cwd=str(cwd or self.dir), timeout=timeout)

    async def receipt_check(self, receipt: dict[str, Any], bot: str, strict: bool, receipt_path: str | None) -> dict[str, Any]:
        scratch = Path(tempfile.mkdtemp(prefix="desk-receipt-"))
        try:
            rel = receipt_path or f".receipts/{bot}/gateway-check.json"
            target = scratch / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            results = {}
            argv = ["--receipt", str(target), "--bot", bot]
            if strict:
                argv.append("--strict")
            results["G-2"] = await self.run_gate("check_receipt.py", argv)
            results["G-3"] = await self.run_gate("check_secrets.py", ["--files", str(target)])
            results["G-5/G-6"] = await self.run_gate("check_rollback.py", ["--receipt", str(target)])
            return {"ok": all(r["exit_code"] == 0 for r in results.values()), "gates": results}
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


async def _archive_bytes(repo_dir: Path, ref: str) -> bytes | None:
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git", "archive", "--format=tar", ref, cwd=str(repo_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await asyncio.wait_for(proc.communicate(), 60)
    return out if proc.returncode == 0 else None
