"""Behavior tests for the phase-68 faithful resource/protocol tier (REQ-QTELEPORT-001–004).

Consumer-visible math, branch evidence, and lifecycle invariants over the new
async workflows (BellPairPool / EntanglementPurifier / EntanglementSwapper /
QuantumRepeaterMesh / QuantumTeleportationProtocol) with deterministic
injected RNGs and LocalNodeTransport. No source-text, wiring, mock-echo, or
incidental-default assertions: every claim is exercised behavior.
"""

import asyncio
import json
import math

import pytest

from desk_gateway import quantum_state
from desk_gateway.quantum_node import QuantumNodeWorker
from desk_gateway.quantum_transport import LocalNodeTransport, NodeCommandFailed, NodeTransportAmbiguous
from desk_gateway.quantum_teleportation import (
    BellPairPool,
    BellStateType,
    EntanglementPurifier,
    EntanglementSwapper,
    QuantumRepeaterMesh,
    QuantumResourceError,
    QuantumTeleportationProtocol,
)


class ScriptedRng:
    """Deterministic injected draw source; exhausts loudly, never silently."""

    def __init__(self, draws):
        self._draws = list(draws)

    def random(self):
        assert self._draws, "scripted RNG exhausted"
        value = self._draws.pop(0)
        assert 0.0 <= value < 1.0
        return value


def _run(awaitable):
    return asyncio.run(awaitable)


def _setup(nodes=("alice", "bob"), capacities=None, worker_rngs=None, pool_draws=None, sink=True):
    from desk_gateway.quantum_transport import LocalNodeTransport

    workers = {}
    for name in nodes:
        draws = (worker_rngs or {}).get(name, [0.5])
        workers[name] = QuantumNodeWorker(
            name,
            capacity=(capacities or {}).get(name, 8),
            token=f"tok-{name}",
            rng=ScriptedRng(list(draws)),
        )
    transport = LocalNodeTransport(workers)
    events = []

    async def append_event(event):
        events.append(dict(event))
        return {"receipt_id": f"r-{len(events)}", "seq": len(events)}

    pool = BellPairPool(
        rng=ScriptedRng(list(pool_draws) if pool_draws else [0.5] * 64),
        transport=transport,
        append_event=append_event if sink else None,
    )
    ctx = {"workers": workers, "transport": transport, "pool": pool, "events": events}
    return type("Ctx", (), ctx)()


async def _pair(pool, node_a="alice", node_b="bob", kind=BellStateType.PHI_PLUS, fidelity=1.0):
    return await pool.create_pair(node_a, node_b, kind, fidelity)


def _werner_oracles(f1, f2):
    a = (1.0 - f1) / 3.0
    b = (1.0 - f2) / 3.0
    p_accept = (f1 + a) * (f2 + b) + 4.0 * a * b
    f_accept = (f1 * f2 + a * b) / p_accept
    return p_accept, f_accept


# --------------------------------------------------------------------------
# pool lifecycle


def test_pool_create_snapshot_and_status():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool, fidelity=0.98)
        assert pair.fidelity == pytest.approx(0.98, abs=1e-9)
        assert pair.frame == (0, 0)
        snap = ctx.pool.snapshot(pair.pair_id)
        assert snap is not None
        assert snap.status.value == "active"
        assert snap.fidelity == pytest.approx(0.98, abs=1e-9)
        assert ctx.pool.status_of(pair.pair_id).value == "active"
        active = ctx.pool.list_active_pairs("alice", "bob")
        assert [s.pair_id for s in active] == [pair.pair_id]
        assert ctx.pool.snapshot("bell-missing") is None
        assert ctx.pool.status_of("bell-missing") is None

    _run(body())


def test_pool_consume_is_single_use():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool)
        await ctx.pool.reserve_pairs((pair.pair_id,), operation_id="op-1")
        await ctx.pool.consume_pairs((pair.pair_id,), operation_id="op-1")
        assert ctx.pool.status_of(pair.pair_id).value == "consumed"
        assert ctx.pool.list_active_pairs("alice", "bob") == []
        # Retried consumption of the same pair reports conflict, never success.
        with pytest.raises(QuantumResourceError) as exc:
            await ctx.pool.reserve_pairs((pair.pair_id,), operation_id="op-2")
        assert exc.value.code == "pair_unavailable"
        assert exc.value.status == 409
        with pytest.raises(QuantumResourceError) as exc:
            await ctx.pool.reserve_pairs(("bell-missing",), operation_id="op-3")
        assert exc.value.code == "unknown_pair"
        assert exc.value.status == 404

    _run(body())


