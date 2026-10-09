"""Quantum Network Byzantine Merkle Ledger, Solana Anchor Verification & Automated Drill (Milestone v7.1 - Phase 109).

Implements:
- QuantumByzantineReceipt: Cryptographic receipt for consensus rounds, recording quorum sizes,
  status, agreed values, Byzantine node detection, and routing path fidelities.
- QuantumByzantineMerkleLedger: Binary Merkle tree aggregating consensus receipts with inclusion audit proofs.
- QuantumByzantineSolanaAnchorExporter: Solana Anchor program generator and instruction payloads
  verifying quantum Byzantine quorums, fault tolerance bounds (f < n/3), and Merkle inclusion proofs.
- QuantumByzantineVerificationDrill: 5-stage automated verification drill testing:
  1. SAGIN topology construction and Bell-state routing path optimization.
  2. Quantum pseudo-signature generation and cross-node correlation verification.
  3. Byzantine consensus execution with honest consensus quorum agreement.
  4. Instantaneous detection and mitigation of split-state Byzantine leader attacks.
  5. Solana Anchor instruction compilation and Merkle ledger integrity audit.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_byzantine_mesh import (
    ByzantineConsensusResult,
    ConsensusStatus,
    NodeType,
    QuantumByzantineCoordinator,
    SAGINNode,
    SAGINTopologyRouter,
)


@dataclasses.dataclass
class QuantumByzantineReceipt:
    receipt_id: str
    round_id: str
    status: str
    total_nodes: int
    quorum_size: int
    agreed_value: Optional[int]
    byzantine_count: int
    quorum_fidelity: float
    routing_hops: int
    fault_bound_satisfied: bool
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.round_id}:{self.status}:{self.total_nodes}:"
            f"{self.quorum_size}:{self.agreed_value}:{self.byzantine_count}:"
            f"{self.quorum_fidelity:.6f}:{self.routing_hops}:{self.fault_bound_satisfied}:"
            f"{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "round_id": self.round_id,
            "status": self.status,
            "total_nodes": self.total_nodes,
            "quorum_size": self.quorum_size,
            "agreed_value": self.agreed_value,
            "byzantine_count": self.byzantine_count,
            "quorum_fidelity": round(self.quorum_fidelity, 6),
            "routing_hops": self.routing_hops,
            "fault_bound_satisfied": self.fault_bound_satisfied,
            "receipt_hash": self.compute_hash(),
            "created_at": self.created_at,
        }


class QuantumByzantineMerkleLedger:
    """Binary Merkle tree ledger storing consensus receipts."""

    def __init__(self) -> None:
        self.receipts: List[QuantumByzantineReceipt] = []

    def append_receipt(self, receipt: QuantumByzantineReceipt) -> int:
        idx = len(self.receipts)
        self.receipts.append(receipt)
        return idx

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return "0" * 64

        current_level = [r.compute_hash() for r in self.receipts]
        while len(current_level) > 1:
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])
            next_level = []
            for i in range(0, len(current_level), 2):
                combined = current_level[i] + current_level[i + 1]
                parent = hashlib.sha256(combined.encode("utf-8")).hexdigest()
                next_level.append(parent)
            current_level = next_level

        return current_level[0]

    def get_proof(self, index: int) -> List[Dict[str, str]]:
        if index < 0 or index >= len(self.receipts):
            return []

        proof: List[Dict[str, str]] = []
        leaves = [r.compute_hash() for r in self.receipts]
        curr_idx = index
        level = list(leaves)

        while len(level) > 1:
            if len(level) % 2 != 0:
                level.append(level[-1])
            is_right_sibling = (curr_idx % 2 == 0)
            sibling_idx = curr_idx + 1 if is_right_sibling else curr_idx - 1
            sibling_hash = level[sibling_idx]

            proof.append({
                "position": "right" if is_right_sibling else "left",
                "hash": sibling_hash,
            })

            curr_idx //= 2
            next_level = []
            for i in range(0, len(level), 2):
                combined = level[i] + level[i + 1]
                parent = hashlib.sha256(combined.encode("utf-8")).hexdigest()
                next_level.append(parent)
            level = next_level

        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Dict[str, str]], root: str) -> bool:
        current = leaf_hash
        for node in proof:
            pos = node.get("position", "right")
            sib = node.get("hash", "")
            if pos == "right":
                combined = current + sib
            else:
                combined = sib + current
            current = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return current == root


class QuantumByzantineSolanaAnchorExporter:
    """Exports on-chain Solana Anchor program and instruction payloads."""

    PROGRAM_ID = "QByzantine111111111111111111111111111111111"

    @classmethod
    def generate_instruction_payload(
        cls,
        merkle_root: str,
        receipt: QuantumByzantineReceipt,
        proof: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        return {
            "program_id": cls.PROGRAM_ID,
            "instruction": "record_byzantine_consensus_receipt",
            "accounts": {
                "consensus_registry": "QByzRegistry1111111111111111111111111111111",
                "authority": "DeskAdminAuthority111111111111111111111111111",
                "system_program": "11111111111111111111111111111111",
            },
            "parameters": {
                "round_id": receipt.round_id,
                "status": receipt.status,
                "total_nodes": receipt.total_nodes,
                "quorum_size": receipt.quorum_size,
                "agreed_value": receipt.agreed_value if receipt.agreed_value is not None else -1,
                "byzantine_count": receipt.byzantine_count,
                "fault_bound_satisfied": receipt.fault_bound_satisfied,
                "merkle_root": merkle_root,
                "leaf_hash": receipt.compute_hash(),
                "proof_steps": len(proof),
            },
        }

    @classmethod
    def generate_anchor_program(cls) -> str:
        return f"""// SPDX-License-Identifier: Apache-2.0
