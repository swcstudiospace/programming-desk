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
import base64
import json
import random

import pytest

from desk_gateway.quantum_key import (
    estimate_chsh,
    reconcile_candidates,
    sample_chsh_outcome,
    toeplitz_hash,
)
from desk_gateway.quantum_node import (
    QuantumNodeWorker,
    decode_signals,
    encode_density,
    encode_signals,
)
from desk_gateway.quantum_qkd_mesh import (
    EavesdropDetector,
    QKDProtocolEngine,
    QuantumChannelInterception,
    QuantumTeleportationDrillSimulator,
)
from desk_gateway.quantum_teleportation import (
    BellPairPool,
    BellStateType,
    PairStatus,
    QuantumRepeaterMesh,
    QuantumTeleportationProtocol,
    QuantumResourceError,
)
from desk_gateway.quantum_state import QuantumStateVector
from desk_gateway.quantum_transport import (
    LocalNodeTransport,
    NodeCommandFailed,
    NodeTransportAmbiguous,
    NodeTransportUnavailable,
)

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


def make_stack(seed_engine=20260612, seed_alice=1001, seed_bob=2002, sink=None, transport_type=LocalNodeTransport):
    """One shared graph: workers, transport, pool, engine."""
    workers = make_workers(seed_alice, seed_bob)
    transport = transport_type(workers)
    pool = BellPairPool(transport=transport)
    mesh = QuantumRepeaterMesh(pool, rng=random.Random(911))
    mesh.register_node(ALICE, "test-a")
    mesh.register_node(BOB, "test-b")
    mesh.register_link(ALICE, BOB)
    engine = QKDProtocolEngine(
        mesh,
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



async def assert_unbound(transport, node, session_id, tag):
    """Early admission never creates a private worker session."""
    for action, method in (("lengths", transport.qkd_step), ("capability", transport.qkd_owner)):
        with pytest.raises(NodeCommandFailed) as exc:
            await method(
                node, operation_id=f"{tag}-{node}-{action}",
                session_id=session_id, action=action, payload={},
            )
        assert exc.value.code == "unknown_session"


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
        assert repr(session) == f"QKDKeyExchangeSession({session.session_id})"

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
            if protocol == "E91":
                await assert_unbound(transport, node, session.session_id, "short-e91")
            else:
                await assert_keyless(transport, node, session.session_id, f"short-{protocol}")

    _run(main())



def test_no_transport_fails_closed_without_keys():
    async def main():
        from desk_gateway.quantum_teleportation import BellPairPool as Pool

        engine = QKDProtocolEngine(pool=Pool(), rng=random.Random(3))
        assert engine.transport is None
        for coro in (
            engine.run_bb84(ALICE, BOB, 100),
            engine.run_e91(ALICE, BOB, 8000),
        ):
            session = await coro
            assert session.status == "failed"
            assert session.keys_agreed is False
            assert session.key_commitment_hex is None

    _run(main())


def test_qber_integer_gate_boundary():
    assert EavesdropDetector.exceeds(11, 100) is False
    assert EavesdropDetector.exceeds(12, 100) is True
    assert EavesdropDetector.exceeds(0, 100) is False
    assert EavesdropDetector.exceeds(100, 100) is True
    for bad in (
        lambda: EavesdropDetector.exceeds(True, 100),
        lambda: EavesdropDetector.exceeds(1, 0),
        lambda: EavesdropDetector.exceeds(-1, 100),
        lambda: EavesdropDetector.exceeds(101, 100),
        lambda: EavesdropDetector.exceeds(float("nan"), 100),
        lambda: EavesdropDetector.exceeds(1, "100"),
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
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
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


def make_repeater_stack(*, transport_type=LocalNodeTransport, sink=None, extra_workers=()):
    """Four real workers, capacity-limited to the genuine three-hop route."""
    route = (ALICE, "repeater-a", "repeater-b", BOB)
    workers = {
        node: QuantumNodeWorker(
            node, token=TOKEN, capacity=1 if node in (ALICE, BOB) else 2,
            rng=random.Random(8001 + index),
        )
        for index, node in enumerate(route)
    }
    workers.update({
        node: QuantumNodeWorker(node, token=TOKEN, rng=random.Random(991))
        for node in extra_workers
    })
    transport = transport_type(workers)
    observed = {"created": [], "swapped": [], "corrections": set()}

    async def record_resource(event):
        if event["event_type"] == "bell.created":
            observed["created"].append((tuple(event["nodes"]), event["resources"][0]))
        elif event["event_type"] == "swap.completed":
            observed["swapped"].append(event["resources"][-1])
            payload = event["payload"]
            observed["corrections"].add((payload["correction_x"], payload["correction_z"]))
        return {"receipt_id": "observed-resource"}

    pool = BellPairPool(transport=transport, append_event=record_resource)
    mesh = QuantumRepeaterMesh(pool, rng=random.Random(411))
    for node in route:
        mesh.register_node(node, "repeater-test", qubit_capacity=workers[node].capacity)
    for left, right in zip(route, route[1:]):
        mesh.register_link(left, right)
    engine = QKDProtocolEngine(
        mesh, transport=transport, rng=random.Random(4404), append_event=sink,
    )
    return workers, transport, pool, engine, observed


def test_e91_full_count_repeater_witness_key_and_lease_consumption():
    """Actual two-BSM rounds feed the witness and independent endpoint keys."""
    async def main():
        _, transport, pool, engine, observed = make_repeater_stack()
        assert frozenset((ALICE, BOB)) not in engine.mesh.links
        session = await engine.run_e91(ALICE, BOB, 20000)
        assert session.status == "established" and session.reason is None
        assert session.raw_count == 20000 and session.extracted_bits == 256
        assert session.keys_agreed and session.qber == 0.0
        assert session.entropy_budget["chsh_S_lower"] > 2.0
        assert set(session.entropy_budget["chsh_counts"]) == {"0", "1", "2", "3"}
        assert sum(session.entropy_budget["chsh_counts"].values()) == 10000
        assert session.phase_test_count == 4000
        assert len(observed["created"]) == 60000
        assert len(observed["swapped"]) == 40000
        assert any(x or z for x, z in observed["corrections"])
        assert set(nodes for nodes, _ in observed["created"]) == {
            (ALICE, "repeater-a"), ("repeater-a", "repeater-b"), ("repeater-b", BOB),
        }
        for _, pair_id in observed["created"]:
            assert pool.status_of(pair_id) is PairStatus.CONSUMED
        for pair_id in observed["swapped"]:
            assert pool.status_of(pair_id) is PairStatus.CONSUMED
        for node in engine.mesh.nodes:
            info = await transport.inspect(node)
            assert info["active_count"] == 0 and info["lease_count"] == 0
        await owner_use_both(transport, session, "repeater-use")
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "repeater-gone")
        assert_public_clean(session.to_dict())
        assert pool.list_active_pairs() == []

    _run(main())


@pytest.mark.parametrize("topology", ("absent", "disconnected", "unregistered", "overlong", "different_pool"))
def test_e91_missing_route_has_no_discovery_vault_rng_or_pool_effects(topology):
    async def main():
        class ObservedTransport(LocalNodeTransport):
            probe_calls = 0

            async def inspect(self, node_id, **kwargs):
                self.probe_calls += 1
                return await super().inspect(node_id, **kwargs)

            async def qkd_step(self, node_id, **kwargs):
                self.probe_calls += 1
                return await super().qkd_step(node_id, **kwargs)

            async def reserve(self, node_id, **kwargs):
                self.probe_calls += 1
                return await super().reserve(node_id, **kwargs)

        _, transport, pool, engine = make_stack(transport_type=ObservedTransport)
        if topology == "absent":
            engine.mesh = None
        elif topology == "disconnected":
            engine.mesh.links.clear()
        elif topology == "unregistered":
            del engine.mesh.nodes[BOB]
        elif topology == "different_pool":
            engine.mesh.bell_pool = BellPairPool(transport=transport)
        else:
            engine.mesh.links.clear()
            path = [ALICE, *(f"route-mid-{i:02}" for i in range(15)), BOB]
            for node in path[1:-1]:
                engine.mesh.register_node(node, "test-long")
            for left, right in zip(path, path[1:]):
                engine.mesh.register_link(left, right)
        before_rng = engine._rng.getstate()
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "failed" and session.reason == "route_unavailable"
        assert transport.probe_calls == 0 and engine._rng.getstate() == before_rng
        assert engine._session_instances == {}
        assert pool.list_active_pairs() == [] and pool.uncertain_reserves() == {}
        assert not session.keys_agreed and session.key_commitment_hex is None
        for node in (ALICE, BOB):
            await assert_unbound(transport, node, session.session_id, "no-route")
            assert (await transport.inspect(node))["active_count"] == 0

    _run(main())


def test_e91_short_admission_precedes_missing_topology_and_draws():
    async def main():
        engine = QKDProtocolEngine(rng=random.Random(42))
        before = engine._rng.getstate()
        for count in (0, 200):
            session = await engine.run_e91(ALICE, BOB, count)
            assert session.status == "aborted" and session.reason == "insufficient_sample"
            assert session.qber is None and session.extracted_bits == 0
        assert engine._rng.getstate() == before
        assert engine._session_instances == {}
        assert engine.pool.list_active_pairs() == []

    _run(main())


@pytest.mark.parametrize("after_effect", (False, True))
@pytest.mark.parametrize("partition_abort", (False, True))
def test_e91_first_release_fault_is_failed_keyless_or_key_quarantined(after_effect, partition_abort):
    async def main():
        class UnconfirmedRelease(LocalNodeTransport):
            retire_calls = []

            async def release(self, node_id, **kwargs):
                if "-retire-0-" in kwargs["operation_id"]:
                    self.retire_calls.append((node_id, kwargs["operation_id"]))
                    if after_effect:
                        await super().release(node_id, **kwargs)
                    raise NodeTransportAmbiguous("lost terminal acknowledgement")
                return await super().release(node_id, **kwargs)

            async def qkd_step(self, node_id, **kwargs):
                if partition_abort and node_id == BOB and kwargs["action"] in ("abort", "lengths"):
                    raise NodeTransportUnavailable("abort partition")
                return await super().qkd_step(node_id, **kwargs)

        events, sink = make_sink()
        workers, transport, pool, engine = make_stack(transport_type=UnconfirmedRelease, sink=sink)
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "failed" and session.reason == "resource_cleanup_unconfirmed"
        assert session.extracted_bits == 0 and not session.keys_agreed
        assert session.key_id is None
        assert session.commitment_alice_hex is None and session.commitment_bob_hex is None
        assert session.key_commitment_hex is None
        assert len(transport.retire_calls) == 1  # Never retry an ambiguous mutation.
        assert [event["event_type"] for event in events] == ["qkd.failed"]
        pair_ids = {
            lease["resource_id"] for node in (ALICE, BOB)
            for lease in (await transport.inspect(node))["leases"]
        }
        assert len(pair_ids) == 1
        assert pool.status_of(next(iter(pair_ids))) is PairStatus.QUARANTINED
        assert (await transport.inspect(ALICE))["active_count"] == (0 if after_effect else 1)
        assert (await transport.inspect(BOB))["active_count"] == 1
        local = LocalNodeTransport(workers)
        await assert_keyless(local, ALICE, session.session_id, "release-fault-a")
        if partition_abort:
            assert engine._quarantined_sessions[session.session_id] == {
                BOB: (await local.inspect(BOB))["instance_id"],
            }
        else:
            await assert_keyless(local, BOB, session.session_id, "release-fault-b")
            assert session.session_id not in engine._quarantined_sessions
        assert_public_clean(session.to_dict())

    _run(main())


def test_e91_partial_route_capacity_failure_never_falls_back():
    async def main():
        unrelated = "unrelated-owner"
        workers, transport, pool, engine, observed = make_repeater_stack(extra_workers=(unrelated,))
        held = await pool.create_pair(BOB, unrelated, BellStateType.PHI_PLUS, 1.0, operation_id="held-pair")
        before = {node: (await transport.inspect(node))["active_count"] for node in workers}
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "failed" and session.reason == "resource_cleanup_unconfirmed"
        assert session.raw_count == 8000 and session.extracted_bits == 0
        assert not session.keys_agreed and session.key_commitment_hex is None
        assert observed["swapped"] == []
        assert [nodes for nodes, _ in observed["created"]] == [
            (BOB, unrelated), (ALICE, "repeater-a"), ("repeater-a", "repeater-b"),
        ]
        assert pool.status_of(held.pair_id) is PairStatus.ACTIVE
        assert {node: (await transport.inspect(node))["active_count"] for node in workers} == before
        for _, pair_id in observed["created"][1:]:
            assert pool.status_of(pair_id) is PairStatus.DISCARDED
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "partial-route")

    _run(main())


