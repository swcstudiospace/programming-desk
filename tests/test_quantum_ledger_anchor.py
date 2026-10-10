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
    LedgerError,
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
        elif self.tx_mode == "slot_missing":
            slot = None
        return {
            "slot": slot,
            "meta": meta,
            "transaction": {
                "signatures": [sig],
                "message": {
                    "header": {
                        "numRequiredSignatures": 1,
                        "numReadonlySignedAccounts": 0,
                        "numReadonlyUnsignedAccounts": 2,
                    },
                    "accountKeys": keys,
                    "recentBlockhash": b58encode(self.blockhash_bytes),
                    "instructions": instructions,
                },
            },
            "blockTime": None,
        }


class RpcByteStream(httpx.AsyncByteStream):
    """Count stream pulls and closure without trusting Content-Length."""

    def __init__(self, chunks: list[bytes], *, stall: bool = False) -> None:
        self.chunks = chunks
        self.stall = stall
        self.pulled = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.pulled += 1
            yield chunk
        if self.stall:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


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
    conn.execute("UPDATE ledger_checkpoints SET root_hex = CASE SUBSTR(root_hex, 1, 1) WHEN '0' THEN '1' ELSE '0' END || SUBSTR(root_hex, 2) WHERE tree_size = 2;")
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

def test_confirmed_publishes_once_with_exact_message(tmp_path, monkeypatch):
    from desk_gateway.quantum_anchor import SignerIdentity

    signatures_created = []
    original_sign = SignerIdentity.sign

    def counted_sign(identity, message):
        signatures_created.append(message)
        return original_sign(identity, message)

    monkeypatch.setattr(SignerIdentity, "sign", counted_sign)
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
        assert len(signatures_created) == 1
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


# ---------------------------------------------------------------------------
# 69-04 gap closure: ledger integrity, proofs, writers, listing (AC-008)
# ---------------------------------------------------------------------------

def _teleport_summary(seq=7):
    return {
        "leaf_type": "teleport",
        "flags": 1,
        "seq": seq,
        "event_id_hex": "ab" * 16,
        "metadata_commit_hex": "cd" * 32,
        "teleport": dict(teleport_payload(), node_count=2),
        "drill": None,
    }


def test_column_event_type_tamper_fails_replay(tmp_path):
    src = tmp_path / "colsrc"
    ledger = QuantumTeleportationReceiptLedger(src)
    try:
        asyncio.run(append_teleport(ledger, "col-1"))
    finally:
        ledger.close()
    victim = _copy_db(tmp_path, src, "victim-column")
    conn = sqlite3.connect(victim / "quantum_teleportation.sqlite3")
    conn.execute("DROP TRIGGER ledger_no_update_events;")
    conn.execute("UPDATE ledger_events SET event_type = 'evil.rewrite' WHERE seq = 1;")
    conn.commit()
    conn.close()
    with pytest.raises(LedgerCorruptError):
        QuantumTeleportationReceiptLedger(victim)


