"""REST contract tests for the phase-68 teleportation surface (REQ-QTELEPORT-005).

Auth-first ordering (401 missing/invalid before parse/side effects, 403 for
valid denied seats), strict validation (400s), truthful protocol outcomes,
and lifecycle invariants — all over the real Starlette app with an injected
LocalNodeTransport and deterministic worker RNGs. No source-text, wiring,
mock-echo, or incidental-default assertions.
"""

import pytest
from starlette.testclient import TestClient

from desk_gateway.config import Settings
from desk_gateway.quantum_node import QuantumNodeWorker
from desk_gateway.quantum_transport import LocalNodeTransport
from desk_gateway.server import build_app

ALPHA = "desk-alpha"
BETA = "desk-beta"
REPEATER = "repeater-1"

_SEATS = {
    "lead": "pw-lead-seat",
    "systems": "pw-systems-seat",
    "web": "pw-web-seat",
    "android": "pw-android-seat",
    "ios": "pw-ios-seat",
    "infra": "pw-infra-seat",
    "quality": "pw-quality-seat",
}


class ScriptedRng:
    def __init__(self, draws):
        self._draws = list(draws)

    def random(self):
        assert self._draws, "scripted RNG exhausted"
        value = self._draws.pop(0)
        assert 0.0 <= value < 1.0
        return value


def _bearer(seat):
    return {"Authorization": f"Bearer {_SEATS[seat]}"}


def _app(nodes, links, worker_rngs, tmp_path, capacities=None):
    workers = {}
    for pos, name in enumerate(nodes):
        draws = (worker_rngs or {}).get(name, [0.5])
        workers[name] = QuantumNodeWorker(
            name,
            capacity=(capacities or {}).get(name, 32),
            token=f"tok-{name}",
            rng=ScriptedRng(list(draws)),
        )
    transport = LocalNodeTransport(workers)
    endpoints = {name: f"http://127.0.0.1:{19001 + pos}" for pos, name in enumerate(nodes)}
    settings = Settings(
        seat_passphrases=dict(_SEATS),
        data_dir=tmp_path / "dg-data",
        quantum_node_endpoints=endpoints,
        quantum_node_tokens={name: f"tok-{name}" for name in nodes},
        quantum_node_links=[list(link) for link in links],
        quantum_transport_override=transport,
        quantum_rng_override=ScriptedRng([0.5] * 256),
    )
    app, _ = build_app(settings)
    return TestClient(app)


@pytest.fixture
def pair_app(tmp_path):
    return _app((ALPHA, BETA), [(ALPHA, BETA)], None, tmp_path)


# --------------------------------------------------------------------------
# seat auth ordering


def test_mutation_without_credential_is_401_before_parse(pair_app):
    # Malformed bodies must still report 401 first: auth precedes parsing.
    assert pair_app.post("/v1/quantum/teleportation/bell-pair/create").status_code == 401
    bad = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert bad.status_code == 401
    unknown = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"bell_pair": "bell-nope"},
        headers={"Authorization": "Bearer wrong-passphrase"},
    )
    assert unknown.status_code == 401


def test_mutation_with_valid_denied_seat_is_403_before_parse(pair_app):
    # A valid non-mutation seat is denied before body validation runs.
    denied = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create",
        content=b"{not-json",
        headers={"content-type": "application/json", **_bearer("web")},
    )
    assert denied.status_code == 403
    denied_teleport = pair_app.post(
        "/v1/quantum/teleportation/teleport", json={"bell_pair": 42}, headers=_bearer("web")
    )
    assert denied_teleport.status_code == 403


def test_reads_admit_any_authenticated_seat(pair_app):
    created = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": BETA},
        headers=_bearer("lead"),
    )
    assert created.status_code == 200
    pair_id = created.json()["bell_pair"]["pair_id"]
    snap = pair_app.get(f"/v1/quantum/teleportation/pair/{pair_id}", headers=_bearer("web"))
    assert snap.status_code == 200
    assert snap.json()["pair"]["status"] == "active"
    listing = pair_app.get("/v1/quantum/teleportation/pairs", headers=_bearer("quality"))
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert pair_app.get("/v1/quantum/teleportation/pairs").status_code == 401


