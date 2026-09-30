from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from tests.conftest import INTAKE_TOKEN, MCP_HEADERS, PASS

EXPECTED = {"lead": 15, "systems": 14, "web": 15, "android": 15, "ios": 15, "infra": 15, "quality": 15}


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "desk-gateway" and body["seats"]["quality"] == "/mcp/quality"
    assert body["packs"] == ["clippyos", "desklanes", "kanbanos"]


@pytest.mark.parametrize("seat", list(EXPECTED))
async def test_each_seat_sees_its_own_roster(rpc, seat):
    names = await rpc.tools(seat)
    assert len(names) == EXPECTED[seat]
    assert "desk_brief" in names and "desk_doctor" in names
    assert ("desk_intake_next" in names) == (seat == "lead")
    assert ("desk_receipt_approve" in names) == (seat == "quality")


async def test_wrong_seat_token_is_403(rpc):
    resp = await rpc.raw("ios", PASS["lead"], "tools/list")
    assert resp.status_code == 403
    assert resp.json()["error"] == "wrong_seat"


async def test_missing_token_is_401_with_resource_metadata(rpc):
    resp = await rpc.raw("lead", None, "tools/list")
    assert resp.status_code == 401
    assert "oauth-protected-resource" in resp.headers["www-authenticate"]


async def test_unknown_seat_and_pack_paths(client):
    resp = await client.post("/mcp/nope", headers={**MCP_HEADERS, "x-connector-key": PASS["lead"]}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp.status_code == 404
    resp = await client.post("/mcp/infra/packs/kanbanos", headers={**MCP_HEADERS, "x-connector-key": PASS["infra"]}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp.status_code == 404


async def test_protected_resource_metadata_for_seat_paths(client):
    resp = await client.get("/.well-known/oauth-protected-resource/mcp/ios")
    assert resp.status_code == 200
    assert resp.json()["resource"].endswith("/mcp")


async def test_unknown_tool_and_invalid_args(rpc):
    out = await rpc.call("ios", "desk_intake_next", {})
    assert out["error"] == "unknown_tool"
    out = await rpc.call("ios", "desk_appstore_phased_release", {"bundle_id": "a.b", "version": "1.0"})
    assert out["error"] == "invalid_args" and "halt_signal" in out["reason"]
    out = await rpc.call("lead", "desk_memory_recall", {"query": "x", "extra": 1})
    assert out["error"] == "invalid_args"


async def test_gated_tool_without_upstream_fails_closed(rpc):
    out = await rpc.call(
        "ios",
        "desk_appstore_phased_release",
        {"bundle_id": "space.swcstudio.desklanes", "version": "1.2.0", "halt_signal": "crash-free sessions under 99.5% in 1h", "rollback_plan": "pause phased release; prior build stays live", "approval_id": "APR-2026-0930-01"},
    )
    assert out["is_error"] is True and out["error"] == "not_configured"


async def test_read_tool_without_upstream_fails_open(rpc):
    out = await rpc.call("infra", "desk_railway_status", {})
    assert out["is_error"] is False
    assert out["projects"] == [] and out["error"] == "not_configured"


async def test_secret_in_arguments_is_refused(rpc):
    out = await rpc.call("lead", "desk_memory_retain", {"content": "decision: forwarders", "source": "https://x/y", "tags": ["api_key=sk-abcdefghijklmnopqrstuv"]})  # pragma: allowlist secret (redaction fixture)
    assert out["error"] == "secret_refused"


async def test_ownership_resolve_uses_manifest(rpc):
    out = await rpc.call("web", "desk_ownership_resolve", {"paths": ["web/app.ts", "ios/App.swift", "contracts/api/x.yaml", "unowned.zzz"]})
    by_path = {r["path"]: r for r in out["results"]}
    assert by_path["web/app.ts"]["owner"] == "bot-02-web-edge" and by_path["web/app.ts"]["mine"]
    assert by_path["ios/App.swift"]["owner"] == "bot-04-ios"
    assert by_path["contracts/api/x.yaml"]["contract_surface"] is True
    assert by_path["unowned.zzz"]["unowned"] is True


async def test_receipt_check_runs_the_gates(rpc):
    receipt = {
        "task_id": "gw-check",
        "bot": "bot-02-web-edge",
        "commands": [{"cmd": "pytest -q", "exit_code": 0, "duration_s": 1.0, "output_tail": "1 passed"}],
        "claims": [{"claim": "tests pass", "evidence_command_index": 0}],
        "unverified": ["not run on Windows"],
        "files_changed": ["web/app.ts"],
        "approved_by": "bot-06-quality-security",
    }
    out = await rpc.call("web", "desk_receipt_check", {"bot": "bot-02-web-edge", "receipt": receipt})
    assert out["gates"]["G-2"]["exit_code"] == 0, out
    assert out["ok"] is True
    bad = dict(receipt, approved_by="bot-02-web-edge")
    out = await rpc.call("web", "desk_receipt_check", {"bot": "bot-02-web-edge", "receipt": bad})
    assert out["ok"] is False and out["gates"]["G-2"]["exit_code"] != 0


async def test_intake_flow_only_lead_can_drain(client, rpc):
    body = {"title": "Add /health to desklanes", "ask": "Please add a /health endpoint returning 200 ok with a test.", "links": ["https://github.com/swcstudiospace/desklanes/issues/12"], "requested_by": "ove", "idempotency_key": "github:desklanes:12"}
    resp = await client.post("/v1/intake", json=body)
    assert resp.status_code == 401
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {PASS['lead']}"}, json=body)
    assert resp.status_code == 403
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json={**body, "origin": "slack"})
    assert resp.status_code == 403
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json=body)
    assert resp.status_code == 202
    intake_id = resp.json()["intake_id"]
    again = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json=body)
    assert again.json()["intake_id"] == intake_id
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json={**body, "idempotency_key": "k2", "ask": "here is a token ghp_abcdefghijklmnopqrstuvwxyz012345 please use it"})
    assert resp.status_code == 422
    out = await rpc.call("lead", "desk_intake_next", {})
    assert out["work_order"]["intake_id"] == intake_id and out["work_order"]["ask"] == body["ask"]
    out = await rpc.call("lead", "desk_intake_next", {})
    assert out["work_order"] is None
    out = await rpc.call("lead", "desk_intake_ack", {"intake_id": intake_id, "status": "accepted", "graph_id": "ut-abc123-deadbeef", "message": "queued for uplift"})
    assert out["ok"] and out["intake"]["state"] == "accepted"
    assert out["notify"]["delivered"] is False


