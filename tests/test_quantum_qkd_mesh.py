"""Behavioral tests for the transport-cutover BB84/E91 engine (phase 69-06).

The engine holds no worker references and supplies no private draws: every
endpoint step runs through the shared ``qkd_step``/``qkd_owner`` transport
with strict codecs, so Local and Remote paths share one bounded contract.
Worker RNGs are seeded per test (test-only injection); the engine channel
RNG is seeded for Eve/shuffle/disclosed-round determinism. No test reads
worker vaults: agreement is proved through public commitments and the
private owner capability/use path, keylessness through ``lengths`` and
owner-capability refusal.
"""

import asyncio
import json
import random

import pytest

from desk_gateway.quantum_key import (
    estimate_chsh,
    qber_exceeds,
    reconcile_candidates,
    sample_chsh_outcome,
    toeplitz_hash,
)
from desk_gateway.quantum_node import QuantumNodeWorker, encode_density
from desk_gateway.quantum_qkd_mesh import QKDProtocolEngine, QuantumTeleportationDrill
from desk_gateway.quantum_teleportation import (
    BellPairPool,
    BellStateType,
    QuantumRepeaterMesh,
    QuantumTeleportationProtocol,
)
from desk_gateway.quantum_state import QuantumStateVector
from desk_gateway.quantum_transport import LocalNodeTransport, NodeCommandFailed

ALICE = "desk-alpha"
BOB = "desk-beta"
TOKEN = "qkd-test-token"

PUBLIC_KEYS = {
    "session_id",
    "protocol",
    "model",
    "status",
    "reason",
    "sender",
    "receiver",
    "raw_count",
    "sifted_count",
    "test_count",
    "error_count",
    "phase_test_count",
    "phase_error_count",
    "qber",
    "phase_error_bound",
    "syndrome_bits",
    "branch_bits",
    "tag_bits",
    "entropy_budget",
    "extracted_bits",
    "keys_agreed",
    "key_id",
    "commitment_alice_hex",
    "commitment_bob_hex",
    "key_commitment_hex",
    "duration_ms",
    "receipt_id",
}

FORBIDDEN_KEY_SUBSTRINGS = (
    "blinding",
    "capability",
    "secret",
    "bearer",
    "signer",
    "password",
    "passwd",
    "mnemonic",
    "private",
    "token",
)


def _run(awaitable):
    return asyncio.run(awaitable)


def make_workers(seed_alice=1001, seed_bob=2002):
    return {
        ALICE: QuantumNodeWorker(ALICE, token=TOKEN, rng=random.Random(seed_alice)),
        BOB: QuantumNodeWorker(BOB, token=TOKEN, rng=random.Random(seed_bob)),
    }


def make_stack(seed_engine=20260612, seed_alice=1001, seed_bob=2002, sink=None):
    """One shared graph: workers, transport, pool, engine."""
    workers = make_workers(seed_alice, seed_bob)
    transport = LocalNodeTransport(workers)
    pool = BellPairPool(transport=transport)
    engine = QKDProtocolEngine(
        pool=pool,
        transport=transport,
        rng=random.Random(seed_engine),
        append_event=sink,
    )
    return workers, transport, pool, engine


def make_sink():
    events = []

    async def append_event(event):
        events.append(event)

        class _Receipt:
            receipt_id = f"sink-{len(events)}"

        return _Receipt()

    return events, append_event


def assert_public_clean(public):
    assert set(public.keys()) == PUBLIC_KEYS
    dumped = json.dumps(public, sort_keys=True)
    for needle in FORBIDDEN_KEY_SUBSTRINGS:
        assert needle not in dumped, needle
    assert public["model"] == "trusted-device-simulator-v1"


async def owner_use_both(transport, session, tag, operation="qkd_test"):
    """Consume both endpoint keys via the private owner path; return outcomes."""
    outcomes = {}
    for node, key in ((ALICE, "commitment_alice_hex"), (BOB, "commitment_bob_hex")):
        capability = await transport.qkd_owner(
            node,
            operation_id=f"{tag}-{node}-cap",
            session_id=session.session_id,
            action="capability",
            payload={},
        )
        assert set(capability) == {"ok", "session_id", "capability"}
        outcome = await transport.qkd_owner(
            node,
            operation_id=f"{tag}-{node}-use",
            session_id=session.session_id,
            action="use",
            payload={"operation": operation, "capability": capability["capability"]},
        )
        assert outcome == {
            "ok": True,
            "outcome": "accepted",
            "operation": operation,
            "commitment": getattr(session, key),
        }
        outcomes[node] = outcome
    return outcomes