def test_e91_shortest_route_lexical_tie_uses_real_repeater():
    async def main():
        _, transport, pool, engine, observed = make_repeater_stack()
        # Equal two-hop routes replace the original three-hop chain.
        # Register in reverse lexical order to expose incidental iteration ties.
        engine.mesh.links.clear()
        for repeater in ("repeater-b", "repeater-a"):
            engine.mesh.register_link(ALICE, repeater)
            engine.mesh.register_link(repeater, BOB)
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "established" and session.extracted_bits == 256
        assert session.entropy_budget["chsh_S_lower"] > 2.0
        assert set(nodes for nodes, _ in observed["created"]) == {
            (ALICE, "repeater-a"), ("repeater-a", BOB),
        }
        assert len(observed["created"]) == 16000
        assert len(observed["swapped"]) == 8000
        assert (await transport.inspect("repeater-b"))["active_count"] == 0
        assert pool.list_active_pairs() == []
        await owner_use_both(transport, session, "lexical-route")

    _run(main())


@pytest.mark.parametrize("kind,fidelity,established", (
    (BellStateType.PSI_MINUS, 1.0, True),
    (BellStateType.PHI_PLUS, 0.5, False),
))
def test_e91_uses_actual_returned_density_and_known_frame(kind, fidelity, established):
    async def main():
        class PhysicalResourcePool(BellPairPool):
            async def create_pair(self, node_a, node_b, state_type, requested_fidelity, **kwargs):
                # A deterministic physical-state seam, not a routing success
                # stub: the real pool creates the density and both worker leases.
                return await super().create_pair(node_a, node_b, kind, fidelity, **kwargs)

        workers = make_workers()
        transport = LocalNodeTransport(workers)
        pool = PhysicalResourcePool(transport=transport)
        mesh = QuantumRepeaterMesh(pool)
        mesh.register_node(ALICE, "density-a")
        mesh.register_node(BOB, "density-b")
        mesh.register_link(ALICE, BOB)
        engine = QKDProtocolEngine(mesh, rng=random.Random(4404))
        session = await engine.run_e91(ALICE, BOB, 8000)
        if established:
            assert session.status == "established" and session.qber == 0.0
            assert session.extracted_bits == 256
            assert session.entropy_budget["chsh_S_lower"] > 2.0
            await owner_use_both(transport, session, "normalized-frame")
        else:
            assert session.status == "aborted" and session.reason == "entanglement_witness_failed"
            assert session.entropy_budget["chsh_S_lower"] <= 2.0
            assert session.extracted_bits == 0 and session.key_commitment_hex is None
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "actual-density")
            assert (await transport.inspect(node))["active_count"] == 0
        assert pool.list_active_pairs() == []

    _run(main())