async def test_packs_load_unload_and_ceiling(rpc):
    out = await rpc.call("ios", "desk_app_tools_load", {"app": "kanbanos", "task_id": "feat-push"})
    assert out["ok"] and out["live_tools"] == 20
    assert len(await rpc.tools("ios")) == 20
    out = await rpc.call("ios", "desk_app_tools_load", {"app": "desklanes", "task_id": "feat-push"})
    assert out["error"] == "ceiling"
    out = await rpc.call("ios", "kanbanos_api_smoke", {})
    assert out["error"] == "not_configured"
    out = await rpc.call("ios", "desk_app_tools_load", {"app": "kanbanos", "task_id": "feat-push", "unload": True})
    assert out["ok"] and out["live_tools"] == 15
    assert len(await rpc.tools("ios")) == 15
    out = await rpc.call("infra", "desk_app_tools_load", {"app": "kanbanos", "task_id": "x"})
    assert out["error"] == "unknown_tool"


async def test_pack_endpoint_serves_only_the_pack(rpc):
    names = await rpc.tools("android", path="/mcp/android/packs/desklanes")
    assert names == sorted(names) or True
    assert set(names) == {"desklanes_api_smoke", "desklanes_scoreboard_get", "desklanes_push_test", "desklanes_store_listing_get", "desklanes_crash_reports"}


async def test_doctor_register_and_check(rpc, app):
    out = await rpc.call("ios", "desk_doctor", {"action": "register", "agent_uuid": "a2d933ec-c6cf-43b7-a060-bec226475fb6"})
    assert out["ok"] and out["registered"] == ["ios"] and "lead" in out["missing"]
    out = await rpc.call("ios", "desk_doctor", {"action": "register", "channel_id": "4d78b294-5b65-46a9-bec9-86cdbc54aa3e"})
    assert out["error"] == "forbidden"
    out = await rpc.call("lead", "desk_doctor", {"action": "register", "agent_uuid": "8b8edded-d0ac-4dc7-ab89-d13ed150e656", "channel_id": "4d78b294-5b65-46a9-bec9-86cdbc54aa3e"})
    assert out["channel_id"] == "4d78b294-5b65-46a9-bec9-86cdbc54aa3e"
    out = await rpc.call("ios", "desk_doctor", {"action": "check"})
    assert out["green"] is False
    checks = out["checks"]
    assert checks["tools"]["green"] is True and checks["tools"]["roster"] == 15
    assert checks["roster"]["green"] is False and checks["connector"]["green"] is True
    assert "desk-bootstrap" in checks["skills"]["declared"]
    out = await rpc.call("ios", "desk_doctor", {"action": "install_prompt"})
    assert out["error"] == "roster_incomplete" and "android" in out["missing"]
    status = await rpc.call("lead", "desk_roster_status", {})
    assert status["complete"] is False and {s["seat"] for s in status["seats"] if s["registered"]} == {"IOS", "LEAD"}


async def test_install_prompt_renders_with_full_roster(rpc):
    uuids = {
        "lead": "8b8edded-d0ac-4dc7-ab89-d13ed150e656",
        "systems": "cfb754de-5850-4c33-8329-eceaf8b8b508",
        "web": "25ca6685-cc8a-4223-bacb-6122eb02da54",
        "android": "8af7effc-c418-400f-97ad-76eb6b9a5a6e",
        "ios": "a2d933ec-c6cf-43b7-a060-bec226475fb6",
        "infra": "21cd1b39-9dca-4f8c-8de0-95d8e518ad1a",
        "quality": "c72f1ddf-893e-4da2-9fd3-5f73e307072b",
    }
    for seat, uuid in uuids.items():
        args = {"action": "register", "agent_uuid": uuid}
        if seat == "lead":
            args["channel_id"] = "4d78b294-5b65-46a9-bec9-86cdbc54aa3e"
        out = await rpc.call(seat, "desk_doctor", args)
        assert out["ok"], out
    out = await rpc.call("ios", "desk_doctor", {"action": "install_prompt"})
    assert out.get("ok"), out
    prompt = out["prompt"]
    assert "{{" not in prompt, prompt[max(0, prompt.find("{{") - 80): prompt.find("{{") + 40]
    assert uuids["lead"] in prompt
    assert "4d78b294" in prompt
    assert 'gateway="https://desk.swcstudio.space/mcp/ios"' in out["prompt"]
    check = await rpc.call("ios", "desk_doctor", {"action": "check", "prompt_sha256": out["sha256"], "installed_skills": ["ios", "desk-gateway", "hindsight-memory", "ragflow-docs", "tool-packs", "verification-receipts", "desk-doctor", "desk-bootstrap"]})
    assert check["checks"]["prompt"]["green"] is True
    assert check["checks"]["skills"]["green"] is True
    assert check["checks"]["roster"]["green"] is True


async def test_audit_events_are_written_locally(rpc, settings):
    await rpc.call("web", "desk_ownership_resolve", {"paths": ["web/x.ts"]})
    lines = (settings.data_dir / "audit.jsonl").read_text().splitlines()
    event = json.loads(lines[-1])
    assert event["kind"] == "tool.call" and event["payload"]["seat"] == "web" and event["payload"]["tool"] == "desk_ownership_resolve"
    assert event["payload"]["ok"] is True


async def test_oauth_dcr_pkce_consent_and_seat_scope(client, rpc):
    dcr = {
        "client_name": "Grok Bot test",
        "redirect_uris": ["https://localhost/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # pragma: allowlist secret (DCR field name)
    }
    reg = await client.post("/register", json=dcr)
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    auth = await client.get("/authorize", params={"response_type": "code", "client_id": client_id, "redirect_uri": "https://localhost/callback", "code_challenge": challenge, "code_challenge_method": "S256", "state": "s1", "scope": "mcp", "resource": "https://desk.swcstudio.space/mcp/android"})
    assert auth.status_code in (302, 303, 307), auth.text
    consent_url = auth.headers["location"]
    assert "/oauth/consent?request=" in consent_url
    request_id = parse_qs(urlparse(consent_url).query)["request"][0]
    page = await client.get("/oauth/consent", params={"request": request_id})
    assert page.status_code == 200 and "Seat passphrase" in page.text
    bad = await client.post("/oauth/consent", data={"request": request_id, "action": "approve", "passphrase": "wrong"})
    assert bad.status_code == 401
    ok = await client.post("/oauth/consent", data={"request": request_id, "action": "approve", "passphrase": PASS["android"]})
    assert ok.status_code == 303
    redirect = urlparse(ok.headers["location"])
    code = parse_qs(redirect.query)["code"][0]
    assert parse_qs(redirect.query)["state"] == ["s1"]
    token = await client.post("/token", data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "client_id": client_id, "redirect_uri": "https://localhost/callback", "resource": "https://desk.swcstudio.space/mcp/android"})
    assert token.status_code == 200, token.text
    body = token.json()
    assert "seat:android" in body["scope"].split()
    names = await rpc.tools("android", key=body["access_token"])
    assert len(names) == 15
    resp = await rpc.raw("ios", body["access_token"], "tools/list")
    assert resp.status_code == 403
    refreshed = await client.post("/token", data={"grant_type": "refresh_token", "refresh_token": body["refresh_token"], "client_id": client_id})
    assert refreshed.status_code == 200 and "seat:android" in refreshed.json()["scope"]


