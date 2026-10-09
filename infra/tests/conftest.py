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
    os.defpath (`/bin:/usr/bin`) for that process. Byte-keyed
    environments are accepted, matching os.get_exec_path.
    """
    return os.pathsep.join(os.get_exec_path(env))


def _mapping_get(source: dict, key: str) -> object | None:
    """Value for `key` in a str-keyed or bytes-keyed environment.

    os.environ rejects bytes keys. A plain dict and os.environb accept them.
    """
    if key in source:
        return source[key]
    encoded = os.fsencode(key)
    try:
        if encoded in source:
            return source[encoded]
    except (TypeError, UnicodeError):
        return None
    return None


def resolved_program(
    args: object,
    executable: object,
    env: dict | None,
    cwd: object = None,
) -> str | None:
    """Program Popen executes.

    Matches Popen._execute_child: an omitted executable is args[0]; a path
    with a directory component is used as given; a bare name is searched on
    the child's PATH. The child chdirs to `cwd` before exec, so a relative
    path is resolved there rather than in the parent process.
    """
    if executable is None:
        if not isinstance(args, (list, tuple)) or not args:
            return None
        program = _command_text(args[0])
    else:
        program = _command_text(executable)
    if not program:
        return None
    if os.path.isabs(program):
        return program
    if os.path.dirname(program):
        base = _command_text(cwd) if cwd is not None else None
        if base:
            return os.path.join(base, program)
        return program
    return shutil.which(program, path=_command_search_path(env)) or program


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
    cwd: object = None,
) -> list[str]:
    """SYSTEMCTL_BIN / NGINX_BIN values that resolve to the host binary."""
    host_bins = HOST_SERVICE_BINS if host is None else host
    source = os.environ if env is None else env
    path = _command_search_path(env)
    hits: list[str] = []
    for key, name in _SERVICE_BIN_ENV.items():
        chosen = _command_text(_mapping_get(source, key))
        reals = _host_realpaths(host_bins.get(name))
        if not chosen or not reals:
            continue
        if os.path.isabs(chosen):
            candidate = chosen
        elif os.path.dirname(chosen):
            # A path with a directory component is relative to the child cwd.
            base = _command_text(cwd) if cwd is not None else None
            candidate = os.path.join(base, chosen) if base else chosen
        else:
            candidate = shutil.which(chosen, path=path) or ""
        if candidate and os.path.realpath(candidate) in reals:
            hits.append(f"{key} -> {candidate}")
    return hits


def executable_reaches_host_service(
    args: object,
    executable: object,
    env: dict | None,
    host: dict | None = None,
    cwd: object = None,
) -> list[str]:
    """Popen `executable=` that is the host systemctl or nginx binary."""
    if executable is None:
        return []
    host_bins = HOST_SERVICE_BINS if host is None else host
    program = resolved_program(args, executable, env, cwd)
    if not program:
        return []
    real = os.path.realpath(program)
    hits: list[str] = []
    for name in _SERVICE_BIN_ENV.values():
        if real in _host_realpaths(host_bins.get(name)):
            hits.append(f"executable -> {program}")
    return hits


def argv_reaches_host_service(
    args: object,
    host: dict | None = None,
    cwd: object = None,
) -> list[str]:
    """argv0 that is the host systemctl or nginx binary.

    subprocess accepts str, bytes, and pathlib.Path. An absolute path is
    used as given. A relative path with a directory component is resolved
    in the child cwd, because Popen uses argv0 when executable= is omitted.
    """
    host_bins = HOST_SERVICE_BINS if host is None else host
    if not isinstance(args, (list, tuple)) or not args:
        return []
    exe = _command_text(args[0])
    if exe is None:
        return []
    if os.path.isabs(exe):
        candidate = exe
    elif os.path.dirname(exe):
        base = _command_text(cwd) if cwd is not None else None
        candidate = os.path.join(base, exe) if base else exe
    else:
        return []
    real = os.path.realpath(candidate)
    hits: list[str] = []
    for name in _SERVICE_BIN_ENV.values():
        if real in _host_realpaths(host_bins.get(name)):
            hits.append(f"{name} -> {exe}")
    return hits


def reject_host_service_bins(
    args: object,
    env: dict | None,
    host: dict | None = None,
    executable: object = None,
    cwd: object = None,
) -> None:
    hits = (
        reachable_host_service_bins(env, host)
        + selected_service_bins(env, host, cwd)
        + argv_reaches_host_service(args, host, cwd)
        + executable_reaches_host_service(args, executable, env, host, cwd)
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
            # Popen(args, bufsize, executable, ..., env=). subprocess.run
            # passes executable and env as keywords; a positional call puts
            # executable in popenargs[1].
            executable = kwargs.get("executable")
            if executable is None and len(popenargs) >= 2:
                executable = popenargs[1]
            env = kwargs.get("env")
            if env is None and len(popenargs) >= 10:
                env = popenargs[9]
            # cwd sits just before env in the positional signature.
            cwd = kwargs.get("cwd")
            if cwd is None and len(popenargs) >= 9:
                cwd = popenargs[8]
            reject_host_service_bins(args, env, executable=executable, cwd=cwd)
            super().__init__(args, *popenargs, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", GuardedPopen)
    yield deny_dir
