"""Worker / transport / resource behavior tests for phase 68-02.

Consumer-visible math, lifecycle, auth, replay, timeout, and capacity
behavior only: no source-text, wiring, or mock-echo assertions. All async
workflows run via ``asyncio.run`` so these tests need no asyncio plugin
mode. ``LocalNodeTransport`` checks are contract tests, never distributed
proof (parent owns separate-process acceptance).
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SRC = Path(__file__).resolve().parents[1] / "services" / "desk-gateway" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desk_gateway import quantum_state
from desk_gateway.quantum_node import (
    MAX_QKD_SESSIONS,
    QKD_OWNER_ACTIONS,
    QKD_STEP_ACTIONS,
    QuantumNodeError,
    QuantumNodeWorker,
    build_node_parser,
    create_node_app,
    decode_bits,
    decode_density,
    decode_indices,
    decode_signals,
    encode_bits,
    encode_density,
    encode_indices,
    encode_signals,
    worker_token_from_env,
)
from desk_gateway.quantum_teleportation import (
    BellPairPool,
    BellStateType,
    EntanglementPurifier,
    EntanglementSwapper,
    QuantumRepeaterMesh,
    QuantumResourceError,
    QuantumTeleportationProtocol,
    TeleportationResult,
)
from desk_gateway.quantum_transport import (
    LocalNodeTransport,
    NodeCommandFailed,
    NodeTransportAmbiguous,
    NodeTransportDeadline,
    NodeTransportUnavailable,
    RemoteNodeTransport,
)


# --------------------------------------------------------------------------
# harness


class ScriptedRng:
    def __init__(self, draws):
        self._draws = list(draws)

    def random(self):
        assert self._draws, "scripted RNG exhausted"
        value = self._draws.pop(0)
        assert 0.0 <= value < 1.0
        return value


def _run(awaitable):
    return asyncio.run(awaitable)


def _setup(nodes=("alice", "bob"), capacities=None, rngs=None, sink=True):
    workers = {}
    for name in nodes:
        workers[name] = QuantumNodeWorker(
            name,
            capacity=(capacities or {}).get(name, 8),
            token=f"tok-{name}",
            rng=(rngs or {}).get(name),
        )
    transport = LocalNodeTransport(workers)
    events = []

    async def append_event(event):
        events.append(dict(event))
        return {"receipt_id": f"r-{len(events)}", "seq": len(events)}

    pool = BellPairPool(transport=transport, append_event=append_event if sink else None)
    return SimpleNamespace(workers=workers, transport=transport, pool=pool, events=events)


async def _pair(pool, node_a="alice", node_b="bob", kind=BellStateType.PHI_PLUS, fidelity=1.0):
    return await pool.create_pair(node_a, node_b, kind, fidelity)


def _proto(ctx, mesh=None):
    return QuantumTeleportationProtocol(mesh, pool=ctx.pool, transport=ctx.transport)


# --------------------------------------------------------------------------
# worker ownership / auth / replay


def test_worker_reserve_enforces_capacity():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=1, token="t")
        first = await worker.reserve(
            operation_id="op-1", resource_id="res-a", count=1, token="t", node="n1", instance=worker.instance_id,
        )
        assert len(first["leases"]) == 1
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(
                operation_id="op-2", resource_id="res-b", count=1, token="t", node="n1", instance=worker.instance_id,
            )
        assert exc.value.code == "capacity_exhausted"
        assert exc.value.status == 409

    _run(body())


def test_worker_rejects_bad_credential_scope_and_instance():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        good = {"operation_id": "op-1", "resource_id": "r", "count": 1,
                "token": "t", "node": "n1", "instance": worker.instance_id}
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(**{**good, "token": "wrong"})
        assert exc.value.status == 401
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(**{**good, "node": "other"})
        assert exc.value.code == "wrong_node"
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(**{**good, "instance": "stale"})
        assert exc.value.code == "stale_instance"

    _run(body())


def test_worker_operation_replay_rules():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        kwargs = {"operation_id": "op-1", "resource_id": "r", "count": 1,
                  "token": "t", "node": "n1", "instance": worker.instance_id}
        first = await worker.reserve(**kwargs)
        second = await worker.reserve(**kwargs)
        assert first["leases"] == second["leases"]
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(**{**kwargs, "count": 2})
        assert exc.value.code == "operation_conflict"

    _run(body())


def test_worker_correction_is_one_shot():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        lease = held["leases"][0]
        zero = [[ [1.0, 0.0], [0.0, 0.0] ], [ [0.0, 0.0], [0.0, 0.0] ]]
        await worker.stage_conditional_state(
            operation_id="op-s", lease_id=lease, session_id="sess", rho_matrix=zero, **scope)
        first = await worker.correct(
            operation_id="op-c1", lease_id=lease, session_id="sess",
            bsm_x=1, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert first["correction_x"] == 1 and first["correction_z"] == 0
        assert first["gate_x"] is True and first["gate_z"] is False
        # X|0><0|X = |1><1|.
        assert first["rho_matrix"][1][1] == [1.0, 0.0]
        second = await worker.correct(
            operation_id="op-c2", lease_id=lease, session_id="sess",
            bsm_x=1, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert second["rho_matrix"] == first["rho_matrix"]
        assert first["acknowledgement"] == "ack-op-c1"
        assert second["acknowledgement"] == "ack-op-c2"
        replay = await worker.correct(
            operation_id="op-c2", lease_id=lease, session_id="sess",
            bsm_x=1, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert replay == second
        with pytest.raises(QuantumNodeError) as exc:
            await worker.correct(
                operation_id="op-c2", lease_id=lease, session_id="sess",
                bsm_x=0, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert exc.value.code == "operation_conflict"
        with pytest.raises(QuantumNodeError) as exc:
            await worker.correct(
                operation_id="op-c3", lease_id=lease, session_id="sess",
                bsm_x=0, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert exc.value.code == "correction_conflict"

    _run(body())


def test_worker_release_applies_at_most_once():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        await worker.release(operation_id="op-x", lease_ids=held["leases"], **scope)
        with pytest.raises(QuantumNodeError) as exc:
            await worker.release(operation_id="op-y", lease_ids=held["leases"], **scope)
        assert exc.value.code == "already_released"

    _run(body())


def test_worker_inspect_exposes_no_state_or_secrets():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        zero = [[ [1.0, 0.0], [0.0, 0.0] ], [ [0.0, 0.0], [0.0, 0.0] ]]
        await worker.stage_conditional_state(
            operation_id="op-s", lease_id=held["leases"][0], session_id="sess", rho_matrix=zero, **scope)
        seen = await worker.inspect(**scope)
        dumped = json.dumps(seen)
        assert "tok" not in dumped.replace("token", "")
        assert "rho" not in dumped
        assert seen["active_count"] == 1
        assert seen["leases"][0]["state"] == "staged"

    _run(body())


def test_worker_measure_drives_branch_and_destroys_lease():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t", rng=ScriptedRng([0.3]))
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        answer = await worker.measure(
            operation_id="op-m", lease_ids=held["leases"], token="t", node="n1",
            instance=worker.instance_id,
            branch_probabilities=[0.25, 0.25, 0.25, 0.25],
            branch_bits=[[0, 0], [0, 1], [1, 0], [1, 1]],
        )
        assert answer["bits"] == [0, 1]
        assert answer["probability"] == pytest.approx(0.25)
        assert answer["acknowledgement"] == "ack-op-m"
        seen = await worker.inspect(**scope)
        assert seen["active_count"] == 1
        assert seen["lease_count"] == 1
        assert seen["leases"][0]["state"] == "measured"

    _run(body())


def test_cli_carries_no_credential_argv(monkeypatch):
    parser = build_node_parser()
    args = parser.parse_args(["--node", "n1", "--capacity", "4", "--port", "8899"])
    assert args.node == "n1" and args.capacity == 4 and args.port == 8899
    with pytest.raises(SystemExit):
        parser.parse_args(["--node", "n1", "--token", "x"])
    monkeypatch.setenv("QUANTUM_NODE_TOKEN", "  scoped-secret  ")
    assert worker_token_from_env() == "scoped-secret"


def test_asgi_worker_auth_capacity_and_body_cap():
    import httpx

    async def body():
        worker = QuantumNodeWorker("web", capacity=1, token="tok-web")
        app = create_node_app(worker)

        def envelope(node="web", instance=None, operation_id="op-1", **extra):
            body = {"node": node, "instance": instance or worker.instance_id,
                    "operation_id": operation_id}
            body.update(extra)
            return body

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            bad = await client.post("/v1/node/reserve", json=envelope(resource_id="r", count=1),
                                    headers={"Authorization": "Bearer wrong"})
            assert bad.status_code == 401
            first = await client.post("/v1/node/reserve", json=envelope(resource_id="r", count=1),
                                      headers={"Authorization": "Bearer tok-web"})
            assert first.status_code == 200
            second = await client.post("/v1/node/reserve", json=envelope(operation_id="op-2", resource_id="s", count=1),
                                       headers={"Authorization": "Bearer tok-web"})
            assert second.status_code == 409
            huge = await client.post("/v1/node/inspect", content=b"x" * (64 * 1024 + 1),
                                     headers={"Authorization": "Bearer tok-web",
                                              "Content-Type": "application/json"})
            assert huge.status_code == 413

    _run(body())


# --------------------------------------------------------------------------
# transport


def _remote(handler, endpoints=None, tokens=None, **kwargs):
    import httpx

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x")
    return RemoteNodeTransport(
        endpoints or {"n": "http://127.0.0.1:8891"}, tokens or {"n": "s3cret"},
        client=client, **kwargs,
    )


def test_remote_uses_fixed_destination_and_scoped_token():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content.decode())
        from httpx import Response
        return Response(200, json={"ok": True, "instance_id": "i-1", "active_count": 0, "leases": []})

    async def body():
        transport = _remote(handler)
        payload = await transport.inspect("n")
        assert payload["instance_id"] == "i-1"
        assert seen["url"] == "http://127.0.0.1:8891/v1/node/inspect"
        assert seen["auth"] == "Bearer s3cret"
        assert "url" not in seen["body"] and "token" not in seen["body"]
        await transport.aclose()

    _run(body())


def test_remote_client_defaults_and_lifespan_close():
    async def body():
        transport = RemoteNodeTransport({"n": "https://node.example:8891"}, {"n": "s3cret"})
        assert transport.client is None
        client = await transport._acquire()
        assert client.trust_env is False
        assert client.follow_redirects is False
        first = await transport._acquire()
        assert first is client
        await transport.aclose()
        assert client.is_closed
        assert transport.client is None

    _run(body())


def test_remote_failure_mapping():
    import httpx

    def timeout_handler(request):
        raise httpx.ConnectTimeout("slow")

    def refused_handler(request):
        return httpx.Response(409, json={"ok": False, "error": "capacity_exhausted", "detail": "full"})

    async def body():
        transport = _remote(timeout_handler)
        with pytest.raises(NodeTransportAmbiguous):
            await transport.reserve("n", operation_id="op-1", resource_id="r", count=1, instance="i")
        with pytest.raises(NodeTransportDeadline):
            await transport.inspect("n")
        await transport.aclose()

        transport2 = _remote(refused_handler)
        with pytest.raises(NodeCommandFailed) as exc:
            await transport2.reserve("n", operation_id="op-1", resource_id="r", count=1, instance="i")
        assert exc.value.code == "capacity_exhausted"
        assert exc.value.status == 409
        await transport2.aclose()

    _run(body())


def test_remote_rejects_bad_endpoints_and_unknown_nodes():
    with pytest.raises(ValueError):
        RemoteNodeTransport({"n": "http://node.example:8891"}, {"n": "t"})
    with pytest.raises(ValueError):
        RemoteNodeTransport({"n": "http://127.0.0.1:8891/x"}, {"n": "t"})
    with pytest.raises(ValueError):
        RemoteNodeTransport({"n": "http://127.0.0.1:8891"}, {})
    RemoteNodeTransport({"n": "http://127.0.0.1:8891"}, {"n": "t"})
    RemoteNodeTransport({"n": "https://node.example:8891"}, {"n": "t"})

    async def body():
        transport = _remote(lambda request: None)
        with pytest.raises(NodeTransportUnavailable):
            await transport.inspect("ghost")
        with pytest.raises(NodeTransportUnavailable):
            await transport.reserve("n", operation_id="op-1", resource_id="r", count=1)
        await transport.aclose()

    _run(body())


def test_remote_cancellation_propagates():
    import httpx

    async def handler(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json={"ok": True})

    async def body():
        transport = _remote(handler)
        task = asyncio.ensure_future(transport.inspect("n"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await transport.aclose()

    _run(body())


def test_local_transport_unknown_node():
    async def body():
        ctx = _setup(nodes=("alice",))
        with pytest.raises(NodeTransportUnavailable):
            await ctx.transport.inspect("ghost")

    _run(body())


# --------------------------------------------------------------------------
# pool lifecycle / mesh


def test_pool_create_holds_worker_leases_and_derived_fidelity():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool, fidelity=0.99)
        assert ctx.pool.status_of(pair.pair_id).value == "active"
        assert pair.fidelity == pytest.approx(0.99, abs=1e-9)
        for node in ("alice", "bob"):
            seen = await ctx.transport.inspect(node)
            assert seen["active_count"] == 1
        snapshot = ctx.pool.snapshot(pair.pair_id)
        assert snapshot.fidelity == pytest.approx(0.99, abs=1e-9)

    _run(body())


def test_pool_over_capacity_fails_closed_without_registration():
    async def body():
        ctx = _setup(capacities={"alice": 1, "bob": 8})
        first = await _pair(ctx.pool)
        assert first is not None
        with pytest.raises(QuantumResourceError) as exc:
            await _pair(ctx.pool)
        assert exc.value.code == "worker_refused"
        assert len(ctx.pool.list_active_pairs()) == 1

    _run(body())


def test_mesh_duplicate_registration_never_resets():
    async def body():
        ctx = _setup()
        mesh = QuantumRepeaterMesh(ctx.pool)
        mesh.register_node("alice", "east")
        pair = await _pair(ctx.pool)
        with pytest.raises(QuantumResourceError) as exc:
            mesh.register_node("alice", "west")
        assert exc.value.code == "duplicate_node"
        assert ctx.pool.status_of(pair.pair_id).value == "active"
        assert mesh.nodes["alice"].cluster_region == "east"

    _run(body())


def test_mesh_rejects_bad_routes():
    async def body():
        ctx = _setup(nodes=("a", "r", "b"))
        mesh = QuantumRepeaterMesh(ctx.pool)
        for name in ("a", "r", "b"):
            mesh.register_node(name, "east")
        mesh.register_link("a", "r")
        mesh.register_link("r", "b")
        ok, pair, _ = await mesh.establish_multi_hop_entanglement(["a", "ghost", "b"])
        assert ok is False and pair is None
        ok, pair, _ = await mesh.establish_multi_hop_entanglement(["a", "r", "a"])
        assert ok is False and pair is None
        ok, pair, _ = await mesh.establish_multi_hop_entanglement(["a", "b"])
        assert ok is False and pair is None
        long_route = [f"n{i}" for i in range(17)]
        for name in long_route:
            try:
                mesh.register_node(name, "east")
            except QuantumResourceError:
                pass
        for left, right in zip(long_route, long_route[1:]):
            try:
                mesh.register_link(left, right)
            except QuantumResourceError:
                pass
        ok, pair, _ = await mesh.establish_multi_hop_entanglement(long_route)
        assert ok is False and pair is None
        assert ctx.pool.list_active_pairs() == []

    _run(body())


def test_pool_concurrent_reservation_has_one_winner():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool)

        async def attempt(tag):
            try:
                await ctx.pool.reserve_pairs((pair.pair_id,), operation_id=f"op-{tag}")
                return "won"
            except QuantumResourceError:
                return "lost"

        first, second = await asyncio.gather(attempt("a"), attempt("b"))
        assert sorted((first, second)) == ["lost", "won"]

    _run(body())


def test_mesh_two_hop_route_succeeds():
    async def body():
        ctx = _setup(nodes=("a", "r", "b"))
        mesh = QuantumRepeaterMesh(ctx.pool)
        for name in ("a", "r", "b"):
            mesh.register_node(name, "east")
        mesh.register_link("a", "r")
        mesh.register_link("r", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(["a", "r", "b"], purify_hops=False)
        assert ok is True and pair is not None
        assert {pair.node_a, pair.node_b} == {"a", "b"}
        assert logs

    _run(body())


def test_mesh_purification_rejection_aborts_route_without_reuse():
    async def body():
        ctx = _setup(
            nodes=("a", "r", "b"),
            rngs={"a": ScriptedRng([0.6]), "r": ScriptedRng([0.05])},
        )
        mesh = QuantumRepeaterMesh(ctx.pool)
        for name in ("a", "r", "b"):
            mesh.register_node(name, "east")
        mesh.register_link("a", "r")
        mesh.register_link("r", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(["a", "r", "b"], purify_hops=True)
        assert ok is False and pair is None
        assert any("aborted" in entry for entry in logs)
        assert ctx.pool.list_active_pairs() == []
        for name in ("a", "r", "b"):
            seen = await ctx.transport.inspect(name)
            assert seen["active_count"] == 0

    _run(body())


# --------------------------------------------------------------------------
# BBPSSW purification


def _werner_oracles(f1, f2):
    a = (1.0 - f1) / 3.0
    b = (1.0 - f2) / 3.0
    p_accept = (f1 + a) * (f2 + b) + 4.0 * a * b
    f_accept = (f1 * f2 + a * b) / p_accept
    return p_accept, f_accept


def test_purify_accept_transfers_survivor_and_keeps_untwirled_state():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.1]), "bob": ScriptedRng([0.5])})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is True
        assert result.protocol == "BBPSSW"
        assert result.branch_bits == (0, 0)
        p_accept, f_accept = _werner_oracles(0.90, 0.92)
        assert p_accept == pytest.approx(0.887111111111, abs=1e-9)
        assert f_accept == pytest.approx(0.934368737475, abs=1e-9)
        assert result.p_accept == pytest.approx(p_accept, abs=1e-9)
        assert result.output_fidelity == pytest.approx(f_accept, abs=1e-9)
        # Accept branches carry exactly half the acceptance weight by symmetry.
        assert result.branch_probability == pytest.approx(p_accept / 2, abs=1e-12)
        output = ctx.pool.get_pair(result.output_pair_id)
        assert output is not None
        rewernered = quantum_state.QuantumDensityMatrix.bell_mixture("PHI_PLUS", f_accept)
        worst = max(
            abs(output.rho.rows[i][j] - rewernered.rows[i][j]) for i in range(4) for j in range(4)
        )
        assert worst > 1e-6
        assert ctx.pool.status_of(first.pair_id).value == "consumed"
        assert ctx.pool.status_of(second.pair_id).value == "consumed"
        kinds = [event["event_type"] for event in ctx.events]
        assert "purify.accepted" in kinds

    _run(body())


def test_purify_reject_consumes_both_inputs_with_no_output():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.6]), "bob": ScriptedRng([0.05])})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is False
        assert result.output_pair_id is None
        assert result.branch_bits == (1, 0)
        p_accept, _ = _werner_oracles(0.90, 0.92)
        assert result.p_accept == pytest.approx(p_accept, abs=1e-9)
        assert result.branch_probability == pytest.approx((1 - p_accept) / 2, abs=1e-12)
        assert result.branch_probability == pytest.approx(0.056444444444, abs=1e-9)
        assert ctx.pool.status_of(first.pair_id).value == "discarded"
        assert ctx.pool.status_of(second.pair_id).value == "discarded"
        assert ctx.pool.list_active_pairs() == []
        for node in ("alice", "bob"):
            seen = await ctx.transport.inspect(node)
            assert seen["active_count"] == 0
        kinds = [event["event_type"] for event in ctx.events]
        assert "purify.rejected" in kinds

    _run(body())


def test_purify_rejects_same_resource_and_foreign_endpoints():
    async def body():
        ctx = _setup(nodes=("a", "b", "c"))
        purifier = EntanglementPurifier(ctx.pool)
        pair = await _pair(ctx.pool, "a", "b")
        with pytest.raises(QuantumResourceError) as exc:
            await purifier.purify(pair.pair_id, pair.pair_id)
        assert exc.value.code == "same_resource"
        other = await _pair(ctx.pool, "b", "c")
        with pytest.raises(QuantumResourceError) as exc:
            await purifier.purify(pair.pair_id, other.pair_id)
        assert exc.value.code == "endpoint_mismatch"
        assert ctx.pool.status_of(pair.pair_id).value == "active"
        assert ctx.pool.status_of(other.pair_id).value == "active"

    _run(body())


def test_purify_handles_reversed_orientation():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.1]), "bob": ScriptedRng([0.5])})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, "alice", "bob", fidelity=0.90)
        second = await _pair(ctx.pool, "bob", "alice", fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is True
        output = ctx.pool.get_pair(result.output_pair_id)
        assert {output.node_a, output.node_b} == {"alice", "bob"}

    _run(body())


# --------------------------------------------------------------------------
# swap


_SWAP_KINDS = ("PHI_PLUS", "PHI_MINUS", "PSI_PLUS", "PSI_MINUS")


def test_swap_covers_all_sixteen_frames():
    async def body():
        for kind_a in _SWAP_KINDS:
            for kind_b in _SWAP_KINDS:
                ctx = _setup(nodes=("a", "r", "c"), rngs={"r": ScriptedRng([0.1])})
                swapper = EntanglementSwapper(ctx.pool)
                left = await _pair(ctx.pool, "a", "r", getattr(BellStateType, kind_a))
                right = await _pair(ctx.pool, "r", "c", getattr(BellStateType, kind_b))
                result = await swapper.swap(left.pair_id, right.pair_id)
                assert result.accepted is True
                assert result.bsm_bits == (0, 0)
                assert result.output_fidelity == pytest.approx(1.0, abs=1e-9)
                assert (result.correction_x, result.correction_z) == (
                    quantum_state.BellState(kind_a).frame[0] ^ quantum_state.BellState(kind_b).frame[0],
                    quantum_state.BellState(kind_a).frame[1] ^ quantum_state.BellState(kind_b).frame[1],
                )
                output = ctx.pool.get_pair(result.output_pair_id)
                assert {output.node_a, output.node_b} == {"a", "c"}

    _run(body())


def test_swap_covers_all_bsm_branches_and_orientations():
    async def body():
        for draw, bits in ((0.1, (0, 0)), (0.3, (0, 1)), (0.6, (1, 0)), (0.8, (1, 1))):
            ctx = _setup(nodes=("a", "r", "c"), rngs={"r": ScriptedRng([draw])})
            swapper = EntanglementSwapper(ctx.pool)
            left = await _pair(ctx.pool, "r", "a")
            right = await _pair(ctx.pool, "c", "r")
            result = await swapper.swap(left.pair_id, right.pair_id)
            assert result.bsm_bits == bits
            assert result.output_fidelity == pytest.approx(1.0, abs=1e-9)

    _run(body())


def test_swap_noisy_inputs_match_werner_identity():
    async def body():
        ctx = _setup(nodes=("a", "r", "c"), rngs={"r": ScriptedRng([0.3])})
        swapper = EntanglementSwapper(ctx.pool)
        left = await _pair(ctx.pool, "a", "r", fidelity=0.98)
        right = await _pair(ctx.pool, "r", "c", fidelity=0.98)
        result = await swapper.swap(left.pair_id, right.pair_id)
        assert result.output_fidelity == pytest.approx(0.98 * 0.98 + (0.02 * 0.02) / 3, abs=1e-9)
        assert result.correction_origin == "worker-authorized"

    _run(body())


def test_swap_rejects_bad_topology():
    async def body():
        ctx = _setup(nodes=("a", "b", "c", "d"))
        swapper = EntanglementSwapper(ctx.pool)
        left = await _pair(ctx.pool, "a", "b")
        parallel = await _pair(ctx.pool, "a", "b")
        with pytest.raises(QuantumResourceError) as exc:
            await swapper.swap(left.pair_id, parallel.pair_id)
        assert exc.value.code == "endpoint_mismatch"
        far = await _pair(ctx.pool, "c", "d")
        with pytest.raises(QuantumResourceError) as exc:
            await swapper.swap(left.pair_id, far.pair_id)
        assert exc.value.code == "endpoint_mismatch"
        assert ctx.pool.status_of(left.pair_id).value == "active"

    _run(body())


# --------------------------------------------------------------------------
# teleport


_INPUTS = {
    "zero": (1.0 + 0j, 0.0j),
    "one": (0.0j, 1.0 + 0j),
    "plus": (1.0 + 0j, 1.0 + 0j),
    "minus": (1.0 + 0j, -1.0 + 0j),
    "plus_i": (1.0 + 0j, 1.0j),
    "general": (0.6 + 0.2j, 0.3 - 0.5j),
}


def test_teleport_covers_all_frames_and_bsm_branches():
    async def body():
        for kind in _SWAP_KINDS:
            for draw, bits in ((0.1, (0, 0)), (0.3, (0, 1)), (0.6, (1, 0)), (0.8, (1, 1))):
                ctx = _setup(rngs={"alice": ScriptedRng([draw])})
                proto = _proto(ctx)
                pair = await _pair(ctx.pool, kind=getattr(BellStateType, kind))
                result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 1.0 + 0j, pair.pair_id)
                assert result.success is True
                assert result.fidelity == pytest.approx(1.0, abs=1e-9)
                assert result.bsm_bits == bits
                frame = quantum_state.BellState(kind).frame
                assert (result.correction.correction_x, result.correction.correction_z) == (
                    bits[1] ^ frame[0], bits[0] ^ frame[1],
                )
                assert result.gate_x == bool(result.correction.correction_x)
                assert result.gate_z == bool(result.correction.correction_z)
                assert result.acknowledged is True
                assert result.input_destroyed is True
                assert result.resource_consumed is True
                assert result.receipt is not None
                assert ctx.pool.status_of(pair.pair_id).value == "consumed"

    _run(body())


def test_teleport_axis_and_complex_inputs():
    async def body():
        for label, (alpha, beta) in _INPUTS.items():
            ctx = _setup(rngs={"alice": ScriptedRng([0.8])})
            proto = _proto(ctx)
            pair = await _pair(ctx.pool)
            result = await proto.teleport_qubit("alice", "bob", alpha, beta, pair.pair_id)
            assert result.success is True, label
            assert result.fidelity == pytest.approx(1.0, abs=1e-9)

    _run(body())


class _RecordingTransport(LocalNodeTransport):
    def __init__(self, workers):
        super().__init__(workers)
        self.staged = []

    async def stage_conditional_state(self, node_id, **kwargs):
        self.staged.append({"node_id": node_id, **kwargs})
        return await super().stage_conditional_state(node_id, **kwargs)


def test_teleport_correction_carries_ids_and_bits_only():
    async def body():
        workers = {
            "alice": QuantumNodeWorker("alice", capacity=8, token="tok-alice", rng=ScriptedRng([0.3])),
            "bob": QuantumNodeWorker("bob", capacity=8, token="tok-bob"),
        }
        transport = _RecordingTransport(workers)
        pool = BellPairPool(transport=transport)
        proto = QuantumTeleportationProtocol(pool=pool, transport=transport)
        pair = await pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, pair.pair_id)
        # Branch (0, 1): X maps staged |1> back to corrected |0>.
        assert result.correction.correction_x == 1
        assert len(transport.staged) == 1
        staged = transport.staged[0]
        assert set(staged) == {"node_id", "operation_id", "lease_id", "session_id", "rho_matrix", "instance"}
        before = staged["rho_matrix"]
        after = result.receiver_matrix
        worst = max(abs(before[i][j][0] - after[i][j][0]) for i in range(2) for j in range(2))
        assert worst > 1e-6
        assert result.success is True

    _run(body())


def test_teleport_below_threshold_consumes_resource():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.1])})
        proto = _proto(ctx)
        pair = await _pair(ctx.pool, fidelity=0.90)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 1.0 + 0j, pair.pair_id)
        assert result.fidelity == pytest.approx((2 * 0.90 + 1) / 3, abs=1e-9)
        assert result.fidelity == pytest.approx(0.933333333333, abs=1e-9)
        assert result.success is False
        assert result.reason == "below_threshold"
        assert ctx.pool.status_of(pair.pair_id).value == "consumed"
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 1.0 + 0j, pair.pair_id)
        assert exc.value.code == "pair_unavailable"

    _run(body())


def test_teleport_rejects_bad_selection_and_inputs():
    async def body():
        ctx = _setup(nodes=("alice", "bob", "cara"))
        proto = _proto(ctx)
        pair = await _pair(ctx.pool)
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "cara", 1.0 + 0j, 0.0j, pair.pair_id)
        assert exc.value.code == "endpoint_mismatch"
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, "bell-ghost")
        assert exc.value.code == "unknown_pair"
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, pair.pair_id, ["rep"])
        assert exc.value.code == "invalid_selection"
        for alpha, beta in ((0.0j, 0.0j), (float("nan"), 1.0), (True, 0.0)):
            with pytest.raises(QuantumResourceError) as exc:
                await proto.teleport_qubit("alice", "bob", alpha, beta, pair.pair_id)
            assert exc.value.code == "invalid_input"
        assert ctx.pool.status_of(pair.pair_id).value == "active"

    _run(body())


def test_teleport_explicit_allocation_mode_succeeds():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.1])})
        proto = _proto(ctx)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j)
        assert isinstance(result, TeleportationResult)
        assert result.success is True
        assert result.fidelity >= 0.95
        assert ctx.pool.status_of(result.pair_id).value == "consumed"

    _run(body())


def test_teleport_receipt_failure_is_not_green():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.1])})
        pair = await _pair(ctx.pool)

        async def failing_sink(event):
            raise RuntimeError("ledger down")

        ctx.pool._append_event = failing_sink
        proto = QuantumTeleportationProtocol(pool=ctx.pool, transport=ctx.transport, append_event=failing_sink)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, pair.pair_id)
        assert result.success is False
        assert result.reason == "receipt_failed"
        assert ctx.pool.status_of(pair.pair_id).value == "consumed"

    _run(body())


class _AmbiguousTransport(LocalNodeTransport):
    async def correct(self, node_id, **kwargs):
        raise NodeTransportAmbiguous("may have applied")


def test_teleport_ambiguity_quarantines_and_raises():
    async def body():
        workers = {
            "alice": QuantumNodeWorker("alice", capacity=8, token="tok-alice", rng=ScriptedRng([0.1])),
            "bob": QuantumNodeWorker("bob", capacity=8, token="tok-bob"),
        }
        pool = BellPairPool(transport=_AmbiguousTransport(workers))
        proto = QuantumTeleportationProtocol(pool=pool)
        pair = await pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        with pytest.raises(QuantumResourceError):
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, pair.pair_id)
        assert pool.status_of(pair.pair_id).value == "quarantined"

    _run(body())


def test_teleport_input_slot_capacity_fails_before_gates():
    async def body():
        ctx = _setup(capacities={"alice": 1, "bob": 8}, rngs={"alice": ScriptedRng([0.1])})
        proto = _proto(ctx)
        pair = await _pair(ctx.pool)
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, pair.pair_id)
        assert exc.value.code == "worker_refused"
        assert ctx.pool.status_of(pair.pair_id).value == "active"

    _run(body())


def test_teleport_canonical_event_payload():
    async def body():
        ctx = _setup(rngs={"alice": ScriptedRng([0.8])})
        proto = _proto(ctx)
        pair = await _pair(ctx.pool)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 1.0 + 0j, pair.pair_id)
        completed = [event for event in ctx.events if event["event_type"] == "teleport.completed"]
        assert len(completed) == 1
        event = completed[0]
        assert event["outcome"] == "success"
        payload = event["payload"]
        assert payload["model_version"] == 1
        assert (payload["bsm_x"], payload["bsm_z"]) == (1, 1)
        assert (payload["correction_x"], payload["correction_z"]) == (
            result.correction.correction_x, result.correction.correction_z)
        assert payload["gate_x"] is True and payload["gate_z"] is True
        assert payload["fidelity"] == result.fidelity
        assert payload["acknowledged"] is True and payload["resource_consumed"] is True

    _run(body())


def test_teleport_multi_hop_route_uses_selected_output():
    async def body():
        ctx = _setup(
            nodes=("alice", "rep", "bob"),
            rngs={"rep": ScriptedRng([0.1, 0.1, 0.1]), "alice": ScriptedRng([0.1, 0.1]),
                  "bob": ScriptedRng([0.5])},
        )
        mesh = QuantumRepeaterMesh(ctx.pool)
        for name in ("alice", "rep", "bob"):
            mesh.register_node(name, "east")
        mesh.register_link("alice", "rep")
        mesh.register_link("rep", "bob")
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, None, ["rep"])
        assert result.success is True
        assert {result.source_node, result.target_node} == {"alice", "bob"}

    _run(body())


# --------------------------------------------------------------------------
# phase 68-05: shared worker / transport primitives
#
# Real worker objects and the real ASGI app over real HTTP semantics in
# every case; no canned worker echoes. Transport taxonomy faults raise the
# genuine httpx error types through MockTransport (same pattern as
# test_remote_failure_mapping).


def test_asgi_rejects_wrong_token_large_body_before_buffering():
    import httpx

    async def body():
        worker = QuantumNodeWorker("web", capacity=4, token="tok-web")
        app = create_node_app(worker)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            oversized = b"x" * (64 * 1024 + 1)
            # Unauthenticated bulk sender: 401 before any body buffering.
            denied = await client.post(
                "/v1/node/reserve", content=oversized,
                headers={"Authorization": "Bearer wrong", "Content-Type": "application/json"},
            )
            assert denied.status_code == 401
            assert denied.json()["error"] == "unauthenticated"
            # Authenticated oversized body: streamed 413 cap.
            capped = await client.post(
                "/v1/node/reserve", content=oversized,
                headers={"Authorization": "Bearer tok-web", "Content-Type": "application/json"},
            )
            assert capped.status_code == 413

    _run(body())


def test_worker_malformed_gate_type_refuses():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        for pos, gate in enumerate(([], {"gate": "H"}, 7, None)):
            with pytest.raises(QuantumNodeError) as exc:
                await worker.apply_circuit(
                    operation_id=f"op-g{pos}", lease_ids=held["leases"],
                    operations=[{"gate": gate, "target": 0}], **scope,
                )
            assert exc.value.status == 400
            assert exc.value.code == "invalid_circuit"

    _run(body())


def test_worker_overflow_numerics_refuse():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        with pytest.raises(QuantumNodeError) as exc:
            await worker.measure(
                operation_id="op-big", lease_ids=held["leases"],
                branch_probabilities=[10**401], branch_bits=[[0]], **scope,
            )
        assert exc.value.status == 400
        assert exc.value.code == "invalid_branches"
        huge = [[[10**401, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]
        with pytest.raises(QuantumNodeError) as exc:
            await worker.stage_conditional_state(
                operation_id="op-huge", lease_id=held["leases"][0],
                session_id="sess", rho_matrix=huge, **scope,
            )
        assert exc.value.status == 400
        assert exc.value.code == "invalid_state"

    _run(body())


def test_worker_measure_replay_draws_once():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t", rng=ScriptedRng([0.3]))
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        kwargs = {
            "operation_id": "op-m", "lease_ids": held["leases"],
            "branch_probabilities": [0.25, 0.25, 0.25, 0.25],
            "branch_bits": [[0, 0], [0, 1], [1, 0], [1, 1]], **scope,
        }
        first = await worker.measure(**kwargs)
        assert first["bits"] == [0, 1]
        # The scripted draw is spent; a replay must return the saved
        # acknowledgement without consuming another draw (ScriptedRng
        # raises if drawn while empty).
        second = await worker.measure(**kwargs)
        assert second == first

    _run(body())


def test_worker_long_resource_lease_is_releasable():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        res_a = "x" * 117 + "A" * 11
        res_b = "x" * 117 + "B" * 11
        assert len(res_a) == 128 and len(res_b) == 128
        held_a = await worker.reserve(operation_id="op-a", resource_id=res_a, count=1, **scope)
        held_b = await worker.reserve(operation_id="op-b", resource_id=res_b, count=1, **scope)
        lease_a, lease_b = held_a["leases"][0], held_b["leases"][0]
        assert lease_a != lease_b
        assert len(lease_a) <= 128 and len(lease_b) <= 128
        await worker.release(operation_id="op-rel", lease_ids=[lease_a, lease_b], **scope)
        with pytest.raises(QuantumNodeError) as exc:
            await worker.release(operation_id="op-rel2", lease_ids=[lease_a], **scope)
        assert exc.value.code == "already_released"

    _run(body())


def test_worker_stage_digest_covers_matrix():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=4, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        zero = [[[1.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]
        one = [[[0.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]]]
        first = await worker.stage_conditional_state(
            operation_id="op-s", lease_id=held["leases"][0],
            session_id="sess", rho_matrix=zero, **scope,
        )
        assert first["acknowledgement"] == "ack-op-s"
        with pytest.raises(QuantumNodeError) as exc:
            await worker.stage_conditional_state(
                operation_id="op-s", lease_id=held["leases"][0],
                session_id="sess", rho_matrix=one, **scope,
            )
        assert exc.value.status == 409
        assert exc.value.code == "operation_conflict"

    _run(body())


def test_worker_evicted_replay_never_reexecutes(monkeypatch):
    monkeypatch.setattr("desk_gateway.quantum_node._SEEN_OPS_CAP", 2)

    async def body():
        worker = QuantumNodeWorker("n1", capacity=8, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        await worker.reserve(operation_id="op-1", resource_id="ra", count=1, **scope)
        await worker.reserve(operation_id="op-2", resource_id="rb", count=1, **scope)
        await worker.reserve(operation_id="op-3", resource_id="rc", count=1, **scope)
        before = worker._active_count()
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(operation_id="op-1", resource_id="ra", count=1, **scope)
        assert exc.value.status == 409
        assert exc.value.code == "operation_expired"
        assert worker._active_count() == before
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(operation_id="op-1", resource_id="ra", count=2, **scope)
        assert exc.value.code == "operation_conflict"
        replay = await worker.reserve(operation_id="op-3", resource_id="rc", count=1, **scope)
        assert replay["active_count"] == before

    _run(body())


def test_worker_saturation_admits_cleanup_only(monkeypatch):
    monkeypatch.setattr("desk_gateway.quantum_node._NON_CLEANUP_EFFECT_CAP", 2)

    async def body():
        worker = QuantumNodeWorker("n1", capacity=8, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        first = await worker.reserve(operation_id="op-1", resource_id="ra", count=1, **scope)
        await worker.reserve(operation_id="op-2", resource_id="rb", count=1, **scope)
        with pytest.raises(QuantumNodeError) as exc:
            await worker.reserve(operation_id="op-3", resource_id="rc", count=1, **scope)
        assert exc.value.status == 409
        assert exc.value.code == "history_exhausted"
        # Terminal cleanup consumes a reserved slot and retains history.
        released = await worker.release(operation_id="op-rel", lease_ids=first["leases"], **scope)
        assert released["ok"] is True
        replay = await worker.reserve(operation_id="op-1", resource_id="ra", count=1, **scope)
        assert replay["leases"] == first["leases"]

    _run(body())


def test_worker_release_reclaims_records():
    async def body():
        worker = QuantumNodeWorker("n1", capacity=8, token="t")
        scope = {"token": "t", "node": "n1", "instance": worker.instance_id}
        held = await worker.reserve(operation_id="op-r", resource_id="res", count=1, **scope)
        lease = held["leases"][0]
        zero = [[[1.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]
        await worker.stage_conditional_state(
            operation_id="op-s", lease_id=lease, session_id="sess", rho_matrix=zero, **scope)
        await worker.correct(
            operation_id="op-c", lease_id=lease, session_id="sess",
            bsm_x=0, bsm_z=0, frame_x=0, frame_z=0, **scope)
        assert worker._corrections, "correction must be recorded before release"
        await worker.release(operation_id="op-x", lease_ids=[lease], **scope)
        assert lease not in worker._leases
        assert lease in worker._released_ids
        assert worker._corrections == {}
        # Surviving leases keep full ownership behavior.
        held2 = await worker.reserve(operation_id="op-r2", resource_id="res2", count=1, **scope)
        await worker.stage_conditional_state(
            operation_id="op-s2", lease_id=held2["leases"][0],
            session_id="sess2", rho_matrix=zero, **scope)
        seen = await worker.inspect(**scope)
        assert seen["active_count"] == 1
        assert seen["leases"][0]["lease_id"] == held2["leases"][0]

    _run(body())


def test_remote_taxonomy_splits_connect_and_postsend():
    import httpx

    def connect_handler(request):
        raise httpx.ConnectError("dns failed", request=request)

    def read_handler(request):
        raise httpx.ReadError("lost reply", request=request)

    def write_handler(request):
        raise httpx.WriteError("broken pipe", request=request)

    def gone_handler(request):
        return httpx.Response(500, json={"ok": False, "error": "boom", "detail": "boom"})

    def refused_handler(request):
        return httpx.Response(409, json={"ok": False, "error": "capacity_exhausted", "detail": "full"})

    async def body():
        # Definitive pre-send failure: unavailable, never ambiguous.
        transport = _remote(connect_handler)
        with pytest.raises(NodeTransportUnavailable):
            await transport.reserve("n", operation_id="op-1", resource_id="r", count=1, instance="i")
        with pytest.raises(NodeTransportUnavailable):
            await transport.inspect("n")
        await transport.aclose()
        # Post-send failures on mutation: ambiguous, never a refusal.
        for handler in (read_handler, write_handler, gone_handler):
            transport = _remote(handler)
            with pytest.raises(NodeTransportAmbiguous):
                await transport.reserve("n", operation_id="op-1", resource_id="r", count=1, instance="i")
            await transport.aclose()
        # Post-send failure on the read-only probe: unavailable, never ambiguous.
        transport = _remote(read_handler)
        with pytest.raises(NodeTransportUnavailable):
            await transport.inspect("n")
        await transport.aclose()
        # Explicit worker refusal stays a refusal.
        transport = _remote(refused_handler)
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.reserve("n", operation_id="op-1", resource_id="r", count=1, instance="i")
        assert exc.value.code == "capacity_exhausted"
        await transport.aclose()

    _run(body())


def test_remote_preserves_ipv6_brackets():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        from httpx import Response
        return Response(200, json={"ok": True, "instance_id": "i-6", "active_count": 0, "leases": []})

    async def body():
        transport = _remote(handler, endpoints={"n": "http://[::1]:8891"})
        payload = await transport.inspect("n")
        assert payload["instance_id"] == "i-6"
        assert seen["url"] == "http://[::1]:8891/v1/node/inspect"
        await transport.aclose()

    _run(body())


def test_remote_restart_discovery_keeps_lease_pinned():
    import httpx

    class _SwapTransport(httpx.AsyncBaseTransport):
        def __init__(self, inner):
            self.inner = inner

        async def handle_async_request(self, request):
            return await self.inner.handle_async_request(request)

    async def body():
        first = QuantumNodeWorker("n", capacity=8, token="tok")
        swap = _SwapTransport(httpx.ASGITransport(app=create_node_app(first)))
        client = httpx.AsyncClient(transport=swap, base_url="http://x")
        transport = RemoteNodeTransport({"n": "http://127.0.0.1:8891"}, {"n": "tok"}, client=client)
        probed = await transport.inspect("n")
        assert probed["instance_id"] == first.instance_id
        held = await transport.reserve("n", operation_id="op-r", resource_id="res", count=1)
        assert len(held["leases"]) == 1
        old_instance = first.instance_id
        # Worker restarts: new process, same node, fresh instance.
        second = QuantumNodeWorker("n", capacity=8, token="tok")
        swap.inner = httpx.ASGITransport(app=create_node_app(second))
        # Live binding stays pinned: the old instance is refused, never rebound.
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.reserve(
                "n", operation_id="op-r2", resource_id="res", count=1, instance=old_instance)
        assert exc.value.status == 409
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.inspect("n", instance=old_instance, resource_ids=["res"])
        assert exc.value.code == "stale_instance"
        # Unscoped probe discovers the restarted worker for future commands.
        rediscovered = await transport.inspect("n")
        assert rediscovered["instance_id"] == second.instance_id
        fresh = await transport.reserve("n", operation_id="op-r3", resource_id="res", count=1)
        assert len(fresh["leases"]) == 1
        await transport.aclose()

    _run(body())


# --------------------------------------------------------------------------
# phase 69-05: authenticated QKD action/transport contract
#
# Deterministic behavior tests for the fixed qkd_step/qkd_owner contract:
# codecs, allowlists, auth-before-draws, one-shot stages, owner-only
# capability/use, session bounds, and Local/Remote parity. Real worker
# objects and the real ASGI app over real HTTP semantics in every case; no
# canned worker echoes. Parent runs this file post-integration; nothing here
# is executed mid-flight by the gap executor.


class _FixedQkdRng:
    """Deterministic random()-only worker RNG with cycling draws."""

    def __init__(self, draws=(0.1, 0.9)):
        self._draws = list(draws)
        self._i = 0
        self.draws = 0

    def random(self):
        value = self._draws[self._i % len(self._draws)]
        self._i += 1
        self.draws += 1
        return value



def _qkd_workers():
    alice = QuantumNodeWorker("alice", capacity=64, token="tok-alice", rng=_FixedQkdRng())
    bob = QuantumNodeWorker("bob", capacity=64, token="tok-bob", rng=_FixedQkdRng((0.7, 0.3)))
    return alice, bob


async def _step(worker, token, operation_id, session_id, action, payload):
    return await worker.qkd_step(
        operation_id=operation_id, session_id=session_id, action=action,
        payload=payload, token=token, node=worker.node_id, instance=worker.instance_id,
    )


async def _owner(worker, token, operation_id, session_id, action, payload):
    return await worker.qkd_owner(
        operation_id=operation_id, session_id=session_id, action=action,
        payload=payload, token=token, node=worker.node_id, instance=worker.instance_id,
    )


async def _begin(worker, token, operation_id, session_id, protocol="BB84", role="alice", peer="bob"):
    return await _step(
        worker, token, operation_id, session_id, "begin",
        {"protocol": protocol, "role": role, "peer": peer},
    )


def _joint_phi_plus():
    rho = quantum_state.BellState("PHI_PLUS").density()
    return {
        "encoding": "density-v1",
        "qubits": 2,
        "matrix": [[[c.real, c.imag] for c in row] for row in rho.rows],
    }



def test_qkd_unknown_actions_rejected():
    async def body():
        alice, _ = _qkd_workers()
        for action in ("accept_bit", "qkd_accept_bit", "", "BEGIN", "begin_qkd"):
            with pytest.raises(QuantumNodeError) as exc:
                await _step(alice, "tok-alice", f"op-{action or 'empty'}", "s1", action, {})
            assert exc.value.status == 400
            assert exc.value.code == "unknown_action"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-o", "s1", "capability_plus", {})
        assert exc.value.code == "unknown_action"

    _run(body())


def test_qkd_bits_codec_extremes():
    import base64

    assert decode_bits(encode_bits([1, 0, 1]), "b") == (1, 0, 1)
    assert decode_bits(encode_bits([]), "b") == ()
    dto = encode_bits([1, 1, 1])
    assert dto["encoding"] == "bits-msb-v1" and dto["count"] == 3
    assert len(base64.b64decode(dto["data"])) == 1
    cases = []
    wrong_tag = dict(dto, encoding="bits-lsb-v1")
    cases.append((wrong_tag, "invalid_codec"))
    cases.append((dict(dto, count=9), "invalid_bits"))
    cases.append((dict(dto, count=True), "invalid_bits"))
    cases.append((dict(dto, data="!!!"), "invalid_bits"))
    two_bytes = dict(dto, data=base64.b64encode(b"\xa0\x00").decode())
    cases.append((two_bytes, "invalid_bits"))
    raw = bytearray(base64.b64decode(dto["data"]))
    raw[0] |= 0x01
    nonzero_pad = dict(dto, data=base64.b64encode(bytes(raw)).decode())
    cases.append((nonzero_pad, "invalid_bits"))
    cases.append((dict(dto, extra=1), "invalid_codec"))
    cases.append(("bits", "invalid_codec"))
    for bad, code in cases:
        with pytest.raises(QuantumNodeError) as exc:
            decode_bits(bad, "b")
        assert exc.value.status == 400
        assert exc.value.code == code
    with pytest.raises(QuantumNodeError) as exc:
        decode_bits(dto, "b", exact=4)
    assert exc.value.code == "invalid_bits"


def test_qkd_indices_codec_ordered_unique_bounded():
    import base64

    assert decode_indices(encode_indices([5, 3, 7]), "k") == (5, 3, 7)
    assert decode_indices(encode_indices([]), "k") == ()
    dto = encode_indices([1, 2])
    cases = [
        (dict(dto, encoding="u16-v1"), "invalid_codec"),
        (dict(dto, count=3), "invalid_index"),
        (dict(dto, data="!!!"), "invalid_index"),
        (dict(dto, data=base64.b64encode(b"\x00").decode()), "invalid_index"),
        (dict(dto, extra=1), "invalid_codec"),
    ]
    dup = dict(dto, data=base64.b64encode(b"\x00\x01\x00\x01").decode(), count=2)
    cases.append((dup, "invalid_index"))
    over = dict(dto, data=base64.b64encode((20000).to_bytes(2, "big")).decode(), count=1)
    cases.append((over, "invalid_index"))
    for bad, code in cases:
        with pytest.raises(QuantumNodeError) as exc:
            decode_indices(bad, "k")
        assert exc.value.status == 400
        assert exc.value.code == code
    with pytest.raises(QuantumNodeError):
        encode_indices([0, 20000])


def test_qkd_signals_codec_two_bit_ensemble():
    import base64

    assert decode_signals(encode_signals([0, 1, 2, 3, 0]), "s") == (0, 1, 2, 3, 0)
    assert decode_signals(encode_signals([]), "s") == ()
    dto = encode_signals([3, 3, 3, 3, 3])
    assert len(base64.b64decode(dto["data"])) == 2
    raw = bytearray(base64.b64decode(dto["data"]))
    raw[-1] |= 0x03
    nonzero_pad = dict(dto, data=base64.b64encode(bytes(raw)).decode())
    cases = [
        (dict(dto, encoding="signals-v1"), "invalid_codec"),
        (dict(dto, count=4), "invalid_signal"),
        (dict(dto, data="!!!"), "invalid_signal"),
        (dict(dto, data=base64.b64encode(b"\xff\xff\xff").decode()), "invalid_signal"),
        (nonzero_pad, "invalid_signal"),
        (dict(dto, extra=1), "invalid_codec"),
    ]
    for bad, code in cases:
        with pytest.raises(QuantumNodeError) as exc:
            decode_signals(bad, "s")
        assert exc.value.status == 400
        assert exc.value.code == code
    with pytest.raises(QuantumNodeError):
        encode_signals([0, 4])


def test_qkd_density_codec_kernel_validated():
    zero = {"encoding": "density-v1", "qubits": 1,
            "matrix": [[[1.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]}
    rho = decode_density(zero, "z", qubits=1)
    assert rho.qubits == 1
    joint = encode_density(quantum_state.BellState("PHI_PLUS").density())
    assert joint["qubits"] == 2 and len(joint["matrix"]) == 4
    assert decode_density(joint, "j", qubits=2).qubits == 2
    non_psd = {"encoding": "density-v1", "qubits": 1,
               "matrix": [[[1.5, 0.0], [0.0, 0.0]], [[0.0, 0.0], [-0.5, 0.0]]]}
    bad_trace = {"encoding": "density-v1", "qubits": 1,
                 "matrix": [[[0.6, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.6, 0.0]]]}
    non_finite = {"encoding": "density-v1", "qubits": 1,
                  "matrix": [[[float("inf"), 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]}
    boolean = {"encoding": "density-v1", "qubits": 1,
               "matrix": [[[True, 0.0], [0.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]]]}
    for bad in (non_psd, bad_trace, non_finite, boolean):
        with pytest.raises(QuantumNodeError) as exc:
            decode_density(bad, "d", qubits=1)
        assert exc.value.status == 400
        assert exc.value.code == "invalid_state"
    with pytest.raises(QuantumNodeError) as exc:
        decode_density(joint, "j", qubits=1)
    assert exc.value.code == "invalid_state"
    with pytest.raises(QuantumNodeError) as exc:
        decode_density(dict(zero, qubits=True), "z", qubits=1)
    assert exc.value.code == "invalid_state"
    with pytest.raises(QuantumNodeError) as exc:
        decode_density(dict(zero, extra=1), "z", qubits=1)
    assert exc.value.code == "invalid_codec"


def test_qkd_envelope_rejects_unknown_and_forbidden_fields():
    async def body():
        alice, _ = _qkd_workers()
        await _begin(alice, "tok-alice", "op-b", "s1")
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-x", "s1", "lengths", {"verbose": True})
        assert exc.value.status == 400
        assert exc.value.code == "invalid_payload"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-y", "s1", "prepare_bb84", {"count": 4, "rng": "x"})
        assert exc.value.code == "invalid_payload"

    _run(body())


def test_qkd_http_envelope_rejects_body_credential_and_owner():
    import httpx

    async def body():
        worker = QuantumNodeWorker("web", capacity=8, token="tok-web")
        app = create_node_app(worker)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": "Bearer tok-web", "Content-Type": "application/json"}
            base = {"node": "web", "instance": worker.instance_id,
                    "operation_id": "op-1", "session_id": "s1",
                    "action": "begin", "payload": {"protocol": "BB84", "role": "alice", "peer": "bob"}}
            ok = await client.post("/v1/node/qkd_step", json=base, headers=headers)
            assert ok.status_code == 200
            smuggled = dict(base, operation_id="op-2", owner="mallory")
            denied = await client.post("/v1/node/qkd_step", json=smuggled, headers=headers)
            assert denied.status_code == 400
            assert denied.json()["error"] == "invalid_envelope"
            keyed = dict(base, operation_id="op-3", token="tok-web")
            denied = await client.post("/v1/node/qkd_step", json=keyed, headers=headers)
            assert denied.status_code == 400
            extra = dict(base, operation_id="op-4",zzz="field")
            denied = await client.post("/v1/node/qkd_step", json=extra, headers=headers)
            assert denied.status_code == 400

    _run(body())


async def _matched_keep(prep, meas, n):
    """Sift keep/phase DTOs from two public basis DTOs (full ordered lists)."""
    bases_a = decode_bits(prep["bases"], "ba")
    bases_b = decode_bits(meas["bases"], "bb")
    keep = [i for i in range(n) if bases_a[i] == bases_b[i]]
    return encode_indices(keep), encode_indices([]), keep


async def _bb84_to_tagged(alice, bob, sess, n, prefix):
    """Drive both BB84 endpoints through tag; return (tag_a, tag_b, kept)."""
    await _begin(alice, "tok-alice", f"{prefix}-ba", sess, "BB84", "alice", "bob")
    await _begin(bob, "tok-bob", f"{prefix}-bb", sess, "BB84", "bob", "alice")
    prep = await _step(alice, "tok-alice", f"{prefix}-p", sess, "prepare_bb84", {"count": n})
    assert set(prep) == {"ok", "signals", "bases"}
    meas = await _step(bob, "tok-bob", f"{prefix}-m", sess, "measure_bb84", {"signals": prep["signals"]})
    assert set(meas) == {"ok", "bases", "count"} and meas["count"] == n
    keep_dto, phase_dto, keep = await _matched_keep(prep, meas, n)
    adopt_a = await _step(alice, "tok-alice", f"{prefix}-sa", sess, "adopt_indices",
                          {"keep": keep_dto, "phase": phase_dto})
    adopt_b = await _step(bob, "tok-bob", f"{prefix}-sb", sess, "adopt_indices",
                          {"keep": keep_dto, "phase": phase_dto})
    assert adopt_a["key_length"] == len(keep) == adopt_b["key_length"]
    assert decode_bits(adopt_a["phase_sample"], "ps") == ()
    order = encode_indices(list(range(len(keep))))
    syn = await _step(alice, "tok-alice", f"{prefix}-syn", sess, "syndrome", {"order": order})
    assert set(syn) == {"ok", "syndrome", "leaked"} and syn["leaked"] > 0
    corr = await _step(bob, "tok-bob", f"{prefix}-cor", sess, "correct",
                       {"order": order, "syndrome": syn["syndrome"]})
    assert corr["corrected_count"] == 0
    tag_a = await _step(alice, "tok-alice", f"{prefix}-ta", sess, "tag", {"seed": None})
    tag_b = await _step(bob, "tok-bob", f"{prefix}-tb", sess, "tag", {"seed": tag_a["seed"]})
    return tag_a, tag_b, len(keep)


def test_qkd_bb84_full_matrix_to_established():
    async def body():
        alice, bob = _qkd_workers()
        sess = "bb84-full"
        tag_a, tag_b, n = await _bb84_to_tagged(alice, bob, sess, 64, "full")
        assert n == 64
        # SAME public seed, independently hashed candidates: tags agree.
        assert tag_a["tag"] == tag_b["tag"]
        assert tag_a["seed"] == tag_b["seed"]
        assert len(decode_bits(tag_a["seed"], "s")) == n + 31
        ext_a = await _step(alice, "tok-alice", "full-xa", sess, "extract",
                            {"output_length": 128, "seed": None})
        assert set(ext_a) == {"ok", "seed", "commitment", "output_length"}
        assert ext_a["output_length"] == 128
        assert len(decode_bits(ext_a["seed"], "s")) == n + 128 - 1
        assert ext_a["seed"] != tag_a["seed"]
        ext_b = await _step(bob, "tok-bob", "full-xb", sess, "extract",
                            {"output_length": 128, "seed": ext_a["seed"]})
        assert len(ext_a["commitment"]) == 64 and len(ext_b["commitment"]) == 64
        # Per-node blinding stays private: node-bound commitments differ.
        assert ext_b["commitment"] != ext_a["commitment"]
        for reply in (tag_a, tag_b, ext_a, ext_b):
            blob = json.dumps(reply)
            for secret in ("capability", "raw_bits", "raw_bases", "key_bits", "blinding"):
                assert secret not in blob
        lengths = await _step(alice, "tok-alice", "full-la", sess, "lengths", {})
        assert lengths == {"ok": True, "key_length": 0, "phase_length": 0,
                           "key_available": True, "state": "established"}
        # One-shot stages refuse seconds with fresh operations.
        prep = await _step(alice, "tok-alice", "full-lp", sess, "lengths", {})
        assert prep["state"] == "established"
        order = encode_indices(list(range(n)))
        repeats = [
            ("alice", "tok-alice", "prepare_bb84", {"count": 64}),
            ("alice", "tok-alice", "adopt_indices",
             {"keep": encode_indices([]), "phase": encode_indices([])}),
            ("alice", "tok-alice", "syndrome", {"order": order}),
            ("alice", "tok-alice", "tag", {"seed": None}),
            ("alice", "tok-alice", "extract", {"output_length": 128, "seed": None}),
        ]
        for pos, (node, token, action, payload) in enumerate(repeats):
            worker = alice if node == "alice" else bob
            with pytest.raises(QuantumNodeError) as exc:
                await _step(worker, token, f"full-r{pos}", sess, action, payload)
            assert exc.value.status == 409
            assert exc.value.code == "session_step"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "full-rm", sess, "measure_bb84",
                       {"signals": encode_signals([0] * 4)})
        assert exc.value.code == "session_step"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "full-rc", sess, "correct",
                       {"order": order, "syndrome": encode_bits([0])})
        assert exc.value.code == "session_step"

    _run(body())


def test_qkd_local_remote_reply_parity():
    import httpx

    async def body():
        la, lb = _qkd_workers()
        ra = QuantumNodeWorker("alice", capacity=64, token="tok-alice", rng=_FixedQkdRng())
        rb = QuantumNodeWorker("bob", capacity=64, token="tok-bob", rng=_FixedQkdRng((0.7, 0.3)))
        local = LocalNodeTransport({"alice": la, "bob": lb})
        client_a = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(ra)),
                                     base_url="http://a")
        client_b = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(rb)),
                                     base_url="http://b")
        remote_a = RemoteNodeTransport({"alice": "http://127.0.0.1:8891"}, {"alice": "tok-alice"},
                                       client=client_a)
        remote_b = RemoteNodeTransport({"bob": "http://127.0.0.1:8891"}, {"bob": "tok-bob"},
                                       client=client_b)
        await remote_a.inspect("alice")
        await remote_b.inspect("bob")
        sess, n = "parity", 24
        begun_l = await local.qkd_step("alice", operation_id="op-b", session_id=sess,
                                       action="begin",
                                       payload={"protocol": "BB84", "role": "alice", "peer": "bob"})
        begun_r = await remote_a.qkd_step("alice", operation_id="op-b", session_id=sess,
                                          action="begin",
                                          payload={"protocol": "BB84", "role": "alice", "peer": "bob"})
        assert begun_l == begun_r == {"ok": True, "session_id": sess}
        await local.qkd_step("bob", operation_id="op-bb", session_id=sess, action="begin",
                             payload={"protocol": "BB84", "role": "bob", "peer": "alice"})
        await remote_b.qkd_step("bob", operation_id="op-bb", session_id=sess, action="begin",
                                payload={"protocol": "BB84", "role": "bob", "peer": "alice"})
        prep_l = await local.qkd_step("alice", operation_id="op-p", session_id=sess,
                                      action="prepare_bb84", payload={"count": n})
        prep_r = await remote_a.qkd_step("alice", operation_id="op-p", session_id=sess,
                                         action="prepare_bb84", payload={"count": n})
        assert prep_l == prep_r
        meas_l = await local.qkd_step("bob", operation_id="op-m", session_id=sess,
                                      action="measure_bb84", payload={"signals": prep_l["signals"]})
        meas_r = await remote_b.qkd_step("bob", operation_id="op-m", session_id=sess,
                                         action="measure_bb84", payload={"signals": prep_r["signals"]})
        assert meas_l == meas_r
        keep_dto, phase_dto, keep = await _matched_keep(prep_l, meas_l, n)
        adopt_l = await local.qkd_step("alice", operation_id="op-s", session_id=sess,
                                       action="adopt_indices",
                                       payload={"keep": keep_dto, "phase": phase_dto})
        adopt_r = await remote_a.qkd_step("alice", operation_id="op-s", session_id=sess,
                                          action="adopt_indices",
                                          payload={"keep": keep_dto, "phase": phase_dto})
        assert adopt_l == adopt_r
        order = encode_indices(list(range(len(keep))))
        syn_l = await local.qkd_step("alice", operation_id="op-syn", session_id=sess,
                                     action="syndrome", payload={"order": order})
        syn_r = await remote_a.qkd_step("alice", operation_id="op-syn", session_id=sess,
                                        action="syndrome", payload={"order": order})
        assert syn_l == syn_r
        tag_l = await local.qkd_step("alice", operation_id="op-t", session_id=sess,
                                     action="tag", payload={"seed": None})
        tag_r = await remote_a.qkd_step("alice", operation_id="op-t", session_id=sess,
                                        action="tag", payload={"seed": None})
        assert tag_l == tag_r
        # Refusals carry identical typed codes over both transports.
        with pytest.raises(NodeCommandFailed) as exc_l:
            await local.qkd_step("alice", operation_id="op-x", session_id=sess,
                                 action="nope", payload={})
        with pytest.raises(NodeCommandFailed) as exc_r:
            await remote_a.qkd_step("alice", operation_id="op-x", session_id=sess,
                                    action="nope", payload={})
        assert (exc_l.value.status, exc_l.value.code) == (400, "unknown_action")
        assert (exc_r.value.status, exc_r.value.code) == (400, "unknown_action")
        await remote_a.aclose()
        await remote_b.aclose()

    _run(body())


def test_qkd_auth_and_stage_precede_draws():
    async def body():
        rng_a, rng_b = _FixedQkdRng(), _FixedQkdRng()
        alice = QuantumNodeWorker("alice", capacity=8, token="tok-alice", rng=rng_a)
        bob = QuantumNodeWorker("bob", capacity=8, token="tok-bob", rng=rng_b)
        await _begin(alice, "tok-alice", "op-b", "s1")
        await _begin(bob, "tok-bob", "op-bb", "s1", role="bob", peer="alice")
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "wrong", "op-p", "s1", "prepare_bb84", {"count": 4})
        assert exc.value.status == 401
        assert rng_a.draws == 0
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-pb", "s1", "prepare_bb84", {"count": 4})
        assert exc.value.status == 403
        assert exc.value.code == "wrong_role"
        assert rng_b.draws == 0
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-s", "s1", "adopt_indices",
                       {"keep": encode_indices([]), "phase": encode_indices([])})
        assert exc.value.status == 409
        assert rng_a.draws == 0
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-m", "s1", "measure_bb84",
                       {"signals": encode_signals([])})
        assert exc.value.status == 400
        assert rng_b.draws == 0
        before = rng_a.draws
        first = await _step(alice, "tok-alice", "op-p4", "s1", "prepare_bb84", {"count": 2})
        assert set(first) == {"ok", "signals", "bases"}
        assert rng_a.draws > before
        # Same operation, changed field: conflict, never a second draw.
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-p4", "s1", "prepare_bb84", {"count": 3})
        assert exc.value.status == 409
        assert exc.value.code == "operation_conflict"
        mid = rng_a.draws
        # Identical replay returns the saved reply with no new draw.
        again = await _step(alice, "tok-alice", "op-p4", "s1", "prepare_bb84", {"count": 2})
        assert again == first
        assert rng_a.draws == mid
        # Stale instances fail closed before any draw.
        stale_before = rng_a.draws
        with pytest.raises(QuantumNodeError) as exc:
            await alice.qkd_step(operation_id="op-st", session_id="s1", action="prepare_bb84",
                                 payload={"count": 2}, token="tok-alice",
                                 node="alice", instance="stale")
        assert exc.value.status == 409
        assert exc.value.code == "stale_instance"
        assert rng_a.draws == stale_before

    _run(body())


def test_qkd_abort_is_terminal_and_replayable():
    async def body():
        alice, bob = _qkd_workers()
        sess = "abort-1"
        await _begin(alice, "tok-alice", "op-ba", sess)
        await _begin(bob, "tok-bob", "op-bb", sess, role="bob", peer="alice")
        prep = await _step(alice, "tok-alice", "op-p", sess, "prepare_bb84", {"count": 8})
        meas = await _step(bob, "tok-bob", "op-m", sess, "measure_bb84", {"signals": prep["signals"]})
        keep_dto, phase_dto, _ = await _matched_keep(prep, meas, 8)
        await _step(alice, "tok-alice", "op-s", sess, "adopt_indices",
                    {"keep": keep_dto, "phase": phase_dto})
        aborted = await _step(alice, "tok-alice", "op-ab", sess, "abort", {"reason": "user_abort"})
        assert aborted == {"ok": True, "session_id": sess, "state": "aborted"}
        replay = await _step(alice, "tok-alice", "op-ab", sess, "abort", {"reason": "user_abort"})
        assert replay == aborted
        lengths = await _step(alice, "tok-alice", "op-l", sess, "lengths", {})
        assert lengths == {"ok": True, "key_length": 0, "phase_length": 0,
                           "key_available": False, "state": "aborted"}
        for op, action, payload in (
            ("op-ab2", "abort", {"reason": "user_abort"}),
            ("op-p2", "prepare_bb84", {"count": 8}),
        ):
            with pytest.raises(QuantumNodeError) as exc:
                await _step(alice, "tok-alice", op, sess, action, payload)
            assert exc.value.status == 409
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-cap", sess, "capability", {})
        assert exc.value.code == "already_aborted"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-use", sess, "use",
                         {"operation": "qkd_test", "capability": "00" * 16})
        assert exc.value.code == "already_aborted"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-br", sess, "abort", {"reason": "nope"})
        assert exc.value.status == 400
        assert exc.value.code == "invalid_reason"

    _run(body())


async def _bb84_establish(alice, bob, sess, n, prefix, ell=128):
    """Full BB84 to extracted on both endpoints; return (ext_a, ext_b)."""
    await _bb84_to_tagged(alice, bob, sess, n, prefix)
    ext_a = await _step(alice, "tok-alice", f"{prefix}-xa", sess, "extract",
                        {"output_length": ell, "seed": None})
    ext_b = await _step(bob, "tok-bob", f"{prefix}-xb", sess, "extract",
                        {"output_length": ell, "seed": ext_a["seed"]})
    return ext_a, ext_b


def test_qkd_owner_capability_and_one_shot_use():
    async def body():
        alice, bob = _qkd_workers()
        sess = "owner-1"
        await _begin(alice, "tok-alice", "op-ba", sess)
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-cap-early", sess, "capability", {})
        assert exc.value.status == 409
        assert exc.value.code == "key_unavailable"
        ext_a, _ = await _bb84_establish(alice, bob, sess, 8, "own")
        cap = await _owner(alice, "tok-alice", "op-cap", sess, "capability", {})
        assert set(cap) == {"ok", "session_id", "capability"}
        assert len(cap["capability"]) == 32
        assert await _owner(alice, "tok-alice", "op-cap", sess, "capability", {}) == cap
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-wrong", sess, "use",
                         {"operation": "qkd_test", "capability": "00" * 16})
        assert exc.value.status == 403
        assert exc.value.code == "wrong_capability"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-badop", sess, "use",
                         {"operation": "publish", "capability": cap["capability"]})
        assert exc.value.status == 400
        assert exc.value.code == "invalid_operation"
        use = await _owner(alice, "tok-alice", "op-use", sess, "use",
                           {"operation": "qkd_test", "capability": cap["capability"]})
        assert use == {"ok": True, "outcome": "accepted", "operation": "qkd_test",
                       "commitment": ext_a["commitment"]}
        replay = await _owner(alice, "tok-alice", "op-use", sess, "use",
                              {"operation": "qkd_test", "capability": cap["capability"]})
        assert replay == use
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-use", sess, "use",
                         {"operation": "qkd_test", "capability": "ff" * 16})
        assert exc.value.status == 409
        assert exc.value.code == "operation_conflict"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-use2", sess, "use",
                         {"operation": "qkd_test", "capability": cap["capability"]})
        assert exc.value.status == 409
        assert exc.value.code == "already_used"
        # Terminal checks precede cached capability replies.
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-cap", sess, "capability", {})
        assert exc.value.code == "already_used"
        record = alice._qkd[sess]
        assert record.key is None and record.blinding is None and record.capability is None
        assert record.key_bits == [] and record.raw_bits == [] and record.raw_bases == []
        assert record.used is True
        lengths = await _step(alice, "tok-alice", "op-l", sess, "lengths", {})
        assert lengths["state"] == "used" and lengths["key_available"] is False
        await _begin(alice, "tok-alice", "op-b2", "owner-2")
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-use3", "owner-2", "use",
                         {"operation": "qkd_test", "capability": cap["capability"]})
        assert exc.value.code == "key_unavailable"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-cap3", "missing", "capability", {})
        assert exc.value.status == 404
        assert exc.value.code == "unknown_session"

    _run(body())


def test_qkd_owner_scope_is_node_bound():
    async def body():
        alice, bob = _qkd_workers()
        await _begin(alice, "tok-alice", "op-b", "s1")
        # A sibling worker holds no such session: unknown, never cross-read.
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-x", "s1", "lengths", {})
        assert exc.value.status == 404
        # Ownership tampering fails closed at the binding guard.
        alice._qkd["s1"].owner = "mallory"
        with pytest.raises(QuantumNodeError) as exc:
            await _owner(alice, "tok-alice", "op-cap", "s1", "capability", {})
        assert exc.value.status == 403
        assert exc.value.code == "wrong_owner"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-bob", "op-y", "s1", "lengths", {})
        assert exc.value.status == 401

    _run(body())


def test_qkd_session_capacity_counts_unused_keys():
    async def body():
        alice, bob = _qkd_workers()
        await _bb84_establish(alice, bob, "cap-est", 8, "cap0")
        for i in range(63):
            await _begin(alice, "tok-alice", f"op-fill-{i}", f"cap-{i}")
        assert alice._qkd_nonterminal_count() == 64
        with pytest.raises(QuantumNodeError) as exc:
            await _begin(alice, "tok-alice", "op-full", "cap-full")
        assert exc.value.status == 409
        assert exc.value.code == "qkd_capacity"
        # Established-but-unused keys count: consuming one frees a slot.
        cap = await _owner(alice, "tok-alice", "op-cap", "cap-est", "capability", {})
        await _owner(alice, "tok-alice", "op-use", "cap-est", "use",
                     {"operation": "qkd_test", "capability": cap["capability"]})
        await _begin(alice, "tok-alice", "op-after-use", "cap-after-use")
        with pytest.raises(QuantumNodeError) as exc:
            await _begin(alice, "tok-alice", "op-full2", "cap-full2")
        assert exc.value.code == "qkd_capacity"
        # Terminal cleanup keeps working at saturation and frees its slot.
        await _step(alice, "tok-alice", "op-ab0", "cap-0", "abort", {"reason": "user_abort"})
        await _begin(alice, "tok-alice", "op-after-abort", "cap-after-abort")
        assert alice._qkd_nonterminal_count() == 64
        assert alice._qkd["cap-0"].terminal is True

    _run(body())


def test_qkd_saturation_admits_terminal_cleanup(monkeypatch):
    async def body():
        alice, bob = _qkd_workers()
        await _bb84_establish(alice, bob, "sat-1", 8, "sat1")
        await _bb84_establish(alice, bob, "sat-2", 8, "sat2")
        monkeypatch.setattr(
            "desk_gateway.quantum_node._NON_CLEANUP_EFFECT_CAP", len(alice._tombstones))
        with pytest.raises(QuantumNodeError) as exc:
            await _begin(alice, "tok-alice", "op-sat3", "sat-3")
        assert exc.value.status == 409
        assert exc.value.code == "history_exhausted"
        cap = await _owner(alice, "tok-alice", "op-cap2", "sat-2", "capability", {})
        assert len(cap["capability"]) == 32
        use = await _owner(alice, "tok-alice", "op-use2", "sat-2", "use",
                           {"operation": "drill_release", "capability": cap["capability"]})
        assert use["outcome"] == "accepted"
        aborted = await _step(alice, "tok-alice", "op-ab1", "sat-1", "abort",
                              {"reason": "resource_exhausted"})
        assert aborted["state"] == "aborted"

    _run(body())


def test_qkd_evicted_replay_never_reexecutes(monkeypatch):
    monkeypatch.setattr("desk_gateway.quantum_node._SEEN_OPS_CAP", 2)

    async def body():
        alice, _ = _qkd_workers()
        await _begin(alice, "tok-alice", "op-1", "e1")
        await _begin(alice, "tok-alice", "op-2", "e2")
        await _begin(alice, "tok-alice", "op-3", "e3")
        with pytest.raises(QuantumNodeError) as exc:
            await _begin(alice, "tok-alice", "op-1", "e1")
        assert exc.value.status == 409
        assert exc.value.code == "operation_expired"
        assert set(alice._qkd) == {"e1", "e2", "e3"}

    _run(body())


async def _reserve(worker, token, operation_id, resource_id, count):
    held = await worker.reserve(
        operation_id=operation_id, resource_id=resource_id, count=count,
        token=token, node=worker.node_id, instance=worker.instance_id,
    )
    return held["leases"]


async def _e91_round(alice, bob, lease_a, lease_b, sess, i, prefix, joint=None):
    """One ordered E91 key round; asserts the exact private-seam replies."""
    joint = joint if joint is not None else _joint_phi_plus()
    begun_a = {"round_index": i, "pair_id": f"pair-{i}", "lease_id": lease_a,
               "setting": 0, "state": joint}
    alice_reply = await _step(alice, "tok-alice", f"{prefix}-a{i}", sess, "measure_e91", begun_a)
    assert set(alice_reply) == {"ok", "round_index", "pair_id", "conditional"}
    assert alice_reply["round_index"] == i and alice_reply["pair_id"] == f"pair-{i}"
    conditional = decode_density(alice_reply["conditional"], "c", qubits=1)
    assert conditional.qubits == 1
    bob_reply = await _step(bob, "tok-bob", f"{prefix}-b{i}", sess, "measure_e91",
                            {"round_index": i, "pair_id": f"pair-{i}", "lease_id": lease_b,
                             "setting": 0, "state": alice_reply["conditional"]})
    assert bob_reply == {"ok": True, "round_index": i, "pair_id": f"pair-{i}", "count": i + 1}
    return alice_reply


def test_qkd_e91_private_seam_to_established():
    async def body():
        alice, bob = _qkd_workers()
        sess = "e91-full"
        await _begin(alice, "tok-alice", "op-ba", sess, "E91", "alice", "bob")
        await _begin(bob, "tok-bob", "op-bb", sess, "E91", "bob", "alice")
        leases_a = await _reserve(alice, "tok-alice", "op-ra", "e91", 4)
        leases_a += await _reserve(alice, "tok-alice", "op-ra2", "e91", 4)
        leases_b = await _reserve(bob, "tok-bob", "op-rb", "e91", 4)
        leases_b += await _reserve(bob, "tok-bob", "op-rb2", "e91", 4)
        for i in range(8):
            await _e91_round(alice, bob, leases_a[i], leases_b[i], sess, i, "e91")
        held = await _step(alice, "tok-alice", "op-len", sess, "lengths", {})
        assert held["key_length"] == 8 and held["state"] == "active"
        # E91 candidacy finalizes with empty index lists; non-empty is rejected.
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-sx", sess, "adopt_indices",
                       {"keep": encode_indices([0]), "phase": encode_indices([])})
        assert exc.value.status == 400
        adopt_a = await _step(alice, "tok-alice", "op-sa", sess, "adopt_indices",
                              {"keep": encode_indices([]), "phase": encode_indices([])})
        adopt_b = await _step(bob, "tok-bob", "op-sb", sess, "adopt_indices",
                              {"keep": encode_indices([]), "phase": encode_indices([])})
        assert adopt_a["key_length"] == 8 == adopt_b["key_length"]
        order = encode_indices(list(range(8)))
        syn = await _step(alice, "tok-alice", "op-syn", sess, "syndrome", {"order": order})
        await _step(bob, "tok-bob", "op-cor", sess, "correct",
                    {"order": order, "syndrome": syn["syndrome"]})
        tag_a = await _step(alice, "tok-alice", "op-ta", sess, "tag", {"seed": None})
        tag_b = await _step(bob, "tok-bob", "op-tb", sess, "tag", {"seed": tag_a["seed"]})
        # Ideal Phi+ Z/Z rounds correlate perfectly: independent hashes agree.
        assert tag_a["tag"] == tag_b["tag"]
        ext_a = await _step(alice, "tok-alice", "op-xa", sess, "extract",
                            {"output_length": 128, "seed": None})
        ext_b = await _step(bob, "tok-bob", "op-xb", sess, "extract",
                            {"output_length": 128, "seed": ext_a["seed"]})
        assert ext_a["output_length"] == 128 == ext_b["output_length"]
        assert ext_a["commitment"] != ext_b["commitment"]
        for node, worker, token in (("alice", alice, "tok-alice"), ("bob", bob, "tok-bob")):
            lengths = await _step(worker, token, f"op-l-{node}", sess, "lengths", {})
            assert lengths["state"] == "established"
            assert lengths["key_available"] is True

    _run(body())


def test_qkd_e91_round_scope_guards():
    async def body():
        alice, bob = _qkd_workers()
        sess = "e91-guards"
        await _begin(alice, "tok-alice", "op-ba", sess, "E91", "alice", "bob")
        await _begin(bob, "tok-bob", "op-bb", sess, "E91", "bob", "alice")
        leases_a = await _reserve(alice, "tok-alice", "op-ra", "e91", 4)
        leases_b = await _reserve(bob, "tok-bob", "op-rb", "e91", 4)
        await _e91_round(alice, bob, leases_a[0], leases_b[0], sess, 0, "g")
        # Replayed round index, skipped index, and reused pair all refuse.
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-a0b", sess, "measure_e91",
                       {"round_index": 0, "pair_id": "pair-9", "lease_id": leases_a[1],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.code == "stale_round"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-a2", sess, "measure_e91",
                       {"round_index": 2, "pair_id": "pair-2", "lease_id": leases_a[1],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.code == "future_round"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-ad", sess, "measure_e91",
                       {"round_index": 1, "pair_id": "pair-0", "lease_id": leases_a[1],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.code == "duplicate_round"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-au", sess, "measure_e91",
                       {"round_index": 1, "pair_id": "pair-1", "lease_id": "nope",
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.status == 404
        # Consumed leases never sample twice.
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-ac", sess, "measure_e91",
                       {"round_index": 1, "pair_id": "pair-1", "lease_id": leases_a[0],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.status == 409
        assert exc.value.code == "lease_unavailable"
        # Role/state shape: alice needs the joint density, bob the conditional.
        first = await _step(alice, "tok-alice", "op-a1", sess, "measure_e91",
                            {"round_index": 1, "pair_id": "pair-1", "lease_id": leases_a[1],
                             "setting": 0, "state": _joint_phi_plus()})
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-a1b", sess, "measure_e91",
                       {"round_index": 2, "pair_id": "pair-2", "lease_id": leases_a[2],
                        "setting": 0, "state": first["conditional"]})
        assert exc.value.status == 400
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-bj", sess, "measure_e91",
                       {"round_index": 1, "pair_id": "pair-j", "lease_id": leases_b[1],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.status == 400
        tampered = dict(first["conditional"])
        tampered["matrix"] = [[[1.5, 0.0], [0.0, 0.0]], [[0.0, 0.0], [-0.5, 0.0]]]
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-bt", sess, "measure_e91",
                       {"round_index": 0, "pair_id": "pair-t", "lease_id": leases_b[1],
                        "setting": 0, "state": tampered})
        assert exc.value.status == 400
        # BB84 sessions never take E91 rounds.
        await _begin(alice, "tok-alice", "op-bb84", "bb84-only")
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-x", "bb84-only", "measure_e91",
                       {"round_index": 0, "pair_id": "pair-x", "lease_id": leases_a[3],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.code == "protocol_mismatch"

    _run(body())


def test_qkd_e91_round_bound_is_20000(monkeypatch):
    import desk_gateway.quantum_node as quantum_node

    assert quantum_node._MAX_E91_ROUNDS == 20000
    monkeypatch.setattr(quantum_node, "_MAX_E91_ROUNDS", 2)

    async def body():
        alice, bob = _qkd_workers()
        sess = "e91-cap"
        await _begin(alice, "tok-alice", "op-ba", sess, "E91", "alice", "bob")
        await _begin(bob, "tok-bob", "op-bb", sess, "E91", "bob", "alice")
        leases_a = await _reserve(alice, "tok-alice", "op-ra", "e91", 2)
        leases_b = await _reserve(bob, "tok-bob", "op-rb", "e91", 2)
        await _e91_round(alice, bob, leases_a[0], leases_b[0], sess, 0, "c")
        await _e91_round(alice, bob, leases_a[1], leases_b[1], sess, 1, "c")
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-a2", sess, "measure_e91",
                       {"round_index": 2, "pair_id": "pair-2", "lease_id": leases_a[0],
                        "setting": 0, "state": _joint_phi_plus()})
        assert exc.value.status == 400
        assert exc.value.code == "invalid_round"

    _run(body())


def test_qkd_bounds_reject_out_of_range_inputs():
    async def body():
        alice, bob = _qkd_workers()
        sess = "bounds"
        await _begin(alice, "tok-alice", "op-ba", sess)
        await _begin(bob, "tok-bob", "op-bb", sess, role="bob", peer="alice")
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-big", sess, "prepare_bb84", {"count": 20001})
        assert exc.value.code == "invalid_count"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-big", sess, "measure_bb84",
                       {"signals": encode_signals([0] * 20001)})
        assert exc.value.code == "invalid_signal"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-big", sess, "prepare_bb84", {"count": True})
        assert exc.value.code == "invalid_count"
        prep = await _step(alice, "tok-alice", "op-p", sess, "prepare_bb84", {"count": 8})
        meas = await _step(bob, "tok-bob", "op-m", sess, "measure_bb84", {"signals": prep["signals"]})
        keep_dto, phase_dto, _ = await _matched_keep(prep, meas, 8)
        await _step(alice, "tok-alice", "op-sa", sess, "adopt_indices",
                    {"keep": keep_dto, "phase": phase_dto})
        await _step(bob, "tok-bob", "op-sb", sess, "adopt_indices",
                    {"keep": keep_dto, "phase": phase_dto})
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-sx", sess, "adopt_indices",
                       {"keep": encode_indices([8]), "phase": encode_indices([])})
        assert exc.value.code == "session_step"
        await _begin(alice, "tok-alice", "op-bb2", "bounds-2")
        await _step(alice, "tok-alice", "op-pb2", "bounds-2", "prepare_bb84", {"count": 4})
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-sb2", "bounds-2", "adopt_indices",
                       {"keep": encode_indices([4]), "phase": encode_indices([])})
        assert exc.value.status == 400
        assert exc.value.code == "invalid_index"
        order = encode_indices(list(range(8)))
        syn = await _step(alice, "tok-alice", "op-syn", sess, "syndrome", {"order": order})
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-syn2", sess, "syndrome",
                       {"order": encode_indices([0])})
        assert exc.value.code == "session_step"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-cor", sess, "correct",
                       {"order": order, "syndrome": encode_bits([0])})
        assert exc.value.code == "invalid_syndrome"
        await _step(bob, "tok-bob", "op-cor-ok", sess, "correct",
                    {"order": order, "syndrome": syn["syndrome"]})
        tag_a = await _step(alice, "tok-alice", "op-ta", sess, "tag", {"seed": None})
        with pytest.raises(QuantumNodeError) as exc:
            await _step(bob, "tok-bob", "op-tb", sess, "tag", {"seed": encode_bits([0] * 5)})
        assert exc.value.code == "invalid_seed"
        with pytest.raises(QuantumNodeError) as exc:
            await _step(alice, "tok-alice", "op-ta2", sess, "tag", {"seed": tag_a["seed"]})
        assert exc.value.code == "session_step"
        for ell in (64, 100, 264):
            with pytest.raises(QuantumNodeError) as exc:
                await _step(alice, "tok-alice", f"op-x{ell}", sess, "extract",
                            {"output_length": ell, "seed": None})
            assert exc.value.code == "invalid_extract_length"
        assert syn["leaked"] > 0

    _run(body())


def test_qkd_maximum_session_pipeline():
    async def body():
        import json as json_lib

        alice, bob = _qkd_workers()
        sess = "max-pipe"
        n = 20000
        await _begin(alice, "tok-alice", "op-ba", sess)
        await _begin(bob, "tok-bob", "op-bb", sess, role="bob", peer="alice")
        prep = await _step(alice, "tok-alice", "op-p", sess, "prepare_bb84", {"count": n})
        assert len(json_lib.dumps(prep).encode()) < 64 * 1024
        meas = await _step(bob, "tok-bob", "op-m", sess, "measure_bb84", {"signals": prep["signals"]})
        assert meas["count"] == n
        keep_dto, phase_dto, keep = await _matched_keep(prep, meas, n)
        assert len(keep) == n
        adopt = await _step(alice, "tok-alice", "op-sa", sess, "adopt_indices",
                            {"keep": keep_dto, "phase": phase_dto})
        assert adopt["key_length"] == n
        await _step(bob, "tok-bob", "op-sb", sess, "adopt_indices",
                    {"keep": keep_dto, "phase": phase_dto})
        order = encode_indices(list(range(n)))
        syn = await _step(alice, "tok-alice", "op-syn", sess, "syndrome", {"order": order})
        corr = await _step(bob, "tok-bob", "op-cor", sess, "correct",
                           {"order": order, "syndrome": syn["syndrome"]})
        assert corr["corrected_count"] == 0
        tag_a = await _step(alice, "tok-alice", "op-ta", sess, "tag", {"seed": None})
        tag_b = await _step(bob, "tok-bob", "op-tb", sess, "tag", {"seed": tag_a["seed"]})
        assert tag_a["tag"] == tag_b["tag"]
        ext_a = await _step(alice, "tok-alice", "op-xa", sess, "extract",
                            {"output_length": 128, "seed": None})
        assert len(decode_bits(ext_a["seed"], "s")) == n + 128 - 1
        assert ext_a["output_length"] == 128
        lengths = await _step(alice, "tok-alice", "op-l", sess, "lengths", {})
        assert lengths["state"] == "established"

    _run(body())


def test_qkd_oversized_envelopes_refuse_before_send():
    import httpx

    async def body():
        alice, bob = _qkd_workers()
        local = LocalNodeTransport({"alice": alice, "bob": bob})
        pad = {"count": 1, "pad": "x" * 70000}
        with pytest.raises(NodeCommandFailed) as exc:
            await local.qkd_step("alice", operation_id="op-pad", session_id="s",
                                 action="prepare_bb84", payload=pad)
        assert exc.value.status == 413
        ra = QuantumNodeWorker("alice", capacity=8, token="tok-alice")
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(ra)),
                                   base_url="http://a")
        remote = RemoteNodeTransport({"alice": "http://127.0.0.1:8891"}, {"alice": "tok-alice"},
                                     client=client)
        await remote.inspect("alice")
        with pytest.raises(NodeCommandFailed) as exc:
            await remote.qkd_step("alice", operation_id="op-pad", session_id="s",
                                  action="prepare_bb84", payload=pad)
        assert exc.value.status == 413
        await remote.aclose()

    _run(body())


def test_qkd_lengths_readonly_and_remote_taxonomy():
    import httpx

    async def body():
        alice, bob = _qkd_workers()
        await _bb84_establish(alice, bob, "ro-1", 8, "ro")
        first = await _step(alice, "tok-alice", "op-l", "ro-1", "lengths", {})
        second = await _step(alice, "tok-alice", "op-l", "ro-1", "lengths", {})
        assert first == second
        assert "op-l" not in alice._tombstones

    _run(body())

    def read_handler(request):
        raise httpx.ReadError("lost reply", request=request)

    def timeout_handler(request):
        raise httpx.TimeoutException("too slow", request=request)

    async def remote():
        transport = _remote(read_handler)
        with pytest.raises(NodeTransportUnavailable):
            await transport.qkd_step("n", operation_id="op-l", session_id="s",
                                     action="lengths", payload={}, instance="i")
        with pytest.raises(NodeTransportAmbiguous):
            await transport.qkd_step("n", operation_id="op-p", session_id="s",
                                     action="prepare_bb84", payload={"count": 4}, instance="i")
        await transport.aclose()
        transport = _remote(timeout_handler)
        with pytest.raises(NodeTransportDeadline):
            await transport.qkd_step("n", operation_id="op-l", session_id="s",
                                     action="lengths", payload={}, instance="i")
        await transport.aclose()

    _run(remote())


def test_qkd_capability_absent_from_public_surfaces():
    async def body():
        alice, bob = _qkd_workers()
        sess = "pub-1"
        ext_a, _ = await _bb84_establish(alice, bob, sess, 8, "pub")
        cap = await _owner(alice, "tok-alice", "op-cap", sess, "capability", {})
        secret = cap["capability"]
        assert secret
        lengths = await _step(alice, "tok-alice", "op-l", sess, "lengths", {})
        seen = await alice.inspect(token="tok-alice", node="alice", instance=alice.instance_id)
        use = await _owner(alice, "tok-alice", "op-use", sess, "use",
                           {"operation": "qkd_test", "capability": secret})
        for public in (lengths, seen, use, ext_a):
            assert secret not in json.dumps(public)
        assert secret not in repr(alice)
        assert secret not in repr(alice._qkd[sess])
        assert secret not in json.dumps(alice._seen_ops.get("op-use", ("", {}))[1])

    _run(body())


# Post-review worker boundary regressions. Authenticated consumers exercise
# retention, bounded inspection, and streamed reply admission; parent runs.


@pytest.mark.parametrize("remote", [False, True])
def test_measured_handles_charge_capacity_until_owner_release(remote):
    import httpx

    async def body():
        worker = QuantumNodeWorker("n", capacity=4, token="tok", rng=ScriptedRng([0.2]))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(worker))) as client:
            transport = (
                RemoteNodeTransport({"n": "http://127.0.0.1:8891"}, {"n": "tok"}, client=client)
                if remote else LocalNodeTransport({"n": worker})
            )
            instance = (await transport.inspect("n"))["instance_id"]
            held = await transport.reserve(
                "n", operation_id="retain-r", resource_id="retained", count=4, instance=instance)
            fields = {
                "operation_id": "retain-m", "lease_ids": held["leases"],
                "branch_probabilities": [1.0], "branch_bits": [[0]], "instance": instance,
            }
            measured = await transport.measure("n", **fields)
            assert measured["active_count"] == 4
            assert await transport.measure("n", **fields) == measured
            with pytest.raises(NodeCommandFailed) as exc:
                await transport.reserve(
                    "n", operation_id="retain-full", resource_id="overflow", count=1, instance=instance)
            assert exc.value.code == "capacity_exhausted"
            seen = await transport.inspect("n", instance=instance, resource_ids=["retained"])
            assert seen["lease_count"] == seen["active_count"] == 4
            assert all(lease["state"] == "measured" for lease in seen["leases"])
            released = await transport.release(
                "n", operation_id="retain-x", lease_ids=held["leases"], instance=instance)
            assert released["active_count"] == 0
            assert await transport.release(
                "n", operation_id="retain-x", lease_ids=held["leases"], instance=instance) == released
            # Historical reserve replay must not recreate reclaimed handles.
            assert await transport.reserve(
                "n", operation_id="retain-r", resource_id="retained", count=4, instance=instance) == held
            assert (await transport.inspect("n", instance=instance))["lease_count"] == 0
            fresh = await transport.reserve(
                "n", operation_id="retain-new", resource_id="fresh", count=4, instance=instance)
            assert fresh["active_count"] == 4
            assert set(fresh["leases"]).isdisjoint(held["leases"])

    _run(body())


def test_maximum_retention_fits_reserved_terminal_cleanup(monkeypatch):
    # Reduce only the history ceilings, not capacity/session bounds. Drive
    # actual effects up to the soft ceiling rather than seeding tombstones.
    import desk_gateway.quantum_node as quantum_node

    soft_cap = 256 * 2 + MAX_QKD_SESSIONS
    monkeypatch.setattr(quantum_node, "_NON_CLEANUP_EFFECT_CAP", soft_cap)
    monkeypatch.setattr(quantum_node, "_MAX_EFFECT_HISTORY", soft_cap + quantum_node._RESERVED_CLEANUP_SLOTS)
    monkeypatch.setattr(quantum_node, "_SEEN_OPS_CAP", 2)

    async def body():
        worker = QuantumNodeWorker("n", capacity=1024, token="tok")
        transport = LocalNodeTransport({"n": worker})
        instance = worker.instance_id
        handles = []
        for index in range(256):
            held = await transport.reserve(
                "n", operation_id=f"cleanup-r{index}", resource_id=f"res-{index}",
                count=4, instance=instance)
            handles.extend(held["leases"])
            await transport.measure(
                "n", operation_id=f"cleanup-m{index}", lease_ids=held["leases"], instance=instance)
        for index in range(MAX_QKD_SESSIONS):
            await transport.qkd_step(
                "n", operation_id=f"cleanup-b{index}", session_id=f"qkd-{index}", action="begin",
                payload={"protocol": "BB84", "role": "alice", "peer": "peer"}, instance=instance)
        assert (await transport.inspect("n", instance=instance))["active_count"] == 1024
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.reserve(
                "n", operation_id="cleanup-over", resource_id="over", count=1, instance=instance)
        assert exc.value.code == "history_exhausted"
        # Worst-case cleanup is one release per handle plus one abort per
        # session: exactly 1088 effects, including all measured handles.
        for index, lease in enumerate(handles):
            await transport.release(
                "n", operation_id=f"cleanup-x{index}", lease_ids=[lease], instance=instance)
        for index in range(MAX_QKD_SESSIONS):
            await transport.qkd_step(
                "n", operation_id=f"cleanup-a{index}", session_id=f"qkd-{index}",
                action="abort", payload={"reason": "user_abort"}, instance=instance)
        seen = await transport.inspect("n", instance=instance)
        assert seen["leases"] == [] and seen["lease_count"] == seen["active_count"] == 0
        assert worker._qkd_nonterminal_count() == 0
        assert len(worker._tombstones) == quantum_node._MAX_EFFECT_HISTORY
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.measure(
                "n", operation_id="cleanup-m0", lease_ids=handles[:4], instance=instance)
        assert exc.value.code == "operation_expired"
        assert (await transport.inspect("n", instance=instance))["lease_count"] == 0

    _run(body())


def test_maximum_long_id_inspection_pages_over_real_http():
    import socket

    import httpx
    import uvicorn

    async def body():
        worker = QuantumNodeWorker("n", capacity=1024, token="tok")
        ready = asyncio.Event()

        class ReadyServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                ready.set()

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        sock.setblocking(False)
        endpoint = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = ReadyServer(uvicorn.Config(
            create_node_app(worker), log_level="critical", access_log=False, lifespan="off"))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            await asyncio.wait_for(ready.wait(), timeout=5)
            assert server.started
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
                transport = RemoteNodeTransport({"n": endpoint}, {"n": "tok"}, client=client)
                instance = (await transport.inspect("n"))["instance_id"]
                resources, handles = [], []
                for index in range(256):
                    resource = "r" * 124 + f"{index:04d}"
                    resources.append(resource)
                    held = await transport.reserve(
                        "n", operation_id=f"http-r{index}", resource_id=resource,
                        session_id="s" * 128, count=4, instance=instance)
                    handles.extend(held["leases"])
                assert all(len(handle) == 128 for handle in handles)
                # Unpinned discovery remains usable at maximum occupancy.
                discovery = await transport.inspect("n")
                assert discovery["instance_id"] == instance
                assert discovery["lease_count"] == discovery["active_count"] == 1024
                assert discovery["next_offset"] == 64
                gathered, offset = [], 0
                while offset is not None:
                    page = await transport.inspect("n", instance=instance, lease_offset=offset)
                    assert page["lease_count"] == 1024 and page["lease_limit"] == 64
                    assert page["lease_offset"] == offset and len(page["leases"]) == 64
                    assert len(json.dumps(page).encode()) <= 64 * 1024
                    gathered.extend(row["lease_id"] for row in page["leases"])
                    offset = page["next_offset"]
                assert gathered == handles
                # Filtering must happen before offsets, not after the first
                # 64 records. Chosen resources live near the end of storage.
                selected = resources[-4:]
                page = await transport.inspect(
                    "n", instance=instance, resource_ids=selected, lease_offset=3, lease_limit=5)
                assert page["lease_count"] == 16 and page["active_count"] == 1024
                assert page["next_offset"] == 8
                assert [row["lease_id"] for row in page["leases"]] == handles[-16:][3:8]
                tail = await transport.inspect(
                    "n", instance=instance, resource_ids=selected, lease_offset=15, lease_limit=1)
                assert tail["next_offset"] is None and len(tail["leases"]) == 1
                empty = await transport.inspect("n", instance=instance, resource_ids=[])
                assert empty["lease_count"] == 0 and empty["leases"] == [] and empty["next_offset"] is None
                past = await transport.inspect("n", instance=instance, lease_offset=1024)
                assert past["lease_count"] == 1024 and past["leases"] == [] and past["next_offset"] is None
                with pytest.raises(NodeCommandFailed) as exc:
                    await transport.inspect("n", instance="original-instance-is-stale", resource_ids=selected)
                assert exc.value.code == "stale_instance"
                assert (await transport.inspect("n", instance=instance))["lease_count"] == 1024
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, timeout=5)
            sock.close()

    _run(body())


@pytest.mark.parametrize("fields,code", [
    ({"lease_offset": True}, "invalid_offset"),
    ({"lease_offset": -1}, "invalid_offset"),
    ({"lease_offset": 0.0}, "invalid_offset"),
    ({"lease_limit": True}, "invalid_limit"),
    ({"lease_limit": 0}, "invalid_limit"),
    ({"lease_limit": 65}, "invalid_limit"),
    ({"lease_limit": "64"}, "invalid_limit"),
    ({"resource_ids": "r"}, "invalid_resources"),
    ({"resource_ids": ("r",)}, "invalid_resources"),
    ({"resource_ids": ["r"] * 2}, "invalid_resources"),
    ({"resource_ids": ["a", "b", "c", "d", "e"]}, "invalid_resources"),
    ({"resource_ids": [True]}, "invalid_id"),
    ({"resource_ids": ["x" * 129]}, "invalid_id"),
    ({"resource_ids": ["bad/id"]}, "invalid_id"),
])
@pytest.mark.parametrize("remote", [False, True])
def test_inspect_strict_bounds_and_filters(fields, code, remote):
    import httpx

    async def body():
        worker = QuantumNodeWorker("n", token="tok")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(worker))) as client:
            transport = (
                RemoteNodeTransport({"n": "http://127.0.0.1:8891"}, {"n": "tok"}, client=client)
                if remote else LocalNodeTransport({"n": worker})
            )
            with pytest.raises(NodeCommandFailed) as exc:
                await transport.inspect("n", instance=worker.instance_id, **fields)
            assert exc.value.status == 400 and exc.value.code == code
            assert worker._tombstones == {} and worker._leases == {}

    _run(body())


def test_inspect_authentication_precedes_filter_admission():
    import httpx

    async def body():
        worker = QuantumNodeWorker("n", token="tok")
        with pytest.raises(QuantumNodeError) as exc:
            await worker.inspect(token="wrong", node="n", lease_limit=True, resource_ids=["bad/id"])
        assert exc.value.code == "unauthenticated"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_node_app(worker))) as client:
            reply = await client.post(
                "http://worker/v1/node/inspect",
                headers={"Authorization": "Bearer wrong"},
                json={"node": "n", "lease_limit": True, "resource_ids": ["bad/id"]})
            assert reply.status_code == 401 and reply.json()["error"] == "unauthenticated"
        assert worker._tombstones == {} and worker._leases == {}

    _run(body())


def _streamed_remote(chunks, *, headers=None, deadline=20):
    import httpx

    class ReplyStream(httpx.AsyncByteStream):
        def __init__(self):
            self.yielded = 0
            self.closed = False

        async def __aiter__(self):
            for chunk in chunks:
                self.yielded += 1
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk

        async def aclose(self):
            self.closed = True

    stream = ReplyStream()
    transport = _remote(
        lambda request: httpx.Response(200, headers=headers, stream=stream), deadline=deadline)
    return transport, stream


@pytest.mark.parametrize("operation", ["reserve", "inspect", "lengths"])
def test_streamed_reply_overflow_closes_before_reading_remainder(operation):
    async def body():
        # Exactly one cap of chunks, one bounded overflow chunk, and a
        # sentinel remainder which must never be requested.
        transport, stream = _streamed_remote([b" " * 4096] * 17 + [AssertionError("read remainder")])
        expected = NodeTransportAmbiguous if operation == "reserve" else NodeTransportUnavailable
        try:
            with pytest.raises(expected):
                if operation == "reserve":
                    await transport.reserve(
                        "n", operation_id="stream-r", resource_id="r", count=1, instance="i")
                elif operation == "lengths":
                    await transport.qkd_step(
                        "n", operation_id="stream-l", session_id="s", action="lengths",
                        payload={}, instance="i")
                else:
                    await transport.inspect("n")
            assert stream.yielded == 17 and stream.closed
        finally:
            await transport.client.aclose()

    _run(body())


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_streamed_compressed_reply_has_decompressed_byte_cap(encoding):
    import random
    import zlib

    compressor = zlib.compressobj(wbits=16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
    # sync-flush supplies a whole first wire chunk which expands beyond the
    # cap; the remainder contains the still-unread compressed frame trailer.
    compressed = compressor.compress(b" " * (128 * 1024)) + compressor.flush(zlib.Z_SYNC_FLUSH)
    # An incompressible deterministic suffix makes the first wire chunk
    # complete without needing to ask for the sentinel remainder.
    suffix = random.Random(0).randbytes(8192)
    compressed += compressor.compress(suffix) + compressor.flush(zlib.Z_SYNC_FLUSH)
    trailer = compressor.flush()
    assert len(compressed) >= 4096

    async def body():
        transport, stream = _streamed_remote(
            [compressed[:4096], AssertionError("read compressed remainder")],
            headers={"Content-Encoding": encoding})
        try:
            with pytest.raises(NodeTransportUnavailable, match="oversized"):
                await transport.inspect("n")
            assert stream.yielded == 1 and stream.closed
        finally:
            await transport.client.aclose()
        assert trailer  # The fixture intentionally did not supply EOF.

    _run(body())


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
def test_streamed_valid_reply_exact_cap_and_compression(encoding):
    import zlib

    # Keep the payload exactly at the admission boundary.
    raw = b'{"ok":true,"padding":"' + b"x" * (65536 - len(b'{"ok":true,"padding":""}')) + b'"}'
    assert len(raw) == 65536
    if encoding != "identity":
        compressor = zlib.compressobj(wbits=16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS)
        raw = compressor.compress(raw) + compressor.flush()

    async def body():
        transport, stream = _streamed_remote(
            [raw[index:index + 4096] for index in range(0, len(raw), 4096)],
            headers={"Content-Encoding": encoding})
        try:
            reply = await transport.inspect("n")
            assert reply["ok"] is True
            assert stream.closed
        finally:
            await transport.client.aclose()

    _run(body())


@pytest.mark.parametrize("frame", [b"", b"{", b"[]", b"null", b"{}", b'{"ok":1}', b"\xff"])
@pytest.mark.parametrize("operation", ["reserve", "inspect", "lengths"])
def test_streamed_malformed_or_empty_reply_taxonomy(frame, operation):
    async def body():
        transport, stream = _streamed_remote([frame])
        expected = NodeTransportAmbiguous if operation == "reserve" else NodeTransportUnavailable
        try:
            with pytest.raises(expected):
                if operation == "reserve":
                    await transport.reserve(
                        "n", operation_id="bad-r", resource_id="r", count=1, instance="i")
                elif operation == "lengths":
                    await transport.qkd_step(
                        "n", operation_id="bad-l", session_id="s",
                        action="lengths", payload={}, instance="i")
                else:
                    await transport.inspect("n")
            assert stream.closed
        finally:
            await transport.client.aclose()

    _run(body())


@pytest.mark.parametrize("operation", ["reserve", "inspect", "lengths"])
def test_streamed_overall_deadline_bounds_repeated_chunks(operation, monkeypatch):
    import httpx

    import desk_gateway.quantum_transport as quantum_transport

    clock = {"now": 0.0}
    # Replace only this module's time binding, never the event loop clock.
    monkeypatch.setattr(quantum_transport, "time", SimpleNamespace(monotonic=lambda: clock["now"]))

    async def body():
        reached, closed = [], []

        class NeverEndingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                while True:
                    # Synchronous chunks need the monotonic guard too:
                    # wait_for cannot interrupt a task which never yields.
                    reached.append(True)
                    clock["now"] += 1.0
                    yield b" " * 4096

            async def aclose(self):
                closed.append(True)

        transport = _remote(
            lambda request: httpx.Response(200, stream=NeverEndingStream()),
            deadline=3)
        expected = NodeTransportAmbiguous if operation == "reserve" else NodeTransportDeadline
        try:
            with pytest.raises(expected):
                if operation == "reserve":
                    await transport.reserve(
                        "n", operation_id="deadline-r", resource_id="r", count=1, instance="i")
                elif operation == "lengths":
                    await transport.qkd_step(
                        "n", operation_id="deadline-l", session_id="s",
                        action="lengths", payload={}, instance="i")
                else:
                    await transport.inspect("n")
            assert len(reached) == 3 and closed == [True]
        finally:
            await transport.client.aclose()

    _run(body())


@pytest.mark.parametrize("value", [True, False, 0.0, 1.0, 0.5, "0", None, {}, [], -1, 2])
def test_encode_bits_rejects_noninteger_or_nonbit_values(value):
    with pytest.raises(QuantumNodeError) as exc:
        encode_bits([value])
    assert exc.value.status == 400 and exc.value.code == "invalid_bits"


def test_qkd_random_only_rng_prepares_and_measures_both_bases():
    async def body():
        # Alice: bit1/Z, bit0/X. Bob: Z/outcome1, X/outcome0.
        alice = QuantumNodeWorker("alice", token="tok-alice", rng=ScriptedRng([0.1, 0.1, 0.9, 0.9]))
        bob = QuantumNodeWorker("bob", token="tok-bob", rng=ScriptedRng([0.1, 0.2, 0.9, 0.2]))
        transport = LocalNodeTransport({"alice": alice, "bob": bob})
        for node, role, peer in (("alice", "alice", "bob"), ("bob", "bob", "alice")):
            await transport.qkd_step(
                node, operation_id="rng-b", session_id="rng", action="begin",
                payload={"protocol": "BB84", "role": role, "peer": peer})
        prep = await transport.qkd_step(
            "alice", operation_id="rng-p", session_id="rng",
            action="prepare_bb84", payload={"count": 2})
        assert decode_signals(prep["signals"], "signals") == (1, 2)
        assert decode_bits(prep["bases"], "bases") == (0, 1)
        meas = await transport.qkd_step(
            "bob", operation_id="rng-m", session_id="rng",
            action="measure_bb84", payload={"signals": prep["signals"]})
        assert decode_bits(meas["bases"], "bases") == (0, 1)
        for node in ("alice", "bob"):
            adopted = await transport.qkd_step(
                node, operation_id="rng-a", session_id="rng", action="adopt_indices",
                payload={"keep": encode_indices([]), "phase": encode_indices([0, 1])})
            assert decode_bits(adopted["phase_sample"], "phase") == (1, 0)
        # Replays do not draw again from the now-exhausted minimal RNGs.
        assert await transport.qkd_step(
            "alice", operation_id="rng-p", session_id="rng",
            action="prepare_bb84", payload={"count": 2}) == prep
        assert await transport.qkd_step(
            "bob", operation_id="rng-m", session_id="rng",
            action="measure_bb84", payload={"signals": prep["signals"]}) == meas

    _run(body())


@pytest.mark.parametrize("draw", [True, None, "0.1", float("nan"), float("inf"), -0.1, 1.0])
@pytest.mark.parametrize("action", ["prepare_bb84", "measure_bb84"])
def test_qkd_invalid_basis_rng_is_typed_failure(draw, action):
    async def body():
        # Preparation consumes a valid bit draw before its invalid basis;
        # measurement draws its basis first, before any state mutation.
        values = [0.1, draw] if action == "prepare_bb84" else [draw]
        worker = QuantumNodeWorker("n", token="tok", rng=_FixedQkdRng(values))
        transport = LocalNodeTransport({"n": worker})
        await transport.qkd_step(
            "n", operation_id="invalid-b", session_id="invalid", action="begin",
            payload={"protocol": "BB84", "role": "alice" if action == "prepare_bb84" else "bob", "peer": "peer"})
        payload = {"count": 1} if action == "prepare_bb84" else {"signals": encode_signals([0])}
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.qkd_step(
                "n", operation_id="invalid-draw", session_id="invalid", action=action, payload=payload)
        assert exc.value.status == 503 and exc.value.code == "rng_failure"
        assert "invalid-draw" not in worker._tombstones
        assert worker._qkd["invalid"].raw_bits == [] and worker._qkd["invalid"].raw_bases == []

    _run(body())


@pytest.mark.parametrize("encoding,frame", [
    ("gzip", b"not-a-gzip-frame"),
    ("deflate", b"not-a-deflate-frame"),
    ("gzip", b"\x1f\x8b\x08"),
    ("br", b"unsupported"),
])
@pytest.mark.parametrize("mutating", [False, True])
def test_streamed_invalid_compression_remains_nonacknowledgement(encoding, frame, mutating):
    async def body():
        transport, stream = _streamed_remote([frame], headers={"Content-Encoding": encoding})
        try:
            with pytest.raises(NodeTransportAmbiguous if mutating else NodeTransportUnavailable):
                if mutating:
                    await transport.reserve(
                        "n", operation_id="codec-r", resource_id="r", count=1, instance="i")
                else:
                    await transport.inspect("n")
            assert stream.closed
        finally:
            await transport.client.aclose()

    _run(body())


def test_qkd_missing_random_method_is_typed_failure():
    async def body():
        worker = QuantumNodeWorker("n", token="tok", rng=object())
        transport = LocalNodeTransport({"n": worker})
        await transport.qkd_step(
            "n", operation_id="missing-b", session_id="missing", action="begin",
            payload={"protocol": "BB84", "role": "alice", "peer": "peer"})
        with pytest.raises(NodeCommandFailed) as exc:
            await transport.qkd_step(
                "n", operation_id="missing-p", session_id="missing",
                action="prepare_bb84", payload={"count": 1})
        assert exc.value.code == "rng_failure" and exc.value.status == 503
        assert "missing-p" not in worker._tombstones

    _run(body())
