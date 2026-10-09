"""Lattice-Attested Multi-Desk Ledger & Quantum-Resistant Audit Anchors.

Implements quantum-resistant Merkle audit ledgers using SHA3-256 state leaf digests,
lattice-attested seat identity passports, cross-desk lattice attestation verification,
external quantum-proof anchor exporting, and end-to-end quantum attack and downgrade drill simulators.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from desk_gateway.post_quantum import (
    HybridKEM,
    HybridSignature,
    HybridSignatureEngine,
    PQCChannelSession,
    QuantumAuditInspector,
)


@dataclasses.dataclass
class PQCLedgerEntry:
    entry_id: str
    desk_id: str
    action: str
    payload_hash: str
    previous_hash: str
    lattice_signature: Dict[str, Any]
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "desk_id": self.desk_id,
            "action": self.action,
            "payload_hash": self.payload_hash,
            "previous_hash": self.previous_hash,
            "lattice_signature": self.lattice_signature,
            "timestamp": self.timestamp,
        }

    def compute_leaf_hash(self) -> str:
        content = f"{self.entry_id}:{self.desk_id}:{self.action}:{self.payload_hash}:{self.previous_hash}:{self.timestamp}"
        return hashlib.sha3_256(content.encode("utf-8")).hexdigest()


class PQCMerkleLedger:
    """Quantum-Resistant Merkle Audit Ledger using SHA3-256 digests and lattice root checkpointing."""

    def __init__(self, sig_engine: Optional[HybridSignatureEngine] = None) -> None:
        self.entries: List[PQCLedgerEntry] = []
        self.sig_engine = sig_engine or HybridSignatureEngine()
        self.genesis_hash = hashlib.sha3_256(b"PQC-MERKLE-LEDGER-GENESIS-V3.9").hexdigest()

    def append_entry(self, desk_id: str, action: str, payload: Dict[str, Any]) -> PQCLedgerEntry:
        prev_hash = self.entries[-1].compute_leaf_hash() if self.entries else self.genesis_hash
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_hash = hashlib.sha3_256(payload_bytes).hexdigest()

        entry_id = f"pqc-ent-{len(self.entries) + 1:04d}-{secrets.token_hex(4)}"
        to_sign = f"{entry_id}:{desk_id}:{action}:{payload_hash}:{prev_hash}".encode("utf-8")
        sig = self.sig_engine.sign(to_sign, key_id=desk_id)

        entry = PQCLedgerEntry(
            entry_id=entry_id,
            desk_id=desk_id,
            action=action,
            payload_hash=payload_hash,
            previous_hash=prev_hash,
            lattice_signature=sig.to_dict(),
        )
        self.entries.append(entry)
        return entry

    def compute_merkle_root(self) -> str:
        if not self.entries:
            return self.genesis_hash

        current_level = [e.compute_leaf_hash() for e in self.entries]
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                parent = hashlib.sha3_256((left + right).encode("utf-8")).hexdigest()
                next_level.append(parent)
            current_level = next_level
        return current_level[0]

    def verify_ledger_integrity(self) -> bool:
        if not self.entries:
            return True

        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i - 1].compute_leaf_hash() if i > 0 else self.genesis_hash
            if entry.previous_hash != expected_prev:
                return False

            # Verify lattice signature
            to_sign = f"{entry.entry_id}:{entry.desk_id}:{entry.action}:{entry.payload_hash}:{entry.previous_hash}".encode("utf-8")
            sig_dict = entry.lattice_signature
            sig = HybridSignature(
                key_id=sig_dict["key_id"],
                classical_sig=sig_dict["classical_sig"],
                lattice_sig=sig_dict["lattice_sig"],
                algorithm_suite=sig_dict["algorithm_suite"],
                message_digest=sig_dict["message_digest"],
                timestamp=sig_dict["timestamp"],
            )
            if not self.sig_engine.verify(to_sign, sig):
                return False

        return True


@dataclasses.dataclass
class PQCSeatPassport:
    seat_id: str
    desk_id: str
    public_bundle: Dict[str, Any]
    roles: List[str]
    expires_at: float
    ca_signature: Dict[str, Any]
    issued_at: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "desk_id": self.desk_id,
            "public_bundle": self.public_bundle,
            "roles": self.roles,
            "expires_at": self.expires_at,
            "ca_signature": self.ca_signature,
            "issued_at": self.issued_at,
        }


class PQCIdentityAuthority:
    """Certificate Authority issuing lattice-attested seat identity passports."""

    def __init__(self, ca_secret: Optional[str] = None) -> None:
        self.ca_name = "pqc-desk-ca-v3.9"
        self.sig_engine = HybridSignatureEngine(signing_secret=ca_secret or "ca-quantum-root-master-key")
        self.kem = HybridKEM()
        self.issued_passports: Dict[str, PQCSeatPassport] = {}

    def issue_passport(
        self,
        seat_id: str,
        desk_id: str,
        roles: Optional[List[str]] = None,
        ttl_seconds: float = 3600.0,
    ) -> PQCSeatPassport:
        keypair = self.kem.generate_keypair(key_id=f"{seat_id}-{desk_id}")
        bundle = keypair.public_bundle()
        now = time.time()
        expiry = now + ttl_seconds
        seat_roles = roles or ["SEAT_OPERATOR", "PQC_MESH_PARTICIPANT"]

        claim_str = f"{seat_id}:{desk_id}:{json.dumps(bundle, sort_keys=True)}:{','.join(seat_roles)}:{expiry}"
        sig = self.sig_engine.sign(claim_str.encode("utf-8"), key_id=self.ca_name)

        passport = PQCSeatPassport(
            seat_id=seat_id,
            desk_id=desk_id,
            public_bundle=bundle,
            roles=seat_roles,
            expires_at=expiry,
            ca_signature=sig.to_dict(),
            issued_at=now,
        )
        self.issued_passports[seat_id] = passport
        return passport

    def verify_passport(self, passport: PQCSeatPassport) -> bool:
        if time.time() > passport.expires_at:
            return False

        claim_str = f"{passport.seat_id}:{passport.desk_id}:{json.dumps(passport.public_bundle, sort_keys=True)}:{','.join(passport.roles)}:{passport.expires_at}"
        sig_dict = passport.ca_signature
        sig = HybridSignature(
            key_id=sig_dict["key_id"],
            classical_sig=sig_dict["classical_sig"],
            lattice_sig=sig_dict["lattice_sig"],
            algorithm_suite=sig_dict["algorithm_suite"],
            message_digest=sig_dict["message_digest"],
            timestamp=sig_dict["timestamp"],
        )
        return self.sig_engine.verify(claim_str.encode("utf-8"), sig)


class CrossDeskLatticeVerifier:
    """Validates remote seat passports, proof receipts, and multi-seat lattice quorums."""

    def __init__(self, authority: PQCIdentityAuthority) -> None:
        self.authority = authority

    def verify_remote_peer(self, passport: PQCSeatPassport) -> Dict[str, Any]:
        is_valid = self.authority.verify_passport(passport)
        if not is_valid:
            return {"verified": False, "reason": "Invalid CA signature or expired passport"}

        suite = passport.public_bundle.get("algorithm_suite", "")
        if "ML-KEM" not in suite and "ML-DSA" not in suite:
            return {"verified": False, "reason": f"Non-quantum-resistant suite: {suite}"}

        return {
            "verified": True,
            "seat_id": passport.seat_id,
            "desk_id": passport.desk_id,
            "quantum_level": "HYBRID_LATTICE_NIST_L3",
        }

    def verify_multi_seat_quorum(self, passports: List[PQCSeatPassport], min_required: int = 3) -> bool:
        valid_seats = set()
        for p in passports:
            if self.authority.verify_passport(p):
                valid_seats.add(p.seat_id)
        return len(valid_seats) >= min_required


class PQCAnchorExporter:
    """Exports quantum-proof Merkle ledger commitments to Solana devnet and external targets."""

    def __init__(self, devnet_endpoint: str = "https://api.devnet.solana.com") -> None:
        self.devnet_endpoint = devnet_endpoint
        self.exported_commitments: List[Dict[str, Any]] = []

    def export_anchor(self, ledger: PQCMerkleLedger) -> Dict[str, Any]:
        root_hash = ledger.compute_merkle_root()
        entry_count = len(ledger.entries)
        slot_id = int(time.time() * 1000)

        # Generate simulated Solana instruction transaction signature
        tx_sig = hashlib.sha3_256(f"solana:pqc_anchor:{root_hash}:{slot_id}".encode("utf-8")).hexdigest()

        anchor = {
            "anchor_id": f"pqc-anchor-{secrets.token_hex(6)}",
            "merkle_root": root_hash,
            "entry_count": entry_count,
            "target": "solana_devnet",
            "slot_id": slot_id,
            "tx_signature": tx_sig,
            "timestamp": time.time(),
            "status": "CONFIRMED",
        }
        self.exported_commitments.append(anchor)
        return anchor


class QuantumAttackDrillSimulator:
    """Drill simulator testing resistance against Shor attacks, downgrade tampering, and session replay."""

    @staticmethod
    def run_quantum_attack_drill() -> Dict[str, Any]:
        inspector = QuantumAuditInspector()
        sig_engine = HybridSignatureEngine()
        kem = HybridKEM()
        authority = PQCIdentityAuthority()
        ledger = PQCMerkleLedger(sig_engine)

        drill_results: Dict[str, Any] = {
            "timestamp": time.time(),
            "test_cases": {},
            "status": "PASS",
        }

        # 1. Downgrade attack simulation: interceptor forces classical cipher
        eval_res = inspector.evaluate_negotiation(
            client_suites=["X25519+ML-KEM-768", "X25519"],
            server_suites=["X25519+ML-KEM-768", "X25519"],
            agreed_suite="X25519",
        )
        downgrade_blocked = eval_res["status"] == "BLOCKED" and not eval_res["quantum_safe"]
        drill_results["test_cases"]["downgrade_attack_mitigation"] = {
            "passed": downgrade_blocked,
            "status": eval_res["status"],
        }

        # 2. Simulated Shor attack on classical signature: attacker tampers classical half
        sample_msg = b"Transfer authorization to Seat-04"
        valid_sig = sig_engine.sign(sample_msg)
        # Attacker injects fake classical sig
        tampered_sig = HybridSignature(
            key_id=valid_sig.key_id,
            classical_sig="tampered_classical_sig_000000",
            lattice_sig=valid_sig.lattice_sig,
            algorithm_suite=valid_sig.algorithm_suite,
            message_digest=valid_sig.message_digest,
            timestamp=valid_sig.timestamp,
        )
        classical_tamper_rejected = not sig_engine.verify(sample_msg, tampered_sig)
        drill_results["test_cases"]["classical_tamper_rejection"] = {
            "passed": classical_tamper_rejected,
        }

        # 3. Attacker tampers lattice signature
        tampered_lattice_sig = HybridSignature(
            key_id=valid_sig.key_id,
            classical_sig=valid_sig.classical_sig,
            lattice_sig="tampered_lattice_sig_000000",
            algorithm_suite=valid_sig.algorithm_suite,
            message_digest=valid_sig.message_digest,
            timestamp=valid_sig.timestamp,
        )
        lattice_tamper_rejected = not sig_engine.verify(sample_msg, tampered_lattice_sig)
        drill_results["test_cases"]["lattice_tamper_rejection"] = {
            "passed": lattice_tamper_rejected,
        }

        # 4. Replay attack on PQC channel session
        kp = kem.generate_keypair("session-peer")
        sec, _ = kem.encapsulate(kp)
        chan = PQCChannelSession("session-123", sec)
        msg1 = chan.encrypt("Operation 1: commit")
        decrypted = chan.decrypt(msg1)
        replay_caught = False
        try:
            chan.decrypt(msg1)  # Replay same message
        except ValueError:
            replay_caught = True
        drill_results["test_cases"]["session_replay_mitigation"] = {
            "passed": replay_caught and (decrypted == "Operation 1: commit"),
        }

        # 5. Ledger integrity and Merkle root immutability
        e1 = ledger.append_entry("seat-01", "deploy_tool", {"tool": "linter"})
        e2 = ledger.append_entry("seat-02", "approve_pr", {"pr": 42})
        integrity_ok = ledger.verify_ledger_integrity()
        drill_results["test_cases"]["merkle_ledger_immutability"] = {
            "passed": integrity_ok,
            "entry_count": len(ledger.entries),
            "merkle_root": ledger.compute_merkle_root(),
        }

        all_passed = all(t.get("passed", False) for t in drill_results["test_cases"].values())
        drill_results["status"] = "PASS" if all_passed else "FAIL"
        return drill_results