@pytest.mark.parametrize("failure_stage", ("reserve", "consume"))
def test_e91_unconfirmed_pool_retirement_prevents_extraction(failure_stage):
    async def main():
        class UnconfirmedRetirement(BellPairPool):
            attempted = []

            async def reserve_pairs(self, pair_ids, **kwargs):
                result = await super().reserve_pairs(pair_ids, **kwargs)
                if failure_stage == "reserve" and "-retire-" in kwargs["operation_id"]:
                    self.attempted.extend(pair_ids)
                    raise QuantumResourceError("retirement_unconfirmed", "reservation acknowledgement lost")
                return result

            async def consume_pairs(self, pair_ids, **kwargs):
                await super().consume_pairs(pair_ids, **kwargs)
                if failure_stage == "consume" and "-retire-" in kwargs["operation_id"]:
                    self.attempted.extend(pair_ids)
                    raise QuantumResourceError("retirement_unconfirmed", "consumption acknowledgement lost")

        workers = make_workers()
        transport = LocalNodeTransport(workers)
        pool = UnconfirmedRetirement(transport=transport)
        mesh = QuantumRepeaterMesh(pool)
        mesh.register_node(ALICE, "retire-a")
        mesh.register_node(BOB, "retire-b")
        mesh.register_link(ALICE, BOB)
        engine = QKDProtocolEngine(mesh, rng=random.Random(4404))
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "failed" and session.reason == "resource_cleanup_unconfirmed"
        assert session.extracted_bits == 0 and session.key_commitment_hex is None
        assert len(pool.attempted) == 1
        assert pool.status_of(pool.attempted[0]) is PairStatus.QUARANTINED
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "retire-unconfirmed")
            assert (await transport.inspect(node))["active_count"] == 0

    _run(main())


