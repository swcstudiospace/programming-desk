"""Focused behavioral tests for the quantum teleportation receipt ledger (REQ-008)
and the Devnet Memo anchor publisher (REQ-009).

Scope: durable receipts, historical proofs, tamper/replay/concurrency,
binary execution codec, wire caps, signer loader, and the full RPC
status/readback matrix against a scripted in-process RPC fixture. No live
network, no real keys, no source-text or wiring assertions: every test
exercises observable behavior and would fail if the behavior regressed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from desk_gateway.quantum_anchor import (
    ATTEST_PREFIX,
    COMPUTE_BUDGET_PROGRAM_ID,
    DEVNET_GENESIS_HASH,
    MEMO_PROGRAM_ID,
    AnchorError,
    PayloadTooLargeError,
    QuantumTeleportationAnchorExporter,
    assert_wire_caps,
    b58decode,
    b58encode,
    build_message,
    decode_attestation,
    encode_attestation,
    load_signer,
    parse_message,
    shortvec_decode,
    shortvec_encode,
    transaction_bytes,
    verify_message_shape,
    verify_signature,
)
from desk_gateway.quantum_ledger import (
    EMPTY_ROOT_HEX,
    InclusionProof,
    LedgerCorruptError,
    QuantumTeleportationReceiptLedger,
    canonical_event_bytes,
    decode_execution_leaf,
    encode_execution_leaf,
    metadata_commit_hex,
    proof_from_jsonable,
    proof_to_jsonable,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_ledger(tmp_path: Path, name: str = "ledger") -> QuantumTeleportationReceiptLedger:
    return QuantumTeleportationReceiptLedger(tmp_path / name)


def teleport_payload(**over) -> dict:
    base = {
        "model_version": 1,
        "frame_x": 0,
        "frame_z": 1,
        "bsm_x": 1,
        "bsm_z": 0,
        "correction_x": 1,
        "correction_z": 1,
        "gate_x": True,
        "gate_z": True,
        "correction_applied": True,
        "acknowledged": True,
        "input_destroyed": True,
        "resource_consumed": True,
        "fidelity": 0.97,
    }
    base.update(over)
    return base


def teleport_event(session: str = "tele-a", **over) -> dict:
    payload = teleport_payload(**over.pop("payload", {})) if "payload" in over else teleport_payload()
    event = {
        "event_type": "teleport.completed",
        "session_id": session,
        "actor": "simulator",
        "nodes": ["node-a", "node-b"],
        "resources": ["pair-1"],
        "outcome": "success",
        "payload": payload,
    }
    event.update(over)
    return event


def drill_event(session: str = "drill-1") -> dict:
    commitment = hashlib.sha256(b"node-a-blind-commitment|node-b-blind-commitment").hexdigest()
    return {
        "event_type": "drill.summary",
        "session_id": session,
        "actor": "simulator",
        "nodes": ["node-a", "node-b"],
        "resources": ["pair-1", "pair-2"],
        "outcome": "success",
        "payload": {
            "teleport": teleport_payload(),
            "purification": {"baseline_fidelity": 0.80, "output_fidelity": 0.92},
            "swap": {"fidelity": 0.96},
            "clean": {
                "sifted_count": 1000,
                "test_count": 100,
                "error_count": 5,
                "output_bits": 256,
                "established": True,
                "key_agreement": True,
            },
            "eve": {
                "test_count": 200,
                "error_count": 40,
                "basis": 0,
                "aborted": True,
                "both_keyless": True,
            },
            "key_commitment_hex": commitment,
        },
    }


def aborted_event(session: str = "qkd-eve-1") -> dict:
    return {
        "event_type": "qkd.aborted",
        "session_id": session,
        "actor": "simulator",
        "nodes": ["node-a", "node-b"],
        "resources": ["pair-9"],
        "outcome": "aborted",
        "payload": {
            "reason": "qber_exceeded",
            "test_count": 200,
            "error_count": 41,
            "qber": 0.205,
            "both_keyless": True,
        },
    }


def write_throwaway_signer(tmp_path: Path, name: str = "signer.key") -> tuple[str, bytes]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    seed = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    home = tmp_path / "signerhome"
    home.mkdir(mode=0o700, exist_ok=True)
    os.chmod(home, 0o700)
    path = home / name
    path.write_bytes(bytes(seed) + bytes(pub))
    os.chmod(path, 0o600)
    return str(path), bytes(pub)


# ---------------------------------------------------------------------------
# Scripted Devnet RPC fixture (in-process; no network)
# ---------------------------------------------------------------------------

TX_SLOT = 509319991


class RpcFixture:
    """Deterministic JSON-RPC double recording every call in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.genesis = DEVNET_GENESIS_HASH
        self.blockhash_bytes = bytes(range(32))
        self.last_valid = 10_000_000
        self.fee: int | None = 5000
        self.balance: int | None = 1_000_000
        self.fail: dict[str, str] = {}  # method -> transport|rpcerror|malformed
        self.send_mode = "echo"  # echo|mismatch|error
        self.status_queue: list = []
        self.status_default = {
            "slot": TX_SLOT,
            "confirmations": None,
            "err": None,
            "confirmationStatus": "confirmed",
        }
        self.tx_mode = "match"
        self.height = 9_999_999
        self.sent: dict = {}

    # -- handler ----------------------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        method = body["method"]
        params = body.get("params", [])
        self.calls.append((method, params))
        failure = self.fail.get(method)
        if failure == "transport":
            raise httpx.ConnectError("boom", request=request)
        if failure == "rpcerror":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32005, "message": "node busy"}})
        if failure == "malformed":
            return httpx.Response(200, json={"nope": True})
        result = self._result(method, params)
        if isinstance(result, Exception):
            raise result
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": result})

    def methods_called(self, method: str) -> int:
        return sum(1 for m, _ in self.calls if m == method)

    # -- per-method results -------------------------------------------------
    def _result(self, method: str, params):
        if method == "getGenesisHash":
            return self.genesis
        if method == "getLatestBlockhash":
            return {
                "context": {"slot": 509319990},
                "value": {
                    "blockhash": b58encode(self.blockhash_bytes),
                    "lastValidBlockHeight": self.last_valid,
                },
            }
        if method == "getFeeForMessage":
            if self.fee is None:
                return {"context": {"slot": 1}, "value": None}
            return {"context": {"slot": 1}, "value": self.fee}
        if method == "getBalance":
            if self.balance is None:
                return {"context": {"slot": 1}, "value": None}
            return {"context": {"slot": 1}, "value": self.balance}
        if method == "sendTransaction":
            if self.send_mode == "error":
                raise httpx.ConnectError("send blew up", request=None)
            raw = base64.b64decode(params[0])
            signature, message = raw[1:65], raw[65:]
            parsed = parse_message(message)
            memo = bytes(parsed["instructions"][1]["data"])
            payer = parsed["accounts"][0]
            self.sent = {
                "signature": b58encode(signature),
                "message": message,
                "memo": memo,
                "payer": b58encode(payer),
            }
            if self.send_mode == "mismatch":
                return b58encode(bytes(range(1, 65)))
            return self.sent["signature"]
        if method == "getSignatureStatuses":
            if self.status_queue:
                entry = self.status_queue.pop(0)
            else:
                entry = dict(self.status_default)
            return {"context": {"slot": 509319990}, "value": [entry]}
        if method == "getTransaction":
            return self._tx_result(params[0])
        if method == "getBlockHeight":
            return self.height
        raise AssertionError(f"unexpected method {method}")

    def _tx_result(self, sig: str):
        if self.tx_mode == "null":
            return None
        sent = self.sent
        memo_text = sent["memo"].decode("utf-8")
        slot = TX_SLOT
        meta = {"err": None}
        instructions = [
            {"programIdIndex": 1, "accounts": [], "data": b58encode(b"\x02" + struct.pack("<I", 400000))},
            {"programIdIndex": 2, "accounts": [0], "data": b58encode(sent["memo"])},
        ]
        keys = [sent["payer"], COMPUTE_BUDGET_PROGRAM_ID, MEMO_PROGRAM_ID]
        if self.tx_mode == "meta_err":
            meta = {"err": {"InstructionError": [0, "Custom"]}}
        elif self.tx_mode == "sig_mismatch":
            sig = b58encode(bytes(range(2, 66)))
        elif self.tx_mode == "payer_mismatch":
            keys = [b58encode(bytes(range(10, 42)))] + keys[1:]
        elif self.tx_mode == "shape_extra":
            instructions = instructions + [
                {"programIdIndex": 1, "accounts": [], "data": b58encode(b"\x02" + struct.pack("<I", 1))}
            ]
        elif self.tx_mode == "memo_mismatch":
            instructions[1] = {"programIdIndex": 2, "accounts": [0], "data": b58encode(b"QTELEPORT1:AAAA")}
            memo_text = "QTELEPORT1:AAAA"
        elif self.tx_mode == "slot_missing":
            slot = None
        return {
            "slot": slot,
            "meta": meta,
            "transaction": {"signatures": [sig], "message": {"accountKeys": keys, "instructions": instructions}},
            "blockTime": None,
        }


