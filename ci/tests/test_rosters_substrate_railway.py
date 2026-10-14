"""Rosters for agent-substrate #59, #60 and #62 stay inside the gateway.

The change cites 91487e7, 9231f43 and 1e5e719. It must not add a tool, an input,
or a backend the gateway does not already implement. Follow-ups live on the
change document.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
GATES = REPO / "ci" / "gates"

CORE_TOOLS = {
    "desk_brief": {"graph_id", "task_id", "refresh"},
    "desk_docs_search": {"query", "repo", "limit"},
    "desk_memory_retain": {"content", "receipt_path", "source", "graph_id", "task_id", "tags"},
    "desk_memory_recall": {"query", "limit", "include_shared"},
    "desk_ownership_resolve": {"paths"},
    "desk_receipt_check": {"bot", "receipt", "receipt_path", "strict"},
    "desk_event_emit": {"kind", "graph_id", "task_id", "payload"},
    "desk_doctor": {"action", "agent_uuid", "channel_id", "prompt_sha256", "installed_skills"},
}

INFRA_TOOLS = {
    "desk_railway_status": {"project"},
    "desk_railway_logs": {"project", "service", "deployment_id", "lines"},
    "desk_railway_variable_names": {"project", "service"},
    "desk_railway_redeploy": {"project", "service", "prior_deployment_id", "rollback_plan", "approval_id"},
    "desk_tailscale_status": set(),
    "desk_vps_units": {"units"},
    "desk_db_health": set(),
}

COORD_TOOLS = {
    "coordination_graph_heartbeat": {"graph_id", "node_id", "lease_id", "ttl_seconds"},
    "coordination_drift_scan": {"repo", "path", "git_tip", "branch", "idle_seconds", "limit", "format"},
}

INFRA_BACKENDS = {
    "desk_railway_status": "infra.railway_status",
    "desk_railway_logs": "infra.railway_logs",
    "desk_railway_variable_names": "infra.railway_variable_names",
    "desk_railway_redeploy": "infra.railway_redeploy",
    "desk_tailscale_status": "infra.tailscale_status",
    "desk_vps_units": "infra.vps_units",
    "desk_db_health": "infra.db_health",
}

NOT_ADDED = (
    "desk_parity_check",
    "desk_livez",
    "desk_index_archive",
    "desk_slo_history",
    "desk_metrics_history",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _props(tool: dict) -> set[str]:
    return set((tool.get("input") or {}).get("properties") or {})


def _by_name(doc: dict) -> dict[str, dict]:
    return {tool["name"]: tool for tool in doc["tools"]}


def test_core_infra_and_coordination_keep_the_same_tools():
    core = _by_name(_load(REPO / "contracts/tool-rosters/_core.yaml"))
    infra = _by_name(_load(REPO / "contracts/tool-rosters/infra.yaml"))
    coord = _by_name(_load(REPO / "contracts/tool-packs/coordination.yaml"))

    assert set(core) == set(CORE_TOOLS)
    assert set(infra) == set(INFRA_TOOLS)
    assert set(coord) == set(COORD_TOOLS)
    for name, props in CORE_TOOLS.items():
        assert _props(core[name]) == props
    for name, props in INFRA_TOOLS.items():
        assert _props(infra[name]) == props
        assert infra[name]["backend"] == INFRA_BACKENDS[name]
    for name, props in COORD_TOOLS.items():
        assert _props(coord[name]) == props

    names = set(core) | set(infra) | set(coord)
    assert names.isdisjoint(NOT_ADDED)


def test_change_record_lists_follow_ups_instead_of_new_tools():
    doc = _load(REPO / "contracts/changes/rosters-substrate-railway.yaml")
    assert doc["change_id"] == "rosters-substrate-railway"
    assert doc["breaking"] is False
    ids = [item["id"] for item in doc["follow_ups"]]
    assert ids == [
        "brief-fast-path-fields",
        "livez-and-watchdog",
        "index-archive-verify",
        "metrics-history-read",
        "parity-check-tool",
        "default-units-for-62",
    ]
    for item in doc["follow_ups"]:
        assert item["needs"]
        assert item["cites"]
        assert item["id"] not in NOT_ADDED


def test_skill_cites_the_three_commits_and_names_no_new_tool():
    text = (REPO / "skills/platforms/railway-tailscale/SKILL.md").read_text(encoding="utf-8")
    for sha in ("91487e7", "9231f43", "1e5e719"):
        assert sha in text
    for name in NOT_ADDED:
        assert f"- name: {name}" not in text
    assert "Nothing in this skill is deployed yet" not in text


def test_run_all_discovers_one_change_document():
    spec = importlib.util.spec_from_file_location("run_all", GATES / "run_all.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.discover_change_document([
        "contracts/tool-rosters/infra.yaml",
        "contracts/changes/rosters-substrate-railway.yaml",
    ]) == "contracts/changes/rosters-substrate-railway.yaml"
    assert mod.discover_change_document([
        "contracts/changes/a.yaml",
        "contracts/changes/b.yml",
    ]) is None
    assert mod.discover_change_document(["contracts/tool-rosters/infra.yaml"]) is None