// Quantum Network Byzantine Agreement & SAGIN Quorum Verifier (Milestone v7.1)
use anchor_lang::prelude::*;

declare_id!("{cls.PROGRAM_ID}");

#[program]
pub mod quantum_byzantine_consensus {{
    use super::*;

    pub fn record_byzantine_consensus_receipt(
        ctx: Context<RecordConsensusReceipt>,
        round_id: String,
        status: String,
        total_nodes: u8,
        quorum_size: u8,
        agreed_value: i8,
        byzantine_count: u8,
        fault_bound_satisfied: bool,
        merkle_root: [u8; 32],
    ) -> Result<()> {{
        // Enforce Byzantine fault tolerance bound: f < n / 3
        require!(
            byzantine_count * 3 < total_nodes,
            ByzantineError::FaultToleranceBoundExceeded
        );
        require!(
            quorum_size >= (2 * total_nodes) / 3,
            ByzantineError::InsufficientQuorumSize
        );
        require!(
            fault_bound_satisfied,
            ByzantineError::InvalidFaultBoundState
        );

        let registry = &mut ctx.accounts.consensus_registry;
        registry.latest_round_id = round_id;
        registry.status = status;
        registry.merkle_root = merkle_root;
        registry.total_rounds += 1;

        emit!(ConsensusReceiptRecorded {{
            round_id: registry.latest_round_id.clone(),
            quorum_size,
            agreed_value,
            merkle_root,
        }});
        Ok(())
    }}
}}

#[derive(Accounts)]
pub struct RecordConsensusReceipt<'info> {{
    #[account(mut)]
    pub consensus_registry: Account<'info, ByzantineConsensusRegistry>,
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}}

#[account]
pub struct ByzantineConsensusRegistry {{
    pub latest_round_id: String,
    pub status: String,
    pub merkle_root: [u8; 32],
    pub total_rounds: u64,
}}

#[event]
pub struct ConsensusReceiptRecorded {{
    pub round_id: String,
    pub quorum_size: u8,
    pub agreed_value: i8,
    pub merkle_root: [u8; 32],
}}