async def assert_keyless(transport, node, session_id, tag):
    """Both the lengths projection and the owner path agree: no usable key."""
    lengths = await transport.qkd_step(
        node,
        operation_id=f"{tag}-{node}-len",
        session_id=session_id,
        action="lengths",
        payload={},
    )
    assert lengths["key_available"] is False
    assert lengths["key_length"] == 0
    with pytest.raises(NodeCommandFailed) as exc:
        await transport.qkd_owner(
            node,
            operation_id=f"{tag}-{node}-cap",
            session_id=session_id,
            action="capability",
            payload={},
        )
    assert exc.value.status == 409



def test_clean_bb84_establishes_with_matching_commitments():
    async def main():
        events, sink = make_sink()
        _, transport, pool, engine = make_stack(sink=sink)
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)

        assert session.status == "established"
        assert session.reason is None
        assert session.protocol == "BB84"
        assert session.extracted_bits == 256
        assert session.keys_agreed is True
        assert session.key_id is not None
        assert session.qber == 0.0
        assert session.tag_bits == 32
        assert session.branch_bits == 48
        assert session.syndrome_bits > 0
        assert session.commitment_alice_hex is not None
        assert session.commitment_bob_hex is not None
        assert session.key_commitment_hex is not None
        assert len(session.key_commitment_hex) == 64

        # Agreement is proved without vault reads: both endpoints consume
        # their keys one-shot and report the session's commitments.
        await owner_use_both(transport, session, "clean-use")
        await assert_keyless(transport, ALICE, session.session_id, "clean-a")
        await assert_keyless(transport, BOB, session.session_id, "clean-b")

        public = session.to_dict()
        assert_public_clean(public)
        assert repr(session) == f"QKDSession({session.session_id})"

        assert len(events) == 1
        assert events[0]["event_type"] == "qkd.established"
        assert events[0]["payload"] == {**public, "receipt_id": None}
        assert session.receipt_id == "sink-1"
        assert_public_clean(events[0]["payload"])
        assert len(pool.list_active_pairs()) == 0

    _run(main())


def test_zero_length_aborts_insufficient_sample():
    async def main():
        events, sink = make_sink()
        _, _, _, engine = make_stack(sink=sink)
        for coro in (
            engine.run_bb84(ALICE, BOB, 0),
            engine.run_e91(ALICE, BOB, 0),
        ):
            session = await coro
            assert session.status == "aborted"
            assert session.reason == "insufficient_sample"
            assert session.qber is None
            assert session.keys_agreed is False
            assert session.extracted_bits == 0
            assert session.key_id is None
            assert session.commitment_alice_hex is None
            assert session.commitment_bob_hex is None
            assert session.key_commitment_hex is None
            assert_public_clean(session.to_dict())
        assert len(events) == 2
        assert all(e["event_type"] == "qkd.aborted" for e in events)

    _run(main())

@pytest.mark.parametrize("protocol", ("BB84", "E91"))
def test_short_samples_never_report_estimated_qber(protocol):
    async def main():
        _, transport, _, engine = make_stack()
        run = engine.run_bb84 if protocol == "BB84" else engine.run_e91
        session = await run(ALICE, BOB, 200)
        assert session.status == "aborted" and session.reason == "insufficient_sample"
        assert session.qber is None and session.key_commitment_hex is None
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, f"short-{protocol}")

    _run(main())



def test_no_transport_fails_closed_without_keys():
    async def main():
        from desk_gateway.quantum_teleportation import BellPairPool as Pool

        engine = QKDProtocolEngine(pool=Pool(), rng=random.Random(3))
        assert engine.transport is None
        for coro in (
            engine.run_bb84(ALICE, BOB, 100),
            engine.run_e91(ALICE, BOB, 100),
        ):
            session = await coro
            assert session.status == "failed"
            assert session.keys_agreed is False
            assert session.key_commitment_hex is None

    _run(main())


