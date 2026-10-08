"""Fail infra tests that could reach the host systemctl or nginx binaries.

The reload and deploy scripts look those tools up on PATH. A test that
inherits the host PATH, or passes it through, can reload production nginx
or restart the production gateway. This guard runs for every test in the
directory: the default PATH is pointed at non-functional stand-ins, and any
subprocess whose environment would still resolve systemctl or nginx to the
host binary fails the test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Standard locations are searched even when the runner's PATH omits sbin.
# `/usr/sbin/nginx` is a normal install and is often absent from PATH.
_STANDARD_BIN_DIRS = (
    "/usr/local/sbin",
    "/usr/sbin",
    "/sbin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
)


def _command_text(value: object) -> str | None:
    """String form of an argv or env value subprocess would execute."""
    if isinstance(value, bytes):
        return os.fsdecode(value)
    if isinstance(value, str):
        return value
    if isinstance(value, os.PathLike):
        rendered = os.fspath(value)
        if isinstance(rendered, str):
            return rendered
        return os.fsdecode(rendered)
    return None


def _host_realpaths(value: object) -> set[str]:
    """Normalize one host path, or several, to real paths."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple)):
        found: set[str] = set()
        for item in value:
            found |= _host_realpaths(item)
        return found
    text = _command_text(value)
    if not text:
        return set()
    return {os.path.realpath(text)}


def discover_host_service_bins(
    names: tuple[str, ...] = ("systemctl", "nginx"),
) -> dict[str, tuple[str, ...]]:
    """Host service binaries, including those outside the initial PATH."""
    path_dirs = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    found: dict[str, tuple[str, ...]] = {}
    for name in names:
        reals: list[str] = []
        seen: set[str] = set()
        for directory in (*_STANDARD_BIN_DIRS, *path_dirs):
            candidate = os.path.join(directory, name)
            if not os.path.isfile(candidate) or not os.access(candidate, os.X_OK):
                continue
            real = os.path.realpath(candidate)
            if real in seen:
                continue
            seen.add(real)
            reals.append(real)
        found[name] = tuple(reals)
    return found


# Captured at import, before the autouse fixture rewrites PATH.
HOST_SERVICE_BINS: dict[str, tuple[str, ...]] = discover_host_service_bins()


# Env keys that select a service binary even when PATH points at a recorder.
_SERVICE_BIN_ENV = {
    "SYSTEMCTL_BIN": "systemctl",
    "NGINX_BIN": "nginx",
}


def _command_search_path(env: dict | None) -> str:
    """PATH the child searches.

    An explicit env that omits PATH is not empty: Python uses
    os.defpath (`/bin:/usr/bin`) for that process.
    """
    return os.pathsep.join(os.get_exec_path(env))


def reachable_host_service_bins(
    env: dict | None,
    host: dict | None = None,
) -> list[str]:
    """Host service binaries that `env` would execute."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    path = _command_search_path(env)
    reached: list[str] = []
    for name in _SERVICE_BIN_ENV.values():
        reals = _host_realpaths(host_bins.get(name))
        if not reals or not path:
            continue
        found = shutil.which(name, path=path)
        if found and os.path.realpath(found) in reals:
            reached.append(f"{name} -> {found}")
    return reached


def selected_service_bins(
    env: dict | None,
    host: dict | None = None,
) -> list[str]:
    """SYSTEMCTL_BIN / NGINX_BIN values that resolve to the host binary."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    source = os.environ if env is None else env
    path = _command_search_path(env)
    hits: list[str] = []
    for key, name in _SERVICE_BIN_ENV.items():
        chosen = source.get(key)
        reals = _host_realpaths(host_bins.get(name))
        if not chosen or not reals:
            continue
        if os.path.isabs(chosen):
            candidate = chosen
        else:
            candidate = shutil.which(chosen, path=path) or ""
        if candidate and os.path.realpath(candidate) in reals:
            hits.append(f"{key} -> {candidate}")
    return hits


def argv_reaches_host_service(
    args: object,
    host: dict | None = None,
) -> list[str]:
    """Absolute argv0 that is the host systemctl or nginx binary.

    subprocess accepts str, bytes, and pathlib.Path. All three are checked.
    """
    host_bins = HOST_SERVICE_BINS if host is None else host
    if not isinstance(args, (list, tuple)) or not args:
        return []
    exe = _command_text(args[0])
    if exe is None or not os.path.isabs(exe):
        return []
    real = os.path.realpath(exe)
    hits: list[str] = []
    for name in _SERVICE_BIN_ENV.values():
        if real in _host_realpaths(host_bins.get(name)):
            hits.append(f"{name} -> {exe}")
    return hits


def reject_host_service_bins(
    args: object,
    env: dict | None,
    host: dict | None = None,
) -> None:
    hits = (
        reachable_host_service_bins(env, host)
        + selected_service_bins(env, host)
        + argv_reaches_host_service(args, host)
    )
    if hits:
        pytest.fail(
            "test environment would reach a real service binary: " + ", ".join(hits)
        )


@pytest.fixture(autouse=True)
def forbid_host_systemctl_and_nginx(monkeypatch, tmp_path_factory):
    """Stand in front of host systemctl and nginx, and fail if a test steps around that."""
    deny_dir = tmp_path_factory.mktemp("deny-host-service-bins")
    for name in ("systemctl", "nginx"):
        path = Path(deny_dir) / name
        path.write_text(
            "#!/bin/sh\n"
            "echo \"infra test guard: refusing host ${0##*/} $*\" >&2\n"
            "exit 97\n"
        )
        path.chmod(0o755)
    original = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{deny_dir}{os.pathsep}{original}")

    real_popen = subprocess.Popen

    class GuardedPopen(real_popen):
        def __init__(self, args, *popenargs, **kwargs):
            reject_host_service_bins(args, kwargs.get("env"))
            super().__init__(args, *popenargs, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
    yield deny_dir
