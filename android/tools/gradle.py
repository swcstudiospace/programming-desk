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


def module_task(module: str, task: str = "test") -> str:
    """Convert a filesystem module path (e.g. 'app', 'android/app') into a
    Gradle project task reference (e.g. ':app:test', ':android:app:test').

    Gradle treats any bare positional argument as a task name, so passing
    the raw path (e.g. 'android/app') alongside 'test' makes Gradle look
    for a *second*, nonexistent task called 'android/app' instead of
    scoping the 'test' task to that project.
    """
    normalized = module.strip().replace("\\", "/").strip("/").lstrip(":")
    segments = [seg for seg in normalized.replace(":", "/").split("/") if seg]
    if not segments:
        return task
    return ":" + ":".join(segments) + ":" + task


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
    if module:
        argv = [str(wrapper), module_task(module)]
    else:
        argv = [str(wrapper), "test"]
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
