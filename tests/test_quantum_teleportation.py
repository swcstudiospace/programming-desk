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