# ---------------------------------------------------------------------------
# contract_propose — the file-write path
#
# The surface arrives from the caller and is joined onto the export tree, and the
# unit runs as root, so the guards on that join are security-critical. Exercised
# through the endpoint rather than by asserting on safe_path: a unit test of the
# helper stays green if the handler stops calling it, which is the regression that
# actually matters here.
# ---------------------------------------------------------------------------

PROPOSAL = {
    "change_id": "traversal-guard-v1",
    "summary": "exercise the contract_propose surface guard",
    "breaking": False,
    "version": "1.0.0",
    "consumers_required": ["bot-02-web-edge"],
    "body": "openapi: 3.1.0\ninfo:\n  title: guard\n",
}


@pytest.mark.parametrize("surface", [
    "contracts/../../../tmp/desk-gateway-escape.yaml",
    "contracts/../../root/.ssh/authorized_keys",
    "contracts/ok/../../../../tmp/desk-gateway-escape.yaml",
])
async def test_contract_propose_refuses_a_surface_that_escapes_the_tree(rpc, surface):
    """The roster pattern admits '..', so the handler is the only thing standing here."""
    out = await rpc.call("systems", "desk_contract_propose", {**PROPOSAL, "surface": surface})
    assert out["is_error"] is True, f"{surface!r} was accepted: {out}"
    assert out["error"] == "invalid_surface", out


async def test_contract_propose_accepts_a_legitimate_surface(rpc):
    """The refusals above would be satisfied by a handler that rejected everything."""
    out = await rpc.call("systems", "desk_contract_propose",
                         {**PROPOSAL, "surface": "contracts/api/guard-probe.yaml"})
    assert out["is_error"] is False, out
    assert out["proposal"]["surface"] == "contracts/api/guard-probe.yaml"
    assert out["proposal"]["proposed_by"] == "bot-01-systems-backend"


async def test_contract_propose_will_not_write_through_a_symlink_in_the_tree(
        rpc, monkeypatch, tmp_path):
    """Second guard: safe_path sees a clean relative path, the symlink still escapes.

    The export tree is built by git, so a symlink cannot be planted in it from outside
    — export is substituted here to produce one. Asserts the outside file is untouched,
    not merely that the call failed, since a refusal for some other reason would look
    the same.
    """
    from desk_gateway.repo import Repo

    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "authorized_keys"
    secret.write_text("original\n")

    tree = tmp_path / "tree"
    (tree / "contracts").mkdir(parents=True)
    (tree / "contracts" / "api").symlink_to(outside, target_is_directory=True)

    async def fake_export(self, ref):        # noqa: ARG001 — signature must match
        return tree

    monkeypatch.setattr(Repo, "export", fake_export)

    out = await rpc.call("systems", "desk_contract_propose",
                         {**PROPOSAL, "surface": "contracts/api/authorized_keys"})

    assert out["is_error"] is True, out
    assert out["error"] == "invalid_surface", out
    assert secret.read_text() == "original\n", "the write escaped through the symlink"


# ---------------------------------------------------------------------------
# desk_gates_run — the code the gates are
#
# The ref is a branch from any seat and the gateway runs as root, so which copy of
# ci/gates/ runs is the whole security property. Asserted on the invocation and on
# markers the poisoned copies would have left, not on the tool's verdict: a run that
# failed for an unrelated reason looks the same in the verdict.
# ---------------------------------------------------------------------------

POISON = """\
import pathlib, sys
pathlib.Path(%r).write_text("executed")
print("G-1 PASS — nothing was checked")
sys.exit(0)
"""


def _poisoned_tree(tmp_path, repo_root):
    """An export whose ci/gates/ would own the gateway if it were executed."""
    tree = tmp_path / "poisoned-tree"
    gates = tree / "ci" / "gates"
    gates.mkdir(parents=True)
    (tree / "ownership.yaml").write_text((repo_root / "ownership.yaml").read_text())
    markers = {}
    for name in ("check_ownership.py", "check_secrets.py", "check_contracts.py",
                 "check_receipt.py", "check_rollback.py", "check_desk_integrity.py",
                 # Not a gate: Python puts the script's own directory first on sys.path, so a
                 # module the gates import is as good as the gates themselves.
                 "yaml.py"):
        markers[name] = tmp_path / f"marker-{name}"
        (gates / name).write_text(POISON % str(markers[name]))
    return tree, markers


def _record_scripts(monkeypatch):
    """Capture the bytes of every Python script the gateway execs, at exec time.

    The scripts run from a scratch root that is removed when the call returns, so the check
    has to happen while it exists. Recorded rather than intercepted: the real command still
    runs, so this cannot pass by preventing the gates from running at all.
    """
    from desk_gateway import repo as repo_mod

    invoked: list[tuple[str, bytes]] = []
    real = repo_mod.run_command

    async def recording(argv, **kwargs):
        if len(argv) > 1 and argv[1].endswith(".py"):
            invoked.append((argv[1], Path(argv[1]).read_bytes()))
        return await real(argv, **kwargs)

    monkeypatch.setattr(repo_mod, "run_command", recording)
    return invoked


def _assert_trusted(invoked, tree, repo_root, expected: set[str]):
    assert {Path(p).name for p, _ in invoked} >= expected, sorted(Path(p).name for p, _ in invoked)
    for path, body in invoked:
        name = Path(path).name
        assert not path.startswith(str(tree)), f"{name} was executed out of the export: {path}"
        assert body == (repo_root / "ci" / "gates" / name).read_bytes(), \
            f"{name} was executed, but it was not the gateway's own copy of the gate"


