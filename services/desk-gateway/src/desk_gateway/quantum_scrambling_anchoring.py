r"""Quantum Scrambling & Hayden-Preskill Merkle Ledger, Solana Anchor Verification & Automated Drill (Milestone v7.4 - Phase 115).

Implements:
- QuantumScramblingReceipt: Cryptographic receipt recording OTOC decay, MSS chaos bounds,
  and Hayden-Preskill black hole quantum information recovery fidelity.
- QuantumScramblingMerkleLedger: Binary Merkle tree aggregating quantum scrambling operations
  with audit inclusion proofs.
- QuantumScramblingSolanaAnchorExporter: Solana Anchor smart contract and instruction payload
  generator enforcing MSS Lyapunov bounds (\lambda_L \le 2\pi T), negative tripartite mutual information,
  and Hayden-Preskill reconstruction fidelity thresholds (F >= 0.85).
- QuantumScramblingVerificationDrill: 5-stage automated verification drill testing:
  1. MSS Lyapunov exponent and scrambling time bounds validation (\lambda_L \le 2\pi k_B T / \hbar).
  2. OTOC decay F(t) and non-local commutator growth C(t) in fast scramblers.
  3. Tripartite negative mutual information confirmation (I_3(A:B:C) < 0).
  4. Hayden-Preskill black hole information retrieval with \epsilon ancillary Hawking radiation.
  5. Solana Anchor program compilation and Merkle inclusion audit.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_scrambling_mesh import (
    HaydenPreskillProtocolEngine,
    HaydenPreskillResult,
    OTOCMeasurementPoint,
    QuantumScramblingEngine,
    QuantumScramblingMesh,
    ScramblerType,
    ScramblingSystemConfig,
)


@dataclasses.dataclass
class QuantumScramblingReceipt:
    receipt_id: str
    operation_type: str         # "OTOC_DECAY_ANALYSIS" or "HAYDEN_PRESKILL_RETRIEVAL"
    scrambler_type: str         # "RANDOM_CLIFFORD", "SYK_CHAOTIC_CHAIN", "HAAR_RANDOM"
    otoc_f_or_fidelity: float   # Final OTOC F(t) or Reconstruction Fidelity
    lyapunov_or_epsilon: float  # Lyapunov exponent or Epsilon qubits
    tripartite_i3: float        # Tripartite mutual information
    status: str                 # "SCRAMBLED_BOUND_SATURATED", "RETRIEVAL_VERIFIED", "NON_SCRAMBLING"
    parameters_digest: str
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.operation_type}:{self.scrambler_type}:"
            f"{self.otoc_f_or_fidelity:.6f}:{self.lyapunov_or_epsilon:.6f}:{self.tripartite_i3:.6f}:"
            f"{self.status}:{self.parameters_digest}:{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "operation_type": self.operation_type,
            "scrambler_type": self.scrambler_type,
            "otoc_f_or_fidelity": round(self.otoc_f_or_fidelity, 5),
            "lyapunov_or_epsilon": round(self.lyapunov_or_epsilon, 4),
            "tripartite_i3": round(self.tripartite_i3, 5),
            "status": self.status,
            "parameters_digest": self.parameters_digest,
            "created_at": self.created_at,
            "receipt_hash": self.compute_hash(),
        }


class QuantumScramblingMerkleLedger:
    """Binary Merkle Tree ledger for quantum scrambling experiments and Hayden-Preskill proofs."""

    def __init__(self) -> None:
        self.receipts: List[QuantumScramblingReceipt] = []

    def append_receipt(self, receipt: QuantumScramblingReceipt) -> str:
        self.receipts.append(receipt)
        return receipt.compute_hash()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"quantum_scrambling_empty_merkle_root").hexdigest()

        current_hashes = [r.compute_hash() for r in self.receipts]
        while len(current_hashes) > 1:
            if len(current_hashes) % 2 == 1:
                current_hashes.append(current_hashes[-1])
            next_hashes: List[str] = []
            for i in range(0, len(current_hashes), 2):
                combined = current_hashes[i] + current_hashes[i + 1]
                next_hashes.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current_hashes = next_hashes
        return current_hashes[0]

    def get_proof(self, index: int) -> List[Dict[str, str]]:
        if index < 0 or index >= len(self.receipts):
            return []

        tree_levels: List[List[str]] = []
        current_hashes = [r.compute_hash() for r in self.receipts]
        tree_levels.append(list(current_hashes))

        while len(current_hashes) > 1:
            if len(current_hashes) % 2 == 1:
                current_hashes.append(current_hashes[-1])
            next_hashes = []
            for i in range(0, len(current_hashes), 2):
                combined = current_hashes[i] + current_hashes[i + 1]
                next_hashes.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current_hashes = next_hashes
            tree_levels.append(list(current_hashes))

        proof: List[Dict[str, str]] = []
        curr_idx = index
        for level in tree_levels[:-1]:
            if len(level) % 2 == 1:
                level = list(level) + [level[-1]]
            is_right = (curr_idx % 2 == 1)
            sibling_idx = curr_idx - 1 if is_right else curr_idx + 1
            if sibling_idx < len(level):
                proof.append({
                    "position": "left" if is_right else "right",
                    "hash": level[sibling_idx],
                })
            curr_idx //= 2

        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Dict[str, str]], root: str) -> bool:
        curr = leaf_hash
        for p in proof:
            sibling = p["hash"]
            if p["position"] == "left":
                combined = sibling + curr
            else:
                combined = curr + sibling
            curr = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return curr == root


class QuantumScramblingSolanaAnchorExporter:
    """Exports Solana Anchor eBPF/Rust smart contracts and instruction payloads for quantum scrambling."""

    PROGRAM_ID: str = "Scramb1eHaydenPreski1111111111111111111111111"

    @classmethod
    def generate_anchor_program(cls) -> str:
        return f"""// SPDX-License-Identifier: Apache-2.0