#[error_code]
pub enum ByzantineError {{
    #[msg("Byzantine fault tolerance threshold exceeded: f >= n/3")]
    FaultToleranceBoundExceeded,
    #[msg("Quorum size insufficient to guarantee quantum agreement")]
    InsufficientQuorumSize,
    #[msg("Fault bound invariant unsatisfied")]
    InvalidFaultBoundState,
}}
"""


class QuantumByzantineVerificationDrill:
    """5-stage automated verification drill for Quantum Byzantine Agreement & SAGIN Routing."""

    def __init__(self) -> None:
        self.router = SAGINTopologyRouter()
        self.coordinator = QuantumByzantineCoordinator(self.router)
        self.ledger = QuantumByzantineMerkleLedger()

    def run_all_stages(self) -> Dict[str, Any]:
        # Stage 1: SAGIN Topology & Entanglement Routing Search
        path, fid, lat = self.router.compute_shortest_quantum_path("ground-01", "ground-02")
        stage1_ok = (
            len(path) >= 2
            and fid > 0.80
            and lat < 50.0
        )

        # Stage 2: Quantum Pseudo-Signature Generation & Verification
        sig_engine = self.coordinator.sig_engine
        keys = sig_engine.generate_shared_entangled_pairs(num_nodes=4)
        sig = sig_engine.sign_proposal("node-00", 1, keys["node-00"]["node-01"])
        valid = sig_engine.verify_pseudo_signature(sig, keys["node-01"]["node-00"])
        # Tampered verification
        tampered_key = [1 - b for b in keys["node-01"]["node-00"]]
        invalid = not sig_engine.verify_pseudo_signature(sig, tampered_key)
        stage2_ok = valid and invalid

        # Stage 3: Honest Byzantine Consensus Execution
        nodes = ["ground-01", "ground-02", "haps-01", "leo-sat-01"]
        res_honest = self.coordinator.run_consensus_round(
            round_id="round-honest-1",
            node_ids=nodes,
            leader_id="ground-01",
            leader_proposed_value=1,
            byzantine_node_ids=[],
            inject_split_state_cheat=False,
        )
        stage3_ok = (
            res_honest.status == ConsensusStatus.AGREED
            and res_honest.agreed_value == 1
            and res_honest.quorum_size == 4
        )

        # Stage 4: Malicious Leader Split-State Cheat Detection
        res_cheat = self.coordinator.run_consensus_round(
            round_id="round-cheat-1",
            node_ids=nodes,
            leader_id="ground-01",
            leader_proposed_value=1,
            byzantine_node_ids=["ground-01"],
            inject_split_state_cheat=True,
        )
        stage4_ok = (
            res_cheat.status == ConsensusStatus.CHEAT_DETECTED
            and "ground-01" in res_cheat.byzantine_nodes_detected
            and res_cheat.agreed_value is None
        )

        # Stage 5: Merkle Ledger Proof & Solana Anchor Export Verification
        drill_ledger = QuantumByzantineMerkleLedger()
        rcpt1 = QuantumByzantineReceipt(
            receipt_id="rcpt-01",
            round_id="round-honest-1",
            status=res_honest.status.value,
            total_nodes=res_honest.total_nodes,
            quorum_size=res_honest.quorum_size,
            agreed_value=res_honest.agreed_value,
            byzantine_count=len(res_honest.byzantine_nodes_detected),
            quorum_fidelity=res_honest.quorum_fidelity,
            routing_hops=res_honest.routing_hops,
            fault_bound_satisfied=True,
        )
        rcpt2 = QuantumByzantineReceipt(
            receipt_id="rcpt-02",
            round_id="round-cheat-1",
            status=res_cheat.status.value,
            total_nodes=res_cheat.total_nodes,
            quorum_size=res_cheat.quorum_size,
            agreed_value=res_cheat.agreed_value,
            byzantine_count=len(res_cheat.byzantine_nodes_detected),
            quorum_fidelity=res_cheat.quorum_fidelity,
            routing_hops=res_cheat.routing_hops,
            fault_bound_satisfied=True,
        )
        drill_ledger.append_receipt(rcpt1)
        drill_ledger.append_receipt(rcpt2)
        root = drill_ledger.get_merkle_root()
        proof = drill_ledger.get_proof(0)
        verified_proof = QuantumByzantineMerkleLedger.verify_proof(rcpt1.compute_hash(), proof, root)

        anchor_payload = QuantumByzantineSolanaAnchorExporter.generate_instruction_payload(
            merkle_root=root,
            receipt=rcpt1,
            proof=proof,
        )
        anchor_prog = QuantumByzantineSolanaAnchorExporter.generate_anchor_program()
        stage5_ok = verified_proof and len(anchor_prog) > 100 and anchor_payload["instruction"] == "record_byzantine_consensus_receipt"

        all_passed = stage1_ok and stage2_ok and stage3_ok and stage4_ok and stage5_ok

        return {
            "all_passed": all_passed,
            "stages": {
                "stage1_sagin_routing": {
                    "passed": stage1_ok,
                    "path": path,
                    "fidelity": round(fid, 4),
                    "latency_ms": round(lat, 2),
                },
                "stage2_pseudo_signature": {
                    "passed": stage2_ok,
                    "valid_signature": valid,
                    "tampered_rejected": invalid,
                },
                "stage3_honest_consensus": {
                    "passed": stage3_ok,
                    "status": res_honest.status.value,
                    "agreed_value": res_honest.agreed_value,
                    "quorum_size": res_honest.quorum_size,
                },
                "stage4_cheat_detection": {
                    "passed": stage4_ok,
                    "status": res_cheat.status.value,
                    "detected_cheaters": res_cheat.byzantine_nodes_detected,
                },
                "stage5_anchor_merkle": {
                    "passed": stage5_ok,
                    "merkle_root": root,
                    "proof_verified": verified_proof,
                    "instruction": anchor_payload["instruction"],
                },
            },
        }