def test_pool_concurrent_reservation_admits_single_winner():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool)
        first, second = await asyncio.gather(
            ctx.pool.reserve_pairs((pair.pair_id,), operation_id="op-a"),
            ctx.pool.reserve_pairs((pair.pair_id,), operation_id="op-b"),
            return_exceptions=True,
        )
        wins = [r for r in (first, second) if not isinstance(r, Exception)]
        losses = [r for r in (first, second) if isinstance(r, Exception)]
        assert len(wins) == 1
        assert len(losses) == 1
        assert isinstance(losses[0], QuantumResourceError)
        assert losses[0].code == "pair_unavailable"

    _run(body())


def test_mesh_duplicate_node_registration_never_resets_state():
    async def body():
        ctx = _setup()
        mesh = QuantumRepeaterMesh(ctx.pool)
        first = mesh.register_node("rep-1", "us-east")
        with pytest.raises(QuantumResourceError) as exc:
            mesh.register_node("rep-1", "eu-west")
        assert exc.value.code == "duplicate_node"
        assert mesh.nodes["rep-1"] is first
        assert mesh.nodes["rep-1"].cluster_region == "us-east"

    _run(body())


# --------------------------------------------------------------------------
# BBPSSW purification


def test_purify_accept_reports_branch_evidence_and_keeps_untwirled_state():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.1], "bob": [0.5]})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is True
        assert result.protocol == "BBPSSW"
        assert result.reason == "parity_accept"
        assert result.branch_bits == (0, 0)
        p_accept, f_accept = _werner_oracles(0.90, 0.92)
        assert p_accept == pytest.approx(0.887111111111, abs=1e-9)
        assert f_accept == pytest.approx(0.934368737475, abs=1e-9)
        assert result.p_accept == pytest.approx(p_accept, abs=1e-9)
        assert result.output_fidelity == pytest.approx(f_accept, abs=1e-9)
        assert result.branch_probability == pytest.approx(p_accept / 2, abs=1e-12)
        output = ctx.pool.get_pair(result.output_pair_id)
        assert output is not None
        # The retained rho is the exact untwirled partial trace, not a
        # re-Wernerized mixture at the accepted fidelity.
        rewernered = quantum_state.QuantumDensityMatrix.bell_mixture("PHI_PLUS", f_accept)
        worst = max(
            abs(output.rho.rows[i][j] - rewernered.rows[i][j]) for i in range(4) for j in range(4)
        )
        assert worst > 1e-6
        assert ctx.pool.status_of(first.pair_id).value == "consumed"
        assert ctx.pool.status_of(second.pair_id).value == "consumed"
        assert ctx.pool.status_of(result.output_pair_id).value == "active"
        kinds = [event["event_type"] for event in ctx.events]
        assert "purify.accepted" in kinds

    _run(body())


def test_purify_reject_discards_both_inputs_with_no_output():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.6], "bob": [0.05]})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is False
        assert result.reason == "parity_reject"
        assert result.output_pair_id is None
        assert result.branch_bits == (1, 0)
        p_accept, _ = _werner_oracles(0.90, 0.92)
        assert result.p_accept == pytest.approx(p_accept, abs=1e-9)
        assert result.branch_probability == pytest.approx(0.056444444444, abs=1e-9)
        assert ctx.pool.status_of(first.pair_id).value == "discarded"
        assert ctx.pool.status_of(second.pair_id).value == "discarded"
        assert ctx.pool.list_active_pairs() == []
        kinds = [event["event_type"] for event in ctx.events]
        assert "purify.rejected" in kinds

    _run(body())


# --------------------------------------------------------------------------
# swap


def test_swap_phi_plus_chain_reports_branch_and_worker_authorized_correction():
    async def body():
        ctx = _setup(nodes=("a", "r", "c"), worker_rngs={"r": [0.3]})
        swapper = EntanglementSwapper(ctx.pool)
        left = await _pair(ctx.pool, "a", "r")
        right = await _pair(ctx.pool, "r", "c")
        result = await swapper.swap(left.pair_id, right.pair_id)
        assert result.accepted is True
        assert result.bsm_bits == (0, 1)
        assert (result.correction_x, result.correction_z) == (1, 0)
        assert (result.gate_x, result.gate_z) == (True, False)
        assert result.correction_origin == "worker-authorized"
        assert result.output_fidelity == pytest.approx(1.0, abs=1e-9)
        output = ctx.pool.get_pair(result.output_pair_id)
        assert {output.node_a, output.node_b} == {"a", "c"}
        assert output.fidelity == pytest.approx(1.0, abs=1e-9)
        assert ctx.pool.status_of(left.pair_id).value == "consumed"
        assert ctx.pool.status_of(right.pair_id).value == "consumed"
        kinds = [event["event_type"] for event in ctx.events]
        assert "swap.completed" in kinds

    _run(body())