def test_decoder_rejects_malformed_and_out_of_range():
    encoded = encode_execution_leaf(_teleport_summary())
    with pytest.raises(ValueError):
        decode_execution_leaf(encoded + b"\x00")  # overlong
    with pytest.raises(ValueError):
        decode_execution_leaf(encoded[:-1])  # short
    bad_version = bytearray(encoded)
    bad_version[0] = 2
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(bad_version))
    bad_flags = bytearray(encoded)
    bad_flags[2:4] = (3).to_bytes(2, "big")
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(bad_flags))
    no_nodes = bytearray(encoded)
    no_nodes[62] = 0
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(no_nodes))
    low_fidelity = bytearray(encoded)
    low_fidelity[63:71] = struct.pack(">d", 0.5)
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(low_fidelity))
    nan_fidelity = bytearray(encoded)
    nan_fidelity[63:71] = struct.pack(">d", float("nan"))
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(nan_fidelity))
    broken_xor = bytearray(encoded)
    broken_xor[60] ^= 0x01  # frame_x flip breaks correction_x == bsm_x XOR frame_x
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(broken_xor))
    # Drill leaf: exact 150 bytes and typed numeric success fields.
    drill_summary = {
        "leaf_type": "drill",
        "flags": 1 | 2 | 4 | 8 | 16 | 32 | 64,
        "seq": 3,
        "event_id_hex": "ab" * 16,
        "metadata_commit_hex": "cd" * 32,
        "teleport": dict(teleport_payload(), node_count=2),
        "drill": {
            "purif_baseline": 0.80,
            "purif_output": 0.92,
            "swap_fidelity": 0.96,
            "clean_sifted": 1000,
            "clean_test": 100,
            "clean_errors": 5,
            "clean_output": 256,
            "eve_test": 200,
            "eve_errors": 40,
            "eve_basis": 0,
            "key_commitment": hashlib.sha256(b"commit").digest(),
        },
    }
    drill_encoded = encode_execution_leaf(drill_summary)
    assert len(drill_encoded) == 150
    with pytest.raises(ValueError):
        decode_execution_leaf(drill_encoded[:-1])
    mistyped = bytearray(drill_encoded)
    mistyped[1] = 1  # teleport type byte on a 150-byte body
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(mistyped))
    bad_basis = bytearray(drill_encoded)
    bad_basis[71 + 24 + 14 + 8] = 9
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(bad_basis))
    no_output_bits = bytearray(drill_encoded)
    no_output_bits[71 + 24 + 12:71 + 24 + 14] = (0).to_bytes(2, "big")
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(no_output_bits))
    zero_commitment = bytearray(drill_encoded)
    zero_commitment[118:150] = bytes(32)
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(zero_commitment))
    low_swap = bytearray(drill_encoded)
    low_swap[71 + 16:71 + 24] = struct.pack(">d", 0.5)
    with pytest.raises(ValueError):
        decode_execution_leaf(bytes(low_swap))


def test_kernel_rounded_fidelity_accepted_raw_floor_rejected(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        rounded = asyncio.run(ledger.append_event(teleport_event("round", payload=teleport_payload(fidelity=1.0 + 5e-10))))
        proof = ledger.inclusion_proof(rounded.receipt_id, 1)
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
        assert decode_execution_leaf(bytes(proof.leaf_preimage_bytes))["teleport"]["fidelity"] > 1.0
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(teleport_event("low", payload=teleport_payload(fidelity=0.94))))
        with pytest.raises(ValueError):
            asyncio.run(ledger.append_event(teleport_event("high", payload=teleport_payload(fidelity=1.5))))
        assert ledger.tree_size == 1
    finally:
        ledger.close()