def test_e91_partial_swap_lost_transfer_retains_quarantine_without_retry():
    async def main():
        class LostTransfer(LocalNodeTransport):
            uncertain_ops = []

            async def transfer(self, node_id, **kwargs):
                result = await super().transfer(node_id, **kwargs)
                if "-swap-0-xfer-a" in kwargs["operation_id"]:
                    self.uncertain_ops.append(kwargs["operation_id"])
                    raise NodeTransportAmbiguous("survivor transfer reply lost")
                return result

        _, transport, pool, engine, observed = make_repeater_stack(transport_type=LostTransfer)
        session = await engine.run_e91(ALICE, BOB, 8000)
        assert session.status == "failed" and session.reason == "resource_cleanup_unconfirmed"
        assert not session.keys_agreed and session.extracted_bits == 0
        assert session.key_commitment_hex is None
        assert len(transport.uncertain_ops) == 1
        assert len(observed["created"]) == 3 and observed["swapped"] == []
        assert [
            pool.status_of(pair_id) for _, pair_id in observed["created"]
        ] == [PairStatus.QUARANTINED, PairStatus.QUARANTINED, PairStatus.DISCARDED]
        for node in engine.mesh.nodes:
            assert (await transport.inspect(node))["active_count"] == 0
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "partial-swap")

    _run(main())


def test_channel_interception_applies_born_resend():
    """The live channel resends Eve's Born-measured eigenstate, deterministically."""
    outgoing = encode_signals([0] * 200)
    resent = decode_signals(
        QuantumChannelInterception.apply(outgoing, random.Random(20260612)), "resent",
    )
    assert len(resent) == 200
    # |0> input: a rectilinear resend is 0, a diagonal resend is |+>/|->.
    assert set(resent) <= {0, 2, 3}
    assert len(set(resent)) > 1
    repeat = decode_signals(
        QuantumChannelInterception.apply(outgoing, random.Random(20260612)), "resent",
    )
    assert repeat == resent