def test_swap_frame_xor_correction_with_reversed_orientation():
    async def body():
        ctx = _setup(nodes=("a", "r", "c"), worker_rngs={"r": [0.3]})
        swapper = EntanglementSwapper(ctx.pool)
        left = await _pair(ctx.pool, "r", "a", BellStateType.PSI_PLUS)
        right = await _pair(ctx.pool, "c", "r", BellStateType.PHI_MINUS)
        result = await swapper.swap(left.pair_id, right.pair_id)
        assert result.accepted is True
        frame_a = quantum_state.BellState("PSI_PLUS").frame
        frame_b = quantum_state.BellState("PHI_MINUS").frame
        bsm_z, bsm_x = result.bsm_bits
        assert result.correction_x == (bsm_x ^ frame_a[0] ^ frame_b[0])
        assert result.correction_z == (bsm_z ^ frame_a[1] ^ frame_b[1])
        assert result.gate_x == bool(result.correction_x)
        assert result.gate_z == bool(result.correction_z)
        output = ctx.pool.get_pair(result.output_pair_id)
        assert {output.node_a, output.node_b} == {"a", "c"}

    _run(body())


# --------------------------------------------------------------------------
# mesh routing


def test_mesh_multi_hop_route_and_rejections():
    async def body():
        ctx = _setup(nodes=("a", "r", "b"), worker_rngs={"r": [0.1]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        for node in ("a", "r", "b"):
            mesh.register_node(node, "test")
        mesh.register_link("a", "r")
        mesh.register_link("r", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(
            ["a", "r", "b"], base_fidelity=0.98, purify_hops=False
        )
        assert ok is True
        assert pair is not None
        assert {pair.node_a, pair.node_b} == {"a", "b"}
        assert pair.fidelity == pytest.approx(0.98 * 0.98 + (0.02 * 0.02) / 3, abs=1e-9)
        assert len(logs) >= 1
        # Rejections never crash and never mint a pair.
        too_long = [f"n-{index}" for index in range(17)]
        for bad_route in (too_long, ["a", "ghost", "b"], ["a", "r", "a"], ["a", "b"], []):
            failed, missing, failure_logs = await mesh.establish_multi_hop_entanglement(bad_route)
            assert failed is False
            assert missing is None
            assert len(failure_logs) >= 1

    _run(body())


# --------------------------------------------------------------------------
# teleportation


def test_teleport_complex_input_success_with_receiver_density():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.3]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        pair = await _pair(ctx.pool, fidelity=1.0)
        alpha, beta = complex(0.5, 0.5), complex(0.5, -0.5)
        result = await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair.pair_id)
        assert result.success is True
        assert result.reason == "teleported"
        assert result.fidelity == pytest.approx(1.0, abs=1e-9)
        assert result.correction_applied is True
        assert result.acknowledged is True
        assert result.input_destroyed is True
        assert result.resource_consumed is True
        assert result.correction.correction_x == (result.bsm_bits[1] ^ result.frame[0])
        assert result.correction.correction_z == (result.bsm_bits[0] ^ result.frame[1])
        assert result.gate_x == bool(result.correction.correction_x)
        assert result.gate_z == bool(result.correction.correction_z)
        assert result.receiver_matrix is not None
        assert result.receipt is not None
        assert ctx.pool.status_of(pair.pair_id).value == "consumed"
        body_dict = result.to_dict()
        assert body_dict["fidelity"] == result.fidelity
        assert body_dict["success"] is True
        json.dumps(body_dict)
        # Single use: the same pair can never teleport twice.
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair.pair_id)
        assert exc.value.code == "pair_unavailable"
        assert exc.value.status == 409

    _run(body())


def test_teleport_below_threshold_consumes_resource_with_raw_fidelity():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.3]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        pair = await _pair(ctx.pool, fidelity=0.90)
        result = await proto.teleport_qubit(
            "alice", "bob", complex(0.6, 0.0), complex(0.8, 0.0), bell_pair=pair.pair_id
        )
        assert result.success is False
        assert result.reason == "below_threshold"
        assert result.resource_consumed is True
        assert result.input_destroyed is True
        # Raw Werner teleport overlap (2F+1)/3, exposed unrounded.
        assert result.fidelity == pytest.approx((2 * 0.90 + 1) / 3, abs=1e-9)
        assert result.to_dict()["fidelity"] == result.fidelity
        assert ctx.pool.status_of(pair.pair_id).value == "consumed"

    _run(body())


def test_teleport_selection_errors_are_fail_closed():
    async def body():
        ctx = _setup(nodes=("alice", "bob", "carol"))
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        alpha, beta = complex(1.0, 0.0), complex(0.0, 0.0)
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair="bell-missing")
        assert exc.value.code == "unknown_pair"
        assert exc.value.status == 404
        pair = await _pair(ctx.pool)
        foreign = await _pair(ctx.pool, "alice", "carol")
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair.pair_id,
                                       intermediate_hops=["relay"])
        assert exc.value.code == "invalid_selection"
        assert exc.value.status == 400
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=foreign.pair_id)
        assert exc.value.code == "endpoint_mismatch"
        assert exc.value.status == 409
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair)
        assert exc.value.code == "invalid_selection"
        assert exc.value.status == 400
        with pytest.raises(QuantumResourceError):
            await proto.teleport_qubit("alice", "alice", alpha, beta)

    _run(body())