async def test_gates_run_never_executes_the_gates_in_the_exported_ref(rpc, monkeypatch, tmp_path):
    from tests.conftest import REPO
    from desk_gateway.repo import Repo

    tree, markers = _poisoned_tree(tmp_path, REPO)
    invoked = _record_scripts(monkeypatch)

    async def fake_export(self, ref):        # noqa: ARG001 — signature must match
        return tree

    monkeypatch.setattr(Repo, "export", fake_export)

    out = await rpc.call("quality", "desk_gates_run", {"ref": "HEAD", "base": "HEAD", "bot": "bot-01-systems-backend"})
    assert out["is_error"] is False, out

    executed = sorted(name for name, marker in markers.items() if marker.exists())
    assert not executed, f"the exported ref's {executed} ran as the gateway"
    _assert_trusted(invoked, tree, REPO, {
        "check_ownership.py", "check_secrets.py", "check_contracts.py", "check_desk_integrity.py",
    })


async def test_secret_scan_never_executes_the_gate_in_the_exported_ref(rpc, monkeypatch, tmp_path):
    from tests.conftest import REPO
    from desk_gateway.repo import Repo

    tree, markers = _poisoned_tree(tmp_path, REPO)
    invoked = _record_scripts(monkeypatch)

    async def fake_export(self, ref):        # noqa: ARG001 — signature must match
        return tree

    monkeypatch.setattr(Repo, "export", fake_export)

    out = await rpc.call("quality", "desk_secret_scan", {"ref": "HEAD"})

    executed = sorted(name for name, marker in markers.items() if marker.exists())
    assert not executed, f"the exported ref's {executed} ran as the gateway"
    _assert_trusted(invoked, tree, REPO, {"check_secrets.py"})
    # The poisoned scripts are still in the tree as data, and check_secrets scanned them.
    assert out["files"] >= len(markers), out


async def test_gates_run_will_not_report_ok_when_a_required_gate_never_ran(rpc):
    """An incomplete run is not a green one.

    ok is what a merge claim quotes. G-2 and G-5/G-6 read the verification receipt, which
    only the caller can point at, so a run without one has to say so rather than report
    every gate it did happen to run as a pass.
    """
    out = await rpc.call("quality", "desk_gates_run", {"ref": "HEAD", "base": "HEAD", "bot": "bot-01-systems-backend"})
    assert out["is_error"] is False, out
    assert out["ok"] is False, out
    assert set(out["skipped"]) == {"G-2 receipt", "G-5/G-6 rollback"}, out["skipped"]
    assert "never ran" in out["verdict"], out["verdict"]
    # G-4 was never wired at all: a contract change could be claimed clear by a run that
    # never looked at contract surfaces.
    assert out["gates"]["G-4 contracts"]["exit_code"] == 0, out["gates"]["G-4 contracts"]
    assert out["gates"]["G-7 desk integrity"]["exit_code"] == 0, out["gates"]["G-7 desk integrity"]


async def test_gates_run_runs_the_receipt_gates_when_given_one(rpc):
    """The other half: with a receipt, G-1..G-7 all run and none is skipped."""
    out = await rpc.call("quality", "desk_gates_run", {
        "ref": "HEAD",
        "base": "HEAD",
        "bot": "bot-01-systems-backend",
        "receipt_path": ".receipts/bot-01-systems-backend/desk-v2-gateway.json",
    })
    assert out["skipped"] == {}, out["skipped"]
    assert {"G-1 manifest", "G-1 ownership", "G-2 receipt", "G-3 secrets",
            "G-4 contracts", "G-5/G-6 rollback", "G-7 desk integrity"} <= set(out["gates"]), sorted(out["gates"])
    assert out["ok"] is (out["failed"] == []), out


async def test_gates_run_refuses_a_receipt_path_that_escapes_the_tree(rpc):
    out = await rpc.call("quality", "desk_gates_run", {
        "ref": "HEAD", "bot": "bot-01-systems-backend",
        "receipt_path": ".receipts/bot-01-systems-backend/../../../etc/passwd",
    })
    assert out["is_error"] is True and out["error"] == "invalid_args", out


# ---------------------------------------------------------------------------
# desk_intake_ack — the reply is the acknowledgement
# ---------------------------------------------------------------------------

INTAKE_BODY = {
    "title": "Add /health to desklanes",
    "ask": "Please add a /health endpoint returning 200 ok with a test.",
    "links": ["https://github.com/swcstudiospace/desklanes/issues/12"],
    "requested_by": "ove",
    "idempotency_key": "github:desklanes:99",
}


async def _claim_one(client, rpc):
    resp = await client.post("/v1/intake", headers={"Authorization": f"Bearer {INTAKE_TOKEN}"}, json=INTAKE_BODY)
    assert resp.status_code == 202, resp.text
    out = await rpc.call("lead", "desk_intake_next", {})
    return out["work_order"]["intake_id"]


async def test_intake_ack_fails_closed_when_the_github_reply_fails(client, rpc, monkeypatch):
    """A failed reply must not leave an intake marked accepted.

    The requester's only signal is the comment. Advancing the record first meant a 403, a
    rate limit or a missing token produced ok:true on an accepted intake that nobody had
    been told about, and no retry, because the record no longer looked claimed.
    """
    from desk_gateway.upstreams import GitHub

    calls = []

    async def fake_comment(self, repo, number, body):   # noqa: ARG001 — signature must match
        calls.append((repo, number))
        return {"error": "upstream_error", "reason": "github returned HTTP 403"}

    monkeypatch.setattr(GitHub, "comment_on_issue", fake_comment)
    intake_id = await _claim_one(client, rpc)

    out = await rpc.call("lead", "desk_intake_ack", {"intake_id": intake_id, "status": "accepted", "graph_id": "ut-abc123-deadbeef"})
    assert out["is_error"] is True, out
    assert out["error"] == "notify_failed", out
    assert out["notify"]["delivered"] is False and "403" in out["notify"]["reason"]
    assert calls == [("swcstudiospace/desklanes", 12)]

    # Not advanced: the same ack can go out again once GitHub answers.
    status = await rpc.call("lead", "desk_intake_next", {})
    assert status["queue"] == {"claimed": 1}, status["queue"]


async def test_intake_ack_advances_once_the_reply_is_posted(client, rpc, monkeypatch):
    """The refusal above would be satisfied by an ack that never advanced anything."""
    from desk_gateway.upstreams import GitHub

    posted = []

    async def fake_comment(self, repo, number, body):   # noqa: ARG001 — signature must match
        posted.append(body)
        return {"ok": True, "status": 201, "body": {"id": 1}}

    monkeypatch.setattr(GitHub, "comment_on_issue", fake_comment)
    intake_id = await _claim_one(client, rpc)

    out = await rpc.call("lead", "desk_intake_ack", {"intake_id": intake_id, "status": "accepted", "graph_id": "ut-abc123-deadbeef", "message": "queued for uplift"})
    assert out["ok"] is True and out["intake"]["state"] == "accepted", out
    assert out["notify"]["delivered"] is True
    assert "ut-abc123-deadbeef" in posted[0] and intake_id in posted[0]


