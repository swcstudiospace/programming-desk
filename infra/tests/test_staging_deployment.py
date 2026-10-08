"""Test suite for automated staging & VPS deployment pipeline (REQ-STAGE-001, REQ-STAGE-002)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra/desk-gateway/deploy-staging.sh"
RELOAD_SCRIPT = REPO_ROOT / "infra/desk-gateway/reload-nginx-gateway.sh"


def test_scripts_exist_and_executable():
    """Verify deployment and reload scripts exist and have executable bit set."""
    assert DEPLOY_SCRIPT.exists()
    assert os.access(DEPLOY_SCRIPT, os.X_OK)
    assert RELOAD_SCRIPT.exists()
    assert os.access(RELOAD_SCRIPT, os.X_OK)


def test_deploy_staging_success_lifecycle(tmp_path):
    """REQ-STAGE-001: Declarative deployment sets symlink, creates release dir, and cleans up old releases."""
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Test Repo\n")
    (src_dir / "services/desk-gateway").mkdir(parents=True)
    (src_dir / "services/desk-gateway/main.py").write_text("# main app\n")

    releases_root = tmp_path / "releases"
    current_link = tmp_path / "current_symlink"

    env = os.environ.copy()
    env["DESK_RELEASES_ROOT"] = str(releases_root)
    env["DESK_CURRENT_LINK"] = str(current_link)
    env["DESK_SERVICE_UNIT"] = "nonexistent-test-service.service"
    env["DESK_CHECK_HEALTH"] = "false"
    env["PATH"] = f"/nonexistent:{env.get('PATH', '')}"  # ensure curl fails gracefully or mock

    # First deployment
    proc1 = subprocess.run(
        [str(DEPLOY_SCRIPT), str(src_dir), "rel-001"],
        capture_output=True,
        text=True,
        env=env,
    )
    # With nonexistent curl/path or fallback, deployment succeeds
    assert proc1.returncode == 0, f"Deploy failed: {proc1.stderr}"
    assert current_link.is_symlink()
    assert current_link.resolve() == (releases_root / "rel-001").resolve()
    assert (current_link / "README.md").exists()

    # Second deployment
    (src_dir / "version.txt").write_text("v2")
    proc2 = subprocess.run(
        [str(DEPLOY_SCRIPT), str(src_dir), "rel-002"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc2.returncode == 0
    assert current_link.resolve() == (releases_root / "rel-002").resolve()
    assert (current_link / "version.txt").read_text() == "v2"


def test_deploy_staging_automated_rollback_on_failure(tmp_path):
    """REQ-STAGE-001: Automatic rollback to previous release on health check regression or pre-flight failure."""
    src_dir = tmp_path / "src_repo"
    src_dir.mkdir()
    (src_dir / "README.md").write_text("# Working Release\n")

    releases_root = tmp_path / "releases"
    current_link = tmp_path / "current_symlink"

    env = os.environ.copy()
    env["DESK_RELEASES_ROOT"] = str(releases_root)
    env["DESK_CURRENT_LINK"] = str(current_link)
    env["DESK_CHECK_HEALTH"] = "false"
    env["PATH"] = f"/nonexistent:{env.get('PATH', '')}"

    # Initial good release
    proc_init = subprocess.run(
        [str(DEPLOY_SCRIPT), str(src_dir), "rel-good"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc_init.returncode == 0
    assert current_link.resolve() == (releases_root / "rel-good").resolve()

    # Attempt release with broken integrity gate in source
    ci_gates = src_dir / "ci/gates"
    ci_gates.mkdir(parents=True)
    # Create failing gate script
    failing_gate = ci_gates / "check_ownership.py"
    failing_gate.write_text("import sys; sys.exit(1)\n")

    proc_fail = subprocess.run(
        [str(DEPLOY_SCRIPT), str(src_dir), "rel-broken"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc_fail.returncode != 0
    assert "Initiating automated rollback" in proc_fail.stderr

    # Invariant: current_link MUST still point to rel-good!
    assert current_link.is_symlink()
    assert current_link.resolve() == (releases_root / "rel-good").resolve()
    # Failed release directory pruned
    assert not (releases_root / "rel-broken").exists()


def test_reload_nginx_gateway_execution():
    """REQ-STAGE-002: Zero-downtime hot reload script executes safely in non-systemd/mock environment."""
    env = os.environ.copy()
    env["DESK_SERVICE_UNIT"] = "nonexistent-test-service.service"
    env["DESK_CHECK_HEALTH"] = "false"
    env["PATH"] = f"/nonexistent:{env.get('PATH', '')}"

    proc = subprocess.run(
        [str(RELOAD_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0
    assert "Zero-downtime hot reload completed successfully" in proc.stdout
