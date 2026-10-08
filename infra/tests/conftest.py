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

# Captured at import, before the autouse fixture rewrites PATH.
HOST_SERVICE_BINS: dict[str, str | None] = {
    "systemctl": shutil.which("systemctl"),
    "nginx": shutil.which("nginx"),
}


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
    host: dict[str, str | None] | None = None,
) -> list[str]:
    """Host service binaries that `env` would execute."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    path = _command_search_path(env)
    reached: list[str] = []
    for name, host_path in host_bins.items():
        if not host_path or not path:
            continue
        found = shutil.which(name, path=path)
        if found and os.path.realpath(found) == os.path.realpath(host_path):
            reached.append(f"{name} -> {found}")
    return reached


def selected_service_bins(
    env: dict | None,
    host: dict[str, str | None] | None = None,
) -> list[str]:
    """SYSTEMCTL_BIN / NGINX_BIN values that resolve to the host binary."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    source = os.environ if env is None else env
    path = _command_search_path(env)
    hits: list[str] = []
    for key, name in _SERVICE_BIN_ENV.items():
        chosen = source.get(key)
        host_path = host_bins.get(name)
        if not chosen or not host_path:
            continue
        if os.path.isabs(chosen):
            candidate = chosen
        else:
            candidate = shutil.which(chosen, path=path) or ""
        if candidate and os.path.realpath(candidate) == os.path.realpath(host_path):
            hits.append(f"{key} -> {candidate}")
    return hits


def argv_reaches_host_service(
    args: object,
    host: dict[str, str | None] | None = None,
) -> list[str]:
    """Absolute argv0 that is the host systemctl or nginx binary."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    if not isinstance(args, (list, tuple)) or not args:
        return []
    exe = args[0]
    if not isinstance(exe, str) or not os.path.isabs(exe):
        return []
    real = os.path.realpath(exe)
    hits: list[str] = []
    for name, host_path in host_bins.items():
        if host_path and real == os.path.realpath(host_path):
            hits.append(f"{name} -> {exe}")
    return hits


def reject_host_service_bins(
    args: object,
    env: dict | None,
    host: dict[str, str | None] | None = None,
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
