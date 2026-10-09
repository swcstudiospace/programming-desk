"""Test suite for automated staging and VPS deployment pipeline (REQ-STAGE-001, REQ-STAGE-002).

Reload and deploy commands run against recorders on a private PATH. Nothing
here signals a host process or reloads host nginx.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra/desk-gateway/deploy-staging.sh"
RELOAD_SCRIPT = REPO_ROOT / "infra/desk-gateway/reload-nginx-gateway.sh"

# External tools the scripts may call. systemctl, nginx, pgrep and kill are
# never linked from the host; tests install their own recorders under those names.
SAFE_TOOLS = (
    "bash",
    "cat",
    "cp",
    "date",
    "git",
    "head",
    "ln",
    "ls",
    "mkdir",
    "python3",
    "readlink",
    "rm",
    "rsync",
    "sleep",
    "tail",
    "tr",
    "xargs",
)


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(body)
    path.chmod(0o755)
    return path


def _link_safe_tools(stub_dir: Path) -> None:
    for name in SAFE_TOOLS:
        dest = stub_dir / name
        if dest.exists():
            continue
        source = shutil.which(name)
        if source is None:
            continue
        if os.path.realpath(source) == os.path.realpath(dest):
            continue
        os.symlink(source, dest)


def _private_env(stub_dir: Path, **extra: str) -> dict[str, str]:
    """Environment whose PATH is only the stub directory."""
    _link_safe_tools(stub_dir)
    env = os.environ.copy()
    env["PATH"] = str(stub_dir)
    env["DESK_CHECK_HEALTH"] = "false"
    env["DESK_RELOAD_NGINX"] = "false"
    env["DESK_SERVICE_UNIT"] = "nonexistent-test-service.service"
    env.pop("DESK_GATEWAY_PID_FILE", None)
    env.pop("DESK_RELOAD_DRY_RUN", None)
    # Drop inherited overrides before extra. A runner that exported
    # SYSTEMCTL_BIN=/usr/bin/systemctl must not bypass the recorder.
    env.pop("SYSTEMCTL_BIN", None)
    env.pop("NGINX_BIN", None)
    env.update(extra)
    return env


def _recorder(stub_dir: Path, name: str, log_name: str, *, exit_code: int = 0, stdout: str = "") -> Path:
    log_path = stub_dir / log_name
    quoted_log = str(log_path).replace("'", "'\\''")
    quoted_out = stdout.replace("'", "'\\''")
    body = (
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{quoted_log}'\n"
        f"printf '%s\\n' '{quoted_out}'\n"
        f"exit {exit_code}\n"
    )
    return _write_executable(stub_dir / name, body)


def _read_log(stub_dir: Path, log_name: str) -> str:
    path = stub_dir / log_name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _unused_pid() -> int:
    """An allocated-range PID that is not a live process.

    Signal 0 does not deliver a signal; it only checks whether the PID exists.
    Linux will not allocate a PID above 4194303.
    """
    for candidate in range(4_194_303, 4_194_303 - 64, -1):
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            continue
    raise RuntimeError("could not find an unused pid for the recorder")


@pytest.fixture
def decoy_gateway(forbid_host_systemctl_and_nginx):
    """A live process whose command line contains desk-gateway.

    The fixture depends on the host-binary guard so the decoy is not started
    with a PATH that still resolves systemctl or nginx to the host.
    """
    del forbid_host_systemctl_and_nginx
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(180)", "desk-gateway"],
        start_new_session=True,
    )
    try:
        cmdline = ""
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.fail(f"decoy exited during setup with status {proc.returncode}")
            try:
                cmdline = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
            except FileNotFoundError:
                cmdline = ""
            if "desk-gateway" in cmdline:
                break
            time.sleep(0.02)
        else:
            pytest.fail(f"decoy command line did not contain desk-gateway: {cmdline!r}")
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_scripts_exist_and_executable():
    """Verify deployment and reload scripts exist and have the executable bit set."""
    assert DEPLOY_SCRIPT.exists()
    assert os.access(DEPLOY_SCRIPT, os.X_OK)
    assert RELOAD_SCRIPT.exists()
    assert os.access(RELOAD_SCRIPT, os.X_OK)


def test_deploy_staging_success_lifecycle(tmp_path):
    """REQ-STAGE-001: deployment sets the symlink and restarts only the stubbed unit."""
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Repo\n")
    (src_dir / "services/desk-gateway").mkdir(parents=True)
    (src_dir / "services/desk-gateway/main.py").write_text("# main app\n")

    releases_root = tmp_path / "releases"
    current_link = tmp_path / "current_symlink"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    systemctl = _recorder(stub_dir, "systemctl", "systemctl.log")

    env = _private_env(
        stub_dir,
        DESK_RELEASES_ROOT=str(releases_root),
        DESK_CURRENT_LINK=str(current_link),
        SYSTEMCTL_BIN=str(systemctl),
    )

    proc1 = _run(DEPLOY_SCRIPT, env, str(src_dir), "rel-001")
    assert proc1.returncode == 0, f"Deploy failed: {proc1.stderr}"
    assert current_link.is_symlink()
    assert current_link.resolve() == (releases_root / "rel-001").resolve()
    assert (current_link / "README.md").exists()

    (src_dir / "version.txt").write_text("v2")
    proc2 = _run(DEPLOY_SCRIPT, env, str(src_dir), "rel-002")
    assert proc2.returncode == 0, proc2.stderr
    assert current_link.resolve() == (releases_root / "rel-002").resolve()
    assert (current_link / "version.txt").read_text() == "v2"

    log = _read_log(stub_dir, "systemctl.log")
    assert "daemon-reload" in log
    assert "restart nonexistent-test-service.service" in log
    assert shutil.which("systemctl", path=env["PATH"]) == str(systemctl)


def test_deploy_staging_automated_rollback_on_failure(tmp_path):
    """REQ-STAGE-001: rollback restarts the stubbed unit, not a host unit."""
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Working Release\n")

    releases_root = tmp_path / "releases"
    current_link = tmp_path / "current_symlink"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    systemctl = _recorder(stub_dir, "systemctl", "systemctl.log")

    env = _private_env(
        stub_dir,
        DESK_RELEASES_ROOT=str(releases_root),
        DESK_CURRENT_LINK=str(current_link),
        SYSTEMCTL_BIN=str(systemctl),
    )

    proc_init = _run(DEPLOY_SCRIPT, env, str(src_dir), "rel-good")
    assert proc_init.returncode == 0, proc_init.stderr
    assert current_link.resolve() == (releases_root / "rel-good").resolve()
    log_after_init = _read_log(stub_dir, "systemctl.log")

    ci_gates = src_dir / "ci/gates"
    ci_gates.mkdir(parents=True)
    failing_gate = ci_gates / "check_ownership.py"
    failing_gate.write_text("import sys; sys.exit(1)\n")

    proc_fail = _run(DEPLOY_SCRIPT, env, str(src_dir), "rel-broken")
    assert proc_fail.returncode != 0
    assert "Initiating automated rollback" in proc_fail.stderr

    assert current_link.is_symlink()
    assert current_link.resolve() == (releases_root / "rel-good").resolve()
    assert not (releases_root / "rel-broken").exists()

    rollback_log = _read_log(stub_dir, "systemctl.log")[len(log_after_init):]
    assert "is-active" in rollback_log
    assert "restart nonexistent-test-service.service" in rollback_log
    assert shutil.which("systemctl", path=env["PATH"]) == str(systemctl)


def test_reload_does_not_signal_decoy_desk_gateway(tmp_path, decoy_gateway):
    """A live desk-gateway command line is not signalled, and nginx is not run.

    systemctl is present but reports the unit inactive, which is the branch
    that used to SIGHUP the first pgrep -f desk-gateway match.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    systemctl_log = stub_dir / "systemctl.log"
    _write_executable(
        stub_dir / "systemctl",
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{systemctl_log}'\n"
        "case \"$1\" in\n"
        "  is-active) exit 1 ;;\n"
        "esac\n"
        "exit 0\n",
    )
    _recorder(stub_dir, "nginx", "nginx.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    _recorder(stub_dir, "kill", "kill.log")

    env = _private_env(stub_dir)
    proc = _run(RELOAD_SCRIPT, env)

    assert decoy_gateway.poll() is None, (
        f"decoy pid {decoy_gateway.pid} was signalled\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    kill_log = _read_log(stub_dir, "kill.log")
    assert str(decoy_gateway.pid) not in kill_log, kill_log
    assert _read_log(stub_dir, "nginx.log") == ""
    assert proc.returncode == 0, proc.stderr


def test_reload_script_has_no_process_pattern_match():
    """The reload script does not search the process table."""
    text = RELOAD_SCRIPT.read_text(encoding="utf-8")
    for pattern in ("pgrep", "pkill", "killall"):
        assert pattern not in text


@pytest.mark.parametrize("dry_run", [False, True], ids=["real-run", "dry-run"])
def test_reload_nginx_gateway_execution(tmp_path, decoy_gateway, dry_run):
    """REQ-STAGE-002: stubbed real run records unit and nginx commands; dry-run records none."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    exit_code = 99 if dry_run else 0
    systemctl = _recorder(stub_dir, "systemctl", "systemctl.log", exit_code=exit_code)
    nginx = _recorder(stub_dir, "nginx", "nginx.log", exit_code=exit_code)
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid), exit_code=exit_code)
    _recorder(stub_dir, "kill", "kill.log", exit_code=exit_code)

    env = _private_env(
        stub_dir,
        DESK_RELOAD_NGINX="true",
        NGINX_BIN=str(nginx),
        SYSTEMCTL_BIN=str(systemctl),
        DESK_RELOAD_DRY_RUN="1" if dry_run else "0",
    )
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    assert decoy_gateway.poll() is None
    assert str(decoy_gateway.pid) not in _read_log(stub_dir, "kill.log")
    assert "Zero-downtime hot reload completed successfully" in proc.stdout

    if dry_run:
        assert "DRY-RUN:" in proc.stdout
        assert "reload-or-restart" in proc.stdout
        assert "-t" in proc.stdout
        assert _read_log(stub_dir, "systemctl.log") == ""
        assert _read_log(stub_dir, "nginx.log") == ""
        assert _read_log(stub_dir, "pgrep.log") == ""
        assert _read_log(stub_dir, "kill.log") == ""
    else:
        systemctl_log = _read_log(stub_dir, "systemctl.log")
        assert "reload-or-restart nonexistent-test-service.service" in systemctl_log
        assert "reload nginx" in systemctl_log
        assert "-t" in _read_log(stub_dir, "nginx.log")
        assert _read_log(stub_dir, "pgrep.log") == ""


def test_reload_fails_closed_without_unit_or_pid_file(tmp_path, decoy_gateway):
    """No systemctl and no PID file is an error, and the decoy stays up."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "nginx", "nginx.log")

    env = _private_env(stub_dir)
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert "DESK_GATEWAY_PID_FILE" in proc.stderr
    assert "pattern" in proc.stderr
    assert decoy_gateway.poll() is None
    assert str(decoy_gateway.pid) not in _read_log(stub_dir, "kill.log")
    assert _read_log(stub_dir, "nginx.log") == ""


def test_reload_signals_only_explicit_pid_file(tmp_path, decoy_gateway):
    """Without systemctl, SIGHUP goes to the PID file and not to the decoy."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    _recorder(stub_dir, "kill", "kill.log")
    target = _unused_pid()
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text(f"{target}\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    kill_log = _read_log(stub_dir, "kill.log")
    assert f"-HUP {target}" in kill_log
    assert str(decoy_gateway.pid) not in kill_log
    assert decoy_gateway.poll() is None
    assert _read_log(stub_dir, "pgrep.log") == ""


def test_reload_rejects_missing_pid_file(tmp_path, decoy_gateway):
    """A PID file path that does not exist fails before any signal."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    missing = tmp_path / "missing.pid"

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(missing))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert "DESK_GATEWAY_PID_FILE" in proc.stderr
    assert _read_log(stub_dir, "kill.log") == ""
    assert decoy_gateway.poll() is None


def test_reload_rejects_non_numeric_pid_file(tmp_path, decoy_gateway):
    """A PID file that is not a single integer fails before any signal."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text("not-a-pid\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert "numeric" in proc.stderr
    assert _read_log(stub_dir, "kill.log") == ""
    assert decoy_gateway.poll() is None


def test_reload_systemctl_targets_unit_not_pid_file(tmp_path, decoy_gateway):
    """When systemctl is on PATH the unit is reloaded and the PID file is ignored."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "systemctl", "systemctl.log")
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text(f"{_unused_pid()}\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    assert "reload-or-restart nonexistent-test-service.service" in _read_log(stub_dir, "systemctl.log")
    assert _read_log(stub_dir, "kill.log") == ""
    assert _read_log(stub_dir, "pgrep.log") == ""
    assert decoy_gateway.poll() is None


def test_nginx_bin_is_configurable(tmp_path):
    """NGINX_BIN selects the nginx executable the opt-in reload validates."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "systemctl", "systemctl.log")
    _recorder(stub_dir, "nginx", "nginx.log")
    custom = tmp_path / "custom-nginx"
    custom_log = tmp_path / "custom-nginx.log"
    _write_executable(
        custom,
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{custom_log}'\n"
        "exit 0\n",
    )

    env = _private_env(
        stub_dir,
        DESK_RELOAD_NGINX="1",
        NGINX_BIN=str(custom),
    )
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    assert "-t" in custom_log.read_text(encoding="utf-8")
    assert _read_log(stub_dir, "nginx.log") == ""


def test_guard_rejects_env_that_resolves_host_binary(tmp_path):
    """The conftest predicate fails an environment that resolves a host service binary."""
    import conftest
    from _pytest.outcomes import Failed

    host_bin = tmp_path / "host" / "systemctl"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\nexit 0\n")
    with pytest.raises(Failed, match="systemctl"):
        conftest.reject_host_service_bins(
            ["echo", "untouched"],
            {"PATH": str(host_bin.parent)},
            host={"systemctl": str(host_bin), "nginx": None},
        )


def test_guard_allows_stub_ahead_of_host_binary(tmp_path):
    """A recorder earlier on PATH is not treated as the host binary."""
    import conftest

    host_bin = tmp_path / "host" / "nginx"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\nexit 0\n")
    stub = tmp_path / "stub" / "nginx"
    stub.parent.mkdir()
    _write_executable(stub, "#!/bin/sh\nexit 0\n")
    conftest.reject_host_service_bins(
        ["echo", "untouched"],
        {"PATH": f"{stub.parent}{os.pathsep}{host_bin.parent}"},
        host={"systemctl": None, "nginx": str(host_bin)},
    )


def test_private_env_drops_inherited_service_bins(tmp_path, monkeypatch):
    """A host SYSTEMCTL_BIN or NGINX_BIN from the runner does not survive into the test env."""
    monkeypatch.setenv("SYSTEMCTL_BIN", "/usr/bin/systemctl")
    monkeypatch.setenv("NGINX_BIN", "/usr/sbin/nginx")
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    env = _private_env(stub_dir)
    assert "SYSTEMCTL_BIN" not in env
    assert "NGINX_BIN" not in env
    chosen = stub_dir / "systemctl"
    _write_executable(chosen, "#!/bin/sh\nexit 0\n")
    overridden = _private_env(stub_dir, SYSTEMCTL_BIN=str(chosen))
    assert overridden["SYSTEMCTL_BIN"] == str(chosen)


@pytest.mark.parametrize("contents", ["0", "0\n", "00\n"])
def test_reload_rejects_zero_pid(tmp_path, decoy_gateway, contents):
    """PID 0 is rejected. kill -HUP 0 would signal the process group."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text(contents, encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert "positive" in proc.stderr
    assert _read_log(stub_dir, "kill.log") == ""
    assert decoy_gateway.poll() is None


def test_reload_accepts_pid_file_without_trailing_newline(tmp_path, decoy_gateway):
    """A single positive PID with no trailing newline is the signal target."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    target = _unused_pid()
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_bytes(str(target).encode("ascii"))

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    assert f"-HUP {target}" in _read_log(stub_dir, "kill.log")
    assert str(decoy_gateway.pid) not in _read_log(stub_dir, "kill.log")
    assert decoy_gateway.poll() is None


def test_reload_normalizes_zero_padded_pid(tmp_path):
    """A zero-padded PID is signalled in base 10, not left for kill to parse."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text("010\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    kill_log = _read_log(stub_dir, "kill.log")
    assert "-HUP 10" in kill_log
    assert "-HUP 010" not in kill_log


@pytest.mark.parametrize(
    "contents",
    [
        "18446744073709551616\n",
        "18446744073709551626\n",
        "4194304\n",
        "0004194304\n",
    ],
)
def test_reload_rejects_pid_outside_supported_range(tmp_path, decoy_gateway, contents):
    """A PID that bash arithmetic would wrap, or that Linux will not allocate, is not signalled."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    _recorder(stub_dir, "pgrep", "pgrep.log", stdout=str(decoy_gateway.pid))
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text(contents, encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert "range" in proc.stderr
    assert _read_log(stub_dir, "kill.log") == ""
    assert decoy_gateway.poll() is None


def test_reload_accepts_highest_linux_pid(tmp_path):
    """4194303 is the highest PID Linux allocates when pid_max is 2^22."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text("4194303\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode == 0, proc.stderr
    assert "-HUP 4194303" in _read_log(stub_dir, "kill.log")


def test_reload_rejects_pid_file_with_several_lines(tmp_path, decoy_gateway):
    """A file with more than one PID line is not a single target."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    _recorder(stub_dir, "kill", "kill.log")
    target = _unused_pid()
    pid_file = tmp_path / "gateway.pid"
    pid_file.write_text(f"{target}\n{target}\n", encoding="utf-8")

    env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
    proc = _run(RELOAD_SCRIPT, env)

    assert proc.returncode != 0
    assert _read_log(stub_dir, "kill.log") == ""
    assert decoy_gateway.poll() is None


def test_deploy_rejects_missing_systemctl_bin_before_cutover(tmp_path):
    """An explicit missing SYSTEMCTL_BIN fails before the release symlink moves."""
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Repo\n")
    releases_root = tmp_path / "releases"
    current_link = tmp_path / "current_symlink"
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()

    env = _private_env(
        stub_dir,
        DESK_RELEASES_ROOT=str(releases_root),
        DESK_CURRENT_LINK=str(current_link),
        SYSTEMCTL_BIN=str(tmp_path / "missing-systemctl"),
    )
    proc = _run(DEPLOY_SCRIPT, env, str(src_dir), "rel-bad")

    assert proc.returncode != 0
    assert "SYSTEMCTL_BIN" in proc.stderr
    assert not current_link.exists()
    assert not (releases_root / "rel-bad").exists()


def test_guard_rejects_env_without_path(tmp_path, monkeypatch):
    """Omitting PATH searches Python's default path, independent of where the host keeps systemctl."""
    import conftest
    from _pytest.outcomes import Failed

    bin_dir = tmp_path / "default-search"
    bin_dir.mkdir()
    systemctl = bin_dir / "systemctl"
    _write_executable(systemctl, "#!/bin/sh\necho guard-regression >&2\nexit 99\n")
    host = {"systemctl": str(systemctl), "nginx": None}
    monkeypatch.setattr(conftest, "HOST_SERVICE_BINS", host)
    real_get_exec_path = os.get_exec_path

    def controlled_exec_path(env=None):
        # get_exec_path prefers confstr("CS_PATH") over os.defpath. Pin the
        # omitted-PATH case to this temporary directory either way.
        if env is not None and "PATH" not in env:
            return [str(bin_dir)]
        return real_get_exec_path(env)

    monkeypatch.setattr(os, "get_exec_path", controlled_exec_path)

    with pytest.raises(Failed, match="systemctl"):
        conftest.reject_host_service_bins(["echo", "untouched"], {})
    with pytest.raises(Failed, match="systemctl"):
        subprocess.run(
            ["systemctl", "is-active", "nonexistent-test-service.service"],
            env={"HOME": "/tmp"},
            check=False,
        )


def test_guard_rejects_selected_host_binary(tmp_path):
    """SYSTEMCTL_BIN is checked even when PATH itself points at a recorder."""
    import conftest
    from _pytest.outcomes import Failed

    host_bin = tmp_path / "host" / "systemctl"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\nexit 0\n")
    stub = tmp_path / "stub" / "systemctl"
    stub.parent.mkdir()
    _write_executable(stub, "#!/bin/sh\nexit 0\n")
    with pytest.raises(Failed, match="SYSTEMCTL_BIN"):
        conftest.reject_host_service_bins(
            ["echo", "untouched"],
            {"PATH": str(stub.parent), "SYSTEMCTL_BIN": str(host_bin)},
            host={"systemctl": str(host_bin), "nginx": None},
        )


def test_discover_finds_nginx_outside_path(tmp_path, monkeypatch):
    """A host nginx under sbin is recorded even when that directory is not on PATH."""
    import conftest
    from _pytest.outcomes import Failed

    sbin = tmp_path / "sbin"
    sbin.mkdir()
    nginx = sbin / "nginx"
    _write_executable(nginx, "#!/bin/sh\necho guard-regression >&2\nexit 99\n")
    monkeypatch.setattr(conftest, "_STANDARD_BIN_DIRS", (str(sbin),))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    found = conftest.discover_host_service_bins()
    assert os.path.realpath(nginx) in found["nginx"]

    stub = tmp_path / "stub"
    stub.mkdir()
    _write_executable(stub / "nginx", "#!/bin/sh\nexit 0\n")
    with pytest.raises(Failed, match="NGINX_BIN"):
        conftest.reject_host_service_bins(
            ["echo", "untouched"],
            {"PATH": str(stub), "NGINX_BIN": str(nginx)},
            host=found,
        )


def test_guard_rejects_pathlike_host_binary(tmp_path, monkeypatch):
    """subprocess accepts pathlib.Path; that form is still a host binary."""
    import conftest
    from _pytest.outcomes import Failed

    host_bin = tmp_path / "host" / "systemctl"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\necho guard-regression >&2\nexit 99\n")
    monkeypatch.setattr(
        conftest,
        "HOST_SERVICE_BINS",
        {"systemctl": (str(host_bin),), "nginx": ()},
    )
    with pytest.raises(Failed, match="systemctl"):
        subprocess.run(
            [Path(host_bin), "restart", "desk-gateway.service"],
            check=False,
        )


def test_guard_rejects_executable_override(tmp_path, monkeypatch):
    """Popen runs `executable`, not the argv name that PATH would resolve."""
    import conftest
    from _pytest.outcomes import Failed

    host_bin = tmp_path / "host" / "systemctl"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\necho guard-regression >&2\nexit 99\n")
    monkeypatch.setattr(
        conftest,
        "HOST_SERVICE_BINS",
        {"systemctl": (str(host_bin),), "nginx": ()},
    )
    with pytest.raises(Failed, match="executable"):
        subprocess.run(
            ["systemctl", "restart", "desk-gateway.service"],
            executable=str(host_bin),
            check=False,
        )


def test_guard_rejects_bytes_systemctl_bin(tmp_path, monkeypatch):
    """A bytes-keyed environment can still name the host systemctl."""
    import conftest
    from _pytest.outcomes import Failed

    host_bin = tmp_path / "host" / "systemctl"
    host_bin.parent.mkdir()
    _write_executable(host_bin, "#!/bin/sh\necho guard-regression >&2\nexit 99\n")
    stub = tmp_path / "stub"
    stub.mkdir()
    _write_executable(stub / "systemctl", "#!/bin/sh\nexit 0\n")
    monkeypatch.setattr(
        conftest,
        "HOST_SERVICE_BINS",
        {"systemctl": (str(host_bin),), "nginx": ()},
    )
    env = {
        b"PATH": os.fsencode(str(stub)),
        b"SYSTEMCTL_BIN": os.fsencode(str(host_bin)),
    }
    with pytest.raises(Failed, match="SYSTEMCTL_BIN"):
        subprocess.run(
            [str(RELOAD_SCRIPT)],
            env=env,
            check=False,
        )


def test_reload_pid_file_keeps_builtin_kill_without_external(tmp_path, decoy_gateway):
    """No external kill leaves Bash's builtin, which signals a child this test owns.

    The child catches SIGHUP and stays up. An unused PID is not a safe target:
    another process can claim it before kill runs.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    marker = tmp_path / "sighup-received"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal, pathlib, time, sys\n"
                "marker = pathlib.Path(sys.argv[1])\n"
                "def on_hup(_signum, _frame):\n"
                "    marker.write_text('hup')\n"
                "signal.signal(signal.SIGHUP, on_hup)\n"
                "marker.write_text('ready')\n"
                "time.sleep(30)\n"
            ),
            str(marker),
        ],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if child.poll() is not None:
                pytest.fail(f"signal target exited during setup with status {child.returncode}")
            if marker.is_file() and marker.read_text(encoding="utf-8") == "ready":
                break
            time.sleep(0.02)
        else:
            pytest.fail("signal target did not become ready")

        pid_file = tmp_path / "gateway.pid"
        pid_file.write_text(f"{child.pid}\n", encoding="utf-8")
        env = _private_env(stub_dir, DESK_GATEWAY_PID_FILE=str(pid_file))
        proc = _run(RELOAD_SCRIPT, env)

        assert proc.returncode == 0, proc.stderr
        assert "command not found" not in proc.stderr
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and marker.read_text(encoding="utf-8") != "hup":
            time.sleep(0.02)
        assert marker.read_text(encoding="utf-8") == "hup"
        assert child.poll() is None
        assert decoy_gateway.poll() is None
        assert child.pid != decoy_gateway.pid
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