def test_qber_integer_gate_boundary():
    assert qber_exceeds(11, 100) is False
    assert qber_exceeds(12, 100) is True
    assert qber_exceeds(0, 100) is False
    assert qber_exceeds(100, 100) is True
    for bad in (
        lambda: qber_exceeds(True, 100),
        lambda: qber_exceeds(1, 0),
        lambda: qber_exceeds(-1, 100),
        lambda: qber_exceeds(101, 100),
        lambda: qber_exceeds(float("nan"), 100),
        lambda: qber_exceeds(1, "100"),
    ):
        with pytest.raises(ValueError):
            bad()


def test_reconciliation_single_error_corrected_double_rejected():
    rng = random.Random(77)
    alice = tuple(1 if rng.random() < 0.5 else 0 for _ in range(200))
    # Single injected error is corrected exactly.
    bob = list(alice)
    bob[17] ^= 1
    corrected, syndrome_len, _blocks, corrections = reconcile_candidates(
        alice, tuple(bob), random.Random(78)
    )
    assert tuple(corrected) == alice
    assert corrections == 1
    assert syndrome_len > 0
    # Two faults in block 0 (post-permutation indices 0 and 1) leave residue
    # the verification tag must catch: the "corrected" string still differs.
    corrected2, _s2, _b2, _c2 = reconcile_candidates(
        alice, alice, random.Random(78), flip_positions=(0, 1)
    )
    assert tuple(corrected2) != alice


def test_intercept_resend_aborts_both_nodes_keyless():
    async def main():
        events, sink = make_sink()
        _, transport, _, engine = make_stack(sink=sink, seed_engine=7)
        session = await engine.run_bb84(ALICE, BOB, 3000, intercept=True)

        assert session.status == "aborted"
        assert session.reason == "qber_exceeded"
        assert session.qber is not None and session.qber > 0.11
        assert session.keys_agreed is False
        assert session.commitment_alice_hex is None
        assert session.commitment_bob_hex is None
        assert session.key_commitment_hex is None
        await assert_keyless(transport, ALICE, session.session_id, "eve-a")
        await assert_keyless(transport, BOB, session.session_id, "eve-b")
        assert len(events) == 1
        assert events[0]["event_type"] == "qkd.aborted"

    _run(main())


def test_sink_failure_withholds_keys_on_both_nodes():
    """A receipt refusal surfaces only after both endpoint keys are destroyed."""
    async def main():
        seen = []

        async def broken_sink(event):
            seen.append(event)
            raise RuntimeError("sink refused receipt")

        _, transport, _, engine = make_stack(sink=broken_sink)
        with pytest.raises(RuntimeError, match="sink refused receipt"):
            await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert len(seen) >= 1
        # Every bound session the engine touched holds no usable key.
        assert list(engine._session_instances) != []
        for session_id in list(engine._session_instances):
            await assert_keyless(transport, ALICE, session_id, f"brk-a-{session_id[-4:]}")
            await assert_keyless(transport, BOB, session_id, f"brk-b-{session_id[-4:]}")

    _run(main())


def test_unreachable_key_cleanup_is_quarantined_not_claimed_keyless():
    from desk_gateway.quantum_transport import NodeTransportUnavailable

    async def main():
        class PartitionedCleanup(LocalNodeTransport):
            partitioned = False
            async def qkd_step(self, node_id, **kwargs):
                if self.partitioned and node_id == BOB and kwargs["action"] in ("abort", "lengths"):
                    raise NodeTransportUnavailable("cleanup partition")
                return await super().qkd_step(node_id, **kwargs)

        async def rejecting_establishment(event):
            if event["event_type"] == "qkd.established":
                raise RuntimeError("establishment receipt unavailable")
            return None

        workers, local, pool, _ = make_stack()
        transport = PartitionedCleanup(workers)

        async def sink(event):
            if event["event_type"] == "qkd.established":
                transport.partitioned = True
            return await rejecting_establishment(event)

        engine = QKDProtocolEngine(
            pool=pool, transport=transport, rng=random.Random(991), append_event=sink,
        )
        session = await engine.run_bb84(ALICE, BOB, 12000)
        assert session.status == "failed" and session.reason == "key_cleanup_unconfirmed"
        assert not session.keys_agreed and session.key_commitment_hex is None
        await assert_keyless(local, ALICE, session.session_id, "partition-a")
        bob = await local.qkd_step(
            BOB, operation_id="partition-observe", session_id=session.session_id,
            action="lengths", payload={},
        )
        assert bob["state"] == "established" and bob["key_available"]
        assert session.session_id in engine._quarantined_sessions
        await local.qkd_step(
            BOB, operation_id="partition-cleanup", session_id=session.session_id,
            action="abort", payload={"reason": "user_abort"},
        )

    _run(main())