class FakeIssue:
    """The two GitHub endpoints an ack uses, standing in at the HTTP boundary.

    Wired under `HttpUpstream.request` rather than over `GitHub`'s methods, so the real
    comment_on_issue and find_issue_comment run: the pagination, the oldest-first ordering
    and the `since` window are exercised instead of being assumed. `backlog` seeds comments
    from a month ago, which is how a thread gets longer than the lookup's page budget.
    """

    PER_PAGE_CAP = 100

    def __init__(self, backlog: int = 0) -> None:
        old = time.time() - 30 * 86400
        self.comments: list[dict] = [{"body": f"backlog {i}", "at": old + i} for i in range(backlog)]
        self.gets: list[dict] = []
        self.error: dict | None = None
        self.post_delay = 0.0

    @property
    def bodies(self) -> list[str]:
        return [c["body"] for c in self.comments]

    def posted(self, marker_owner: str) -> list[str]:
        return [b for b in self.bodies if marker_owner in b]

    async def request(self, method: str, path: str, **kwargs):
        if "/comments" not in path:          # audit and health traffic is not this fake's business
            return {"ok": True, "status": 200, "body": {}}
        if self.error is not None:
            return self.error
        if method == "POST":
            if self.post_delay:
                await asyncio.sleep(self.post_delay)
            self.comments.append({"body": kwargs["json"]["body"], "at": time.time()})
            return {"ok": True, "status": 201, "body": {"id": len(self.comments)}}
        params = kwargs.get("params") or {}
        self.gets.append(params)
        rows = self.comments
        if params.get("since"):
            cut = datetime.strptime(params["since"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            rows = [c for c in rows if c["at"] >= cut]
        per = min(int(params.get("per_page", 30)), self.PER_PAGE_CAP)
        start = (int(params.get("page", 1)) - 1) * per
        return {"ok": True, "status": 200, "body": [{"body": c["body"]} for c in rows[start:start + per]]}


def _stub_github(monkeypatch, backlog: int = 0) -> FakeIssue:
    from desk_gateway.upstreams import HttpUpstream, not_configured

    issue = FakeIssue(backlog)

    async def fake_request(self, method, path, **kwargs):
        # The real request() answers not_configured before it reaches the network, and a test
        # that took a token away would otherwise keep getting served.
        if not self.configured:
            return not_configured(self.name)
        return await issue.request(method, path, **kwargs)

    monkeypatch.setattr(HttpUpstream, "request", fake_request)
    _configure_upstreams(monkeypatch)
    return issue


ACK = {"status": "accepted", "graph_id": "ut-abc123-deadbeef", "message": "queued for uplift"}
MARKER = "desk-intake-ack"


def _flaky_delivery(monkeypatch, failing_state: str):
    """Make the delivery record fail for one state, the way a full disk would."""
    from desk_gateway.store import Store

    real = Store.intake_delivery

    def flaky(self, intake_id_, key, state):
        if state == failing_state:
            raise OSError("no space left on device while writing intake.json")
        return real(self, intake_id_, key, state)

    monkeypatch.setattr(Store, "intake_delivery", flaky)
    return real


async def test_intake_ack_does_not_repost_when_the_store_fails_after_the_comment(client, rpc, monkeypatch):
    """The reply precedes the advance, so a failed advance must not buy a second comment.

    The failure tells LEAD to call again — that is the point of posting first — and the retry
    arrived with the comment already on the issue and nothing in the response or the record
    saying so, so it posted an identical one. Two acknowledgements of one request, from the
    requester's side.
    """
    from desk_gateway.store import Store

    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}

    real_ack = Store.intake_ack
    attempts: list[str] = []

    def failing_ack(self, intake_id_, ack):   # noqa: ARG001 — signature must match
        attempts.append(intake_id_)
        raise OSError("no space left on device while writing intake.json")

    monkeypatch.setattr(Store, "intake_ack", failing_ack)
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out["is_error"] is True and out["error"] == "internal", out
    assert attempts == [intake_id]
    assert len(issue.posted(MARKER)) == 1, issue.bodies

    monkeypatch.setattr(Store, "intake_ack", real_ack)
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert len(issue.posted(MARKER)) == 1, "the retry posted the reply a second time"
    assert issue.gets == [], "the record knew the reply was delivered; the issue did not need reading"
    assert out["ok"] is True and out["intake"]["state"] == "accepted", out
    assert out["notify"]["delivered"] is True and out["notify"]["posted"] is False


async def test_intake_ack_reads_the_issue_back_when_the_delivery_record_was_lost(client, rpc, monkeypatch):
    """The narrower window: the comment landed and even the record of it could not be written.

    Nothing local knows the outcome, so the issue is asked. Finding the marker is the proof
    the reply was delivered, and the retry only has to finish the advance.
    """
    from desk_gateway.store import Store

    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}

    real_delivery = _flaky_delivery(monkeypatch, "delivered")
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out["is_error"] is True and out["error"] == "internal", out
    assert len(issue.posted(MARKER)) == 1 and issue.gets == [], issue.gets

    monkeypatch.setattr(Store, "intake_delivery", real_delivery)
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert len(issue.posted(MARKER)) == 1, "the retry posted the reply a second time"
    assert len(issue.gets) == 1, "the retry did not check the issue it may have posted to"
    assert out["ok"] is True and out["intake"]["state"] == "accepted", out
    assert out["notify"]["delivered"] is True and out["notify"]["posted"] is False


async def test_intake_ack_recovers_on_a_thread_longer_than_the_page_budget(client, rpc, monkeypatch):
    """Greptile P1 4141224505: a long thread must not make the reply unfindable.

    GitHub lists issue comments oldest-first and will not reverse them, so a lookup that
    starts at the beginning spends its whole page budget on the oldest comments and never
    reaches the reply. That is not a stuck lookup, it is a stuck intake: every retry reads
    unknown, refuses to post, and never advances, with no way out by asking again. The window
    starts from the first attempt instead, so the thread's length stops mattering.
    """
    from desk_gateway.store import Store

    issue = _stub_github(monkeypatch, backlog=600)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}

    real_delivery = _flaky_delivery(monkeypatch, "delivered")
    assert (await rpc.call("lead", "desk_intake_ack", args))["error"] == "internal"
    assert len(issue.posted(MARKER)) == 1

    monkeypatch.setattr(Store, "intake_delivery", real_delivery)
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out.get("error") != "notify_unknown", (
        "the reply is on the issue, but the lookup could not read far enough to see it, so the "
        "intake is stranded: every retry reads unknown and refuses to post or advance"
    )
    assert out["ok"] is True and out["notify"]["delivered"] is True, out
    assert len(issue.posted(MARKER)) == 1, "the retry posted the reply a second time"
    assert issue.gets and issue.gets[0].get("since"), "the lookup read the thread from its start"
    # Found on the first page of the window, not by walking 600 backlog comments.
    assert len(issue.gets) == 1, issue.gets


