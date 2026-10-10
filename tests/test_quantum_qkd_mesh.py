"""Behavioral tests for the faithful BB84/E91 numerical engine (phase 69-02).

Deterministic throughout (fixed ``random.Random`` seeds, no seed hunting):
every assertion below follows from the physics or the integer admission
gates, not from tuned randomness. No source reads, no mock echoes, no
"class exists" pins. Key bytes are compared for equality but never printed.

Workflows run via ``asyncio.run`` so these tests need no asyncio plugin.
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
from desk_gateway.quantum_node import QuantumNodeError, QuantumNodeWorker
from desk_gateway.quantum_qkd_mesh import QKDProtocolEngine
from desk_gateway.quantum_state import QuantumStateVector
from desk_gateway.quantum_teleportation import BellPairPool
from desk_gateway.quantum_transport import LocalNodeTransport

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
    "final_shared_key",
    "blinding",
    "capability",
    "secret",
    "bearer",
    "signer",
    "password",
    "passwd",
    "mnemonic",
    "private",
    "seed",
    "token",
)


def _run(awaitable):
    return asyncio.run(awaitable)


def make_workers():
    return {
        ALICE: QuantumNodeWorker(ALICE, token=TOKEN),
        BOB: QuantumNodeWorker(BOB, token=TOKEN),
    }


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


def worker_scope(worker, node):
    return {"token": TOKEN, "node": node, "instance": worker.instance_id}


def test_clean_bb84_establishes_with_equal_private_keys():
    async def main():
        workers = make_workers()
        events, sink = make_sink()
        engine = QKDProtocolEngine(
            pool=BellPairPool(),
            workers=workers,
            append_event=sink,
            rng=random.Random(20260612),
        )
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)

        assert session.status == "established"
        assert session.reason is None
        assert session.protocol == "BB84"
        assert session.extracted_bits == 256
        assert session.keys_agreed is True
        assert session.key_id is not None
        assert session.qber == 0.0
        assert session.commitment_alice_hex is not None
        assert session.commitment_bob_hex is not None
        assert session.key_commitment_hex is not None
        assert session.tag_bits == 32

        alice_key = workers[ALICE]._qkd[session.session_id].key
        bob_key = workers[BOB]._qkd[session.session_id].key
        assert alice_key == bob_key
        assert alice_key is not None and len(alice_key) == 32
        assert not hasattr(engine, "_private")
        assert session.commitment_alice_hex == workers[ALICE]._qkd[session.session_id].commitment_hex
        assert session.commitment_bob_hex == workers[BOB]._qkd[session.session_id].commitment_hex

        public = session.to_dict()
        assert_public_clean(public)
        assert repr(session) == f"QKDSession({session.session_id})"

        assert len(events) == 1
        assert events[0]["event_type"] == "qkd.established"
        # The sink payload is the projection pre-receipt (receipt_id null at
        # emit time); the returned session carries the sink receipt id.
        assert events[0]["payload"] == {**public, "receipt_id": None}
        assert session.receipt_id == "sink-1"
        assert_public_clean(events[0]["payload"])
        key_hex = alice_key.hex()
        assert key_hex not in json.dumps(events[0]["payload"])
        return session

    _run(main())


def test_zero_length_aborts_insufficient_sample():
    async def main():
        workers = make_workers()
        events, sink = make_sink()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, append_event=sink, rng=random.Random(5)
        )
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


def test_engine_single_flip_establishes_double_flip_aborts():
    async def main():
        workers = make_workers()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, rng=random.Random(99)
        )
        good = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256, _flip_bob=[3])
        assert good.status == "established"
        assert good.keys_agreed is True
        assert workers[ALICE]._qkd[good.session_id].key == workers[BOB]._qkd[good.session_id].key
        assert not hasattr(engine, "_private")

        workers2 = make_workers()
        engine2 = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers2, rng=random.Random(100)
        )
        bad = await engine2.run_bb84(ALICE, BOB, 12000, requested_bits=256, _flip_bob=[0, 1])
        assert bad.status == "aborted"
        assert bad.reason == "reconciliation_failed"
        assert bad.keys_agreed is False
        assert bad.commitment_alice_hex is None
        assert bad.key_commitment_hex is None
        assert workers2[ALICE]._qkd[bad.session_id].key is None
        assert workers2[BOB]._qkd[bad.session_id].key is None
        with pytest.raises(QuantumNodeError) as exc:
            await workers2[ALICE].use_key(
                operation_id="probe-1",
                owner=ALICE,
                session=bad.session_id,
                capability="whatever",
                **worker_scope(workers2[ALICE], ALICE),
            )
        assert exc.value.status == 409

    _run(main())


def test_intercept_resend_aborts_both_nodes_keyless():
    async def main():
        workers = make_workers()
        events, sink = make_sink()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, append_event=sink, rng=random.Random(7)
        )
        session = await engine.run_bb84(ALICE, BOB, 3000, intercept=True)

        assert session.status == "aborted"
        assert session.reason == "qber_exceeded"
        assert session.qber is not None and session.qber > 0.11
        assert session.keys_agreed is False
        assert session.commitment_alice_hex is None
        assert session.commitment_bob_hex is None
        assert session.key_commitment_hex is None
        assert workers[ALICE]._qkd[session.session_id].key is None
        assert workers[BOB]._qkd[session.session_id].key is None
        assert len(events) == 1
        assert events[0]["event_type"] == "qkd.aborted"
        for node in (ALICE, BOB):
            with pytest.raises(QuantumNodeError) as exc:
                await workers[node].use_key(
                    operation_id=f"probe-{node}",
                    owner=node,
                    session=session.session_id,
                    capability="whatever",
                    **worker_scope(workers[node], node),
                )
            assert exc.value.status == 409

    _run(main())


def test_e91_phi_plus_witness_and_product_control():
    async def main():
        workers = make_workers()
        transport = LocalNodeTransport(workers)
        pool = BellPairPool(transport=transport)
        engine = QKDProtocolEngine(
            pool=pool, workers=workers, rng=random.Random(4404)
        )
        session = await engine.run_e91(ALICE, BOB, 8000, requested_bits=256)

        budget = session.entropy_budget
        assert budget["chsh_S_lower"] > 2.0
        # Either established, or an honest non-witness abort (never a witness
        # pass with a released key, never a mislabeled Eve abort).
        assert session.reason != "entanglement_witness_failed"
        if session.status == "established":
            assert session.keys_agreed is True
            assert session.extracted_bits == 256
            assert workers[ALICE]._qkd[session.session_id].key == workers[BOB]._qkd[session.session_id].key
        else:
            assert session.status == "aborted"
            assert session.keys_agreed is False
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


def test_use_key_one_shot_and_abort_removes_availability():
    async def main():
        workers = make_workers()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, rng=random.Random(20260612)
        )
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "established"
        capability = workers[ALICE]._qkd[session.session_id].capability
        scope = worker_scope(workers[ALICE], ALICE)

        first = await workers[ALICE].use_key(
            operation_id="use-1", owner=ALICE, session=session.session_id,
            capability=capability, **scope,
        )
        assert first == {"ok": True, "outcome": "accepted"}

        with pytest.raises(QuantumNodeError) as second:
            await workers[ALICE].use_key(
                operation_id="use-2", owner=ALICE, session=session.session_id,
                capability=capability, **scope,
            )
        assert second.value.status == 409

        with pytest.raises(QuantumNodeError) as wrong:
            await workers[ALICE].use_key(
                operation_id="use-3", owner=ALICE, session=session.session_id,
                capability="0" * 32, **scope,
            )
        assert wrong.value.status in (403, 409)

        await workers[ALICE].abort(
            operation_id="abort-1", session_id=session.session_id, **scope
        )
        with pytest.raises(QuantumNodeError) as gone:
            await workers[ALICE].use_key(
                operation_id="use-4", owner=ALICE, session=session.session_id,
                capability=capability, **scope,
            )
        assert gone.value.status == 409

    _run(main())


def test_ledger_accepts_public_event_rejects_key_material(tmp_path):
    from desk_gateway.quantum_ledger import QuantumTeleportationReceiptLedger

    async def main():
        workers = make_workers()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, rng=random.Random(20260612)
        )
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


def test_inspect_carries_no_key_bits():
    async def main():
        workers = make_workers()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, rng=random.Random(20260612)
        )
        session = await engine.run_bb84(ALICE, BOB, 12000, requested_bits=256)
        assert session.status == "established"
        key_hex = workers[ALICE]._qkd[session.session_id].key.hex()

        for node in (ALICE, BOB):
            seen = await workers[node].inspect(**worker_scope(workers[node], node))
            dumped = json.dumps(seen, sort_keys=True)
            assert key_hex not in dumped
            for needle in FORBIDDEN_KEY_SUBSTRINGS:
                assert needle not in dumped, (node, needle)
        assert "token" not in repr(workers[ALICE])
        assert key_hex not in repr(workers[ALICE])

    _run(main())


def test_invalid_inputs_raise_before_allocation():
    async def main():
        workers = make_workers()
        events, sink = make_sink()
        engine = QKDProtocolEngine(
            pool=BellPairPool(), workers=workers, append_event=sink, rng=random.Random(1)
        )
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