def test_cancellation_reraises_and_leaves_no_keys():
    async def main():
        async def cancelling_sink(event):
            raise asyncio.CancelledError("sink cancelled")

        _, transport, _, engine = make_stack(sink=cancelling_sink)
        with pytest.raises(asyncio.CancelledError):
            await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert list(engine._session_instances) != []
        for session_id in list(engine._session_instances):
            await assert_keyless(transport, ALICE, session_id, f"can-a-{session_id[-4:]}")
            await assert_keyless(transport, BOB, session_id, f"can-b-{session_id[-4:]}")

    _run(main())


def test_e91_witness_with_independent_endpoint_custody():
    async def main():
        _, transport, pool, engine = make_stack(seed_engine=4404)
        session = await engine.run_e91(ALICE, BOB, 8000, requested_bits=256)

        budget = session.entropy_budget
        assert budget["chsh_S_lower"] > 2.0
        assert set(budget["chsh_counts"]) == {"0", "1", "2", "3"}
        assert all(count > 0 for count in budget["chsh_counts"].values())
        assert session.status == "established"
        assert session.reason is None
        assert session.keys_agreed is True
        assert session.extracted_bits == 256
        await owner_use_both(transport, session, "e91-use")
        await assert_keyless(transport, ALICE, session.session_id, "e91-a")
        await assert_keyless(transport, BOB, session.session_id, "e91-b")
        assert_public_clean(session.to_dict())
        assert len(pool.list_active_pairs()) == 0

        # Product-state control through the same estimator: |0> x |0> fails.
        rho = QuantumStateVector((1 + 0j, 0j)).density()
        product = rho.tensor(rho)
        rng = random.Random(11)
        records = []
        for setting in range(4):
            for _ in range(250):
                a_bit, b_bit = sample_chsh_outcome(product, setting // 2, setting % 2, rng)
                records.append((setting, a_bit, b_bit))
        control = estimate_chsh(records)
        assert control["passed"] is False
        assert control["S_lower"] <= 2.0

    _run(main())


def test_e91_round_replies_carry_no_peer_click():
    """Each endpoint reply exposes only its own side of the round."""
    async def main():
        _, transport, pool, _ = make_stack()
        instances = {}
        for node in (ALICE, BOB):
            info = await transport.inspect(node)
            instances[node] = info["instance_id"]
        session_id = "cust-seam-1"
        await transport.qkd_step(
            ALICE, operation_id="cust-begin-a", session_id=session_id,
            action="begin", payload={"protocol": "E91", "role": "alice", "peer": BOB},
            instance=instances[ALICE],
        )
        await transport.qkd_step(
            BOB, operation_id="cust-begin-b", session_id=session_id,
            action="begin", payload={"protocol": "E91", "role": "bob", "peer": ALICE},
            instance=instances[BOB],
        )
        pair = await pool.create_pair(
            ALICE, BOB, BellStateType.PHI_PLUS, 1.0, operation_id="cust-mk",
        )
        try:
            leases = pool.leases_of(pair.pair_id)
            rho = pair.oriented(ALICE, BOB)
            alice_round = await transport.qkd_step(
                ALICE, operation_id="cust-round-a", session_id=session_id,
                action="measure_e91",
                payload={
                    "round_index": 0,
                    "pair_id": pair.pair_id,
                    "lease_id": leases[ALICE],
                    "setting": 0,
                    "state": encode_density(rho),
                },
                instance=instances[ALICE],
            )
            # Alice keeps her click and returns only Bob's conditional density.
            assert set(alice_round) == {"ok", "round_index", "pair_id", "conditional"}
            assert alice_round["conditional"]["encoding"] == "density-v1"
            assert alice_round["conditional"]["qubits"] == 1
            bob_round = await transport.qkd_step(
                BOB, operation_id="cust-round-b", session_id=session_id,
                action="measure_e91",
                payload={
                    "round_index": 0,
                    "pair_id": pair.pair_id,
                    "lease_id": leases[BOB],
                    "setting": 0,
                    "state": alice_round["conditional"],
                },
                instance=instances[BOB],
            )
            # Bob reports a count only; his click never crosses the wire.
            assert set(bob_round) == {"ok", "round_index", "pair_id", "count"}
            assert bob_round["count"] == 1
        finally:
            await pool.reserve_pairs([pair.pair_id], operation_id="cust-retire")
            await pool.consume_pairs([pair.pair_id], operation_id="cust-retire")
            await pool.release_pair_leases(pair.pair_id, operation_id="cust-retire")
            for node, tag in ((ALICE, "cust-abort-a"), (BOB, "cust-abort-b")):
                await transport.qkd_step(
                    node, operation_id=tag, session_id=session_id,
                    action="abort", payload={"reason": "user_abort"},
                    instance=instances[node],
                )

    _run(main())


def test_owner_capability_one_shot_and_abort():
    async def main():
        _, transport, _, engine = make_stack()
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "established"

        await owner_use_both(transport, session, "oneshot")

        # A consumed key never serves its capability again.
        with pytest.raises(NodeCommandFailed) as second:
            await transport.qkd_owner(
                ALICE, operation_id="oneshot-retry-cap", session_id=session.session_id,
                action="capability", payload={},
            )
        assert second.value.status == 409

        # A separate unused key can be aborted; both owner paths then refuse.
        aborted = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert aborted.status == "established"
        for node in (ALICE, BOB):
            await transport.qkd_step(
                node, operation_id=f"oneshot-abort-{node}", session_id=aborted.session_id,
                action="abort", payload={"reason": "user_abort"},
            )
            await assert_keyless(transport, node, aborted.session_id, "oneshot-gone")

    _run(main())


def test_ledger_accepts_public_event_rejects_key_material(tmp_path):
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        _, _, _, engine = make_stack()
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "established"
        public = session.to_dict()

        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            receipt = await ledger.append_event(
                {
                    "event_type": "qkd.established",
                    "session_id": session.session_id,
                    "actor": ALICE,
                    "nodes": [ALICE, BOB],
                    "resources": [],
                    "outcome": "established",
                    "payload": public,
                }
            )
            assert receipt.receipt_id

            tainted = dict(public)
            tainted["final_shared_key_hex"] = "00" * 32
            with pytest.raises(ValueError):
                await ledger.append_event(
                    {
                        "event_type": "qkd.established",
                        "session_id": session.session_id + "-tainted",
                        "actor": ALICE,
                        "nodes": [ALICE, BOB],
                        "resources": [],
                        "outcome": "established",
                        "payload": tainted,
                    }
                )
        finally:
            ledger.close()

    _run(main())


def test_toeplitz_known_vector():
    seed = (1, 0, 1, 1, 0)
    data = (1, 1, 0)
    assert toeplitz_hash(seed, data, 3) == _independent_toeplitz(seed, data, 3)


def _independent_toeplitz(seed, data, out_len):
    n = len(data)
    out = []
    for i in range(out_len):
        parity = 0
        for j in range(n):
            parity ^= seed[n - 1 + i - j] & data[j]
        out.append(parity)
    return tuple(out)


def test_public_surfaces_carry_no_secret_material():
    async def main():
        events, sink = make_sink()
        _, transport, _, engine = make_stack(sink=sink)
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "established"

        assert_public_clean(session.to_dict())
        assert_public_clean(events[0]["payload"])
        for node in (ALICE, BOB):
            seen = await transport.inspect(node)
            dumped = json.dumps(seen, sort_keys=True)
            for needle in FORBIDDEN_KEY_SUBSTRINGS:
                assert needle not in dumped, (node, needle)
        assert "token" not in repr(transport)

    _run(main())


def test_invalid_inputs_raise_before_allocation():
    async def main():
        events, sink = make_sink()
        _, _, _, engine = make_stack(sink=sink)
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, BOB, True)
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, BOB, -1)
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, BOB, "100")
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, BOB, 20001)
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, ALICE, 100)
        with pytest.raises(ValueError):
            await engine.run_bb84("", BOB, 100)
        with pytest.raises(ValueError):
            await engine.run_e91(ALICE, BOB, False)
        with pytest.raises(ValueError):
            await engine.run_e91(ALICE, BOB, 20001)
        with pytest.raises(ValueError):
            await engine.run_bb84(ALICE, BOB, 100, requested_bits=512)
        assert events == []

    _run(main())