def test_teleport_concurrent_consumers_admit_single_success():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.2, 0.7]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        pair = await _pair(ctx.pool, fidelity=1.0)
        alpha, beta = complex(1.0, 0.0), complex(0.0, 0.0)
        first, second = await asyncio.gather(
            proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair.pair_id),
            proto.teleport_qubit("alice", "bob", alpha, beta, bell_pair=pair.pair_id),
            return_exceptions=True,
        )
        outcomes = [first, second]
        wins = [r for r in outcomes if not isinstance(r, Exception)]
        losses = [r for r in outcomes if isinstance(r, Exception)]
        assert len(wins) == 1 and wins[0].success is True
        assert len(losses) == 1 and losses[0].code == "pair_unavailable"

    _run(body())


def test_snapshot_is_immutable_and_tracks_lifecycle():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool, fidelity=0.97)
        first = ctx.pool.snapshot(pair.pair_id)
        second = ctx.pool.snapshot(pair.pair_id)
        assert first == second
        with pytest.raises(Exception):
            first.status = "consumed"  # frozen dataclass rejects mutation
        await ctx.pool.reserve_pairs((pair.pair_id,), operation_id="op-9")
        await ctx.pool.consume_pairs((pair.pair_id,), operation_id="op-9")
        third = ctx.pool.snapshot(pair.pair_id)
        assert third.status.value == "consumed"
        assert third.fidelity == pytest.approx(0.97, abs=1e-9)
        # The earlier snapshot still reports the lifecycle moment it captured.
        assert first.status.value == "active"

    _run(body())


# --------------------------------------------------------------------------
# gap-closure helpers: scripted transports and sinks (68-06)


def _ctx_with(transport_factory, nodes=("alice", "bob"), worker_draws=None, sink=True):
    workers = {}
    for name in nodes:
        draws = (worker_draws or {}).get(name, [0.5])
        workers[name] = QuantumNodeWorker(
            name, capacity=8, token=f"tok-{name}", rng=ScriptedRng(list(draws)),
        )
    transport = transport_factory(workers)
    events = []

    async def append_event(event):
        events.append(dict(event))
        return {"receipt_id": f"r-{len(events)}", "seq": len(events)}

    pool = BellPairPool(
        rng=ScriptedRng([0.5] * 64),
        transport=transport,
        append_event=append_event if sink else None,
    )
    ctx = {"workers": workers, "transport": transport, "pool": pool, "events": events}
    return type("Ctx", (), ctx)()


class _CancelOnCall(LocalNodeTransport):
    """Raises CancelledError on the Nth call of one method, delegates otherwise."""

    def __init__(self, workers, *, method, fail_on=1):
        super().__init__(workers)
        self._method = method
        self._fail_on = fail_on
        self._calls = 0

    async def _maybe_cancel(self):
        self._calls += 1
        if self._calls == self._fail_on:
            raise asyncio.CancelledError()

    async def reserve(self, node_id, **kwargs):
        if self._method == "reserve":
            await self._maybe_cancel()
        return await super().reserve(node_id, **kwargs)

    async def measure(self, node_id, **kwargs):
        if self._method == "measure":
            await self._maybe_cancel()
        return await super().measure(node_id, **kwargs)


class _AmbiguousMeasure(LocalNodeTransport):
    async def measure(self, node_id, **kwargs):
        raise NodeTransportAmbiguous("scripted post-send timeout")


class _AmbiguousStage(LocalNodeTransport):
    async def stage_conditional_state(self, node_id, **kwargs):
        raise NodeTransportAmbiguous("scripted post-send timeout")


class _LostReplyReserve(LocalNodeTransport):
    """Applies the first reserve worker-side, then reports a lost reply."""

    def __init__(self, workers):
        super().__init__(workers)
        self._lost = False

    async def reserve(self, node_id, **kwargs):
        if not self._lost:
            self._lost = True
            await super().reserve(node_id, **kwargs)
            raise NodeTransportAmbiguous("scripted reply lost after apply")
        return await super().reserve(node_id, **kwargs)


async def _failing_sink(event):
    raise RuntimeError("ledger down")


# --------------------------------------------------------------------------
# whole-batch atomicity and survivor ownership (Task 1)