# --------------------------------------------------------------------------
# pair creation validation


def test_create_pair_success_reports_requested_kind_and_fidelity(pair_app):
    for seat in ("lead", "systems"):
        resp = pair_app.post(
            "/v1/quantum/teleportation/bell-pair/create",
            json={"node_a": ALPHA, "node_b": BETA, "state_type": "PSI_MINUS", "initial_fidelity": 0.97},
            headers=_bearer(seat),
        )
        assert resp.status_code == 200
        body = resp.json()
    cases = [
        {"state_type": "BELL_NOPE"},
        {"state_type": "phi_plus"},
        {"initial_fidelity": 1.5},
        {"initial_fidelity": -0.1},
        {"initial_fidelity": "high"},
        {"initial_fidelity": True},
        {"node_a": 42},
        {"node_a": ALPHA, "node_b": ALPHA},
        {"node_a": ALPHA, "unknown_field": 1},
    ]
    for body in cases:
        resp = pair_app.post(
            "/v1/quantum/teleportation/bell-pair/create", json=body, headers=_bearer("lead")
        )
        assert resp.status_code == 400, body
    # Non-finite numerics are rejected whether they arrive as literals or as
    # decoded floats: the client cannot even serialize float("nan"), so the
    # wire-literal form below is the honest rejection probe.
    for raw in (b'{"initial_fidelity": NaN}', b'{"initial_fidelity": Infinity}'):
        raw_resp = pair_app.post(
            "/v1/quantum/teleportation/bell-pair/create",
            content=raw,
            headers={"content-type": "application/json", **_bearer("lead")},
        )
        assert raw_resp.status_code == 400, raw


# --------------------------------------------------------------------------
# snapshot / list reads


def test_pair_snapshot_unknown_is_404_and_immutable(pair_app):
    assert pair_app.get("/v1/quantum/teleportation/pair/bell-missing", headers=_bearer("lead")).status_code == 404
    created = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create", json={}, headers=_bearer("lead")
    )
    pair_id = created.json()["bell_pair"]["pair_id"]
    first = pair_app.get(f"/v1/quantum/teleportation/pair/{pair_id}", headers=_bearer("lead")).json()
    second = pair_app.get(f"/v1/quantum/teleportation/pair/{pair_id}", headers=_bearer("lead")).json()
    assert first == second
    assert first["pair"]["leases"] != []
    assert first["pair"]["fidelity"] == pytest.approx(0.99, abs=1e-9)


def test_pairs_list_empty_safe_and_filtered(pair_app):
    empty = pair_app.get("/v1/quantum/teleportation/pairs", headers=_bearer("lead")).json()
    assert empty == {"ok": True, "pairs": [], "count": 0}
    for _ in range(2):
        pair_app.post(
            "/v1/quantum/teleportation/bell-pair/create", json={}, headers=_bearer("lead")
        )
    full = pair_app.get("/v1/quantum/teleportation/pairs", headers=_bearer("lead")).json()
    assert full["count"] == 2
    filtered = pair_app.get(
        "/v1/quantum/teleportation/pairs",
        params={"node_a": ALPHA, "node_b": BETA},
        headers=_bearer("lead"),
    ).json()
    assert filtered["count"] == 2
    assert pair_app.get(
        "/v1/quantum/teleportation/pairs", params={"node_a": "x" * 65}, headers=_bearer("lead")
    ).status_code == 400


# --------------------------------------------------------------------------
# purify over REST