def test_late_begin_after_abort_unknown_stays_quarantined():
    """A delayed begin landing after an unknown_session abort stays tracked/quarantined."""
    async def main():
        class DelayedBegin(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.armed = True
                self.held = None
                self.abort_ops = []

            async def qkd_step(self, node_id, **kwargs):
                if kwargs.get("action") == "abort":
                    self.abort_ops.append((node_id, kwargs.get("operation_id")))
                if (
                    self.armed
                    and kwargs.get("action") == "begin"
                    and node_id == ALICE
                    and self.held is None
                ):
                    self.held = (node_id, dict(kwargs))
                    raise NodeTransportAmbiguous("begin reply lost; may have applied")
                return await super().qkd_step(node_id, **kwargs)

        _events, sink = make_sink()
        workers = make_workers()
        transport = DelayedBegin(workers)
        pool = BellPairPool(transport=transport)
        mesh = QuantumRepeaterMesh(pool, rng=random.Random(911))
        mesh.register_node(ALICE, "test-a")
        mesh.register_node(BOB, "test-b")
        mesh.register_link(ALICE, BOB)
        engine = QKDProtocolEngine(
            mesh, pool=pool, transport=transport, rng=random.Random(5), append_event=sink,
        )
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "failed"
        assert session.reason == "key_cleanup_unconfirmed"
        assert session.keys_agreed is False
        assert session.key_commitment_hex is None
        sid = session.session_id
        # One mutation round only: the pending ALICE begin reconciles
        # read-only after its unknown_session abort, BOB was never bound.
        assert len(transport.abort_ops) == 2
        assert sorted(node for node, _ in transport.abort_ops) == [ALICE, BOB]
        # The delayed begin actually arrives after the unknown_session abort.
        assert transport.held is not None
        node, held_kwargs = transport.held
        transport.armed = False
        reply = await LocalNodeTransport.qkd_step(transport, node, **held_kwargs)
        assert reply["ok"] is True
        # Original scope stays tracked and quarantined: no clearance inference.
        assert sid in engine._session_instances
        assert set(engine._quarantined_sessions[sid]) == {ALICE}
        late = await transport.qkd_step(
            ALICE, operation_id="late-vault-1", session_id=sid, action="lengths", payload={},
            instance=engine._session_instances[sid][ALICE],
        )
        assert late["state"] == "active" and late["key_available"] is False
        # Read-only reconciliation never mutates again and never clears.
        assert await engine.release_session_keys(sid, operation="drill_release") is False
        assert len(transport.abort_ops) == 2
        assert set(engine._quarantined_sessions[sid]) == {ALICE}
        still_late = await transport.qkd_step(
            ALICE, operation_id="late-vault-2", session_id=sid, action="lengths", payload={},
            instance=engine._session_instances[sid][ALICE],
        )
        assert still_late["state"] == "active" and still_late["key_available"] is False
        assert_public_clean(session.to_dict())

    _run(main())


def test_receipt_failure_aborts_exactly_once_per_node():
    """A receipt refusal destroys both endpoint keys with a single abort round."""
    async def main():
        class CountingAbort(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.abort_ops = []

            async def qkd_step(self, node_id, **kwargs):
                if kwargs.get("action") == "abort":
                    self.abort_ops.append((node_id, kwargs.get("operation_id")))
                return await super().qkd_step(node_id, **kwargs)

        workers = make_workers()
        transport = CountingAbort(workers)
        pool = BellPairPool(transport=transport)
        mesh = QuantumRepeaterMesh(pool, rng=random.Random(911))
        mesh.register_node(ALICE, "test-a")
        mesh.register_node(BOB, "test-b")
        mesh.register_link(ALICE, BOB)
        seen = []

        async def broken_sink(event):
            seen.append(event)
            raise RuntimeError("sink refused receipt")

        engine = QKDProtocolEngine(
            mesh, pool=pool, transport=transport, rng=random.Random(11),
            append_event=broken_sink,
        )
        with pytest.raises(RuntimeError, match="sink refused receipt"):
            await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert len(seen) == 2
        assert len(transport.abort_ops) == 2
        assert sorted(node for node, _ in transport.abort_ops) == [ALICE, BOB]
        assert list(engine._session_instances) != []
        for session_id in list(engine._session_instances):
            await assert_keyless(transport, ALICE, session_id, f"rc-a-{session_id[-4:]}")
            await assert_keyless(transport, BOB, session_id, f"rc-b-{session_id[-4:]}")

    _run(main())


def test_receipt_failure_uncertain_abort_quarantines_without_retry():
    """A partitioned abort during receipt failure quarantines with one mutation round."""
    async def main():
        class PartitionedAbort(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.abort_ops = []

            async def qkd_step(self, node_id, **kwargs):
                if kwargs.get("action") == "abort":
                    self.abort_ops.append((node_id, kwargs.get("operation_id")))
                if node_id == BOB and kwargs.get("action") in ("abort", "lengths"):
                    raise NodeTransportUnavailable("abort partition")
                return await super().qkd_step(node_id, **kwargs)

        workers = make_workers()
        transport = PartitionedAbort(workers)
        pool = BellPairPool(transport=transport)
        mesh = QuantumRepeaterMesh(pool, rng=random.Random(911))
        mesh.register_node(ALICE, "test-a")
        mesh.register_node(BOB, "test-b")
        mesh.register_link(ALICE, BOB)

        async def broken_sink(event):
            raise RuntimeError("sink refused receipt")

        engine = QKDProtocolEngine(
            mesh, pool=pool, transport=transport, rng=random.Random(11),
            append_event=broken_sink,
        )
        with pytest.raises(RuntimeError, match="sink refused receipt"):
            await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert len(transport.abort_ops) == 2
        sid = next(iter(engine._session_instances))
        assert set(engine._quarantined_sessions[sid]) == {BOB}
        await assert_keyless(transport, ALICE, sid, "rcu-a")
        local = LocalNodeTransport(workers)
        bob = await local.qkd_step(
            BOB, operation_id="rcu-observe", session_id=sid, action="lengths", payload={},
        )
        assert bob["key_available"] is True
        await local.qkd_step(
            BOB, operation_id="rcu-cleanup", session_id=sid,
            action="abort", payload={"reason": "user_abort"},
        )

    _run(main())


def test_e91_neutral_refusal_with_confirmed_retire_is_failed_reason_none():
    """A neutral mid-round refusal with confirmed retirement keeps failed/reason-None."""
    async def main():
        class NeutralRefusal(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.refused = False

            async def qkd_step(self, node_id, **kwargs):
                if kwargs.get("action") == "measure_e91" and not self.refused:
                    self.refused = True
                    raise NodeCommandFailed(409, "session_step", "injected neutral refusal")
                return await super().qkd_step(node_id, **kwargs)

        workers = make_workers()
        transport = NeutralRefusal(workers)
        pool = BellPairPool(transport=transport)
        mesh = QuantumRepeaterMesh(pool, rng=random.Random(911))
        mesh.register_node(ALICE, "test-a")
        mesh.register_node(BOB, "test-b")
        mesh.register_link(ALICE, BOB)
        engine = QKDProtocolEngine(mesh, pool=pool, transport=transport, rng=random.Random(4404))
        session = await engine.run_e91(ALICE, BOB, 8000, requested_bits=256)
        assert session.status == "failed" and session.reason is None
        assert session.keys_agreed is False
        assert session.extracted_bits == 0
        assert session.key_id is None
        assert session.commitment_alice_hex is None
        assert session.commitment_bob_hex is None
        assert session.key_commitment_hex is None
        assert transport.refused is True
        assert session.session_id not in engine._quarantined_sessions
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "neutral-refusal")
        assert pool.list_active_pairs() == []
        assert_public_clean(session.to_dict())

    _run(main())


def test_engine_tag_mismatch_with_admissible_qber_withholds_key():
    """Public-syndrome tampering breaks agreement without touching signals."""
    async def main():
        class SyndromeTamper(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.tags = {}
                self.extractions = 0

            async def qkd_step(self, node_id, **kwargs):
                if kwargs.get("action") == "extract":
                    self.extractions += 1
                if kwargs.get("action") == "correct":
                    payload = dict(kwargs["payload"])
                    tampered = dict(payload["syndrome"])
                    raw = bytearray(base64.b64decode(tampered["data"]))
                    raw[0] ^= 0x01
                    tampered["data"] = base64.b64encode(bytes(raw)).decode()
                    payload["syndrome"] = tampered
                    kwargs = dict(kwargs, payload=payload)
                reply = await super().qkd_step(node_id, **kwargs)
                if kwargs.get("action") == "tag":
                    self.tags[node_id] = reply["tag"]["data"]
                return reply

        _workers, transport, pool, engine = make_stack(transport_type=SyndromeTamper)
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "aborted" and session.reason == "reconciliation_failed"
        assert session.qber is not None
        assert EavesdropDetector.exceeds(session.error_count, session.test_count) is False
        assert transport.tags[ALICE] != transport.tags[BOB]
        assert transport.extractions == 0
        assert session.keys_agreed is False
        assert session.extracted_bits == 0
        assert session.key_id is None
        assert session.commitment_alice_hex is None
        assert session.commitment_bob_hex is None
        assert session.key_commitment_hex is None
        for node in (ALICE, BOB):
            await assert_keyless(transport, node, session.session_id, "tag-tamper")
        assert pool.list_active_pairs() == []

    _run(main())




def make_drill_trio(transport_type=LocalNodeTransport, pool_type=BellPairPool):
    """Three real workers sharing one pool/mesh/protocol/engine graph."""
    nodes = ("drill-left", "drill-mid", "drill-right")
    workers = {
        name: QuantumNodeWorker(name, token=TOKEN, rng=random.Random(3000 + index))
        for index, name in enumerate(nodes)
    }
    transport = transport_type(workers)
    pool = pool_type(transport=transport)
    engine = QKDProtocolEngine(pool=pool, transport=transport, rng=random.Random(9134))
    mesh = QuantumRepeaterMesh(pool)
    for node in nodes:
        mesh.register_node(node, "drill-region")
    mesh.register_link(nodes[0], nodes[1])
    mesh.register_link(nodes[1], nodes[2])
    protocol = QuantumTeleportationProtocol(mesh, transport=transport)
    return nodes, workers, transport, pool, engine, mesh, protocol


async def _hold_caller_material(transport, pool, protocol, engine, nodes):
    user_pair = await pool.create_pair(
        nodes[0], nodes[2], BellStateType.PHI_PLUS, 1.0, operation_id="caller-pair",
    )
    user_input = await pool.create_pair(
        nodes[0], nodes[2], BellStateType.PHI_PLUS, 1.0, operation_id="caller-teleport-input",
    )
    user_output = await protocol.teleport_qubit(
        nodes[0], nodes[2], 1, 1j, bell_pair=user_input.pair_id,
    )
    user_key = await engine.run_bb84(nodes[0], nodes[2], 12000)
    assert user_output.success is True
    assert user_key.status == "established"
    before = {
        node: (await transport.inspect(node))["leases"] for node in nodes
    }
    return user_pair, user_key, user_output, before


async def _assert_caller_material_intact(transport, pool, protocol, nodes, material):
    user_pair, user_key, user_output, before = material
    assert pool.status_of(user_pair.pair_id) is PairStatus.ACTIVE
    assert protocol.outputs[user_output.session_id].status == "available"
    for node in nodes:
        # Exact original identities plus all live leases prove both caller
        # isolation and cleanup of every known-owned drill allocation.
        assert (await transport.inspect(node))["leases"] == before[node]
    for node, commitment_field in (
        (nodes[0], "commitment_alice_hex"), (nodes[2], "commitment_bob_hex"),
    ):
        held = await transport.qkd_step(
            node, operation_id=f"caller-lengths-{node}", session_id=user_key.session_id,
            action="lengths", payload={},
        )
        assert held["key_available"] is True
        capability = await transport.qkd_owner(
            node, operation_id=f"caller-capability-{node}", session_id=user_key.session_id,
            action="capability", payload={},
        )
        outcome = await transport.qkd_owner(
            node, operation_id=f"caller-use-{node}", session_id=user_key.session_id,
            action="use", payload={"operation": "qkd_test", "capability": capability["capability"]},
        )
        assert outcome["outcome"] == "accepted"
        assert outcome["commitment"] == getattr(user_key, commitment_field)
    released = await protocol.release_teleport_output(
        user_output.session_id, nodes[2], "caller-release-after-negative-drill",
    )
    assert released["ok"] is True
    assert protocol.outputs[user_output.session_id].status == "released"


def test_drill_partial_second_allocation_keeps_caller_material(tmp_path):
    """A refused second purification pair fails the stage without touching user material."""
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        class RefuseSecondReserve(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.reserves = 0
                self.armed = False

            async def reserve(self, node_id, **kwargs):
                if self.armed:
                    self.reserves += 1
                    if self.reserves == 3:
                        raise NodeCommandFailed(409, "worker_capacity", "injected partial refusal")
                return await super().reserve(node_id, **kwargs)

        nodes, _workers, transport, pool, engine, mesh, protocol = make_drill_trio(
            transport_type=RefuseSecondReserve,
        )
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
            material = await _hold_caller_material(transport, pool, protocol, engine, nodes)
            transport.armed = True
            report = await drill.run()
            assert report["all_passed"] is False
            assert report["stages"]["purify"]["passed"] is False
            assert report["stages"]["purify"]["reason"] == "worker_refused"
            assert report["prerequisite"] == "numerical_stage_failed"
            assert "ledger" not in report["stages"]
            await _assert_caller_material_intact(transport, pool, protocol, nodes, material)
        finally:
            ledger.close()

    _run(main())


def test_drill_swap_refusal_never_fake_passes(tmp_path):
    """A refused swap BSM fails the stage while the real purify stage still passes."""
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        class RefuseSwapMeasure(LocalNodeTransport):
            async def measure(self, node_id, **kwargs):
                if "-swap" in kwargs.get("operation_id", ""):
                    raise NodeCommandFailed(409, "worker_refused_measure", "injected swap refusal")
                return await super().measure(node_id, **kwargs)

        nodes, _workers, transport, pool, engine, mesh, protocol = make_drill_trio(
            transport_type=RefuseSwapMeasure,
        )
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
            material = await _hold_caller_material(transport, pool, protocol, engine, nodes)
            report = await drill.run()
            assert report["all_passed"] is False
            assert report["stages"]["purify"]["passed"] is True
            assert report["stages"]["swap"]["passed"] is False
            assert report["prerequisite"] == "numerical_stage_failed"
            assert "ledger" not in report["stages"]
            await _assert_caller_material_intact(transport, pool, protocol, nodes, material)
            user_pair, _, _, _ = material
            leftovers = [
                pair.pair_id for pair in pool.list_active_pairs()
                if pair.pair_id != user_pair.pair_id
            ]
            assert leftovers == []
        finally:
            ledger.close()

    _run(main())


def test_drill_teleport_below_threshold_prevents_summary_and_preserves_caller(tmp_path):
    """Post-swap channel noise changes the actual joint rho, not a result scalar."""
    from dataclasses import replace
    from desk_gateway import quantum_state
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():

        class NoisyLinkPool(BellPairPool):
            async def activate_output(self, pair_id, *, operation_id):
                await super().activate_output(pair_id, operation_id=operation_id)
                record = self._records[pair_id]
                if (record.pair.node_a, record.pair.node_b) == (nodes[0], nodes[2]):
                    # The swap has completed; subsequent link noise degrades
                    # its real registered density before the teleport BSM.
                    record.pair = replace(
                        record.pair,
                        rho=quantum_state.BellState(record.pair.state_type.value).density(0.5),
                    )

        nodes, _workers, transport, pool, engine, mesh, protocol = make_drill_trio(pool_type=NoisyLinkPool)
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
            material = await _hold_caller_material(transport, pool, protocol, engine, nodes)
            report = await drill.run()
            assert report["stages"]["teleport"]["passed"] is False
            assert report["stages"]["teleport"]["reason"] == "below_threshold"
            assert report["stages"]["teleport"]["fidelity"] < 0.95
            for stage in ("purify", "swap", "clean_bb84", "eve"):
                assert report["stages"][stage]["passed"] is True
            assert report["all_passed"] is False
            assert report["prerequisite"] == "numerical_stage_failed"
            assert "ledger" not in report["stages"]
            for summary in ledger.events_by_type("drill.summary"):
                proof = ledger.inclusion_proof(summary["event_id"], ledger.tree_size)
                assert proof.eligible is False
                assert ledger.verify_committed_proof(proof) is True
            await _assert_caller_material_intact(transport, pool, protocol, nodes, material)
        finally:
            ledger.close()

    _run(main())


def test_drill_clean_and_eve_transport_failure_never_passes(tmp_path):
    """Refused BB84 prepares fail both QKD stages without touching user material."""
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        class RefusePrepare(LocalNodeTransport):
            armed = False

            async def qkd_step(self, node_id, **kwargs):
                if self.armed and kwargs.get("action") == "prepare_bb84":
                    raise NodeTransportUnavailable("injected prepare partition")
                return await super().qkd_step(node_id, **kwargs)

        nodes, _workers, transport, pool, engine, mesh, protocol = make_drill_trio(
            transport_type=RefusePrepare,
        )
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
            material = await _hold_caller_material(transport, pool, protocol, engine, nodes)
            transport.armed = True
            report = await drill.run()
            assert report["all_passed"] is False
            assert report["stages"]["clean_bb84"]["passed"] is False
            assert report["stages"]["eve"]["passed"] is False
            assert report["prerequisite"] == "numerical_stage_failed"
            assert "ledger" not in report["stages"]
            await _assert_caller_material_intact(transport, pool, protocol, nodes, material)
        finally:
            ledger.close()

    _run(main())


def test_drill_survivor_cleanup_propagates_and_sweep_stays_sticky():
    """An unconfirmed survivor discard fails purify and is never re-released."""
    async def main():
        class FailFirstDiscardRelease(LocalNodeTransport):
            def __init__(self, workers):
                super().__init__(workers)
                self.discard_releases = 0

            async def release(self, node_id, **kwargs):
                if "discard" in kwargs.get("operation_id", "") and self.discard_releases == 0:
                    self.discard_releases += 1
                    raise NodeTransportAmbiguous("survivor release reply lost")
                return await super().release(node_id, **kwargs)

        nodes, _workers, transport, pool, engine, mesh, protocol = make_drill_trio(
            transport_type=FailFirstDiscardRelease,
        )
        user_pair = await pool.create_pair(
            nodes[0], nodes[2], BellStateType.PHI_PLUS, 1.0, operation_id="user-held",
        )
        quarantined = []
        real_quarantine = pool.quarantine_pairs

        async def spy_quarantine(pair_ids, *, reason):
            quarantined.extend(pair_ids)
            return await real_quarantine(pair_ids, reason=reason)

        pool.quarantine_pairs = spy_quarantine
        drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, None, None)
        owned: list = []
        purify = await drill._purify(nodes[0], nodes[1], "sticky-tag", owned)
        assert purify["passed"] is False
        assert purify["reason"] == "cleanup_unconfirmed"
        assert len(owned) == 3
        survivor = owned[-1]
        assert survivor in quarantined
        assert pool.status_of(survivor) is PairStatus.QUARANTINED
        assert transport.discard_releases == 1
        # The end-of-run sweep never issues a new-op release for it.
        assert await drill._cleanup_owned("sticky-tag", owned, [], []) is False
        assert transport.discard_releases == 1
        assert pool.status_of(survivor) is PairStatus.QUARANTINED
        assert pool.status_of(owned[1]) is PairStatus.CONSUMED
        assert pool.status_of(user_pair.pair_id) is PairStatus.ACTIVE

    _run(main())


def test_real_drill_parity_reject_prevents_summary_and_preserves_caller(tmp_path):
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    class OneBranchDraw:
        def __init__(self, draw, fallback):
            self.draw = draw
            self.fallback = fallback

        def random(self):
            if self.draw is None:
                return self.fallback.random()
            result, self.draw = self.draw, None
            return result

    async def main():
        nodes, workers, transport, pool, engine, mesh, protocol = make_drill_trio()
        ledger = QuantumTeleportationReceiptLedger(data_dir=str(tmp_path))
        try:
            drill = QuantumTeleportationDrillSimulator(pool, mesh, protocol, engine, ledger, None)
            material = await _hold_caller_material(transport, pool, protocol, engine, nodes)
            # Select a genuine positive-probability unequal BBPSSW parity branch.
            workers[nodes[0]]._rng = OneBranchDraw(0.001, workers[nodes[0]]._rng)
            workers[nodes[1]]._rng = OneBranchDraw(0.999, workers[nodes[1]]._rng)
            report = await drill.run()
            assert report["stages"]["purify"]["passed"] is False
            assert report["stages"]["purify"]["reason"] == "purify_rejected"
            for stage in ("swap", "teleport", "clean_bb84", "eve"):
                assert report["stages"][stage]["passed"] is True
            assert report["all_passed"] is False
            assert report["prerequisite"] == "numerical_stage_failed"
            assert "ledger" not in report["stages"]
            for summary in ledger.events_by_type("drill.summary"):
                proof = ledger.inclusion_proof(summary["event_id"], ledger.tree_size)
                assert proof.eligible is False
                assert ledger.verify_committed_proof(proof) is True
            await _assert_caller_material_intact(transport, pool, protocol, nodes, material)
        finally:
            ledger.close()

    _run(main())