def test_rejected_batches_leave_every_record_untouched():
    async def body():
        ctx = _setup()
        first = await _pair(ctx.pool)
        second = await _pair(ctx.pool)
        await ctx.pool.reserve_pairs((first.pair_id, second.pair_id), operation_id="op-1")
        with pytest.raises(QuantumResourceError):
            await ctx.pool.consume_pairs((first.pair_id, "bell-missing"), operation_id="op-1")
        assert ctx.pool.status_of(first.pair_id).value == "reserved"
        assert ctx.pool.status_of(second.pair_id).value == "reserved"
        with pytest.raises(QuantumResourceError):
            await ctx.pool.release_reservation((first.pair_id, second.pair_id), operation_id="op-2")
        assert ctx.pool.status_of(first.pair_id).value == "reserved"
        assert ctx.pool.status_of(second.pair_id).value == "reserved"
        # The holding operation still owns both records: clean consume works.
        await ctx.pool.consume_pairs((first.pair_id, second.pair_id), operation_id="op-1")
        assert ctx.pool.status_of(first.pair_id).value == "consumed"
        assert ctx.pool.status_of(second.pair_id).value == "consumed"

    _run(body())


def test_register_output_strips_survivor_leases_from_inputs():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.1], "bob": [0.5]})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        result = await purifier.purify(first.pair_id, second.pair_id)
        assert result.accepted is True
        output_id = result.output_pair_id
        assert ctx.pool.leases_of(first.pair_id) == {}
        output_leases = ctx.pool.leases_of(output_id)
        assert set(output_leases) == {"alice", "bob"}
        info = await ctx.transport.inspect("bob")
        assert any(entry["resource_id"] == output_id for entry in info["leases"])
        # Releasing a consumed input can no longer disturb its live output.
        await ctx.pool.release_pair_leases(first.pair_id, operation_id="op-clean")
        assert ctx.pool.status_of(output_id).value == "active"
        assert ctx.pool.leases_of(output_id) == output_leases
        info = await ctx.transport.inspect("bob")
        assert any(entry["resource_id"] == output_id for entry in info["leases"])

    _run(body())


# --------------------------------------------------------------------------
# whole-operation failure, ambiguity, and cancellation guards (Task 2)


def test_create_pair_cancellation_releases_granted_lease():
    async def body():
        ctx = _ctx_with(lambda workers: _CancelOnCall(workers, method="reserve", fail_on=2))
        caught = None
        try:
            await ctx.pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        except asyncio.CancelledError as exc:
            caught = exc
        assert caught is not None
        assert ctx.pool.list_active_pairs() == []
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


def test_purify_cancellation_before_mutation_releases():
    async def body():
        ctx = _ctx_with(
            lambda workers: _CancelOnCall(workers, method="measure", fail_on=1),
            worker_draws={"alice": [0.1], "bob": [0.5]},
        )
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        caught = None
        try:
            await purifier.purify(first.pair_id, second.pair_id)
        except asyncio.CancelledError as exc:
            caught = exc
        assert caught is not None
        assert ctx.pool.status_of(first.pair_id).value == "active"
        assert ctx.pool.status_of(second.pair_id).value == "active"

    _run(body())


def test_purify_cancellation_after_mutation_quarantines():
    async def body():
        ctx = _ctx_with(
            lambda workers: _CancelOnCall(workers, method="measure", fail_on=2),
            worker_draws={"alice": [0.1], "bob": [0.5]},
        )
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        caught = None
        try:
            await purifier.purify(first.pair_id, second.pair_id)
        except asyncio.CancelledError as exc:
            caught = exc
        assert caught is not None
        assert ctx.pool.status_of(first.pair_id).value == "quarantined"
        assert ctx.pool.status_of(second.pair_id).value == "quarantined"

    _run(body())


def test_purify_ambiguous_measurement_quarantines_without_retry():
    async def body():
        ctx = _ctx_with(
            lambda workers: _AmbiguousMeasure(workers),
            worker_draws={"alice": [0.1], "bob": [0.5]},
        )
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        with pytest.raises(QuantumResourceError) as exc:
            await purifier.purify(first.pair_id, second.pair_id)
        assert exc.value.code == "transport_ambiguous"
        assert ctx.pool.status_of(first.pair_id).value == "quarantined"
        assert ctx.pool.status_of(second.pair_id).value == "quarantined"
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


class _RefuseTransfer(LocalNodeTransport):
    async def transfer(self, node_id, **kwargs):
        raise NodeCommandFailed(409, "lease_unavailable", "scripted split transfer")


def test_purify_failed_transfer_quarantines_without_splitting_ownership():
    async def body():
        ctx = _ctx_with(
            lambda workers: _RefuseTransfer(workers),
            worker_draws={"alice": [0.1], "bob": [0.5]},
        )
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        with pytest.raises(QuantumResourceError) as exc:
            await purifier.purify(first.pair_id, second.pair_id)
        assert exc.value.code == "transport_ambiguous"
        assert ctx.pool.status_of(first.pair_id).value == "quarantined"
        assert ctx.pool.status_of(second.pair_id).value == "quarantined"
        assert ctx.pool.list_active_pairs() == []
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