def make_exporter(ledger, fixture: RpcFixture, signer_path: str, **kw) -> QuantumTeleportationAnchorExporter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    return QuantumTeleportationAnchorExporter(
        ledger,
        rpc_url="https://devnet.example.invalid",
        signer_path=signer_path,
        http_client=client,
        confirmation_timeout_s=kw.pop("confirmation_timeout_s", 5.0),
        poll_interval_s=kw.pop("poll_interval_s", 0.01),
        **kw,
    )


async def append_teleport(ledger, session="s") -> object:
    return await ledger.append_event(teleport_event(session))


# ---------------------------------------------------------------------------
# Ledger: durability, proofs, codec
# ---------------------------------------------------------------------------

def test_empty_snapshot_uses_versioned_root(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        snap = ledger.snapshot(0)
        assert snap.tree_size == 0
        assert snap.root_hex == EMPTY_ROOT_HEX
        assert snap.receipts == ()
        assert ledger.current_root_hex == EMPTY_ROOT_HEX
    finally:
        ledger.close()


def test_aborted_sample_commits_durably_but_ineligible(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(ledger.append_event(aborted_event()))
        assert receipt.seq == 1
        assert len(receipt.leaf_digest_hex) == 64
        assert receipt.tree_size == 1
        assert receipt.prefix_root_hex == ledger.current_root_hex
        snap = ledger.snapshot()
        assert snap.root_hex == receipt.prefix_root_hex
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert proof.eligible is False
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
    finally:
        ledger.close()


def test_teleport_binary_leaf_is_71_bytes(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert proof.eligible is True
        assert len(proof.leaf_preimage_bytes) == 71
        decoded = decode_execution_leaf(proof.leaf_preimage_bytes)
        assert decoded["leaf_type"] == 1
        assert decoded["flags"] == 1
        assert decoded["seq"] == 1
        assert decoded["teleport"]["fidelity"] == pytest.approx(0.97)
        assert decoded["teleport"]["node_count"] == 2
        assert decoded["metadata_commit_hex"] == metadata_commit_hex(dict(proof.metadata))
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
    finally:
        ledger.close()


def test_drill_binary_leaf_is_150_bytes(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(ledger.append_event(drill_event()))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert len(proof.leaf_preimage_bytes) == 150
        decoded = decode_execution_leaf(proof.leaf_preimage_bytes)
        assert decoded["leaf_type"] == 2
        assert decoded["drill"]["clean_output"] == 256
        assert decoded["drill"]["eve_basis"] == 0
        assert len(decoded["drill"]["key_commitment"]) == 32
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
    finally:
        ledger.close()


def test_proof_binds_complete_metadata(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger, "bind-1"))
        asyncio.run(append_teleport(ledger, "bind-2"))
        proof = ledger.inclusion_proof(receipt.receipt_id, 2)
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
        for field, bad in (
            ("outcome", "failed"),
            ("session_id", "other-session"),
            ("nodes", ["node-a"]),
            ("time", "2000-01-01T00:00:00+00:00"),
        ):
            tampered_meta = dict(proof.metadata)
            tampered_meta[field] = bad
            tampered = InclusionProof(
                version=proof.version,
                leaf_index=proof.leaf_index,
                tree_size=proof.tree_size,
                leaf_preimage_bytes=proof.leaf_preimage_bytes,
                siblings=proof.siblings,
                expected_root_hex=proof.expected_root_hex,
                metadata=tampered_meta,
                eligible=proof.eligible,
                leaf_digest_hex=proof.leaf_digest_hex,
            )
            assert QuantumTeleportationReceiptLedger.verify_proof(tampered) is False
        # Sibling, direction, and root tampering also fail.
        direction, digest = proof.siblings[0]
        flipped = ("left" if direction == "right" else "right", digest)
        bad_sib = InclusionProof(
            version=proof.version, leaf_index=proof.leaf_index, tree_size=proof.tree_size,
            leaf_preimage_bytes=proof.leaf_preimage_bytes,
            siblings=(flipped,) + tuple(proof.siblings[1:]),
            expected_root_hex=proof.expected_root_hex, metadata=dict(proof.metadata),
            eligible=proof.eligible, leaf_digest_hex=proof.leaf_digest_hex,
        )
        assert QuantumTeleportationReceiptLedger.verify_proof(bad_sib) is False
        bad_root = InclusionProof(
            version=proof.version, leaf_index=proof.leaf_index, tree_size=proof.tree_size,
            leaf_preimage_bytes=proof.leaf_preimage_bytes, siblings=proof.siblings,
            expected_root_hex="ff" * 32, metadata=dict(proof.metadata),
            eligible=proof.eligible, leaf_digest_hex=proof.leaf_digest_hex,
        )
        assert QuantumTeleportationReceiptLedger.verify_proof(bad_root) is False
        with pytest.raises(LookupError):
            ledger.inclusion_proof("no-such-receipt", 2)
        with pytest.raises(ValueError):
            ledger.inclusion_proof(receipt.receipt_id, 2 + 1)
    finally:
        ledger.close()


def test_proof_json_projection_roundtrip(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        projected = proof_to_jsonable(proof)
        assert projected["leaf_preimage_hex"] == bytes(proof.leaf_preimage_bytes).hex()
        assert isinstance(projected["siblings"], list)
        rebuilt = proof_from_jsonable(projected)
        assert QuantumTeleportationReceiptLedger.verify_proof(rebuilt) is True
        projected["expected_root_hex"] = "00" * 32
        assert QuantumTeleportationReceiptLedger.verify_proof(proof_from_jsonable(projected)) is False
        with pytest.raises(ValueError):
            proof_from_jsonable({"bogus": True})
    finally:
        ledger.close()


def test_canonical_bytes_are_key_order_invariant(tmp_path):
    meta_a = {"b": 1, "a": [1, 2], "seq": 3}
    meta_b = {"seq": 3, "a": [1, 2], "b": 1}
    assert canonical_event_bytes(meta_a) == canonical_event_bytes(meta_b)
    assert canonical_event_bytes({"seq": 4}) != canonical_event_bytes({"seq": 3})


def test_history_prefixes_are_immutable(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        first = asyncio.run(append_teleport(ledger, "h1"))
        root_one = ledger.snapshot(1).root_hex
        proof_one = ledger.inclusion_proof(first.receipt_id, 1)
        asyncio.run(append_teleport(ledger, "h2"))
        asyncio.run(ledger.append_event(aborted_event("h3")))
        assert ledger.snapshot(1).root_hex == root_one
        assert QuantumTeleportationReceiptLedger.verify_proof(proof_one) is True
        assert ledger.snapshot().tree_size == 3
        by_id = ledger.receipt(first.receipt_id)
        assert by_id.seq == 1 and by_id.leaf_digest_hex == first.leaf_digest_hex
    finally:
        ledger.close()


def test_restart_replays_and_continues(tmp_path):
    path = tmp_path / "restart"
    first = QuantumTeleportationReceiptLedger(path)
    try:
        r1 = asyncio.run(append_teleport(first, "r1"))
        r2 = asyncio.run(ledger_append_drill(first))
        root_two = first.snapshot(2).root_hex
    finally:
        first.close()
    second = QuantumTeleportationReceiptLedger(path)
    try:
        assert second.tree_size == 2
        assert second.snapshot(2).root_hex == root_two
        assert second.receipt(r1.receipt_id).leaf_digest_hex == r1.leaf_digest_hex
        r3 = asyncio.run(append_teleport(second, "r3"))
        assert r3.seq == 3
        proof = second.inclusion_proof(r2.receipt_id, 3)
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
    finally:
        second.close()


async def ledger_append_drill(ledger):
    return await ledger.append_event(drill_event())


def _copy_db(tmp_path: Path, src: Path, name: str) -> Path:
    dest = tmp_path / name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "quantum_teleportation.sqlite3", dest / "quantum_teleportation.sqlite3")
    return dest


def test_tampered_payload_fails_closed(tmp_path):
    src = tmp_path / "orig"
    ledger = QuantumTeleportationReceiptLedger(src)
    try:
        asyncio.run(append_teleport(ledger, "t1"))
        asyncio.run(ledger.append_event(drill_event("t2")))
    finally:
        ledger.close()
    # Privileged rewrite: drop the guard trigger, then alter stored metadata.
    victim = _copy_db(tmp_path, src, "victim-payload")
    conn = sqlite3.connect(victim / "quantum_teleportation.sqlite3")
    conn.execute("DROP TRIGGER ledger_no_update_events;")
    conn.execute("UPDATE ledger_events SET canonical_json = REPLACE(canonical_json, 't1', 'tX') WHERE seq = 1;")
    conn.commit()
    conn.close()
    with pytest.raises(LedgerCorruptError):
        QuantumTeleportationReceiptLedger(victim)
    # The untouched original still replays cleanly.
    reopened = QuantumTeleportationReceiptLedger(src)
    try:
        assert reopened.tree_size == 2
    finally:
        reopened.close()


def test_tampered_checkpoint_and_truncation_fail_closed(tmp_path):
    src = tmp_path / "orig2"
    ledger = QuantumTeleportationReceiptLedger(src)
    try:
        asyncio.run(append_teleport(ledger, "c1"))
        asyncio.run(append_teleport(ledger, "c2"))
    finally:
        ledger.close()
    victim = _copy_db(tmp_path, src, "victim-checkpoint")
    conn = sqlite3.connect(victim / "quantum_teleportation.sqlite3")
    conn.execute("DROP TRIGGER ledger_no_update_checkpoints;")
    conn.execute("UPDATE ledger_checkpoints SET root_hex = 'ff' || SUBSTR(root_hex, 3) WHERE tree_size = 2;")
    conn.commit()
    conn.close()
    with pytest.raises(LedgerCorruptError):
        QuantumTeleportationReceiptLedger(victim)

    cut = _copy_db(tmp_path, src, "victim-truncated")
    dbfile = cut / "quantum_teleportation.sqlite3"
    with open(dbfile, "r+b") as handle:
        handle.truncate(os.path.getsize(dbfile) // 2)
    with pytest.raises(LedgerCorruptError):
        QuantumTeleportationReceiptLedger(cut)


def test_concurrent_appends_keep_unique_sequence(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        async def worker(tag: int):
            out = []
            for i in range(25):
                out.append(await ledger.append_event(teleport_event(f"w{tag}-{i}")))
            return out

        async def main():
            return await asyncio.gather(*[worker(t) for t in range(8)])

        receipts = asyncio.run(main())
        flat = [r for group in receipts for r in group]
        assert len(flat) == 200
        assert sorted(r.seq for r in flat) == list(range(1, 201))
        assert len({r.receipt_id for r in flat}) == 200
    finally:
        ledger.close()
    # Threads race the same interprocess lock path from outside asyncio.
    ledger2 = QuantumTeleportationReceiptLedger(tmp_path / "threads")
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(lambda i=i: asyncio.run(ledger2.append_event(teleport_event(f"t{i}"))))
                for i in range(40)
            ]
            results = [f.result() for f in futures]
        assert sorted(r.seq for r in results) == list(range(1, 41))
    finally:
        ledger2.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"sifted_bits": [0, 1, 1]},
        {"private_blinding": "deadbeef"},
        {"bearer_token": "abc"},
        {"signer_bytes": "AA=="},
        {"capability": "use-key"},
        {"raw_key": "00" * 32},
        {"final_shared_key_hex": "11" * 32},
        {"nested": {"secret": "x"}},
    ],
)
def test_admission_rejects_private_fields(tmp_path, payload):
    ledger = make_ledger(tmp_path)
    try:
        event = aborted_event()
        event["payload"] = payload
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(event))
        assert ledger.tree_size == 0
    finally:
        ledger.close()


def test_admission_rejects_bad_shapes(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event({"event_type": "x"}))
        bad = teleport_event()
        bad["mystery"] = 1
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(bad))
        bad_claim = teleport_event()
        bad_claim["payload"] = teleport_payload(correction_x=0)  # breaks BSM XOR frame
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(bad_claim))
        bad_fidelity = teleport_event()
        bad_fidelity["payload"] = teleport_payload(fidelity=float("nan"))
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(bad_fidelity))
        assert ledger.tree_size == 0
    finally:
        ledger.close()


