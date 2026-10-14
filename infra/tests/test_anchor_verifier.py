"""Test suite for Solana devnet anchor verification and synthetic telemetry stress load (REQ-ALERT-004, REQ-ALERT-005)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "infra/telemetry/verify-anchor-proofs.sh"


def test_verify_anchor_proofs_script_executable():
    """Verify script exists and is executable."""
    assert VERIFY_SCRIPT.exists()
    assert os.access(VERIFY_SCRIPT, os.X_OK)


def test_verify_anchor_proofs_dry_run(tmp_path):
    """REQ-ALERT-004: Dry run generates verified JSON report with Merkle tree and Solana tx confirmation."""
    report_dir = tmp_path / "reports"
    env = os.environ.copy()
    env["REPORT_OUTPUT_DIR"] = str(report_dir)
    env["DRY_RUN"] = "true"

    proc = subprocess.run(
        [str(VERIFY_SCRIPT), "--batch-id", "batch-test-001"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"Script failed: {proc.stderr}"
    assert "Overall valid: True" in proc.stdout

    # Inspect generated JSON report
    report_files = list(report_dir.glob("anchor-verification-*.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text(encoding="utf-8"))

    assert report["dry_run"] is True
    assert report["all_verified"] is True
    assert report["batches_checked"] >= 1
    batch = report["results"][0]
    assert batch["batch_id"] == "batch-test-001"
    assert batch["merkle_valid"] is True
    assert batch["tx_confirmed"] is True
    assert batch["verified"] is True


def test_verify_anchor_proofs_detects_corrupted_merkle_or_tx(tmp_path):
    """REQ-ALERT-004: Fails closed when Merkle root is tampered or Solana transaction is unconfirmed."""
    report_dir = tmp_path / "reports"
    env = os.environ.copy()
    env["REPORT_OUTPUT_DIR"] = str(report_dir)
    env["DRY_RUN"] = "true"

    # Mock corrupted batch: tampered merkle root and invalid tx
    mock_bad_anchors = [
        {
            "batch_id": "batch-corrupt-001",
            "hour_epoch": 492010,
            "event_count": 2,
            "merkle_root": "0000000000000000000000000000000000000000000000000000000000000000",
            "leaves": ["leaf_one", "leaf_two"],
            "solana_tx": "INVALID_TX_SIGNATURE",
            "status": "anchored",
        }
    ]
    env["MOCK_ANCHORS"] = json.dumps(mock_bad_anchors)

    proc = subprocess.run(
        [str(VERIFY_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 1
    assert "Overall valid: False" in proc.stdout

    report_files = list(report_dir.glob("anchor-verification-*.json"))
    report = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert report["all_verified"] is False
    res = report["results"][0]
    assert res["merkle_valid"] is False
    assert res["tx_confirmed"] is False
    assert res["verified"] is False


def _unit_directives(path: Path) -> dict[str, str]:
    """Last assignment wins. Comments and section headers are ignored."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_anchor_proof_systemd_units_match_hourly_oneshot_contract():
    """SPE-12502: the timer is an hourly calendar unit and the service is oneshot."""
    service = _unit_directives(REPO_ROOT / "infra/telemetry/verify-anchor-proofs.service")
    timer = _unit_directives(REPO_ROOT / "infra/telemetry/verify-anchor-proofs.timer")

    assert service["Type"] == "oneshot"
    assert service["User"] == "root"
    assert service["WorkingDirectory"] == "/opt/programming-desk"
    assert service["EnvironmentFile"] == "-/etc/desk-anchor-proofs/anchor.env"
    assert service["ExecStart"].endswith("/infra/telemetry/verify-anchor-proofs.sh")
    assert service["NoNewPrivileges"] == "true"
    assert service["PrivateTmp"] == "true"
    assert service["ProtectSystem"] == "strict"
    assert service["ProtectHome"] == "true"
    assert service["StateDirectory"] == "desk-anchor-proofs"
    assert "REPORT_OUTPUT_DIR=/var/lib/desk-anchor-proofs" in service["Environment"]

    assert timer["OnCalendar"] == "hourly"
    assert timer["Persistent"] == "true"
    assert timer["Unit"] == "verify-anchor-proofs.service"
    delay = int(timer["RandomizedDelaySec"])
    assert 1 <= delay <= 300


def test_anchor_proof_units_pass_systemd_analyze_verify():
    """SPE-12502: unit syntax is clean once ExecStart points at a real checkout.

    The committed paths use /opt/programming-desk, which is the VPS checkout and
    is absent on a dev machine. systemd-analyze then exits 1 for that missing
    binary alone. This rewrites those prefixes to the repo root and verifies
    the copies. It does not install or enable either unit.
    """
    analyze = shutil.which("systemd-analyze")
    if analyze is None:
        pytest.skip("systemd-analyze is not installed")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("verify-anchor-proofs.service", "verify-anchor-proofs.timer"):
            source = (REPO_ROOT / "infra/telemetry" / name).read_text(encoding="utf-8")
            rewritten = source.replace("/opt/programming-desk", str(REPO_ROOT))
            (root / name).write_text(rewritten, encoding="utf-8")
        proc = subprocess.run(
            [
                analyze,
                "verify",
                str(root / "verify-anchor-proofs.service"),
                str(root / "verify-anchor-proofs.timer"),
            ],
            capture_output=True,
            text=True,
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_synthetic_stress_telemetry_audit_suite():
    """REQ-ALERT-005: End-to-end telemetry audit validating metrics, traceparent propagation, and SLO alert triggers."""
    gateway_dir = REPO_ROOT / "services/desk-gateway"
    # Execute full alert & telemetry test suite in the services/desk-gateway environment
    test_file = gateway_dir / "tests/test_alerts.py"
    assert test_file.exists()

    proc = subprocess.run(
        ["uv", "run", "pytest", str(test_file), "-v"],
        cwd=str(gateway_dir),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Gateway telemetry test failed:\n{proc.stdout}\n{proc.stderr}"
    assert "passed" in proc.stdout
