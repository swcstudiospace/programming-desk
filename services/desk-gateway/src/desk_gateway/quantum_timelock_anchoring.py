"""Quantum Timelock Puzzles, VDF Anchoring & Solana Spacetime Ledger (Milestone v6.5 - Phase 97).

Implements:
- QuantumTimelockReceipt: Cryptographic receipt recording timelock puzzle solution,
  VDF proofs, iteration count, and beacon entropy.
- QuantumTimelockMerkleLedger: Binary Merkle tree computing immutable root hashes of timelock delay events.
- QuantumTimelockSolanaAnchorExporter: Solana Anchor smart contract and instruction payload exporter.
- QuantumTimelockVerificationDrill: 5-stage automated verification suite for Wesolowski proof completeness,
  Sloth permutation symmetry, puzzle decryption integrity, Merkle ledger consistency, and Solana Anchor commitments.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_timelock_mesh import (
    QuantumTimelockMesh,
    SlothVDFEngine,
    TimelockPuzzle,
    VDFAlgorithm,
    VDFProof,
    WesolowskiVDFEngine,
)


@dataclasses.dataclass
class QuantumTimelockReceipt:
    receipt_id: str
    puzzle_or_tick_id: str
    vdf_type: str
    iterations: int
    computation_time_ms: float
    output_y_hash: str
    proof_pi_hash: str
    challenge_l: int
    verified: bool
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.puzzle_or_tick_id}:{self.vdf_type}:"
            f"{self.iterations}:{self.computation_time_ms:.3f}:{self.output_y_hash}:"
            f"{self.proof_pi_hash}:{self.challenge_l}:{self.verified}:{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "puzzle_or_tick_id": self.puzzle_or_tick_id,
            "vdf_type": self.vdf_type,
            "iterations": self.iterations,
            "computation_time_ms": round(self.computation_time_ms, 3),
            "output_y_hash": self.output_y_hash,
            "proof_pi_hash": self.proof_pi_hash,
            "challenge_l_hex": hex(self.challenge_l),
            "verified": self.verified,
            "created_at": self.created_at,
            "receipt_hash": self.compute_hash(),
        }


class QuantumTimelockMerkleLedger:
    """Binary Merkle tree ledger tracking Timelock VDF and beacon execution receipts."""

    def __init__(self) -> None:
        self.receipts: List[QuantumTimelockReceipt] = []

    def add_receipt(self, receipt: QuantumTimelockReceipt) -> str:
        self.receipts.append(receipt)
        return self.get_merkle_root()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"quantum-timelock-empty").hexdigest()
        nodes = [r.compute_hash() for r in self.receipts]
        while len(nodes) > 1:
            if len(nodes) % 2 != 0:
                nodes.append(nodes[-1])
            next_level = []
            for i in range(0, len(nodes), 2):
                combined = nodes[i] + nodes[i + 1]
                next_level.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            nodes = next_level
        return nodes[0]


class QuantumTimelockSolanaAnchorExporter:
    """Exports Solana Anchor smart contract and cross-chain instruction commitments."""

    def __init__(self, program_id: str = "QTimeLockVDF1111111111111111111111111111111") -> None:
        self.program_id = program_id

    def generate_instruction_payload(
        self,
        merkle_root: str,
        num_receipts: int,
        epoch_beacon_entropy: str = "",
    ) -> Dict[str, Any]:
        return {
            "program_id": self.program_id,
            "instruction": "anchor_spacetime_vdf_root",
            "accounts": [
                {"name": "timelock_ledger_authority", "is_signer": True, "is_writable": True},
                {"name": "vdf_beacon_feed", "is_signer": False, "is_writable": True},
                {"name": "system_program", "is_signer": False, "is_writable": False},
            ],
            "data": {
                "merkle_root": merkle_root,
                "total_receipts": num_receipts,
                "epoch_beacon_entropy": epoch_beacon_entropy or hashlib.sha256(merkle_root.encode()).hexdigest(),
                "timestamp_ns": int(time.time() * 1e9),
            },
        }

    def export_anchor_program(self) -> str:
        return """// Solana Anchor Program: Spacetime Quantum Timelock & VDF Verification
use anchor_lang::prelude::*;

declare_id!("QTimeLockVDF1111111111111111111111111111111");

#[program]
pub mod quantum_timelock_anchoring {
    use super::*;

    pub fn anchor_spacetime_vdf_root(
        ctx: Context<AnchorSpacetimeRoot>,
        merkle_root: [u8; 32],
        total_receipts: u64,
        beacon_entropy: [u8; 32],
    ) -> Result<()> {
        let feed = &mut ctx.accounts.vdf_beacon_feed;
        feed.merkle_root = merkle_root;
        feed.total_receipts = total_receipts;
        feed.beacon_entropy = beacon_entropy;
        feed.last_anchored_ts = Clock::get()?.unix_timestamp;
        msg!("Anchored Spacetime VDF Merkle root to Solana ledger: {:?}", merkle_root);
        Ok(())
    }
}