def test_proof_seq_and_tree_size_binding(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        first = asyncio.run(append_teleport(ledger, "bind-a"))
        second = asyncio.run(append_teleport(ledger, "bind-b"))
        proof = ledger.inclusion_proof(second.receipt_id, 2)
        assert proof.leaf_index == 1
        assert proof.metadata["seq"] == 2
        assert QuantumTeleportationReceiptLedger.verify_proof(proof) is True
        moved_index = InclusionProof(
            version=proof.version, leaf_index=0, tree_size=proof.tree_size,
            leaf_preimage_bytes=proof.leaf_preimage_bytes, siblings=proof.siblings,
            expected_root_hex=proof.expected_root_hex, metadata=dict(proof.metadata),
            eligible=proof.eligible, leaf_digest_hex=proof.leaf_digest_hex,
        )
        assert QuantumTeleportationReceiptLedger.verify_proof(moved_index) is False
        moved_seq = InclusionProof(
            version=proof.version, leaf_index=proof.leaf_index, tree_size=proof.tree_size,
            leaf_preimage_bytes=proof.leaf_preimage_bytes, siblings=proof.siblings,
            expected_root_hex=proof.expected_root_hex,
            metadata=dict(proof.metadata, seq=99),
            eligible=proof.eligible, leaf_digest_hex=proof.leaf_digest_hex,
        )
        assert QuantumTeleportationReceiptLedger.verify_proof(moved_seq) is False
        swapped_size = InclusionProof(
            version=proof.version, leaf_index=proof.leaf_index, tree_size=3,
            leaf_preimage_bytes=proof.leaf_preimage_bytes, siblings=proof.siblings,
            expected_root_hex=proof.expected_root_hex, metadata=dict(proof.metadata),
            eligible=proof.eligible, leaf_digest_hex=proof.leaf_digest_hex,
        )
        assert QuantumTeleportationReceiptLedger.verify_proof(swapped_size) is False
        assert ledger.inclusion_proof(first.receipt_id, 1).metadata["seq"] == 1
    finally:
        ledger.close()


def test_tampered_checkpoint_blocks_proof_issuance(tmp_path):
    src = tmp_path / "ckptsrc"
    ledger = QuantumTeleportationReceiptLedger(src)
    try:
        receipt = asyncio.run(append_teleport(ledger, "ckpt-1"))
        assert QuantumTeleportationReceiptLedger.verify_proof(ledger.inclusion_proof(receipt.receipt_id, 1)) is True
    finally:
        ledger.close()
    victim = _copy_db(tmp_path, src, "victim-ckpt-proof")
    conn = sqlite3.connect(victim / "quantum_teleportation.sqlite3")
    conn.execute("DROP TRIGGER ledger_no_update_checkpoints;")
    conn.execute("UPDATE ledger_checkpoints SET root_hex = CASE SUBSTR(root_hex, 1, 1) WHEN '0' THEN '1' ELSE '0' END || SUBSTR(root_hex, 2) WHERE tree_size = 1;")
    conn.commit()
    conn.close()
    with pytest.raises(LedgerCorruptError):
        QuantumTeleportationReceiptLedger(victim)


def test_returned_proof_is_deep_copied(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger, "copy-1"))
        first = ledger.inclusion_proof(receipt.receipt_id, 1)
        first.metadata["payload"]["fidelity"] = 0.0
        first.metadata["seq"] = 999
        assert QuantumTeleportationReceiptLedger.verify_proof(first) is False
        second = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert second.metadata["payload"]["fidelity"] == 0.97
        assert QuantumTeleportationReceiptLedger.verify_proof(second) is True
        projected = proof_to_jsonable(second)
        projected["metadata"]["payload"]["fidelity"] = 0.0
        third = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert QuantumTeleportationReceiptLedger.verify_proof(third) is True
    finally:
        ledger.close()


def test_two_ledger_objects_share_one_directory(tmp_path):
    shared = tmp_path / "shared"
    first_ledger = QuantumTeleportationReceiptLedger(shared)
    second_ledger = QuantumTeleportationReceiptLedger(shared)
    try:
        r1 = asyncio.run(first_ledger.append_event(teleport_event("shared-1")))
        assert r1.seq == 1
        r2 = asyncio.run(second_ledger.append_event(teleport_event("shared-2")))
        assert r2.seq == 2
        r3 = asyncio.run(first_ledger.append_event(teleport_event("shared-3")))
        assert r3.seq == 3
        assert len({r1.receipt_id, r2.receipt_id, r3.receipt_id}) == 3
    finally:
        first_ledger.close()
        second_ledger.close()
    reopened = QuantumTeleportationReceiptLedger(shared)
    try:
        assert reopened.tree_size == 3
        for receipt_id in (r1.receipt_id, r2.receipt_id, r3.receipt_id):
            assert QuantumTeleportationReceiptLedger.verify_proof(
                reopened.inclusion_proof(receipt_id, 3)) is True
    finally:
        reopened.close()


def test_threaded_same_file_appends_keep_unique_sequence(tmp_path):
    shared = tmp_path / "hammer"
    ledgers = [QuantumTeleportationReceiptLedger(shared) for _ in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(
                    lambda tag=tag, i=i: asyncio.run(
                        ledgers[tag % 2].append_event(teleport_event(f"hammer-{tag}-{i}"))),
                )
                for tag in range(4)
                for i in range(10)
            ]
            results = [f.result() for f in futures]
        assert sorted(r.seq for r in results) == list(range(1, 41))
        assert len({r.receipt_id for r in results}) == 40
    finally:
        for open_ledger in ledgers:
            open_ledger.close()