def test_uncertain_reserve_is_adopted_through_inspection():
    async def body():
        ctx = _ctx_with(lambda workers: _LostReplyReserve(workers))
        pair = await ctx.pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        assert ctx.pool.status_of(pair.pair_id).value == "active"
        assert set(ctx.pool.leases_of(pair.pair_id)) == {"alice", "bob"}
        ledger = ctx.pool.uncertain_reserves()
        assert len(ledger) == 1
        (key_op, key_resource), entry = next(iter(ledger.items()))
        assert key_resource == pair.pair_id
        assert entry["status"] == "adopted"
        assert len(entry["lease_ids"]) == 1
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 1

    _run(body())


def test_purify_receipt_failure_quarantines_output():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.1], "bob": [0.5]})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        ctx.pool._append_event = _failing_sink
        with pytest.raises(QuantumResourceError) as exc:
            await purifier.purify(first.pair_id, second.pair_id)
        assert exc.value.code == "receipt_failed"
        assert ctx.pool.status_of(first.pair_id).value == "consumed"
        assert ctx.pool.status_of(second.pair_id).value == "consumed"
        quarantined = [
            pair_id for pair_id, record in ctx.pool._records.items()
            if record.status.value == "quarantined"
        ]
        assert len(quarantined) == 1
        assert ctx.pool.leases_of(quarantined[0]) != {}

    _run(body())


def test_route_four_nodes_tracks_hops_with_indexed_swaps():
    async def body():
        ctx = _setup(
            nodes=("a", "r1", "r2", "b"),
            worker_rngs={"a": [0.5], "r1": [0.3], "r2": [0.3], "b": [0.5]},
        )
        mesh = QuantumRepeaterMesh(ctx.pool)
        for node in ("a", "r1", "r2", "b"):
            mesh.register_node(node, "test")
        mesh.register_link("a", "r1")
        mesh.register_link("r1", "r2")
        mesh.register_link("r2", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(
            ["a", "r1", "r2", "b"], base_fidelity=0.98, purify_hops=False,
        )
        assert ok is True
        assert pair is not None
        assert {pair.node_a, pair.node_b} == {"a", "b"}
        bsm_ops = [c.operation_id for c in ctx.transport.calls if c.action == "measure"]
        assert len(bsm_ops) == 2
        assert "-swap-0-" in bsm_ops[0]
        assert "-swap-1-" in bsm_ops[1]
        assert bsm_ops[0] != bsm_ops[1]
        live = ctx.pool.list_active_pairs()
        assert [snap.pair_id for snap in live] == [pair.pair_id]
        for node, want in (("a", 1), ("b", 1), ("r1", 0), ("r2", 0)):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == want

    _run(body())


def test_route_purified_four_nodes_succeeds():
    async def body():
        ctx = _setup(
            nodes=("a", "r1", "r2", "b"),
            worker_rngs={"a": [0.1], "r1": [0.5, 0.1, 0.3], "r2": [0.5, 0.1, 0.3], "b": [0.5]},
        )
        mesh = QuantumRepeaterMesh(ctx.pool)
        for node in ("a", "r1", "r2", "b"):
            mesh.register_node(node, "test")
        mesh.register_link("a", "r1")
        mesh.register_link("r1", "r2")
        mesh.register_link("r2", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(
            ["a", "r1", "r2", "b"], base_fidelity=0.98, purify_hops=True,
        )
        assert ok is True
        assert pair is not None
        assert {pair.node_a, pair.node_b} == {"a", "b"}
        live = ctx.pool.list_active_pairs()
        assert [snap.pair_id for snap in live] == [pair.pair_id]

    _run(body())


def test_route_purify_reject_aborts_without_stranded_capacity():
    async def body():
        ctx = _setup(
            nodes=("a", "r1", "r2", "b"),
            worker_rngs={"a": [0.6], "r1": [0.01], "r2": [0.5], "b": [0.5]},
        )
        mesh = QuantumRepeaterMesh(ctx.pool)
        for node in ("a", "r1", "r2", "b"):
            mesh.register_node(node, "test")
        mesh.register_link("a", "r1")
        mesh.register_link("r1", "r2")
        mesh.register_link("r2", "b")
        ok, pair, logs = await mesh.establish_multi_hop_entanglement(
            ["a", "r1", "r2", "b"], base_fidelity=0.98, purify_hops=True,
        )
        assert ok is False
        assert pair is None
        assert any("abort" in entry for entry in logs)
        assert ctx.pool.list_active_pairs() == []
        for node in ("a", "r1", "r2", "b"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


def test_teleport_stage_ambiguity_quarantines_and_reclaims_leases():
    async def body():
        ctx = _ctx_with(
            lambda workers: _AmbiguousStage(workers),
            worker_draws={"alice": [0.1]},
        )
        proto = QuantumTeleportationProtocol(pool=ctx.pool)
        pair = await _pair(ctx.pool, fidelity=1.0)
        with pytest.raises(QuantumResourceError) as exc:
            await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, bell_pair=pair.pair_id)
        assert exc.value.code == "transport_ambiguous"
        assert ctx.pool.status_of(pair.pair_id).value == "quarantined"
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


# --------------------------------------------------------------------------
# output ownership, truthful physics, and release (Task 3)


def test_release_teleport_output_lifecycle():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.3]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        pair = await _pair(ctx.pool, fidelity=1.0)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, bell_pair=pair.pair_id)
        assert result.success is True
        session = result.session_id
        stored = proto.outputs[session]
        assert stored.status == "available"
        assert stored.receiver == "bob"
        with pytest.raises(QuantumResourceError) as exc:
            await proto.release_teleport_output(session, "carol", "rel-0")
        assert exc.value.code == "receiver_mismatch"
        assert exc.value.status == 403
        with pytest.raises(QuantumResourceError) as exc:
            await proto.release_teleport_output("teleport-missing", "bob", "rel-0")
        assert exc.value.code == "unknown_session"
        assert exc.value.status == 404
        first = await proto.release_teleport_output(session, "bob", "rel-1")
        assert first["ok"] is True
        assert first["acknowledgement"] == "ack-rel-1"
        assert set(first["output"]) == {
            "session_id", "receiver", "resource_id", "lease_id", "instance_id", "status",
        }
        assert first["output"]["status"] == "released"
        assert first["output"]["session_id"] == session
        assert "tok-" not in json.dumps(first)
        assert proto.outputs[session].status == "released"
        info = await ctx.transport.inspect("bob")
        assert info["active_count"] == 0
        with pytest.raises(QuantumResourceError) as exc:
            await proto.release_teleport_output(session, "bob", "rel-2")
        assert exc.value.code == "already_released"
        assert exc.value.status == 409
        replay = await proto.release_teleport_output(session, "bob", "rel-1")
        assert replay == first
        releases = [c for c in ctx.transport.calls if c.action == "release" and c.operation_id == "rel-1"]
        assert len(releases) == 1

    _run(body())


