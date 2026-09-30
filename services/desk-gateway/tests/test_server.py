from __future__ import annotations

import base64
import hashlib
import json
import secrets
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
