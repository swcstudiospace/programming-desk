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
    QuantumNodeError,
    QuantumNodeWorker,
    build_node_parser,
    create_node_app,
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
        assert seen["active_count"] == 0

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