def test_below_threshold_output_is_reclaimed_not_owned():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.3]})
        mesh = QuantumRepeaterMesh(ctx.pool)
        proto = QuantumTeleportationProtocol(mesh, transport=ctx.transport)
        pair = await _pair(ctx.pool, fidelity=0.90)
        result = await proto.teleport_qubit(
            "alice", "bob", complex(0.6, 0.0), complex(0.8, 0.0), bell_pair=pair.pair_id,
        )
        assert result.success is False
        assert result.reason == "below_threshold"
        assert proto.outputs == {}
        with pytest.raises(QuantumResourceError) as exc:
            await proto.release_teleport_output(result.session_id, "bob", "rel-1")
        assert exc.value.code == "unknown_session"
        assert exc.value.status == 404
        for node in ("alice", "bob"):
            info = await ctx.transport.inspect(node)
            assert info["active_count"] == 0

    _run(body())


def test_repeated_purification_reports_actual_branch_odds():
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.1, 0.6], "bob": [0.5, 0.05]})
        purifier = EntanglementPurifier(ctx.pool)
        first = await _pair(ctx.pool, fidelity=0.90)
        second = await _pair(ctx.pool, fidelity=0.92)
        round_one = await purifier.purify(first.pair_id, second.pair_id)
        assert round_one.accepted is True
        survivor = ctx.pool.get_pair(round_one.output_pair_id)
        assert survivor is not None
        fresh = await _pair(ctx.pool, fidelity=0.90)
        round_two = await purifier.purify(survivor.pair_id, fresh.pair_id)
        rho_kept = survivor.oriented("alice", "bob")
        rho_fresh = fresh.oriented("alice", "bob")
        joint = rho_kept.tensor(rho_fresh).apply_cnot(0, 2).apply_cnot(1, 3)
        oracle = math.fsum(
            branch.probability for branch in joint.branches_z((2, 3)) if branch.bits[0] == branch.bits[1]
        )
        assert round_two.p_accept == pytest.approx(oracle, abs=1e-12)

    _run(body())


def test_math_mode_receiver_matrix_is_corrected_state():
    async def body():
        events = []

        async def append_event(event):
            events.append(dict(event))
            return {"receipt_id": f"r-{len(events)}", "seq": len(events)}

        pool = BellPairPool(rng=ScriptedRng([0.5]), transport=None, append_event=append_event)
        proto = QuantumTeleportationProtocol(pool=pool)
        pair = await pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        result = await proto.teleport_qubit("alice", "bob", 1.0 + 0j, 0.0j, bell_pair=pair.pair_id)
        assert result.acknowledged is False
        assert result.reason == "unacknowledged"
        want = quantum_state.QuantumStateVector.from_qubit(1.0 + 0j, 0.0j).density().to_public_matrix()
        worst = max(
            abs(result.receiver_matrix[i][j][k] - want[i][j][k])
            for i in range(2) for j in range(2) for k in range(2)
        )
        assert worst <= 1e-9
        assert proto.outputs == {}

    _run(body())