def test_list_receipts_bounded_first_sequence(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        for i in range(5):
            asyncio.run(ledger.append_event(teleport_event(f"list-{i}")))
        first_two = ledger.list_receipts(2)
        assert type(first_two) is tuple and len(first_two) == 2
        assert [r.seq for r in first_two] == [1, 2]
        for item in first_two:
            assert item.tree_size == item.seq
            assert item.prefix_root_hex == ledger.snapshot(item.seq).root_hex
        everything = ledger.list_receipts(1000)
        assert [r.seq for r in everything] == [1, 2, 3, 4, 5]
        for bad in (0, -1, 1001, "2", 2.0, None):
            with pytest.raises(ValueError):
                ledger.list_receipts(bad)
        with pytest.raises(AttributeError):
            first_two[0].seq = 99  # frozen receipt is immutable
    finally:
        ledger.close()


def test_open_failures_raise_ledger_error_not_corrupt(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"not a directory")
    with pytest.raises(LedgerError) as excinfo:
        QuantumTeleportationReceiptLedger(blocker)
    assert type(excinfo.value) is LedgerError


def test_anchor_claim_single_winner_per_receipt(tmp_path):
    ledger = make_ledger(tmp_path)
    try:
        receipt = asyncio.run(append_teleport(ledger, "claim-1"))
        proof = ledger.inclusion_proof(receipt.receipt_id, 1)
        assert ledger.read_anchor_claim(receipt.receipt_id) is None
        assert ledger.claim_anchor(
            receipt.receipt_id, tree_size=1, root_hex=proof.expected_root_hex,
            leaf_index=proof.leaf_index, payer_b58="Payer111", last_valid=100,
        ) is True
        assert ledger.claim_anchor(
            receipt.receipt_id, tree_size=1, root_hex=proof.expected_root_hex,
            leaf_index=proof.leaf_index, payer_b58="Payer111", last_valid=100,
        ) is False
        stored = ledger.read_anchor_claim(receipt.receipt_id)
        assert stored is not None and stored["tree_size"] == 1 and stored["payer_b58"] == "Payer111"
        assert stored == ledger.read_anchor_claim(receipt.receipt_id, 1)
        second_receipt = asyncio.run(append_teleport(ledger, "claim-2"))
        later_proof = ledger.inclusion_proof(receipt.receipt_id, 2)
        other = QuantumTeleportationReceiptLedger(ledger.data_dir)
        try:
            assert other.claim_anchor(
                receipt.receipt_id, tree_size=2, root_hex=later_proof.expected_root_hex,
                leaf_index=later_proof.leaf_index, payer_b58="OtherPayer", last_valid=200,
            ) is False
            assert other.read_anchor_claim(receipt.receipt_id) == stored
            assert other.claim_anchor(
                second_receipt.receipt_id, tree_size=2, root_hex=later_proof.expected_root_hex,
                leaf_index=1, payer_b58="OtherPayer", last_valid=200,
            ) is True
        finally:
            other.close()
        for bad_call in (
            lambda: ledger.claim_anchor("", tree_size=1, root_hex=proof.expected_root_hex,
                                        leaf_index=0, payer_b58="P", last_valid=None),
            lambda: ledger.claim_anchor(receipt.receipt_id, tree_size=0, root_hex=proof.expected_root_hex,
                                        leaf_index=0, payer_b58="P", last_valid=None),
            lambda: ledger.read_anchor_claim(""),
        ):
            with pytest.raises(ValueError):
                bad_call()
    finally:
        ledger.close()


# ---------------------------------------------------------------------------
# 69-04 gap closure: single-send publisher and aged readback (AC-009)
# ---------------------------------------------------------------------------

def _two_exporters(ledger, fixture, signer_path):
    first_client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    second_client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
    first = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", signer_path=signer_path,
        http_client=first_client, confirmation_timeout_s=5.0, poll_interval_s=0.01,
    )
    second = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", signer_path=signer_path,
        http_client=second_client, confirmation_timeout_s=5.0, poll_interval_s=0.01,
    )
    return first, second, (first_client, second_client)