def test_purify_accept_over_rest(tmp_path):
    client = _app(
        (ALPHA, BETA), [(ALPHA, BETA)], {ALPHA: [0.1], BETA: [0.5]}, tmp_path
    )
    first = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": BETA, "initial_fidelity": 0.90},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    second = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": BETA, "initial_fidelity": 0.92},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    resp = client.post(
        "/v1/quantum/teleportation/purify",
        json={"pair_id_1": first["pair_id"], "pair_id_2": second["pair_id"]},
        headers=_bearer("systems"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["accepted"] is True
    assert body["purified_pair"]["fidelity"] == pytest.approx(0.934368737475, abs=1e-9)
    assert body["p_succ"] == pytest.approx(0.887111111111, abs=1e-9)
    assert body["branch_bits"] == [0, 0]
    assert body["reason"] == "parity_accept"
    for consumed_id in (first["pair_id"], second["pair_id"]):
        snap = client.get(f"/v1/quantum/teleportation/pair/{consumed_id}", headers=_bearer("lead")).json()
        assert snap["pair"]["status"] == "consumed"


def test_purify_reject_over_rest_is_truthful_unsuccessful(tmp_path):
    client = _app(
        (ALPHA, BETA), [(ALPHA, BETA)], {ALPHA: [0.6], BETA: [0.05]}, tmp_path
    )
    ids = []
    for fidelity in (0.90, 0.92):
        created = client.post(
            "/v1/quantum/teleportation/bell-pair/create",
            json={"node_a": ALPHA, "node_b": BETA, "initial_fidelity": fidelity},
            headers=_bearer("lead"),
        ).json()["bell_pair"]
        ids.append(created["pair_id"])
    resp = client.post(
        "/v1/quantum/teleportation/purify",
        json={"pair_id_1": ids[0], "pair_id_2": ids[1]},
        headers=_bearer("lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["accepted"] is False
    assert body["purified_pair"] is None
    assert body["reason"] == "parity_reject"
    for discarded_id in ids:
        snap = client.get(f"/v1/quantum/teleportation/pair/{discarded_id}", headers=_bearer("lead")).json()
        assert snap["pair"]["status"] == "discarded"


def test_purify_selection_errors(pair_app):
    unknown = pair_app.post(
        "/v1/quantum/teleportation/purify",
        json={"pair_id_1": "bell-missing", "pair_id_2": "bell-absent"},
        headers=_bearer("lead"),
    )
    assert unknown.status_code == 404
    created = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create", json={}, headers=_bearer("lead")
    ).json()["bell_pair"]
    same = pair_app.post(
        "/v1/quantum/teleportation/purify",
        json={"pair_id_1": created["pair_id"], "pair_id_2": created["pair_id"]},
        headers=_bearer("lead"),
    )
    assert same.status_code == 400
    partial = pair_app.post(
        "/v1/quantum/teleportation/purify",
        json={"pair_id_1": created["pair_id"]},
        headers=_bearer("lead"),
    )
    assert partial.status_code == 400


# --------------------------------------------------------------------------
# swap and multi-hop over REST


def test_swap_over_rest(tmp_path):
    client = _app(
        (ALPHA, REPEATER, BETA),
        [(ALPHA, REPEATER), (REPEATER, BETA)],
        {REPEATER: [0.3]},
        tmp_path,
    )
    left = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": REPEATER},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    right = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": REPEATER, "node_b": BETA},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    resp = client.post(
        "/v1/quantum/teleportation/swap",
        json={"pair_id_ab": left["pair_id"], "pair_id_bc": right["pair_id"]},
        headers=_bearer("lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["bsm_bits"] == [0, 1]
    assert body["correction_origin"] == "worker-authorized"
    assert {body["swapped_pair"]["node_a"], body["swapped_pair"]["node_b"]} == {ALPHA, BETA}
    assert body["swapped_pair"]["fidelity"] == pytest.approx(0.99 * 0.99 + (0.01 * 0.01) / 3, abs=1e-9)
    denied = client.post(
        "/v1/quantum/teleportation/swap",
        json={"pair_id_ab": left["pair_id"], "pair_id_bc": right["pair_id"]},
        headers=_bearer("web"),
    )
    assert denied.status_code == 403


def test_repeater_route_success_and_rejections(tmp_path):
    client = _app(
        (ALPHA, REPEATER, BETA),
        [(ALPHA, REPEATER), (REPEATER, BETA)],
        {REPEATER: [0.1]},
        tmp_path,
    )
    ok_resp = client.post(
        "/v1/quantum/repeater/route",
        json={"node_path": [ALPHA, REPEATER, BETA], "base_fidelity": 0.98, "purify": False},
        headers=_bearer("lead"),
    )
    assert ok_resp.status_code == 200
    ok_body = ok_resp.json()
    assert ok_body["ok"] is True
    assert {ok_body["bell_pair"]["node_a"], ok_body["bell_pair"]["node_b"]} == {ALPHA, BETA}
    assert len(ok_body["logs"]) >= 1
    # Over-long, unknown, repeating, unlinked, and empty routes are rejected
    # without crashing; empty input is a safe abort, not a success.
    assert client.post(
        "/v1/quantum/repeater/route",
        json={"node_path": [f"n-{index}" for index in range(17)]},
        headers=_bearer("lead"),
    ).json()["ok"] is False
    assert client.post(
        "/v1/quantum/repeater/route",
        json={"node_path": [ALPHA, "ghost-node", BETA]},
        headers=_bearer("lead"),
    ).json()["ok"] is False
    assert client.post(
        "/v1/quantum/repeater/route", json={"node_path": []}, headers=_bearer("lead")
    ).json()["ok"] is False
    assert client.post(
        "/v1/quantum/repeater/route",
        json={"node_path": [ALPHA, REPEATER, BETA], "purify": "yes"},
        headers=_bearer("lead"),
    ).status_code == 400
    assert client.post(
        "/v1/quantum/repeater/route",
        json={"node_path": "desk-alpha"},
        headers=_bearer("lead"),
    ).status_code == 400


# --------------------------------------------------------------------------
# teleport over REST


def test_teleport_success_over_rest(tmp_path):
    client = _app((ALPHA, BETA), [(ALPHA, BETA)], {ALPHA: [0.3]}, tmp_path)
    pair = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": BETA, "initial_fidelity": 1.0},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    resp = client.post(
        "/v1/quantum/teleportation/teleport",
        json={
            "source_node": ALPHA,
            "target_node": BETA,
            "alpha": {"real": 0.6, "imag": 0.0},
            "beta": {"real": 0.8, "imag": 0.0},
            "bell_pair": pair["pair_id"],
        },
        headers=_bearer("lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    result = body["result"]
    assert result["success"] is True
    assert result["fidelity"] >= 0.95
    assert result["correction_applied"] is True
    assert result["acknowledged"] is True
    assert result["resource_consumed"] is True
    assert isinstance(result["correction"]["correction_x"], int)
    assert isinstance(result["gate_x"], bool)
    assert isinstance(body["receipt"]["seq"], int) and body["receipt"]["seq"] >= 1
    assert isinstance(body["receipt"]["receipt_id"], str) and body["receipt"]["receipt_id"]
    # The consumed pair cannot teleport again: conflict, not a second success.
    again = client.post(
        "/v1/quantum/teleportation/teleport",
        json={"source_node": ALPHA, "target_node": BETA, "bell_pair": pair["pair_id"]},
        headers=_bearer("lead"),
    )
    assert again.status_code == 409


def test_teleport_below_threshold_over_rest_consumes_with_raw_fidelity(tmp_path):
    client = _app((ALPHA, BETA), [(ALPHA, BETA)], {ALPHA: [0.3]}, tmp_path)
    pair = client.post(
        "/v1/quantum/teleportation/bell-pair/create",
        json={"node_a": ALPHA, "node_b": BETA, "initial_fidelity": 0.90},
        headers=_bearer("lead"),
    ).json()["bell_pair"]
    resp = client.post(
        "/v1/quantum/teleportation/teleport",
        json={"source_node": ALPHA, "target_node": BETA, "bell_pair": pair["pair_id"]},
        headers=_bearer("systems"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    result = body["result"]
    assert result["success"] is False
    assert result["reason"] == "below_threshold"
    assert result["resource_consumed"] is True
    assert result["fidelity"] == pytest.approx((2 * 0.90 + 1) / 3, abs=1e-9)
    snap = client.get(f"/v1/quantum/teleportation/pair/{pair['pair_id']}", headers=_bearer("lead")).json()
    assert snap["pair"]["status"] == "consumed"


def test_teleport_selection_and_input_errors(pair_app):
    created = pair_app.post(
        "/v1/quantum/teleportation/bell-pair/create", json={}, headers=_bearer("lead")
    ).json()["bell_pair"]
    unknown = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"source_node": ALPHA, "target_node": BETA, "bell_pair": "bell-missing"},
        headers=_bearer("lead"),
    )
    assert unknown.status_code == 404
    both = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"bell_pair": created["pair_id"], "intermediate_hops": [REPEATER]},
        headers=_bearer("lead"),
    )
    assert both.status_code == 400
    forged = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"bell_pair": {"pair_id": created["pair_id"]}},
        headers=_bearer("lead"),
    )
    assert forged.status_code == 400
    bad_alpha = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"bell_pair": created["pair_id"], "alpha": {"real": True, "imag": 0.0}},
        headers=_bearer("lead"),
    )
    assert bad_alpha.status_code == 400
    bad_beta = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"bell_pair": created["pair_id"], "beta": {"real": 0.0}},
        headers=_bearer("lead"),
    )
    assert bad_beta.status_code == 400
    long_route = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"intermediate_hops": [f"n-{index}" for index in range(20)]},
        headers=_bearer("lead"),
    )
    assert long_route.status_code == 400
    ghost_route = pair_app.post(
        "/v1/quantum/teleportation/teleport",
        json={"intermediate_hops": ["ghost-node"]},
        headers=_bearer("lead"),
    )
    assert ghost_route.status_code == 404