def test_codec_strictness_and_layout():
    summary = {
        "leaf_type": "teleport",
        "flags": 1,
        "seq": 7,
        "event_id_hex": "ab" * 16,
        "metadata_commit_hex": "cd" * 32,
        "teleport": dict(teleport_payload(), node_count=2),
        "drill": None,
    }
    encoded = encode_execution_leaf(summary)
    assert len(encoded) == 71
    assert encoded[4:12] == (7).to_bytes(8, "big")
    assert encoded[63:71] == struct.pack(">d", 0.97)
    assert decode_execution_leaf(encoded)["teleport"]["correction_x"] == 1
    with pytest.raises(ValueError):
        decode_execution_leaf(b"\x01" * 70)
    tampered = bytearray(encoded)
    tampered[2] = 0x80  # reserved flag bit
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(tampered))
    gated = bytearray(encoded)
    gated[61] = 0xF0  # reserved gate bits
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(gated))
    with pytest.raises(ValueError):
        encode_execution_leaf(dict(summary, seq=0))
    with pytest.raises(ValueError):
        decode_execution_leaf(b"\x02\x01" + b"\x00" * 69)


def test_depth16_full_path_wire_cap(tmp_path):
    ledger = QuantumTeleportationReceiptLedger(tmp_path / "deep")
    try:
        for i in range(2**16):
            asyncio.run(ledger.append_event(teleport_event(f"deep-{i}")))
        assert ledger.tree_size == 2**16
        victim_receipt = ledger.snapshot().receipts[12345]
        proof = ledger.inclusion_proof(victim_receipt.receipt_id, 2**16)
        assert len(proof.siblings) == 16
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
        memo_text = encode_attestation(
            tree_size=proof.tree_size,
            leaf_index=proof.leaf_index,
            root_hex=proof.expected_root_hex,
            leaf=bytes(proof.leaf_preimage_bytes),
            siblings=[h for _, h in proof.siblings],
        )
        assert memo_text.startswith(ATTEST_PREFIX)
        memo_bytes = memo_text.encode("utf-8")
        memo_len, packet_len = assert_wire_caps(memo_bytes)
        assert memo_len <= 1021
        assert packet_len <= 1232
        decoded = decode_attestation(memo_text)
        assert decoded["root_hex"] == proof.expected_root_hex
        assert decoded["leaf"] == bytes(proof.leaf_preimage_bytes)
        assert decoded["siblings"] == [h for _, h in proof.siblings]
    finally:
        ledger.close()