def test_two_exporters_sharing_ledger_send_once(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    first, second, clients = _two_exporters(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        one = asyncio.run(first.export_commitment(receipt.receipt_id))
        assert one.ok
        two = asyncio.run(second.export_commitment(receipt.receipt_id))
        assert two.ok and two.signature == one.signature
        assert two.slot == TX_SLOT
        assert fixture.methods_called("sendTransaction") == 1
        raced = asyncio.run(append_teleport(ledger, "race-2"))

        async def race():
            return await asyncio.gather(
                first.export_commitment(raced.receipt_id),
                second.export_commitment(raced.receipt_id),
            )

        out_a, out_b = asyncio.run(race())
        assert out_a.ok and out_b.ok and out_a.signature == out_b.signature
        assert fixture.methods_called("sendTransaction") == 2
    finally:
        asyncio.run(first.aclose())
        asyncio.run(second.aclose())
        for client in clients:
            asyncio.run(client.aclose())
        ledger.close()


def test_prepared_lookup_indexed_and_failclosed(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert result.ok
        for i in range(3):
            decoy = asyncio.run(append_teleport(ledger, f"decoy-{i}"))
            assert asyncio.run(exporter.export_commitment(decoy.receipt_id)).ok
        assert fixture.methods_called("sendTransaction") == 4
        cold = make_exporter(ledger, fixture, signer_path)
        try:
            # Cold exporter finds the prepared signature through the indexed
            # ledger lookup with no memory state.
            assert cold.prepared_signature(receipt.receipt_id) == result.signature
            events = ledger.anchor_prepared_events(receipt.receipt_id)
            assert len(events) == 1
            assert events[0]["payload"]["signature"] == result.signature
        finally:
            asyncio.run(cold.aclose())
        # Damage the event store: prepared lookup must fail closed with
        # ledger_unavailable and must not sign or resend.
        raw = sqlite3.connect(str(ledger.db_path))
        raw.execute("DROP TABLE ledger_events;")
        raw.commit()
        raw.close()
        with pytest.raises(LedgerError):
            ledger.anchor_prepared_events(receipt.receipt_id)
        stranded = make_exporter(ledger, fixture, signer_path)
        try:
            out = asyncio.run(stranded.export_commitment(receipt.receipt_id))
            assert out.error_code == "ledger_unavailable" and out.http_status == 503
            assert fixture.methods_called("sendTransaction") == 4
        finally:
            asyncio.run(stranded.aclose())
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_aged_confirmation_recovers_through_historical_readback(tmp_path):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    fixture.status_queue = [None] * 100
    fixture.height = fixture.last_valid + 5  # recent window already past expiry
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        first = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert first.status == "unknown" and first.error_code == "expired"
        assert fixture.methods_called("sendTransaction") == 1
        late_client = httpx.AsyncClient(transport=httpx.MockTransport(fixture.handler))
        late = QuantumTeleportationAnchorExporter(
            ledger, rpc_url="https://devnet.example.invalid", signer_path=signer_path,
            http_client=late_client, confirmation_timeout_s=5.0, poll_interval_s=0.01,
        )
        try:
            second = asyncio.run(late.export_commitment(receipt.receipt_id))
            assert second.ok and second.signature == first.signature
            assert second.slot == TX_SLOT
            assert fixture.methods_called("sendTransaction") == 1
        finally:
            asyncio.run(late.aclose())
            asyncio.run(late_client.aclose())
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


def test_base58_long_memo_fixed_behavior_pinned():
    memo = bytes((i * 37 + 11) % 256 for i in range(1021))
    text = b58encode(memo)
    assert len(text) > 256  # a full inclusion-path memo exceeds the short cap
    assert b58decode(text, max_len=2048) == memo
    with pytest.raises(ValueError):
        b58decode(text)  # default short cap still rejects overlong input


def test_live_checkpoint_tamper_blocks_proof_issuance(tmp_path):
    live = tmp_path / "cklive"
    ledger = QuantumTeleportationReceiptLedger(live)
    try:
        receipt = asyncio.run(append_teleport(ledger, "cklive-1"))
        assert QuantumTeleportationReceiptLedger.verify_proof(ledger.inclusion_proof(receipt.receipt_id, 1)) is True
        raw = sqlite3.connect(str(ledger.db_path))
        raw.execute("DROP TRIGGER ledger_no_update_checkpoints;")
        raw.execute("UPDATE ledger_checkpoints SET root_hex = CASE SUBSTR(root_hex, 1, 1) WHEN '0' THEN '1' ELSE '0' END || SUBSTR(root_hex, 2) WHERE tree_size = 1;")
        raw.commit()
        raw.close()
        with pytest.raises(LedgerCorruptError):
            ledger.inclusion_proof(receipt.receipt_id, 1)
    finally:
        ledger.close()


@pytest.mark.parametrize(
    "method,path,replacement",
    [
        ("getSignatureStatuses", ("value", 0, "err"), "missing"),
        ("getSignatureStatuses", ("value", 0, "slot"), "missing"),
        *[("getSignatureStatuses", ("value", 0, field), value)
          for field in ("slot", "confirmations") for value in (-1, True, 1 << 64)],
        ("getSignatureStatuses", ("value", 0, "confirmationStatus"), "missing"),
        ("getSignatureStatuses", ("value", 0, "confirmationStatus"), "confirmed-ish"),
        ("getSignatureStatuses", ("value", 0, "confirmations"), "missing"),
        ("getTransaction", ("meta", "err"), "missing"),
        *[("getTransaction", ("slot",), value) for value in (-1, True, 1 << 64)],
        ("getTransaction", ("transaction", "message", "header"), "missing"),
        *[("getTransaction", ("transaction", "message", "header", field), value)
          for field, value in (("numRequiredSignatures", True), ("numRequiredSignatures", 2),
                               ("numReadonlySignedAccounts", 1), ("numReadonlyUnsignedAccounts", 1))],
        ("getTransaction", ("transaction", "message", "recentBlockhash"), "missing"),
        ("getTransaction", ("transaction", "message", "recentBlockhash"), "0"),
        ("getTransaction", ("transaction", "message", "recentBlockhash"), b58encode(b"\x09" * 32)),
        *[("getTransaction", ("transaction", "message", "instructions", 0, "programIdIndex"), value)
          for value in ("missing", -1, True, 3)],
        ("getTransaction", ("transaction", "message", "instructions", 1, "programIdIndex"), "missing"),
        ("getTransaction", ("transaction", "message", "instructions", 1, "programIdIndex"), False),
        ("getTransaction", ("transaction", "message", "instructions", 0, "accounts"), "missing"),
        ("getTransaction", ("transaction", "message", "instructions", 0, "accounts"), [0]),
        ("getTransaction", ("transaction", "message", "instructions", 1, "accounts"), []),
        ("getTransaction", ("transaction", "message", "instructions", 1, "accounts"), [False]),
        ("getTransaction", ("transaction", "message", "instructions", 0, "data"), "missing"),
        ("getTransaction", ("transaction", "message", "instructions", 0, "data"), b58encode(b"\x02" + struct.pack("<I", 1))),
        ("getTransaction", ("transaction", "message", "instructions", 0, "data"), b58encode(b"\x03" + struct.pack("<I", 400000))),
        ("getTransaction", ("transaction", "message", "instructions", 1, "data"), "missing"),
    ],
)
def test_malformed_success_fields_never_confirm(tmp_path, method, path, replacement):
    class CorruptFixture(RpcFixture):
        def _result(self, requested, params):
            result = super()._result(requested, params)
            if requested == method:
                target = result
                for key in path[:-1]:
                    target = target[key]
                if replacement == "missing":
                    del target[path[-1]]
                else:
                    target[path[-1]] = replacement
            return result

    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = CorruptFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        first = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        repeated = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not first.ok and not repeated.ok
        assert first.status != "confirmed" and repeated.status != "confirmed"
        assert first.slot is None and repeated.slot is None
        assert first.signature == repeated.signature == fixture.sent["signature"]
        assert fixture.methods_called("sendTransaction") == 1
        assert not ledger.events_by_type("anchor.confirmed")
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


@pytest.mark.parametrize("mode", ["program_name_bypass", "invalid_program_name_bypass", "extra_key", "extra_signature", "reordered"])
def test_json_readback_requires_exact_transaction_shape(tmp_path, mode):
    class WrongShapeFixture(RpcFixture):
        def _tx_result(self, sig):
            result = super()._tx_result(sig)
            txn = result["transaction"]
            message = txn["message"]
            if mode in ("program_name_bypass", "invalid_program_name_bypass"):
                message["instructions"] = [
                    {"program": COMPUTE_BUDGET_PROGRAM_ID, "accounts": [0], "data": "bad"},
                    {"program": MEMO_PROGRAM_ID, "accounts": [], "data": b58encode(self.sent["memo"])},
                ]
                if mode == "invalid_program_name_bypass":
                    for instruction in message["instructions"]:
                        instruction["programIdIndex"] = 99
            elif mode == "extra_key":
                message["accountKeys"].append(MEMO_PROGRAM_ID)
            elif mode == "extra_signature":
                txn["signatures"].append(sig)
            else:
                message["instructions"].reverse()
            return result

    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = WrongShapeFixture()
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not result.ok and result.status == "failed"
        assert fixture.methods_called("sendTransaction") == 1
        assert not ledger.events_by_type("anchor.confirmed")
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


@pytest.mark.parametrize("method", ["getGenesisHash", "sendTransaction", "getSignatureStatuses", "getTransaction"])
@pytest.mark.parametrize(
    "mode",
    ["missing_id", "bool_id", "wrong_id", "string_id", "wrong_version", "both", "neither", "null_error", "bool_error_code"],
)
def test_rpc_envelope_corruption_is_not_confirmation(tmp_path, method, mode):
    fixture = RpcFixture()

    def handler(request):
        response = fixture.handler(request)
        if json.loads(request.content)["method"] != method:
            return response
        body = response.json()
        if mode == "missing_id":
            del body["id"]
        elif mode == "bool_id":
            body["id"] = True
        elif mode == "wrong_id":
            body["id"] += 1
        elif mode == "string_id":
            body["id"] = str(body["id"])
        elif mode == "wrong_version":
            body["jsonrpc"] = "1.0"
        elif mode == "both":
            body["error"] = None
        elif mode == "neither":
            del body["result"]
        elif mode == "null_error":
            del body["result"]
            body["error"] = None
        else:
            del body["result"]
            body["error"] = {"code": True, "message": "invalid code"}
        return httpx.Response(200, json=body)

    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", signer_path=signer_path, http_client=client,
    )
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not result.ok and result.status != "confirmed"
        if method == "sendTransaction":
            assert result.status == "unknown" and result.error_code == "send_failed"
            fixture.fail["getSignatureStatuses"] = "malformed"
            repeated = asyncio.run(exporter.export_commitment(receipt.receipt_id))
            assert not repeated.ok
        assert fixture.methods_called("sendTransaction") == (0 if method == "getGenesisHash" else 1)
        assert not ledger.events_by_type("anchor.confirmed")
    finally:
        asyncio.run(client.aclose())
        ledger.close()


@pytest.mark.parametrize("field", ["last_valid", "fee", "balance"])
@pytest.mark.parametrize("value", [-1, True, 1 << 64])
def test_rpc_u64_prerequisites_are_bounded(tmp_path, field, value):
    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = RpcFixture()
    setattr(fixture, field, value)
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not result.ok and result.status == "failed"
        assert fixture.methods_called("sendTransaction") == 0
        assert exporter.prepared_signature(receipt.receipt_id) is None
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()


@pytest.mark.parametrize("compressed", [False, True])
def test_rpc_stream_cap_closes_before_remainder_and_json_parse(tmp_path, compressed, monkeypatch):
    import gzip

    prefix = b'{"jsonrpc":"2.0","id":1,"result":"' + b"x" * (64 * 1024)
    chunks = [gzip.compress(prefix), b"unconsumed"] if compressed else [prefix[:32768], prefix[32768:], b"unconsumed"]
    stream = RpcByteStream(chunks)
    headers = {"content-encoding": "gzip"} if compressed else {"content-length": "1"}
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers=headers, stream=stream))
    )
    ledger = make_ledger(tmp_path)
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", http_client=client,
    )

    def forbidden_parse(*args, **kwargs):
        raise AssertionError("overflow must be rejected before parsing JSON")

    monkeypatch.setattr("desk_gateway.quantum_anchor.json.loads", forbidden_parse)
    try:
        with pytest.raises(AnchorError) as excinfo:
            asyncio.run(exporter._rpc("getGenesisHash", []))
        assert excinfo.value.error_code == "rpc_shape_invalid"
        assert stream.pulled == (1 if compressed else 2)
        assert stream.closed
    finally:
        asyncio.run(client.aclose())
        ledger.close()