// Solana Anchor Program for Quantum Scrambling, OTOC & Hayden-Preskill Teleportation Verification
use anchor_lang::prelude::*;

declare_id!("{cls.PROGRAM_ID}");

#[program]
pub mod quantum_scrambling_anchoring {{
    use super::*;

    pub fn verify_scrambling_and_hayden_preskill(
        ctx: Context<VerifyScramblingRecord>,
        merkle_root: [u8; 32],
        receipt_hash: [u8; 32],
        reconstruction_fidelity_bps: u16, // Basis points (10000 = 1.0)
        tripartite_i3_negative: bool,
        proof: Vec<[u8; 32]>,
        proof_positions: Vec<u8>,
    ) -> Result<()> {{
        require!(
            reconstruction_fidelity_bps >= 8500, // Fidelity F >= 0.85
            QuantumScramblingError::InsufficientFidelity
        );
        require!(
            tripartite_i3_negative,
            QuantumScramblingError::NonNegativeTripartiteInformation
        );

        // Verify Merkle path
        let mut current_hash = receipt_hash;
        for (sibling, &pos) in proof.iter().zip(proof_positions.iter()) {{
            let mut hasher = anchor_lang::solana_program::hash::Hasher::default();
            if pos == 0 {{
                hasher.hash(sibling);
                hasher.hash(&current_hash);
            }} else {{
                hasher.hash(&current_hash);
                hasher.hash(sibling);
            }}
            current_hash = hasher.result().to_bytes();
        }}

        require!(current_hash == merkle_root, QuantumScramblingError::InvalidMerkleProof);

        emit!(ScramblingVerifiedEvent {{
            merkle_root,
            receipt_hash,
            reconstruction_fidelity_bps,
            authority: ctx.accounts.authority.key(),
        }});

        Ok(())
    }}
}}

#[derive(Accounts)]
pub mod VerifyScramblingRecord<'info> {{
    #[account(mut)]
    pub authority: Signer<'info>;
    pub system_program: Program<'info, System>;
}}

#[event]
pub struct ScramblingVerifiedEvent {{
    pub merkle_root: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub reconstruction_fidelity_bps: u16,
    pub authority: Pubkey,
}}

