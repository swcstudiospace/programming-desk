"""SPE-12501: lease-heartbeat installer, env mode, and unit verification."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HEARTBEAT = REPO_ROOT / "infra" / "lease-heartbeat"
INSTALL = HEARTBEAT / "install.sh"
VERIFY = HEARTBEAT / "verify-units.sh"
EXAMPLE = HEARTBEAT / "heartbeat.env.example"

REQUIRED = (
    "LEASE_SEAT",
    "LEASE_HOLDER_ID",
    "LEASE_ENDPOINT_URL",
    "LEASE_ENDPOINT_TOKEN",
    "LEASE_TTL_S",
    "LEASE_INTERVAL_S",
    "LEASE_JITTER_S",
    "LEASE_TIMEOUT_S",
    "LEASE_MAX_MISSED",
    "LEASE_STATE_DIR",
    "LEASE_HELD_FILE",
    "LEASE_LOG_LEVEL",
    "LEASE_LOG_BYTES",
)

# Placeholder-shaped on purpose so the secrets gate treats it as a fixture, not a credential.
TOKEN = "test_lease_token_value"

UNITS = (
    "desk-lease-heartbeat.service",
    "desk-lease-heartbeat.timer",
    "substrate-lease-reap.service",
    "substrate-lease-reap.timer",
)


def env_text(values: dict[str, str] | None = None, *, omit: str | None = None) -> str:
    chosen = values or {}
    lines = []
    for name in REQUIRED:
        if name == omit:
            continue
        lines.append(f"{name}={chosen.get(name, '')}")
    return "\n".join(lines) + "\n"


def run_install(sysroot: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL), "--sysroot", str(sysroot), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def seed_env(sysroot: Path, text: str, mode: int = 0o644) -> Path:
    path = sysroot / "etc" / "desk-lease-heartbeat" / "heartbeat.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def assert_token_hidden(proc: subprocess.CompletedProcess[str]) -> None:
    assert TOKEN not in proc.stdout
    assert TOKEN not in proc.stderr


def test_example_is_blank_and_lists_the_thirteen_names():
    text = EXAMPLE.read_text(encoding="utf-8")
    present = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        assert value == "", f"{key} is not blank"
        present.add(key)
    assert present == set(REQUIRED)


def test_fresh_install_is_mode_0600_and_passes_default_timing(tmp_path: Path):
    sysroot = tmp_path / "root"
    proc = run_install(sysroot)
    assert proc.returncode == 0, proc.stderr
    env = sysroot / "etc" / "desk-lease-heartbeat" / "heartbeat.env"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE(env.parent.stat().st_mode) == 0o700
    assert env.read_text(encoding="utf-8") == EXAMPLE.read_text(encoding="utf-8")
    for name in UNITS:
        installed = sysroot / "etc" / "systemd" / "system" / name
        assert installed.read_text(encoding="utf-8") == (HEARTBEAT / name).read_text(encoding="utf-8")
    state = sysroot / "var" / "lib" / "desk-lease-heartbeat"
    assert state.is_dir()
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert "systemctl" not in proc.stdout
    assert "timers not enabled" in proc.stdout


def test_existing_env_is_not_overwritten_and_mode_becomes_0600(tmp_path: Path):
    sysroot = tmp_path / "root"
    original = env_text(
        {
            "LEASE_SEAT": "bot-05-infrastructure",
            "LEASE_HOLDER_ID": "host-a",
            "LEASE_ENDPOINT_TOKEN": TOKEN,
            "LEASE_TTL_S": "900",
            "LEASE_INTERVAL_S": "60",
            "LEASE_JITTER_S": "5",
            "LEASE_TIMEOUT_S": "10",
        }
    )
    path = seed_env(sysroot, original, mode=0o644)
    before = path.read_bytes()
    proc = run_install(sysroot)
    assert proc.returncode == 0, proc.stderr
    assert path.read_bytes() == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert_token_hidden(proc)
    again = run_install(sysroot)
    assert again.returncode == 0, again.stderr
    assert path.read_bytes() == before
    assert_token_hidden(again)


def test_secret_stays_out_of_output_when_timing_fails(tmp_path: Path):
    sysroot = tmp_path / "root"
    text = env_text(
        {
            "LEASE_ENDPOINT_TOKEN": TOKEN,
            "LEASE_TTL_S": "900",
            "LEASE_INTERVAL_S": "60",
            "LEASE_JITTER_S": "5",
            "LEASE_TIMEOUT_S": "60",
        }
    )
    path = seed_env(sysroot, text)
    before = path.read_bytes()
    proc = run_install(sysroot)
    assert proc.returncode != 0
    assert "LEASE_TIMEOUT_S must be < LEASE_INTERVAL_S" in proc.stderr
    assert "60" not in proc.stdout
    assert_token_hidden(proc)
    assert path.read_bytes() == before
    assert not (sysroot / "etc" / "systemd" / "system" / "desk-lease-heartbeat.service").exists()


def test_sum_above_ttl_third_fails_without_printing_the_token(tmp_path: Path):
    sysroot = tmp_path / "root"
    path = seed_env(
        sysroot,
        env_text(
            {
                "LEASE_ENDPOINT_TOKEN": TOKEN,
                "LEASE_TTL_S": "224",
                "LEASE_INTERVAL_S": "60",
                "LEASE_JITTER_S": "5",
                "LEASE_TIMEOUT_S": "10",
            }
        ),
    )
    before = path.read_bytes()
    proc = run_install(sysroot)
    assert proc.returncode != 0
    assert "LEASE_TTL_S / 3" in proc.stderr
    assert_token_hidden(proc)
    assert "224" not in proc.stdout
    assert "224" not in proc.stderr
    assert path.read_bytes() == before


def test_sum_equal_to_ttl_third_passes(tmp_path: Path):
    sysroot = tmp_path / "root"
    proc_root = seed_env(
        sysroot,
        env_text(
            {
                "LEASE_ENDPOINT_TOKEN": TOKEN,
                "LEASE_TTL_S": "225",
                "LEASE_INTERVAL_S": "60",
                "LEASE_JITTER_S": "5",
                "LEASE_TIMEOUT_S": "10",
            }
        ),
    )
    proc = run_install(sysroot)
    assert proc.returncode == 0, proc.stderr
    assert_token_hidden(proc)
    assert TOKEN in proc_root.read_text(encoding="utf-8")


def test_missing_name_fails_and_keeps_bytes(tmp_path: Path):
    sysroot = tmp_path / "root"
    path = seed_env(sysroot, env_text(omit="LEASE_HELD_FILE"))
    before = path.read_bytes()
    proc = run_install(sysroot)
    assert proc.returncode != 0
    assert "missing required variable LEASE_HELD_FILE" in proc.stderr
    assert path.read_bytes() == before


def test_non_integer_cadence_is_refused_without_echoing_it(tmp_path: Path):
    sysroot = tmp_path / "root"
    raw = "10seconds"
    path = seed_env(
        sysroot,
        env_text({"LEASE_TIMEOUT_S": raw, "LEASE_INTERVAL_S": "60", "LEASE_JITTER_S": "5", "LEASE_TTL_S": "900"}),
    )
    proc = run_install(sysroot)
    assert proc.returncode != 0
    assert "LEASE_TIMEOUT_S is not a canonical non-negative integer" in proc.stderr
    assert raw not in proc.stdout
    assert raw not in proc.stderr
    assert path.read_text(encoding="utf-8").count(raw) == 1


def test_interval_other_than_the_unit_literal_is_refused(tmp_path: Path):
    sysroot = tmp_path / "root"
    seed_env(
        sysroot,
        env_text(
            {
                "LEASE_TTL_S": "9000",
                "LEASE_INTERVAL_S": "120",
                "LEASE_JITTER_S": "5",
                "LEASE_TIMEOUT_S": "10",
            }
        ),
    )
    proc = run_install(sysroot)
    assert proc.returncode != 0
    assert "LEASE_INTERVAL_S does not match the shipped unit literal (60)" in proc.stderr
    assert "120" not in proc.stdout
    assert "120" not in proc.stderr


def test_enable_is_refused_for_a_scratch_sysroot(tmp_path: Path):
    sysroot = tmp_path / "root"
    proc = run_install(sysroot, "--enable")
    assert proc.returncode != 0
    assert "--enable is refused" in proc.stderr
    assert not (sysroot / "etc" / "desk-lease-heartbeat" / "heartbeat.env").exists()


def test_no_legacy_checkout_prefix_in_the_lease_heartbeat_tree():
    legacy = "/opt/" + "programming-desk"
    hits = []
    for path in HEARTBEAT.rglob("*"):
        if not path.is_file():
            continue
        if legacy in path.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == []


def test_shipped_unit_literals():
    service = (HEARTBEAT / "desk-lease-heartbeat.service").read_text(encoding="utf-8")
    timer = (HEARTBEAT / "desk-lease-heartbeat.timer").read_text(encoding="utf-8")
    reap_service = (HEARTBEAT / "substrate-lease-reap.service").read_text(encoding="utf-8")
    reap_timer = (HEARTBEAT / "substrate-lease-reap.timer").read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "Type=oneshot" in reap_service
    assert "WorkingDirectory=/opt/desk-gateway/programming-desk" in service
    assert "WorkingDirectory=/opt/desk-gateway/programming-desk" in reap_service
    assert (
        "ExecStart=/opt/desk-gateway/programming-desk/services/desk-lease-heartbeat/.venv/bin/desk-lease-heartbeat renew"
        in service
    )
    assert (
        "ExecStart=/opt/desk-gateway/programming-desk/infra/lease-heartbeat/substrate-lease-reap.sh"
        in reap_service
    )
    assert "OnUnitActiveSec=60" in timer
    assert "RandomizedDelaySec=5" in timer
    assert "TimeoutStartSec=10" in service
    assert "OnUnitActiveSec=45" in reap_timer
    assert "RandomizedDelaySec=5" in reap_timer


def test_systemd_analyze_verify_on_every_unit():
    if not shutil_which("systemd-analyze"):
        pytest.skip("systemd-analyze is not installed")
    proc = subprocess.run(
        ["bash", str(VERIFY)],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    for name in UNITS:
        assert name in proc.stdout
    assert "systemd-analyze verify" in proc.stdout


def shutil_which(name: str) -> str | None:
    return __import__("shutil").which(name)


def test_env_file_is_root_owned_inside_the_installer(tmp_path: Path):
    """chown root:root is visible as uid 0 to the installing process.

    A user namespace is how this runs without host root. From outside that
    namespace the mapped uid is the caller, so the stat has to happen inside.
    """
    sysroot = tmp_path / "root"
    if os.geteuid() == 0:
        proc = run_install(sysroot)
        assert proc.returncode == 0, proc.stderr
        env = sysroot / "etc" / "desk-lease-heartbeat" / "heartbeat.env"
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
        assert env.stat().st_uid == 0
        assert env.stat().st_gid == 0
        return
    unshare = shutil_which("unshare")
    if unshare is None:
        pytest.skip("unshare is required to observe root ownership without host root")
    script = """
set -euo pipefail
sysroot=$1
install=$2
bash "$install" --sysroot "$sysroot"
stat -c '%u %g %a' "$sysroot/etc/desk-lease-heartbeat/heartbeat.env"
stat -c '%u %g %a' "$sysroot/etc/desk-lease-heartbeat"
"""
    proc = subprocess.run(
        [unshare, "--user", "--map-root-user", "bash", "-c", script, "bash", str(sysroot), str(INSTALL)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line[:1].isdigit()]
    assert lines == ["0 0 600", "0 0 700"]