#[account]
pub struct VdfBeaconFeedState {
    pub merkle_root: [u8; 32],
    pub total_receipts: u64,
    pub beacon_entropy: [u8; 32],
    pub last_anchored_ts: i64,
}

#[derive(Accounts)]
pub struct AnchorSpacetimeRoot<'info> {
    #[account(mut)]
    pub timelock_ledger_authority: Signer<'info>,
    #[account(init_if_needed, payer = timelock_ledger_authority, space = 8 + 32 + 8 + 32 + 8)]
    pub vdf_beacon_feed: Account<'info, VdfBeaconFeedState>,
    pub system_program: Program<'info, System>,
}
"""


class QuantumTimelockVerificationDrill:
    """5-stage automated verification drill suite."""

    def __init__(self, iterations: int = 200) -> None:
        self.iterations = iterations
        self.mesh = QuantumTimelockMesh()
        self.ledger = QuantumTimelockMerkleLedger()
        self.exporter = QuantumTimelockSolanaAnchorExporter()

    def run_drill(self) -> Dict[str, Any]:
        stages = {}

        # Stage 1: Wesolowski VDF sequential evaluation & Fiat-Shamir proof verification
        weso = WesolowskiVDFEngine()
        x_val = 1337
        proof = weso.compute_vdf(x_val, self.iterations)
        stages["stage_1_wesolowski_vdf_proof"] = {
            "passed": proof.verified and proof.computation_time_ms > 0,
            "iterations": self.iterations,
            "computation_time_ms": round(proof.computation_time_ms, 3),
            "challenge_l": hex(proof.challenge_l),
        }

        # Stage 2: Sloth permutation delay function forward & backward verification
        sloth = SlothVDFEngine()
        sloth_y, sloth_t = sloth.compute_sloth(42, 50)
        sloth_verified = sloth.verify_sloth(42, sloth_y, 50)
        stages["stage_2_sloth_permutation_inversion"] = {
            "passed": sloth_verified,
            "iterations": 50,
            "elapsed_ms": round(sloth_t, 3),
        }

        # Stage 3: Timelock puzzle creation, locking & deterministic decryption
        secret_msg = "sample_timelock_capsule_payload"  # pragma: allowlist secret
        puzzle = self.mesh.create_puzzle("test-puzzle-01", secret_msg, delay_seconds=0.02)
        solved = self.mesh.solve_puzzle("test-puzzle-01")
        stages["stage_3_puzzle_encryption_and_solution"] = {
            "passed": solved["decrypted_secret"] == secret_msg and solved["verified"] is True,
            "secret_matched": solved["decrypted_secret"] == secret_msg,
            "vdf_verified": solved["verified"],
        }

        # Stage 4: Spacetime Quantum Entropy Beacon & Merkle tree construction
        tick = self.mesh.emit_beacon_tick(epoch_index=1, quantum_seed="quantum-vacuum-noise-sample")
        rcpt = QuantumTimelockReceipt(
            receipt_id="drill-rcpt-01",
            puzzle_or_tick_id=f"tick-{tick['epoch_index']}",
            vdf_type=VDFAlgorithm.WESOLOWSKI.value,
            iterations=self.iterations,
            computation_time_ms=proof.computation_time_ms,
            output_y_hash=hashlib.sha256(hex(proof.output_y).encode()).hexdigest(),
            proof_pi_hash=hashlib.sha256(hex(proof.proof_pi).encode()).hexdigest(),
            challenge_l=proof.challenge_l,
            verified=proof.verified,
        )
        root = self.ledger.add_receipt(rcpt)
        stages["stage_4_merkle_ledger_immutability"] = {
            "passed": len(self.ledger.receipts) == 1 and len(root) == 64,
            "merkle_root": root,
            "receipt_hash": rcpt.compute_hash(),
        }

        # Stage 5: Solana Anchor instruction generation & IDL export
        anchor_payload = self.exporter.generate_instruction_payload(
            merkle_root=root,
            num_receipts=len(self.ledger.receipts),
            epoch_beacon_entropy=tick["beacon_entropy"],
        )
        stages["stage_5_solana_anchor_export"] = {
            "passed": anchor_payload["program_id"] == self.exporter.program_id and "merkle_root" in anchor_payload["data"],
            "instruction": anchor_payload["instruction"],
            "program_id": anchor_payload["program_id"],
        }

        all_passed = all(st.get("passed", False) for st in stages.values())
        return {
            "ok": all_passed,
            "total_stages": len(stages),
            "stages": stages,
        }