def test_rpc_stream_deadline_covers_stalled_body(tmp_path):
    stream = RpcByteStream([b'{"jsonrpc":'], stall=True)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    )
    ledger = make_ledger(tmp_path)
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", http_client=client, rpc_timeout_s=0.01,
    )
    try:
        with pytest.raises(AnchorError) as excinfo:
            asyncio.run(exporter._rpc("getGenesisHash", []))
        assert excinfo.value.error_code == "rpc_transport_failed"
        assert stream.pulled == 1 and stream.closed
    finally:
        asyncio.run(client.aclose())
        ledger.close()


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate"])
def test_rpc_stream_accepts_exact_budget_with_bounded_inflation(tmp_path, encoding):
    import gzip
    import zlib

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": DEVNET_GENESIS_HASH}).encode()
    body += b" " * (64 * 1024 - len(body))
    wire = gzip.compress(body) if encoding == "gzip" else zlib.compress(body) if encoding == "deflate" else body
    stream = RpcByteStream([wire[:17], wire[17:]])
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"content-encoding": encoding}, stream=stream)
    ))
    ledger = make_ledger(tmp_path)
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", http_client=client,
    )
    try:
        assert asyncio.run(exporter._rpc("getGenesisHash", [])) == DEVNET_GENESIS_HASH
        assert stream.pulled == 2 and stream.closed
    finally:
        asyncio.run(client.aclose())
        ledger.close()


