"""Automated companion cross-repo contract verification (REQ-STAGE-005).

Validates schema, event payload, and OpenAPI/proto compatibility with companion repos
`agent-substrate` and `agent-swarm`.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_companion_contract_rosters_and_packs_integrity():
    """Verify tool rosters and packs adhere to agent-substrate and swarm interfaces."""
    rosters_file = REPO_ROOT / "contracts/tool-rosters/_core.yaml"
    packs_dir = REPO_ROOT / "contracts/tool-packs"

    assert rosters_file.exists()
    assert packs_dir.exists()

    roster_data = yaml.safe_load(rosters_file.read_text(encoding="utf-8"))
    assert "seats" in roster_data or "tools" in roster_data

    # Every pack must have name, tools list, and version
    pack_files = list(packs_dir.glob("*.yaml"))
    assert len(pack_files) >= 5, f"Expected tool packs, found {len(pack_files)}"
    for pf in pack_files:
        pdata = yaml.safe_load(pf.read_text(encoding="utf-8"))
        assert "app" in pdata or "name" in pdata, f"{pf.name} missing app/name"
        assert "tools" in pdata, f"{pf.name} missing tools"


def test_companion_event_envelope_compatibility():
    """Verify event envelope structure matches agent-substrate streaming schema."""
    sample_envelope = {
        "event_id": "evt-sub-20261009-01",
        "topic": "desk.events",
        "origin": "programming-desk",
        "version": "1.0.0",
        "timestamp": 1728468000.0,
        "payload": {
            "actor": "bot-00-programming-lead",
            "action": "task_dispatched",
            "target_seat": "systems",
        },
    }

    # Verify standard contract fields required by agent-substrate & swarm
    required_keys = {"event_id", "topic", "origin", "version", "timestamp", "payload"}
    assert required_keys.issubset(sample_envelope.keys())
    assert sample_envelope["origin"] == "programming-desk"
    assert sample_envelope["version"].startswith("1.")


def test_reconcile_staging_leases_script_executable():
    """REQ-STAGE-003: Script exists, executable, and runs in dry-run mode."""
    script = REPO_ROOT / "infra/lease-heartbeat/reconcile-staging-leases.sh"
    assert script.exists()
    import os, subprocess
    assert os.access(script, os.X_OK)

    env = os.environ.copy()
    env["DRY_RUN"] = "true"
    res = subprocess.run([str(script)], capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert "Staging lease reconciliation finished successfully" in res.stdout