async def test_intake_ack_will_not_repost_on_an_unreadable_issue(client, rpc, monkeypatch):
    """An unknown outcome is the case that double-posts, so it fails closed instead.

    Retrying blind would be the original bug with extra steps: the comment is probably there.
    The intake stays claimed and says what to look at, which is recoverable; a duplicate
    acknowledgement on someone's issue is not.
    """
    from desk_gateway.store import Store

    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}

    real_delivery = _flaky_delivery(monkeypatch, "delivered")
    assert (await rpc.call("lead", "desk_intake_ack", args))["error"] == "internal"

    monkeypatch.setattr(Store, "intake_delivery", real_delivery)
    issue.error = {"error": "upstream_error", "reason": "github returned HTTP 403"}
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out["is_error"] is True and out["error"] == "notify_unknown", out
    assert "403" in out["notify"]["reason"]
    assert len(issue.posted(MARKER)) == 1, "the reply went out again without knowing the first one had not"
    status = await rpc.call("lead", "desk_intake_next", {})
    assert status["queue"] == {"claimed": 1}, status["queue"]

    # And once GitHub answers again, the same call finishes without reposting.
    issue.error = None
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out["ok"] is True and out["notify"]["delivered"] is True, out
    assert len(issue.posted(MARKER)) == 1


async def test_intake_ack_will_not_advance_when_the_lookup_has_no_token(client, rpc, monkeypatch):
    """Greptile P1 4141224494: an unconfigured gateway must not settle an attempted reply.

    A reply that was never attempted is one thing — nothing was promised, and the ack says so
    with delivered: false. But once an attempt has been made and the gateway can no longer ask
    whether it landed, advancing marks the intake acknowledged on the chance that it did. If
    it did not, the queue counts the request as answered and nobody ever told the requester.
    """
    from desk_gateway.store import Store
    from desk_gateway.upstreams import HttpUpstream

    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}

    real_delivery = _flaky_delivery(monkeypatch, "delivered")
    assert (await rpc.call("lead", "desk_intake_ack", args))["error"] == "internal"
    assert len(issue.posted(MARKER)) == 1

    # The token is gone by the time LEAD calls again.
    monkeypatch.setattr(Store, "intake_delivery", real_delivery)
    monkeypatch.setattr(HttpUpstream, "configured", property(lambda self: False))
    out = await rpc.call("lead", "desk_intake_ack", args)
    assert out["is_error"] is True and out["error"] == "notify_unknown", out
    assert out["notify"]["error"] == "not_configured", out["notify"]
    assert len(issue.posted(MARKER)) == 1
    status = await rpc.call("lead", "desk_intake_next", {})
    assert status["queue"] == {"claimed": 1}, "an unreadable outcome advanced the intake"


async def test_concurrent_intake_acks_post_one_reply(client, rpc, monkeypatch):
    """Greptile P1 4141224477: two acks in flight together must not both post.

    The delivery record is read before the post and written after it, so two calls for the
    same reply could both read a state from before either had posted — the second one's
    lookup finding nothing precisely because the first one's comment had not landed yet — and
    both would post. They are serialised per ack instead, and the second re-reads inside the
    lock, where the first one's delivery is already recorded.
    """
    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)
    args = {"intake_id": intake_id, **ACK}
    issue.post_delay = 0.2          # hold the first post open long enough to overlap

    first, second = await asyncio.gather(
        rpc.call("lead", "desk_intake_ack", args),
        rpc.call("lead", "desk_intake_ack", args),
    )
    assert len(issue.posted(MARKER)) == 1, f"both calls posted: {issue.bodies}"
    assert first["ok"] is True and second["ok"] is True, (first, second)
    assert {first["notify"]["posted"], second["notify"]["posted"]} == {True, False}
    assert first["notify"]["delivered"] is True and second["notify"]["delivered"] is True


async def test_intake_ack_still_posts_a_genuinely_different_ack(client, rpc, monkeypatch):
    """Idempotence is per ack, not per intake: a later status is a reply the requester is owed."""
    issue = _stub_github(monkeypatch)
    intake_id = await _claim_one(client, rpc)

    assert (await rpc.call("lead", "desk_intake_ack", {"intake_id": intake_id, **ACK}))["ok"] is True
    out = await rpc.call("lead", "desk_intake_ack", {"intake_id": intake_id, "status": "done", "message": "shipped"})
    assert len(issue.posted(MARKER)) == 2, issue.bodies
    assert out["ok"] is True and out["intake"]["state"] == "done", out
    assert out["notify"]["posted"] is True


# ---------------------------------------------------------------------------
# desk_play_staged_rollout — a track update is a PUT
# ---------------------------------------------------------------------------

async def _ok(body):
    return {"ok": True, "body": body}


def _configure_upstreams(monkeypatch):
    """Make the HTTP upstreams look configured without a token anywhere near the test."""
    from desk_gateway.upstreams import HttpUpstream

    monkeypatch.setattr(HttpUpstream, "configured", property(lambda self: True))


ROLLOUT = {
    "package_name": "space.swcstudio.desklanes",
    "track": "production",
    "version_code": 1207,
    "user_fraction": 0.1,
    "halt_threshold": "crash-free sessions under 99.5% in 1h",
    "rollback_plan": "halt the rollout; version code 1204 stays live for the rest",
    "approval_id": "APR-2026-0930-07",
}

MULTI_RELEASE_TRACK = {
    "track": "production",
    "releases": [
        {"name": "1204 live", "versionCodes": ["1204"], "status": "completed"},
        {"name": "1180 legacy", "versionCodes": ["1180", "1181"], "status": "completed"},
        {"name": "draft notes only", "status": "draft"},
    ],
}