def test_repeated_drills_leave_no_owned_resources(tmp_path):
    """Two full drills stay capacity-neutral and unfunded stays blocked."""
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        nodes = ("drill-left", "drill-mid", "drill-right")
        workers = {
            name: QuantumNodeWorker(name, token=TOKEN, rng=random.Random(3000 + index))
            for index, name in enumerate(nodes)
        }
        transport = LocalNodeTransport(workers)
        pool = BellPairPool(transport=transport)
        engine = QKDProtocolEngine(pool=pool, transport=transport, rng=random.Random(9134))
        mesh = QuantumRepeaterMesh(pool)
        for node, region in (
            ("drill-left", "r1"),
            ("drill-mid", "r1"),
            ("drill-right", "r2"),
        ):
            mesh.register_node(node, region)
        mesh.register_link(nodes[0], nodes[1])
        mesh.register_link(nodes[1], nodes[2])
        protocol = QuantumTeleportationProtocol(mesh, transport=transport)
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            user_pair = await pool.create_pair(nodes[0], nodes[2], BellStateType.PHI_PLUS, 1.0)
            user_input = await pool.create_pair(nodes[0], nodes[2], BellStateType.PHI_PLUS, 1.0)
            user_output = await protocol.teleport_qubit(
                nodes[0], nodes[2], 1, 1j, bell_pair=user_input.pair_id,
            )
            user_key = await engine.run_bb84(nodes[0], nodes[2], 12000)
            assert user_output.success and user_key.status == "established"
            before = {
                node: (await transport.inspect(node))["active_count"] for node in nodes
            }
            drill = QuantumTeleportationDrill(pool, mesh, protocol, engine, ledger, None)
            reports = []
            for _ in range(2):
                report = await drill.run()
                reports.append(report)
                assert set(report) == {"all_passed", "prerequisite", "stages"}
                assert report["all_passed"] is False
                assert set(report["stages"]) >= {
                    "purify", "swap", "teleport", "clean_bb84", "eve",
                }
                assert all(
                    report["stages"][name]["passed"]
                    for name in ("purify", "swap", "teleport", "clean_bb84", "eve")
                )
                assert report["prerequisite"] == "publisher_unavailable"
                assert {
                    node: (await transport.inspect(node))["active_count"] for node in nodes
                } == before
            assert [pair.pair_id for pair in pool.list_active_pairs()] == [user_pair.pair_id]
            assert protocol.outputs[user_output.session_id].status == "available"
            assert all(
                output.status == "released" for session_id, output in protocol.outputs.items()
                if session_id != user_output.session_id
            )
            for node in (nodes[0], nodes[2]):
                lengths = await transport.qkd_step(
                    node, operation_id=f"user-lengths-{node}", session_id=user_key.session_id,
                    action="lengths", payload={},
                )
                assert lengths["key_available"] and lengths["state"] == "established"
            for session in engine.sessions.values():
                if session.session_id == user_key.session_id:
                    continue
                session_id = session.session_id
                for node in (session.sender, session.receiver):
                    with pytest.raises(NodeCommandFailed) as exc:
                        await transport.qkd_owner(
                            node,
                            operation_id=f"drill-cap-{session_id[-6:]}-{node[-5:]}",
                            session_id=session_id,
                            action="capability",
                            payload={},
                        )
                    assert exc.value.status in (404, 409)
            # A failed-close drill never reports a funded chain success.
            assert all(r["prerequisite"] is not None for r in reports)
        finally:
            ledger.close()

        # Shared worker slots still serve a fresh session after both drills.
        session = await engine.run_bb84("drill-left", "drill-right", 12000, requested_bits=256)
        assert session.status == "established"
        assert session.keys_agreed is True

    _run(main())