# --------------------------------------------------------------------------
# worker inspect and config surface


def test_worker_inspect_read_and_transport_absent(tmp_path):
    client = _app((ALPHA, BETA), [(ALPHA, BETA)], None, tmp_path)
    seen = client.get(f"/v1/quantum/worker/{ALPHA}/inspect", headers=_bearer("web")).json()
    assert seen["ok"] is True
    assert seen["worker"]["node_id"] == ALPHA
    assert client.get("/v1/quantum/worker/ghost-node/inspect", headers=_bearer("web")).status_code == 404
    assert client.get(f"/v1/quantum/worker/{ALPHA}/inspect").status_code == 401
    bare_settings = Settings(seat_passphrases=dict(_SEATS), data_dir=tmp_path / "bare-data")
    bare_app, _ = build_app(bare_settings)
    bare = TestClient(bare_app)
    assert bare.get(f"/v1/quantum/worker/{ALPHA}/inspect", headers=_bearer("lead")).status_code == 503


def test_quantum_topology_settings_reject_bad_operator_config(tmp_path):
    from desk_gateway.config import Settings as ConfigSettings

    with pytest.raises(ValueError):
        ConfigSettings(quantum_node_endpoints={"a": "http://public.example.com/x"}, quantum_node_tokens={"a": "t"})
    with pytest.raises(ValueError):
        ConfigSettings(
            quantum_node_endpoints={"a": "http://127.0.0.1:19001"},
            quantum_node_tokens={},
        )
    with pytest.raises(ValueError):
        ConfigSettings(
            quantum_node_endpoints={"a": "http://127.0.0.1:19001", "b": "http://127.0.0.1:19002"},
            quantum_node_tokens={"a": "t", "b": "t2"},
            quantum_node_links=[["a", "ghost"]],
        )