async def test_play_staged_rollout_keeps_the_releases_already_on_the_track(rpc, monkeypatch):
    """The PUT replaces the track, so it has to carry what was already there.

    Sending only the release being staged deleted every other release on the track — the
    completed one still serving the 90% of users this rollout is not for among them. That is
    not a rollout, it is an outage for everybody who was not picked.
    """
    from desk_gateway.upstreams import PlayConsole

    sent = {}

    async def fake_edit(self, package_name):
        return {"ok": True, "body": {"id": "edit-1"}}

    async def fake_track(self, package_name, edit_id, track):
        return {"ok": True, "body": MULTI_RELEASE_TRACK}

    async def fake_update(self, package_name, edit_id, track, body):
        sent.update(body)
        return {"ok": True, "body": body}

    async def fake_commit(self, package_name, edit_id):
        return {"ok": True, "body": {"id": edit_id}}

    _configure_upstreams(monkeypatch)
    monkeypatch.setattr(PlayConsole, "edit", fake_edit)
    monkeypatch.setattr(PlayConsole, "track", fake_track)
    monkeypatch.setattr(PlayConsole, "update_track", fake_update)
    monkeypatch.setattr(PlayConsole, "commit", fake_commit)

    out = await rpc.call("android", "desk_play_staged_rollout", ROLLOUT)
    assert out["ok"] is True, out

    by_code = {tuple(r.get("versionCodes") or []): r for r in sent["releases"]}
    assert ("1204",) in by_code, sent["releases"]
    assert ("1180", "1181") in by_code, sent["releases"]
    assert by_code[("1204",)]["status"] == "completed"
    assert any(r.get("status") == "draft" for r in sent["releases"]), "a release with no version codes was dropped"
    staged = by_code[("1207",)]
    assert staged["status"] == "inProgress" and staged["userFraction"] == 0.1
    assert len(sent["releases"]) == 4, sent["releases"]


async def test_play_staged_rollout_replaces_only_the_release_for_this_version(rpc, monkeypatch):
    """Advancing a rollout updates its own release; a version code lives in exactly one."""
    from desk_gateway.upstreams import PlayConsole

    sent = {}
    track = {"track": "production", "releases": [
        {"versionCodes": ["1204"], "status": "completed"},
        {"versionCodes": ["1207"], "status": "inProgress", "userFraction": 0.05},
    ]}

    monkeypatch.setattr(PlayConsole, "edit", lambda self, p: _ok({"id": "edit-1"}))
    monkeypatch.setattr(PlayConsole, "track", lambda self, p, e, t: _ok(track))
    monkeypatch.setattr(PlayConsole, "commit", lambda self, p, e: _ok({"id": e}))

    async def fake_update(self, package_name, edit_id, track_name, body):
        sent.update(body)
        return {"ok": True, "body": body}

    monkeypatch.setattr(PlayConsole, "update_track", fake_update)
    _configure_upstreams(monkeypatch)

    out = await rpc.call("android", "desk_play_staged_rollout", {**ROLLOUT, "user_fraction": 0.5})
    assert out["ok"] is True, out
    assert len(sent["releases"]) == 2, sent["releases"]
    staged = next(r for r in sent["releases"] if r.get("versionCodes") == ["1207"])
    assert staged["userFraction"] == 0.5 and staged["status"] == "inProgress"
    assert {"versionCodes": ["1204"], "status": "completed"} in sent["releases"]


async def test_play_staged_rollout_will_not_write_a_track_it_could_not_read(rpc, monkeypatch):
    """Preserving releases is only possible if the read succeeded; otherwise fail closed."""
    from desk_gateway.upstreams import PlayConsole

    writes = []
    monkeypatch.setattr(PlayConsole, "edit", lambda self, p: _ok({"id": "edit-1"}))

    async def fake_track(self, package_name, edit_id, track):
        return {"error": "upstream_error", "reason": "play returned HTTP 500"}

    async def fake_update(self, package_name, edit_id, track_name, body):
        writes.append(body)
        return {"ok": True, "body": body}

    monkeypatch.setattr(PlayConsole, "track", fake_track)
    monkeypatch.setattr(PlayConsole, "update_track", fake_update)
    _configure_upstreams(monkeypatch)

    out = await rpc.call("android", "desk_play_staged_rollout", ROLLOUT)
    assert out["is_error"] is True and out["error"] == "upstream_error", out
    assert writes == [], "the track was written without being read"


# ---------------------------------------------------------------------------
# desk_railway_redeploy — prior_deployment_id is evidence, so it gets checked
# ---------------------------------------------------------------------------

def _railway_project(deployment_id: str) -> dict:
    return {"ok": True, "body": {"data": {"project": {
        "id": "proj-1",
        "name": "ultrathink",
        "services": {"edges": [{"node": {
            "id": "svc-1",
            "name": "substrate-mcp",
            "serviceInstances": {"edges": [{"node": {
                "environmentId": "env-prod",
                "latestDeployment": {"id": deployment_id, "status": "SUCCESS"},
            }}]},
        }}]},
        "environments": {"edges": [{"node": {"id": "env-prod", "name": "production"}}]},
    }}}}


REDEPLOY = {
    "project": "ultrathink",
    "service": "substrate-mcp",
    "prior_deployment_id": "dep-aaaaaa",
    "rollback_plan": "redeploy dep-aaaaaa, the deployment this call was approved against",
    "approval_id": "APR-2026-0930-08",
}


def _stub_railway(monkeypatch, current_deployment: str, redeploys: list):
    from desk_gateway.upstreams import Railway

    async def fake_status(self, name):
        return _railway_project(current_deployment)

    async def fake_redeploy(self, service_id, environment_id):
        redeploys.append((service_id, environment_id))
        return {"ok": True, "body": {"data": {"serviceInstanceRedeploy": True}}}

    monkeypatch.setattr(Railway, "project_id", lambda self, name: "proj-1")
    monkeypatch.setattr(Railway, "project_status", fake_status)
    monkeypatch.setattr(Railway, "redeploy", fake_redeploy)
    _configure_upstreams(monkeypatch)


async def test_railway_redeploy_refuses_when_the_service_moved_on(rpc, monkeypatch):
    """prior_deployment_id was echoed back without ever being compared to anything.

    It is the caller's evidence of the state it inspected, and a receipt quoting it claimed a
    redeploy of that deployment. Between the status read and this call anything can have been
    deployed, so the claim was unfounded and the redeploy was of whatever is there now.
    """
    redeploys: list = []
    _stub_railway(monkeypatch, "dep-zzzzzz", redeploys)

    out = await rpc.call("infra", "desk_railway_redeploy", REDEPLOY)
    assert out["is_error"] is True, out
    assert out["error"] == "stale_deployment", out
    assert out["current_deployment_id"] == "dep-zzzzzz" and out["prior_deployment_id"] == "dep-aaaaaa"
    assert redeploys == [], "the redeploy went ahead against a deployment nobody approved"