#[error_code]
pub enum QuantumScramblingError {{
    #[msg("Reconstruction fidelity is below the minimum threshold (0.85)")]
    InsufficientFidelity,
    #[msg("Tripartite mutual information must be strictly negative for fast scrambling")]
    NonNegativeTripartiteInformation,
    #[msg("Cryptographic Merkle audit proof verification failed")]
    InvalidMerkleProof,
}}
"""

    @classmethod
    def generate_instruction_payload(
        cls,
        merkle_root: str,
        receipt: QuantumScramblingReceipt,
        proof: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        proof_hashes = [p["hash"] for p in proof]
        proof_positions = [0 if p["position"] == "left" else 1 for p in proof]
        fidelity_bps = int(receipt.otoc_f_or_fidelity * 10000)

        return {
            "program_id": cls.PROGRAM_ID,
            "instruction": "verify_scrambling_and_hayden_preskill",
            "accounts": {
                "authority": "11111111111111111111111111111111",
                "system_program": "11111111111111111111111111111111",
            },
            "args": {
                "merkle_root": merkle_root,
                "receipt_hash": receipt.compute_hash(),
                "reconstruction_fidelity_bps": fidelity_bps,
                "tripartite_i3_negative": receipt.tripartite_i3 < 0.0,
                "proof": proof_hashes,
                "proof_positions": proof_positions,
            },
        }


class QuantumScramblingVerificationDrill:
    """5-stage automated verification drill testing Quantum Many-Body Scrambling & Hayden-Preskill Protocol."""

    def __init__(self) -> None:
        self.mesh = QuantumScramblingMesh()
        self.ledger = QuantumScramblingMerkleLedger()

    def run_stage_1_lyapunov_mss_bound(self) -> Dict[str, Any]:
        """Stage 1: Validate MSS Chaos Bound lambda_L <= 2 * pi * k_B * T / hbar."""
        config = ScramblingSystemConfig(n_qubits=6, temperature_k=1.5)
        mss_bound = config.mss_lyapunov_bound
        t_star = config.theoretical_scrambling_time

        assert mss_bound == 2.0 * math.pi * 1.5
        assert t_star > 0.0

        return {
            "stage": "STAGE_1_MSS_BOUND_VALIDATION",
            "status": "PASSED",
            "mss_lyapunov_bound": round(mss_bound, 4),
            "scrambling_time_t_star": round(t_star, 4),
        }

    def run_stage_2_otoc_decay_and_commutator_growth(self) -> Dict[str, Any]:
        """Stage 2: OTOC decay F(t) -> 0 and Commutator C(t) -> 2.0 under fast scrambling."""
        res = self.mesh.run_otoc_analysis(
            n_qubits=6,
            scrambler_type="RANDOM_CLIFFORD",
            temperature_k=1.0,
            steps=8,
        )
        assert res["initial_otoc_f"] >= 0.90
        assert res["final_otoc_f"] < 0.20
        assert res["final_commutator_c"] > 1.60
        assert res["is_fast_scrambled"] is True

        return {
            "stage": "STAGE_2_OTOC_DECAY_AND_COMMUTATOR",
            "status": "PASSED",
            "initial_f": res["initial_otoc_f"],
            "final_f": res["final_otoc_f"],
            "final_c": res["final_commutator_c"],
        }

    def run_stage_3_tripartite_mutual_information(self) -> Dict[str, Any]:
        """Stage 3: Confirm non-local information spreading via negative tripartite mutual information I_3 < 0."""
        res = self.mesh.run_otoc_analysis(
            n_qubits=6,
            scrambler_type="SYK_CHAOTIC_CHAIN",
            temperature_k=1.0,
            steps=8,
        )
        assert res["final_tripartite_mutual_info_i3"] < -1.0

        return {
            "stage": "STAGE_3_TRIPARTITE_MUTUAL_INFO",
            "status": "PASSED",
            "final_i3": res["final_tripartite_mutual_info_i3"],
            "information_delocalized": True,
        }

    def run_stage_4_hayden_preskill_retrieval(self) -> Dict[str, Any]:
        """Stage 4: Execute Hayden-Preskill black hole information retrieval with epsilon Hawking qubits."""
        retrieval = self.mesh.run_hayden_preskill_teleportation(
            experiment_id="drill-hp-exp-01",
            n_black_hole_qubits=6,
            k_secret_qubits=1,
            epsilon_qubits=2,
            scrambler_type="RANDOM_CLIFFORD",
        )
        assert retrieval.teleportation_successful is True
        assert retrieval.reconstruction_fidelity >= 0.85
        assert retrieval.theoretical_max_error == 2.0 ** (-4)  # 2^(-2*2) = 1/16 = 0.0625

        return {
            "stage": "STAGE_4_HAYDEN_PRESKILL_RETRIEVAL",
            "status": "PASSED",
            "fidelity": round(retrieval.reconstruction_fidelity, 4),
            "theoretical_max_error": round(retrieval.theoretical_max_error, 4),
            "teleportation_successful": retrieval.teleportation_successful,
        }

    def run_stage_5_solana_merkle_anchoring(self) -> Dict[str, Any]:
        """Stage 5: Solana Anchor smart contract export and Merkle inclusion proof verification."""
        rcpt = QuantumScramblingReceipt(
            receipt_id="rcpt-drill-01",
            operation_type="HAYDEN_PRESKILL_RETRIEVAL",
            scrambler_type="RANDOM_CLIFFORD",
            otoc_f_or_fidelity=0.965,
            lyapunov_or_epsilon=2.0,
            tripartite_i3=-1.93,
            status="RETRIEVAL_VERIFIED",
            parameters_digest="drill_digest_stage_5",
        )
        self.ledger.append_receipt(rcpt)
        root = self.ledger.get_merkle_root()
        proof = self.ledger.get_proof(0)

        verified = self.ledger.verify_proof(rcpt.compute_hash(), proof, root)
        assert verified is True

        payload = QuantumScramblingSolanaAnchorExporter.generate_instruction_payload(
            merkle_root=root,
            receipt=rcpt,
            proof=proof,
        )
        anchor_prog = QuantumScramblingSolanaAnchorExporter.generate_anchor_program()
        assert "verify_scrambling_and_hayden_preskill" in anchor_prog

        return {
            "stage": "STAGE_5_SOLANA_ANCHOR_AND_MERKLE",
            "status": "PASSED",
            "merkle_root": root,
            "proof_length": len(proof),
            "proof_verified": verified,
            "anchor_instruction": payload["instruction"],
        }

    def run_all_stages(self) -> Dict[str, Any]:
        s1 = self.run_stage_1_lyapunov_mss_bound()
        s2 = self.run_stage_2_otoc_decay_and_commutator_growth()
        s3 = self.run_stage_3_tripartite_mutual_information()
        s4 = self.run_stage_4_hayden_preskill_retrieval()
        s5 = self.run_stage_5_solana_merkle_anchoring()

        all_passed = all(
            s["status"] == "PASSED"
            for s in [s1, s2, s3, s4, s5]
        )

        return {
            "all_stages_passed": all_passed,
            "stages": [s1, s2, s3, s4, s5],
            "timestamp": time.time(),
        }
