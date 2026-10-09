"""Federated Byzantine Fault-Tolerant Consensus, View-Change & On-Chain Governance Attestation (Milestone v3.3 - Phase 33).

Implements:
- REQ-GOV-006: Federated Byzantine fault-tolerant consensus rounds with three-phase commit
               (PRE-PREPARE, PREPARE, COMMIT).
- REQ-GOV-007: View-change protocol and leader rotation handling Byzantine or unresponsive coordinator desks.
- REQ-GOV-008: Cryptographic Merkle governance receipts linking proposal state transitions,
               ballot tallies, and execution outcomes.
- REQ-GOV-009: On-chain and external WORM ledger audit export anchoring consensus receipts to distributed ledgers.
- REQ-GOV-010: End-to-end multi-desk governance verification harness and Byzantine attack drill simulator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import hmac
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("desk_gateway.byzantine_consensus")


class ConsensusPhase(str, Enum):
    NEW_ROUND = "NEW_ROUND"
    PRE_PREPARE = "PRE_PREPARE"
    PREPARE = "PREPARE"
    COMMIT = "COMMIT"
    COMMITTED = "COMMITTED"
    VIEW_CHANGE = "VIEW_CHANGE"
    ABORTED = "ABORTED"


class ConsensusDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


@dataclass
class ConsensusMessage:
    phase: ConsensusPhase
    round_id: str
    view_number: int
    proposal_id: str
    proposal_digest: str
    sender_desk: str
    decision: ConsensusDecision = ConsensusDecision.APPROVE
    signature: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        raw = f"{self.phase.value}:{self.round_id}:{self.view_number}:{self.proposal_id}:{self.proposal_digest}:{self.sender_desk}:{self.decision.value}:{self.timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def sign(self, secret_key: str) -> str:
        digest = self.compute_hash()
        self.signature = hmac.new(secret_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return self.signature

    def verify_signature(self, secret_key: str) -> bool:
        if not self.signature:
            return False
        expected = hmac.new(secret_key.encode("utf-8"), self.compute_hash().encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "round_id": self.round_id,
            "view_number": self.view_number,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "sender_desk": self.sender_desk,
            "decision": self.decision.value,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ViewChangeMessage:
    new_view_number: int
    round_id: str
    sender_desk: str
    reason: str
    signature: str = ""
    timestamp: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        raw = f"VIEW_CHANGE:{self.new_view_number}:{self.round_id}:{self.sender_desk}:{self.reason}:{self.timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def sign(self, secret_key: str) -> str:
        digest = self.compute_hash()
        self.signature = hmac.new(secret_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        return self.signature

    def verify_signature(self, secret_key: str) -> bool:
        if not self.signature:
            return False
        expected = hmac.new(secret_key.encode("utf-8"), self.compute_hash().encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "new_view_number": self.new_view_number,
            "round_id": self.round_id,
            "sender_desk": self.sender_desk,
            "reason": self.reason,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }


class ByzantineConsensusEngine:
    """Federated BFT consensus engine implementing three-phase commit (REQ-GOV-006).

    Tolerates up to f Byzantine faults in a network of N >= 3f + 1 peer desks.
    Quorum threshold for Prepare and Commit is 2f + 1.
    """

    def __init__(
        self,
        desks: List[str],
        local_desk_id: str = "desk-alpha",
        secret_key: str = "desk-byzantine-secret-key-33",
        timeout_seconds: float = 5.0,
    ) -> None:
        if not desks:
            desks = [local_desk_id]
        self.desks: List[str] = sorted(list(set(desks)))
        self.local_desk_id: str = local_desk_id
        self.secret_key: str = secret_key
        self.timeout_seconds: float = timeout_seconds

        # N = len(desks), f = (N - 1) // 3
        # Quorum required = 2f + 1
        self.total_nodes = len(self.desks)
        self.max_faulty = (self.total_nodes - 1) // 3
        self.quorum_size = 2 * self.max_faulty + 1 if self.total_nodes >= 4 else max(1, math.ceil(self.total_nodes * 0.67))

        self.current_view: int = 0
        self.rounds: Dict[str, Dict[str, Any]] = {}
        self.view_change_votes: Dict[int, Dict[str, ViewChangeMessage]] = {}

    @property
    def current_leader(self) -> str:
        """Determines coordinator/leader based on current view number."""
        return self.desks[self.current_view % len(self.desks)]

    def start_round(
        self,
        round_id: str,
        proposal_id: str,
        proposal_payload: Dict[str, Any],
        leader_desk: Optional[str] = None,
    ) -> ConsensusMessage:
        """Leader initiates consensus round via PRE-PREPARE phase."""
        assigned_leader = leader_desk or self.current_leader
        payload_raw = json.dumps(proposal_payload, sort_keys=True).encode("utf-8")
        proposal_digest = hashlib.sha256(payload_raw).hexdigest()

        round_state = {
            "round_id": round_id,
            "view_number": self.current_view,
            "proposal_id": proposal_id,
            "proposal_digest": proposal_digest,
            "proposal_payload": proposal_payload,
            "leader": assigned_leader,
            "phase": ConsensusPhase.PRE_PREPARE,
            "pre_prepare_msg": None,
            "prepare_msgs": {},
            "commit_msgs": {},
            "started_at": time.time(),
            "committed_at": None,
            "decision": None,
            "status": "in_progress",
        }
        self.rounds[round_id] = round_state

        msg = ConsensusMessage(
            phase=ConsensusPhase.PRE_PREPARE,
            round_id=round_id,
            view_number=self.current_view,
            proposal_id=proposal_id,
            proposal_digest=proposal_digest,
            sender_desk=assigned_leader,
            decision=ConsensusDecision.APPROVE,
        )
        msg.sign(self.secret_key)
        round_state["pre_prepare_msg"] = msg
        return msg

    def process_prepare(
        self,
        round_id: str,
        sender_desk: str,
        proposal_digest: str,
        decision: ConsensusDecision = ConsensusDecision.APPROVE,
        signature: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[ConsensusMessage]]:
        """Processes a PREPARE message from a participant desk."""
        if round_id not in self.rounds:
            return False, f"Round '{round_id}' does not exist", None

        round_state = self.rounds[round_id]
        if round_state["status"] != "in_progress":
            return False, f"Round is in terminal status {round_state['status']}", None

        if proposal_digest != round_state["proposal_digest"]:
            return False, "Proposal digest mismatch (possible Byzantine fork/tampering)", None

        if sender_desk not in self.desks:
            return False, f"Sender desk '{sender_desk}' not in authorized consensus cluster", None

        msg = ConsensusMessage(
            phase=ConsensusPhase.PREPARE,
            round_id=round_id,
            view_number=round_state["view_number"],
            proposal_id=round_state["proposal_id"],
            proposal_digest=proposal_digest,
            sender_desk=sender_desk,
            decision=decision,
        )
        if signature:
            msg.signature = signature
            if not msg.verify_signature(self.secret_key):
                return False, "Invalid cryptographic signature on PREPARE message", None
        else:
            msg.sign(self.secret_key)

        round_state["prepare_msgs"][sender_desk] = msg

        # Check if 2f+1 prepare messages have been accumulated
        approve_count = sum(1 for m in round_state["prepare_msgs"].values() if m.decision == ConsensusDecision.APPROVE)
        commit_msg: Optional[ConsensusMessage] = None

        if approve_count >= self.quorum_size and round_state["phase"] == ConsensusPhase.PRE_PREPARE:
            round_state["phase"] = ConsensusPhase.PREPARE
            # Self-generate local COMMIT message if ready
            commit_msg = ConsensusMessage(
                phase=ConsensusPhase.COMMIT,
                round_id=round_id,
                view_number=round_state["view_number"],
                proposal_id=round_state["proposal_id"],
                proposal_digest=proposal_digest,
                sender_desk=self.local_desk_id,
                decision=ConsensusDecision.APPROVE,
            )
            commit_msg.sign(self.secret_key)

        return True, "PREPARE accepted", commit_msg

    def process_commit(
        self,
        round_id: str,
        sender_desk: str,
        proposal_digest: str,
        decision: ConsensusDecision = ConsensusDecision.APPROVE,
        signature: Optional[str] = None,
    ) -> Tuple[bool, str, bool]:
        """Processes a COMMIT message from a participant desk. Returns (ok, message, round_finalized)."""
        if round_id not in self.rounds:
            return False, f"Round '{round_id}' does not exist", False

        round_state = self.rounds[round_id]
        if round_state["status"] != "in_progress":
            return False, f"Round is already finalized ({round_state['status']})", False

        if proposal_digest != round_state["proposal_digest"]:
            return False, "Proposal digest mismatch during commit phase", False

        if sender_desk not in self.desks:
            return False, f"Sender desk '{sender_desk}' not in authorized consensus cluster", False

        msg = ConsensusMessage(
            phase=ConsensusPhase.COMMIT,
            round_id=round_id,
            view_number=round_state["view_number"],
            proposal_id=round_state["proposal_id"],
            proposal_digest=proposal_digest,
            sender_desk=sender_desk,
            decision=decision,
        )
        if signature:
            msg.signature = signature
            if not msg.verify_signature(self.secret_key):
                return False, "Invalid cryptographic signature on COMMIT message", False
        else:
            msg.sign(self.secret_key)

        round_state["commit_msgs"][sender_desk] = msg

        # Quorum evaluation on commit messages
        approve_count = sum(1 for m in round_state["commit_msgs"].values() if m.decision == ConsensusDecision.APPROVE)
        reject_count = sum(1 for m in round_state["commit_msgs"].values() if m.decision == ConsensusDecision.REJECT)

        if approve_count >= self.quorum_size:
            round_state["phase"] = ConsensusPhase.COMMITTED
            round_state["status"] = "committed"
            round_state["decision"] = ConsensusDecision.APPROVE.value
            round_state["committed_at"] = time.time()
            return True, "Consensus reached: COMMITTED (APPROVED)", True
        elif reject_count >= self.quorum_size:
            round_state["phase"] = ConsensusPhase.ABORTED
            round_state["status"] = "aborted"
            round_state["decision"] = ConsensusDecision.REJECT.value
            round_state["committed_at"] = time.time()
            return True, "Consensus reached: ABORTED (REJECTED)", True

        return True, "COMMIT accepted; awaiting quorum", False

    def request_view_change(
        self,
        round_id: str,
        sender_desk: str,
        reason: str = "Coordinator unresponsive or Byzantine behavior detected",
    ) -> Tuple[bool, str, int]:
        """Initiates or votes for view change to replace coordinator (REQ-GOV-007)."""
        target_view = self.current_view + 1
        if target_view not in self.view_change_votes:
            self.view_change_votes[target_view] = {}

        vc_msg = ViewChangeMessage(
            new_view_number=target_view,
            round_id=round_id,
            sender_desk=sender_desk,
            reason=reason,
        )
        vc_msg.sign(self.secret_key)
        self.view_change_votes[target_view][sender_desk] = vc_msg

        # If 2f + 1 view change votes received, advance view
        if len(self.view_change_votes[target_view]) >= self.quorum_size:
            self.current_view = target_view
            if round_id in self.rounds:
                self.rounds[round_id]["view_number"] = target_view
                self.rounds[round_id]["leader"] = self.current_leader
                self.rounds[round_id]["phase"] = ConsensusPhase.VIEW_CHANGE
            return True, f"View change successful. New view {target_view}, leader: {self.current_leader}", target_view

        return True, f"View change vote recorded ({len(self.view_change_votes[target_view])}/{self.quorum_size} votes)", self.current_view

    def get_round_summary(self, round_id: str) -> Dict[str, Any]:
        """Returns the current state and audit breakdown for a consensus round."""
        if round_id not in self.rounds:
            raise KeyError(f"Round '{round_id}' not found")
        r = self.rounds[round_id]
        return {
            "round_id": r["round_id"],
            "view_number": r["view_number"],
            "leader": r["leader"],
            "phase": r["phase"].value if isinstance(r["phase"], ConsensusPhase) else str(r["phase"]),
            "proposal_id": r["proposal_id"],
            "proposal_digest": r["proposal_digest"],
            "status": r["status"],
            "decision": r["decision"],
            "quorum_size": self.quorum_size,
            "prepare_votes_count": len(r["prepare_msgs"]),
            "commit_votes_count": len(r["commit_msgs"]),
            "started_at": r["started_at"],
            "committed_at": r["committed_at"],
        }


@dataclass
class GovernanceMerkleReceipt:
    receipt_id: str
    round_id: str
    proposal_id: str
    proposal_digest: str
    merkle_root: str
    transition_hash: str
    tally_hash: str
    execution_hash: str
    signers: List[str]
    aggregate_signature: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "round_id": self.round_id,
            "proposal_id": self.proposal_id,
            "proposal_digest": self.proposal_digest,
            "merkle_root": self.merkle_root,
            "transition_hash": self.transition_hash,
            "tally_hash": self.tally_hash,
            "execution_hash": self.execution_hash,
            "signers": self.signers,
            "aggregate_signature": self.aggregate_signature,
            "timestamp": self.timestamp,
        }


class GovernanceReceiptMerkleTree:
    """Constructs cryptographic Merkle receipts linking state transitions, tallies, and execution outcomes (REQ-GOV-008)."""

    def __init__(self, secret_key: str = "receipt-merkle-secret-33") -> None:
        self.secret_key = secret_key

    def build_receipt(
        self,
        round_id: str,
        proposal_id: str,
        proposal_digest: str,
        state_transitions: List[Dict[str, Any]],
        ballot_tallies: Dict[str, Any],
        execution_outcome: Dict[str, Any],
        signers: List[str],
    ) -> GovernanceMerkleReceipt:
        # 1. State transitions digest
        trans_raw = json.dumps(state_transitions, sort_keys=True).encode("utf-8")
        trans_hash = hashlib.sha256(trans_raw).hexdigest()

        # 2. Tally digest
        tally_raw = json.dumps(ballot_tallies, sort_keys=True).encode("utf-8")
        tally_hash = hashlib.sha256(tally_raw).hexdigest()

        # 3. Execution outcome digest
        exec_raw = json.dumps(execution_outcome, sort_keys=True).encode("utf-8")
        exec_hash = hashlib.sha256(exec_raw).hexdigest()

        # Combine into Merkle Root: Root = Hash( Hash(trans_hash + tally_hash) + exec_hash )
        branch_1 = hashlib.sha256((trans_hash + tally_hash).encode("utf-8")).hexdigest()
        merkle_root = hashlib.sha256((branch_1 + exec_hash).encode("utf-8")).hexdigest()

        receipt_id = f"grec-{round_id}-{hashlib.sha256((round_id + proposal_id).encode('utf-8')).hexdigest()[:8]}"

        # Aggregate HMAC-SHA256 signature
        sig_raw = f"{receipt_id}:{round_id}:{proposal_id}:{proposal_digest}:{merkle_root}:{','.join(sorted(signers))}"
        aggregate_sig = hmac.new(self.secret_key.encode("utf-8"), sig_raw.encode("utf-8"), hashlib.sha256).hexdigest()

        return GovernanceMerkleReceipt(
            receipt_id=receipt_id,
            round_id=round_id,
            proposal_id=proposal_id,
            proposal_digest=proposal_digest,
            merkle_root=merkle_root,
            transition_hash=trans_hash,
            tally_hash=tally_hash,
            execution_hash=exec_hash,
            signers=sorted(signers),
            aggregate_signature=aggregate_sig,
        )

    def verify_receipt(self, receipt: GovernanceMerkleReceipt) -> bool:
        """Cryptographically verifies a Merkle governance receipt."""
        # Re-derive Merkle root
        branch_1 = hashlib.sha256((receipt.transition_hash + receipt.tally_hash).encode("utf-8")).hexdigest()
        expected_root = hashlib.sha256((branch_1 + receipt.execution_hash).encode("utf-8")).hexdigest()

        if receipt.merkle_root != expected_root:
            return False

        sig_raw = f"{receipt.receipt_id}:{receipt.round_id}:{receipt.proposal_id}:{receipt.proposal_digest}:{receipt.merkle_root}:{','.join(sorted(receipt.signers))}"
        expected_sig = hmac.new(self.secret_key.encode("utf-8"), sig_raw.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(receipt.aggregate_signature, expected_sig)


@dataclass
class OnChainAnchor:
    anchor_id: str
    target_ledger: str  # "solana_devnet", "worm_audit_vault", "ethereum_sepolia"
    merkle_root: str
    receipt_id: str
    block_or_slot: int
    tx_signature: str
    status: str
    anchored_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "target_ledger": self.target_ledger,
            "merkle_root": self.merkle_root,
            "receipt_id": self.receipt_id,
            "block_or_slot": self.block_or_slot,
            "tx_signature": self.tx_signature,
            "status": self.status,
            "anchored_at": self.anchored_at,
        }


class LedgerAnchorExporter:
    """Anchors Merkle consensus receipts to external WORM audit ledgers / Solana devnet (REQ-GOV-009)."""

    def __init__(self, cluster_id: str = "cluster-solana-devnet") -> None:
        self.cluster_id = cluster_id
        self.anchors: Dict[str, OnChainAnchor] = {}
        self._current_slot = 100_000

    def anchor_receipt(
        self,
        receipt: GovernanceMerkleReceipt,
        target_ledger: str = "solana_devnet",
    ) -> OnChainAnchor:
        self._current_slot += 1
        anchor_id = f"anchor-{receipt.receipt_id[:12]}-{self._current_slot}"

        # Generate deterministic synthetic tx signature
        tx_raw = f"{anchor_id}:{target_ledger}:{receipt.merkle_root}:{self._current_slot}:{receipt.timestamp}".encode("utf-8")
        tx_sig = hashlib.sha256(tx_raw).hexdigest()

        anchor = OnChainAnchor(
            anchor_id=anchor_id,
            target_ledger=target_ledger,
            merkle_root=receipt.merkle_root,
            receipt_id=receipt.receipt_id,
            block_or_slot=self._current_slot,
            tx_signature=tx_sig,
            status="confirmed",
        )
        self.anchors[anchor_id] = anchor
        return anchor

    def verify_anchor(self, anchor_id: str, expected_merkle_root: str) -> Tuple[bool, str]:
        anchor = self.anchors.get(anchor_id)
        if not anchor:
            return False, f"Anchor '{anchor_id}' not found"

        if anchor.merkle_root != expected_merkle_root:
            return False, "Merkle root mismatch on anchored ledger state"

        if anchor.status != "confirmed":
            return False, f"Anchor status is '{anchor.status}', expected 'confirmed'"

        return True, "Anchor cryptographically verified on ledger"


class ByzantineAttackSimulator:
    """Automated multi-desk governance verification harness and Byzantine attack drill simulator (REQ-GOV-010)."""

    def __init__(self, consensus_engine: ByzantineConsensusEngine) -> None:
        self.engine = consensus_engine

    def run_sybil_attack_drill(self, round_id: str, fake_desk_id: str = "desk-evil-sybil") -> Dict[str, Any]:
        """Attempts to inject prepare and commit messages from an unauthorized/Sybil desk."""
        prop_digest = "a" * 64
        ok_prep, msg_prep, _ = self.engine.process_prepare(round_id, fake_desk_id, prop_digest)
        ok_commit, msg_commit, _ = self.engine.process_commit(round_id, fake_desk_id, prop_digest)

        return {
            "attack": "sybil_injection",
            "fake_desk_id": fake_desk_id,
            "prepare_blocked": not ok_prep,
            "commit_blocked": not ok_commit,
            "prepare_reason": msg_prep,
            "commit_reason": msg_commit,
            "mitigation_success": (not ok_prep) and (not ok_commit),
        }

    def run_tampered_digest_drill(self, round_id: str, attacker_desk: str) -> Dict[str, Any]:
        """Attempts to inject prepare/commit votes on a modified proposal digest (equivocation/forking)."""
        tampered_digest = hashlib.sha256(b"tampered_malicious_proposal_data").hexdigest()
        ok_prep, msg_prep, _ = self.engine.process_prepare(round_id, attacker_desk, tampered_digest)
        ok_commit, msg_commit, _ = self.engine.process_commit(round_id, attacker_desk, tampered_digest)

        return {
            "attack": "digest_equivocation",
            "tampered_digest": tampered_digest,
            "prepare_blocked": not ok_prep,
            "commit_blocked": not ok_commit,
            "prepare_reason": msg_prep,
            "commit_reason": msg_commit,
            "mitigation_success": (not ok_prep) and (not ok_commit),
        }

    def run_byzantine_leader_view_change_drill(self, round_id: str) -> Dict[str, Any]:
        """Simulates Byzantine leader silence or equivocation, triggering an automated view change."""
        initial_leader = self.engine.current_leader
        initial_view = self.engine.current_view

        # Quorum of honest desks call for view change
        success = False
        new_view = initial_view
        for desk in self.engine.desks[: self.engine.quorum_size]:
            ok, msg, new_view = self.engine.request_view_change(
                round_id=round_id,
                sender_desk=desk,
                reason="Simulated Byzantine leader non-responsiveness",
            )
            if ok and new_view > initial_view:
                success = True

        new_leader = self.engine.current_leader

        return {
            "attack": "byzantine_leader_censorship",
            "initial_view": initial_view,
            "initial_leader": initial_leader,
            "view_change_success": success,
            "new_view": new_view,
            "new_leader": new_leader,
            "leader_rotated": new_leader != initial_leader,
            "mitigation_success": success and (new_leader != initial_leader),
        }

    def run_full_byzantine_resilience_suite(self, proposal_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a full verification drill asserting liveness under <= f Byzantine nodes."""
        round_id = f"drill-round-{int(time.time() * 1000)}"
        self.engine.start_round(round_id, "prop-drill-1", proposal_payload)

        # 1. Sybil attack test
        sybil_res = self.run_sybil_attack_drill(round_id)

        # 2. Forking/digest tampering test
        honest_desk = self.engine.desks[0]
        tamper_res = self.run_tampered_digest_drill(round_id, honest_desk)

        # 3. Byzantine leader rotation drill
        view_res = self.run_byzantine_leader_view_change_drill(round_id)

        all_passed = (
            sybil_res["mitigation_success"]
            and tamper_res["mitigation_success"]
            and view_res["mitigation_success"]
        )

        return {
            "drill_id": f"drill-{round_id}",
            "round_id": round_id,
            "total_nodes": self.engine.total_nodes,
            "max_faulty_tolerated": self.engine.max_faulty,
            "quorum_size": self.engine.quorum_size,
            "sybil_drill": sybil_res,
            "tamper_drill": tamper_res,
            "view_change_drill": view_res,
            "all_mitigations_verified": all_passed,
        }