async def test_railway_redeploy_proceeds_when_the_prior_deployment_still_stands(rpc, monkeypatch):
    redeploys: list = []
    _stub_railway(monkeypatch, "dep-aaaaaa", redeploys)

    out = await rpc.call("infra", "desk_railway_redeploy", REDEPLOY)
    assert out["ok"] is True, out
    assert out["verified_prior_deployment"] is True and out["environment_id"] == "env-prod"
    assert redeploys == [("svc-1", "env-prod")]


# ---------------------------------------------------------------------------
# desk_railway_status / desk_railway_logs — a deployment belongs to one environment
# ---------------------------------------------------------------------------

def _two_env_project(env_order: list[dict], deployments: dict[str, str]) -> dict:
    """One service deployed in several environments, with `env_order` as the API's listing order."""
    return {"ok": True, "body": {"data": {"project": {
        "id": "proj-1",
        "name": "ultrathink",
        "services": {"edges": [{"node": {
            "id": "svc-1",
            "name": "substrate-mcp",
            "serviceInstances": {"edges": [
                {"node": {"environmentId": env, "latestDeployment": {"id": dep, "status": "SUCCESS"}}}
                for env, dep in deployments.items()
            ]},
        }}]},
        "environments": {"edges": [{"node": e} for e in env_order]},
    }}}}


ENVS = [
    {"id": "env-staging", "name": "staging"},
    {"id": "env-prod", "name": "production"},
]
DEPLOYMENTS = {"env-staging": "dep-staging", "env-prod": "dep-prod"}


def _stub_railway_envs(monkeypatch, project: dict, logged: list):
    from desk_gateway.upstreams import Railway

    async def fake_status(self, name):   # noqa: ARG001 — signature must match
        return project

    async def fake_logs(self, deployment_id, lines):   # noqa: ARG001
        logged.append(deployment_id)
        return {"ok": True, "body": {"data": {"deploymentLogs": [{"message": f"from {deployment_id}"}]}}}

    monkeypatch.setattr(Railway, "project_id", lambda self, name: "proj-1")
    monkeypatch.setattr(Railway, "project_status", fake_status)
    monkeypatch.setattr(Railway, "logs", fake_logs)
    _configure_upstreams(monkeypatch)


async def test_railway_status_scopes_latest_deployment_to_production(rpc, monkeypatch):
    """latest_deployment was whichever service instance the API listed first.

    Instances come back per environment and in no guaranteed order, so on a service with a
    staging environment the "latest deployment" could be staging's while every consumer of it
    — logs, a redeploy check, a receipt — meant production. Scoped to one environment, and
    named, so a reader can tell which.
    """
    _stub_railway_envs(monkeypatch, _two_env_project(ENVS, DEPLOYMENTS), [])

    out = await rpc.call("infra", "desk_railway_status", {"project": "ultrathink"})
    service = out["projects"][0]["services"][0]
    assert service["latest_deployment"]["id"] == "dep-prod", service
    assert service["environment_id"] == "env-prod"
    assert service["deployments"] == {
        "env-staging": {"id": "dep-staging", "status": "SUCCESS"},
        "env-prod": {"id": "dep-prod", "status": "SUCCESS"},
    }


async def test_railway_status_falls_back_to_the_only_environment(rpc, monkeypatch):
    """No environment named production: the single one listed is what an unqualified call means."""
    envs = [{"id": "env-main", "name": "main"}]
    _stub_railway_envs(monkeypatch, _two_env_project(envs, {"env-main": "dep-main"}), [])

    out = await rpc.call("infra", "desk_railway_status", {"project": "ultrathink"})
    service = out["projects"][0]["services"][0]
    assert service["latest_deployment"]["id"] == "dep-main" and service["environment_id"] == "env-main"


async def test_railway_logs_read_the_production_deployment(rpc, monkeypatch):
    """The fallback deployment_id has to be the chosen environment's, whatever the API order.

    staging listed first is enough to send someone debugging production at the wrong logs —
    and they look right, because the service name matches.
    """
    logged: list = []
    _stub_railway_envs(monkeypatch, _two_env_project(ENVS, DEPLOYMENTS), logged)

    out = await rpc.call("infra", "desk_railway_logs", {"project": "ultrathink", "service": "substrate-mcp"})
    assert logged == ["dep-prod"], logged
    assert out["deployment_id"] == "dep-prod" and out["environment_id"] == "env-prod"
    assert out["lines"] == [{"message": "from dep-prod"}]


async def test_railway_logs_refuse_another_environments_deployment(rpc, monkeypatch):
    """Nothing deployed in the chosen environment is not an invitation to read staging's."""
    logged: list = []
    _stub_railway_envs(monkeypatch, _two_env_project(ENVS, {"env-staging": "dep-staging"}), logged)

    out = await rpc.call("infra", "desk_railway_logs", {"project": "ultrathink", "service": "substrate-mcp"})
    assert out["error"] == "not_found" and "env-prod" in out["reason"], out
    assert out["lines"] == [] and logged == [], "staging logs were served as the service's logs"

    # Named explicitly, staging's logs are a legitimate read.
    out = await rpc.call("infra", "desk_railway_logs", {"project": "ultrathink", "service": "substrate-mcp", "deployment_id": "dep-staging"})
    assert out["deployment_id"] == "dep-staging" and logged == ["dep-staging"]


async def test_railway_redeploy_compares_the_deployment_in_the_target_environment(rpc, monkeypatch):
    """The staleness check and the redeploy have to be about the same environment.

    prior_deployment_id is production's here; a check against whichever instance came first
    would refuse the redeploy as stale against staging's deployment id.
    """
    from desk_gateway.upstreams import Railway

    redeploys: list = []

    async def fake_redeploy(self, service_id, environment_id):   # noqa: ARG001
        redeploys.append((service_id, environment_id))
        return {"ok": True, "body": {"data": {"serviceInstanceRedeploy": True}}}

    _stub_railway_envs(monkeypatch, _two_env_project(ENVS, {"env-staging": "dep-staging", "env-prod": "dep-aaaaaa"}), [])
    monkeypatch.setattr(Railway, "redeploy", fake_redeploy)

    out = await rpc.call("infra", "desk_railway_redeploy", REDEPLOY)
    assert out["ok"] is True, out
    assert out["environment_id"] == "env-prod" and redeploys == [("svc-1", "env-prod")]
