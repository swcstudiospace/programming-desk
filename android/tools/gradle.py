"""Gradle wrappers. Skip cleanly when gradlew is absent."""

from __future__ import annotations

import subprocess
from pathlib import Path


SKIP_LINE = "skipped: no gradlew found (unit_test requires a Gradle wrapper in cwd or --module)"


def find_gradlew(module: str | None = None, cwd: Path | None = None) -> Path | None:
    """Locate ./gradlew relative to cwd or module path."""
    roots: list[Path] = []
    base = Path(cwd) if cwd is not None else Path.cwd()
    if module:
        mod = Path(module)
        if not mod.is_absolute():
            mod = base / mod
        roots.append(mod)
        roots.append(mod if mod.is_dir() else mod.parent)
    roots.append(base)
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        candidate = root / "gradlew"
        if candidate.is_file():
            return candidate
    return None


def unit_test(
    module: str | None = None,
    gradle_args: list[str] | None = None,
    *,
    cwd: Path | None = None,
) -> tuple[int, str]:
    """Run `./gradlew test` (+ module path / extras). Exit 0 with skip line if absent."""
    wrapper = find_gradlew(module=module, cwd=cwd)
    if wrapper is None:
        return 0, SKIP_LINE
    argv = [str(wrapper), "test"]
    if module:
        # Pass module as a Gradle project path hint when provided.
        argv.append(module)
    if gradle_args:
        argv.extend(gradle_args)
    proc = subprocess.run(
        argv,
        cwd=str(wrapper.parent),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip() or f"gradlew exited {proc.returncode}"