def test_wire_cap_gate_rejects_oversize_before_sign(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        memo_text = encode_attestation(
            tree_size=proof.tree_size, leaf_index=proof.leaf_index,
            root_hex=proof.expected_root_hex, leaf=bytes(proof.leaf_preimage_bytes),
            siblings=[h for _, h in proof.siblings],
        )
        memo = memo_text.encode("utf-8")
        assert_wire_caps(memo)  # genuine small proof fits
        oversize = memo + b"X" * (1022 - len(memo))
        assert len(oversize) == 1022
        with pytest.raises(PayloadTooLargeError) as excinfo:
            assert_wire_caps(oversize)
        assert excinfo.value.http_status == 413
        with pytest.raises(ValueError):
            encode_attestation(tree_size=1, leaf_index=1, root_hex=proof.expected_root_hex,
                               leaf=b"leaf", siblings=[])
        with pytest.raises(ValueError):
            decode_attestation("WRONGPREFIX:AAAA")
    finally:
        ledger.close()


# ---------------------------------------------------------------------------
# Signer loader
# ---------------------------------------------------------------------------

def test_signer_loader_accepts_throwaway_key(tmp_path):
    path, pub = write_throwaway_signer(tmp_path)
    identity = load_signer(path)
    assert identity.public_key_bytes == pub
    assert "public_key" in repr(identity)
    message = b"devnet memo smoke"
    signature = identity.sign(message)
    assert verify_signature(pub, signature, message) is True
    assert verify_signature(pub, signature, message + b"x") is False


def test_signer_loader_accepts_json_keypair(tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    seed = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    home = tmp_path / "jsonhome"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    target = home / "key.json"
    target.write_text(json.dumps(list(bytes(seed) + bytes(pub))))
    os.chmod(target, 0o600)
    assert load_signer(str(target)).public_key_bytes == bytes(pub)


@pytest.mark.parametrize("kind", ["symlink", "world_readable", "truncated", "pub_mismatch", "missing", "open_parent"])
def test_signer_loader_rejections_hide_values(tmp_path, kind):
    path, pub = write_throwaway_signer(tmp_path)
    seed_hex = Path(path).read_bytes().hex()
    target = path
    if kind == "symlink":
        link = str(Path(path).parent / "link.key")
        os.symlink(path, link)
        target = link
    elif kind == "world_readable":
        os.chmod(path, 0o644)
    elif kind == "truncated":
        os.chmod(path, 0o600)
        Path(path).write_bytes(Path(path).read_bytes()[:40])
    elif kind == "pub_mismatch":
        raw = bytearray(Path(path).read_bytes())
        raw[40] ^= 0xFF
        Path(path).write_bytes(bytes(raw))
    elif kind == "missing":
        target = str(Path(path).parent / "absent.key")
    elif kind == "open_parent":
        os.chmod(Path(path).parent, 0o755)
    with pytest.raises(AnchorError) as excinfo:
        load_signer(target)
    assert excinfo.value.http_status == 503
    text = str(excinfo.value)
    assert seed_hex not in text
    assert pub.hex() not in text
    # The configured value itself must never surface; only the env name may.
    assert "signerhome" not in text


def test_signer_missing_config_mentions_env_name_only():
    with pytest.raises(AnchorError) as excinfo:
        load_signer(None)
    assert "QUANTUM_SOLANA_SIGNER_PATH" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Publisher: confirmed path + matrix
# ---------------------------------------------------------------------------

def test_confirmed_publishes_once_with_exact_message(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, pub = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger, "pub-1"))
        size = ledger.tree_size
        proof = ledger.inclusion_proof(receipt.receipt_id, size)
        memo_text = encode_attestation(
            tree_size=size, leaf_index=proof.leaf_index, root_hex=proof.expected_root_hex,
            leaf=bytes(proof.leaf_preimage_bytes), siblings=[h for _, h in proof.siblings],
        )
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.ok is True
        assert result.status == "confirmed"
        assert result.slot == TX_SLOT
        assert result.anchored_root_hex == proof.expected_root_hex
        assert result.signature == exporter.prepared_signature(receipt.receipt_id, size)
        assert fixture.methods_called("sendTransaction") == 1
        # Order: genesis, blockhash, fee, balance, then the single send.
        order = [m for m, _ in fixture.calls]
        assert order.index("getGenesisHash") < order.index("getLatestBlockhash")
        assert order.index("getFeeForMessage") < order.index("getBalance")
        assert order.index("getBalance") < order.index("sendTransaction")
        assert order.index("sendTransaction") < order.index("getSignatureStatuses")
        # The fee was estimated for the EXACT prepared message.
        fee_params = next(p for m, p in fixture.calls if m == "getFeeForMessage")
        sent_message = parse_message(base64.b64decode(fee_params[0]))
        assert bytes(sent_message["instructions"][1]["data"]) == memo_text.encode("utf-8")
        assert sent_message["accounts"][0] == pub
        assert sent_message["accounts"][1] == b58decode(COMPUTE_BUDGET_PROGRAM_ID)
        assert sent_message["accounts"][2] == b58decode(MEMO_PROGRAM_ID)
        # Lifecycle records are durable public events.
        kinds = [e["event_type"] for e in ledger.events_by_type("anchor.prepared")]
        assert len(kinds) == 1
        assert ledger.events_by_type("anchor.submitted")
        assert ledger.events_by_type("anchor.confirmed")
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_wrong_genesis_fails_before_send(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.genesis = "11111111111111111111111111111111"
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.ok is False and result.status == "failed"
        assert result.error_code == "wrong_genesis"
        assert result.http_status == 503
        assert result.signature is None
        assert fixture.methods_called("sendTransaction") == 0
        assert exporter.prepared_signature(receipt.receipt_id) is None
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_null_fee_and_failed_fee_lookup_never_send(tmp_path):
    for mode, code, http in (("null", "fee_unavailable", 503), ("rpcerror", "fee_lookup_failed", 502)):
        ledger = make_ledger(tmp_path / f"fee-{mode}")
        signer_path, _ = write_throwaway_signer(tmp_path / f"fee-{mode}")
        fixture = RpcFixture()
        if mode == "null":
            fixture.fee = None
        else:
            fixture.fail["getFeeForMessage"] = "rpcerror"
        exporter = make_exporter(ledger, fixture, signer_path)
        try:
            receipt = asyncio.run(append_teleport(ledger))
            result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
            assert result.status == "failed" and result.error_code == code and result.http_status == http
            assert fixture.methods_called("sendTransaction") == 0
        finally:
            asyncio.run(exporter.aclose())
            ledger.close()


def test_insufficient_balance_blocks_but_later_funded_attempt_proceeds(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.balance = 1  # below any real fee
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        blocked = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert blocked.status == "failed" and blocked.error_code == "insufficient_balance"
        assert blocked.http_status == 503
        assert fixture.methods_called("sendTransaction") == 0
        # A prior prerequisite failure is not a durable block: funding later works.
        fixture.balance = 1_000_000
        funded = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert funded.ok is True
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_processed_status_is_never_green(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.status_queue = [
        {"slot": 509319990, "confirmations": 3, "err": None, "confirmationStatus": "processed"},
    ] * 50
    exporter = make_exporter(ledger, fixture, signer_path, confirmation_timeout_s=0.2)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.ok is False and result.status == "unknown"
        assert result.http_status == 504
        assert result.slot is None
        assert fixture.methods_called("getBlockHeight") >= 1
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_status_error_is_definitive_failure(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.status_queue = [{"slot": 1, "confirmations": None, "err": {"InstructionError": [1, "Custom"]}, "confirmationStatus": None}]
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.status == "failed" and result.error_code == "status_tx_error"
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


@pytest.mark.parametrize(
    "mode,expect_status,expect_code",
    [
        ("memo_mismatch", "failed", "readback_memo_mismatch"),
        ("meta_err", "failed", "readback_tx_error"),
        ("sig_mismatch", "failed", "readback_sig_mismatch"),
        ("payer_mismatch", "failed", "readback_payer_mismatch"),
        ("shape_extra", "failed", "readback_shape_mismatch"),
        ("null", "unknown", "readback_null"),
        ("slot_missing", "failed", "readback_slot_missing"),
    ],
)
def test_readback_matrix(tmp_path, mode, expect_status, expect_code):
    ledger = make_ledger(tmp_path / mode)
    signer_path, _ = write_throwaway_signer(tmp_path / mode)
    fixture = RpcFixture()
    fixture.tx_mode = mode
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.status == expect_status, (mode, result)
        assert result.error_code == expect_code, (mode, result)
        assert not result.ok
        if expect_status == "failed" and mode != "meta_err":
            assert result.http_status == 502
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_expiry_observes_without_resend(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.status_queue = [None] * 100
    fixture.height = fixture.last_valid + 5
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.status == "unknown" and result.error_code == "expired"
        assert result.http_status == 504
        assert result.signature is not None
        assert result.slot is None
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_repeat_and_concurrent_exports_send_once(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        first = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        second = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert first.ok and second.ok
        assert first.signature == second.signature
        assert fixture.methods_called("sendTransaction") == 1

        async def main():
            return await asyncio.gather(*[exporter.export_commitment(receipt.receipt_id) for _ in range(5)])

        again = asyncio.run(main())
        assert {r.signature for r in again} == {first.signature}
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_ineligible_aborted_leaf_makes_no_rpc_calls(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(ledger.append_event(aborted_event()))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.status == "failed" and result.error_code == "ineligible_leaf"
        assert result.http_status == 400
        assert fixture.calls == []
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_send_problems_stay_unknown_with_prepared_sig(tmp_path):
    for mode, code in (("mismatch", "send_sig_mismatch"),):
        ledger = make_ledger(tmp_path / mode)
        signer_path, _ = write_throwaway_signer(tmp_path / mode)
        fixture = RpcFixture()
        fixture.send_mode = mode
        exporter = make_exporter(ledger, fixture, signer_path)
        try:
            receipt = asyncio.run(append_teleport(ledger))
            result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
            assert result.status == "unknown" and result.error_code == code
            assert result.signature == exporter.prepared_signature(receipt.receipt_id)
        finally:
            asyncio.run(exporter.aclose())
            ledger.close()
    ledger = make_ledger(tmp_path / "senderr")
    signer_path, _ = write_throwaway_signer(tmp_path / "senderr")
    fixture = RpcFixture()
    fixture.send_mode = "error"
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.status == "unknown" and result.error_code == "send_failed"
        assert result.http_status == 502
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_rpc_url_and_receipt_gating(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="http://insecure.example.invalid", signer_path=signer_path, http_client=client
    )
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.error_code == "rpc_url_rejected" and result.http_status == 503
        assert fixture.calls == []
        missing = asyncio.run(exporter.export_commitment("does-not-exist"))
        assert missing.error_code == "unknown_receipt" and missing.http_status == 400
    finally:
        asyncio.run(exporter.aclose())
        asyncio.run(client.aclose())
        ledger.close()


def test_local_wire_shape_and_packet_budget(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, pub = write_throwaway_signer(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        memo_text = encode_attestation(
            tree_size=1, leaf_index=0, root_hex=proof.expected_root_hex,
            leaf=bytes(proof.leaf_preimage_bytes), siblings=[],
        )
        memo = memo_text.encode()
        blockhash = bytes(range(32))
        message = build_message(pub, blockhash, memo)
        verify_message_shape(message, payer=pub, memo=memo)
        parsed = parse_message(message)
        assert parsed["accounts"][0] == pub
        assert parsed["instructions"][0]["data"] == b"\x02" + struct.pack("<I", 400000)
        assert parsed["instructions"][1]["accounts"] == [0]
        identity = load_signer(signer_path)
        signature = identity.sign(message)
        assert verify_signature(pub, signature, message) is True
        packet = transaction_bytes(message, signature)
        assert len(packet) == 1 + 64 + len(message)
        assert len(packet) <= 1232
        with pytest.raises(ValueError):
            parse_message(message + b"\x00")
    finally:
        ledger.close()


def test_base58_and_shortvec_boundaries():
    assert b58decode(b58encode(b"\x00\x00abc")) == b"\x00\x00abc"
    assert b58encode(bytes(32)) == "1" * 32
    with pytest.raises(ValueError):
        b58decode("0OIl")
    with pytest.raises(ValueError):
        b58encode(b"")
    for n in (0, 1, 127, 128, 255, 256, 1021, 16383, 65535):
        assert shortvec_decode(shortvec_encode(n)) == (n, len(shortvec_encode(n)))
    with pytest.raises(ValueError):
        shortvec_encode(65536)
    with pytest.raises(ValueError):
        shortvec_decode(b"\xff\xff\xff\x01")


def test_no_secret_material_in_public_artifacts(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, pub = write_throwaway_signer(tmp_path)
    seed_hex = Path(signer_path).read_bytes().hex()
    try:
        receipt = asyncio.run(append_teleport(ledger))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        memo_text = encode_attestation(
            tree_size=1, leaf_index=0, root_hex=proof.expected_root_hex,
            leaf=bytes(proof.leaf_preimage_bytes), siblings=[],
        )
        assert seed_hex not in memo_text
        assert seed_hex not in json.dumps(proof_to_jsonable(proof))
        db_bytes = (tmp_path / "ledger" / "quantum_teleportation.sqlite3").read_bytes()
        assert Path(signer_path).read_bytes() not in db_bytes
        assert seed_hex.encode() not in db_bytes
        fixture = RpcFixture()
        exporter = make_exporter(ledger, fixture, "/nonexistent/signer.key")
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.error_code == "signer_unreadable"
        assert seed_hex not in (result.error_detail or "")
        assert "/nonexistent" not in (result.error_detail or "")
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()