def test_late_reservation_commit_remains_original_instance_quarantine():
    async def body():
        ctx = _setup()
        ready = asyncio.Event()

        class LateReserve(LocalNodeTransport):
            pending = None

            async def reserve(self, node_id, **kwargs):
                if node_id != "alice":
                    return await super().reserve(node_id, **kwargs)

                async def commit_after_timeout():
                    await ready.wait()
                    return await LocalNodeTransport.reserve(self, node_id, **kwargs)

                self.pending = asyncio.create_task(commit_after_timeout())
                raise NodeTransportAmbiguous("handler still pending")

        transport = LateReserve(ctx.workers)
        pool = BellPairPool(transport=transport)
        with pytest.raises(QuantumResourceError) as caught:
            await pool.create_pair("alice", "bob", BellStateType.PHI_PLUS, 1.0)
        assert caught.value.code == "transport_ambiguous"
        uncertainty = next(iter(pool.uncertain_reserves().values()))
        assert uncertainty["status"] == "unresolved"
        assert uncertainty["instance_id"] == ctx.workers["alice"].instance_id
        ready.set()
        granted = await transport.pending
        info = await transport.inspect("alice", instance=uncertainty["instance_id"])
        assert info["active_count"] == 1
        assert next(iter(pool.uncertain_reserves().values()))["status"] == "unresolved"
        await LocalNodeTransport.release(
            transport, "alice", operation_id="late-test-cleanup",
            lease_ids=granted["leases"], instance=uncertainty["instance_id"],
        )

    _run(body())


def test_quarantined_output_release_cannot_issue_another_mutation():
    async def body():
        ctx = _setup()
        pair = await _pair(ctx.pool)
        protocol = QuantumTeleportationProtocol(pool=ctx.pool)
        result = await protocol.teleport_qubit("alice", "bob", 1, 1j, pair.pair_id)

        class DroppedRelease(LocalNodeTransport):
            attempts = 0

            async def release(self, node_id, **kwargs):
                self.attempts += 1
                await super().release(node_id, **kwargs)
                raise NodeTransportAmbiguous("terminal release reply lost")

        transport = DroppedRelease(ctx.workers)
        protocol._transport = transport
        with pytest.raises(QuantumResourceError) as first:
            await protocol.release_teleport_output(result.session_id, "bob", "release-first")
        assert first.value.code == "transport_ambiguous"
        for operation in ("release-first", "release-new"):
            with pytest.raises(QuantumResourceError) as retry:
                await protocol.release_teleport_output(result.session_id, "bob", operation)
            assert retry.value.code == "output_quarantined" and retry.value.status == 409
        assert transport.attempts == 1
        assert protocol.sessions[result.session_id].output.status == "quarantined"
        worker = await ctx.transport.inspect("bob")
        assert all(lease["lease_id"] != result.output.lease_id for lease in worker["leases"])

    _run(body())


@pytest.mark.parametrize("exception_type", [asyncio.CancelledError, KeyboardInterrupt])
def test_cancelled_output_release_quarantines_after_actual_worker_effect(exception_type):
    async def body():
        ctx = _setup(worker_rngs={"alice": [0.3]})
        pair = await _pair(ctx.pool)
        protocol = QuantumTeleportationProtocol(pool=ctx.pool)
        result = await protocol.teleport_qubit("alice", "bob", 1, 1j, pair.pair_id)
        assert result.success is True
        session = result.session_id
        output = protocol.outputs[session]
        assert output.status == "available"
        before = await ctx.transport.inspect("bob", instance=output.instance_id)
        assert any(lease["lease_id"] == output.lease_id for lease in before["leases"])
        interruption = exception_type("release completed before interruption")

        class InterruptedRelease(LocalNodeTransport):
            attempts = 0

            async def release(self, node_id, **kwargs):
                self.attempts += 1
                await super().release(node_id, **kwargs)
                raise interruption

        transport = InterruptedRelease(ctx.workers)
        protocol._transport = transport
        with pytest.raises(exception_type) as caught:
            await protocol.release_teleport_output(session, "bob", "release-first")
        assert caught.value is interruption
        after = await ctx.transport.inspect("bob", instance=output.instance_id)
        assert all(lease["lease_id"] != output.lease_id for lease in after["leases"])
        assert after["active_count"] == 0
        assert protocol.outputs[session].to_dict() == {
            **output.to_dict(), "status": "quarantined",
        }
        assert protocol.sessions[session].to_dict()["output"] == protocol.outputs[session].to_dict()
        assert protocol._release_acks == {}
        assert transport.attempts == 1
        for operation in ("release-first", "release-new"):
            with pytest.raises(QuantumResourceError) as retry:
                await protocol.release_teleport_output(session, "bob", operation)
            assert retry.value.code == "output_quarantined"
            assert retry.value.status == 409
            assert transport.attempts == 1
            assert protocol._release_acks == {}

    _run(body())