def test_oversized_send_reply_retains_unknown_single_send(tmp_path):
    fixture = RpcFixture()
    stream = RpcByteStream([b"x" * (64 * 1024), b"x", b"unconsumed"])

    def handler(request):
        response = fixture.handler(request)
        if json.loads(request.content)["method"] == "sendTransaction":
            return httpx.Response(200, stream=stream)
        return response

    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    exporter = QuantumTeleportationAnchorExporter(
        ledger, rpc_url="https://devnet.example.invalid", signer_path=signer_path, http_client=client,
    )
    try:
        receipt = asyncio.run(append_teleport(ledger))
        result = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not result.ok and result.status == "unknown" and result.error_code == "send_failed"
        assert result.signature == fixture.sent["signature"]
        assert stream.pulled == 2 and stream.closed
        # A later exact observation can recover the same submitted signature,
        # but may never sign or send again because of the oversized reply.
        recovered = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert recovered.ok and recovered.signature == result.signature
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(client.aclose())
        ledger.close()


def test_malformed_aged_status_cannot_fall_through_to_confirmation(tmp_path):
    class HistoricalMalformedFixture(RpcFixture):
        def _result(self, method, params):
            if method == "getSignatureStatuses" and len(params) == 2:
                entry = dict(self.status_default)
                del entry["err"]
                return {"context": {"slot": TX_SLOT}, "value": [entry]}
            return super()._result(method, params)

    ledger = make_ledger(tmp_path)
    signer_path, _ = write_throwaway_signer(tmp_path)
    fixture = HistoricalMalformedFixture()
    fixture.status_queue = [None] * 100
    fixture.height = fixture.last_valid + 1
    exporter = make_exporter(ledger, fixture, signer_path)
    try:
        receipt = asyncio.run(append_teleport(ledger))
        first = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not first.ok and first.error_code == "expired"
        repeated = asyncio.run(exporter.export_commitment(receipt.receipt_id))
        assert not repeated.ok and repeated.status != "confirmed"
        assert repeated.error_code == "status_lookup_failed"
        assert fixture.methods_called("getTransaction") == 0
        assert fixture.methods_called("sendTransaction") == 1
    finally:
        asyncio.run(exporter.aclose())
        ledger.close()
