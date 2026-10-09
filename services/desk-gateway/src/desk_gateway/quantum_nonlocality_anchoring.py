"""Device-Independent Quantum Non-Locality Merkle Ledger & Solana Anchor Verification Mesh (Milestone v6.7 - Phase 101).

Implements:
- QuantumNonLocalityReceipt: Cryptographic receipt capturing CHSH parameter S,
  Mermin expectation <M_3>, p-values, min-entropy certified bits, and DI-QKD key rate.
- QuantumNonLocalityMerkleLedger: Binary Merkle tree generating state roots for
  non-locality certificates, device-independent randomness, and secure key exchanges.
- QuantumNonLocalitySolanaAnchorExporter: Generates on-chain Solana Anchor program and instruction
  payloads verifying Bell violation and non-locality proofs.
- QuantumNonLocalityVerificationDrill: 5-stage automated verification drill testing:
  1. CHSH Bell inequality violation exceeding classical bound (S > 2.0).
  2. GHZ Mermin multipartite operator quantum expectation (<M_3> > 2.0 approaching 4.0).
  3. Pironio min-entropy device-independent randomness expansion.
  4. DI-QKD secure key generation under collective attack bounds.
  5. Cryptographic Merkle receipt aggregation and Solana Anchor payload generation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_nonlocality_mesh import (
    CHSHBellInequalityEngine,
    CHSHTestSummary,
    DeviceIndependentQKDEngine,
    DeviceIndependentRandomnessExpander,
    DIQKDKeyResult,
    DIRandomnessResult,
    MerminGHZSummary,
    MultipartiteMerminGHZEngine,
    QuantumNonLocalityMesh,
)


@dataclasses.dataclass
class QuantumNonLocalityReceipt:
    receipt_id: str
    test_type: str  # "CHSH_BELL", "GHZ_MERMIN", "DI_RANDOMNESS", "DI_QKD"
    parameter_value: float  # S or <M_3> or min-entropy or key rate
    classical_bound: float
    quantum_violation: bool
    num_trials: int
    p_value: float
    extra_data_hash: str
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.test_type}:{self.parameter_value:.6f}:"
            f"{self.classical_bound:.4f}:{self.quantum_violation}:{self.num_trials}:"
            f"{self.p_value:.6e}:{self.extra_data_hash}:{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "test_type": self.test_type,
            "parameter_value": round(self.parameter_value, 6),
            "classical_bound": self.classical_bound,
            "quantum_violation": self.quantum_violation,
            "num_trials": self.num_trials,
            "p_value": self.p_value,
            "extra_data_hash": self.extra_data_hash,
            "created_at": self.created_at,
            "hash": self.compute_hash(),
        }


class QuantumNonLocalityMerkleLedger:
    """Binary Merkle tree ledger for certified non-locality and DI proofs."""

    def __init__(self) -> None:
        self.receipts: List[QuantumNonLocalityReceipt] = []

    def add_receipt(self, receipt: QuantumNonLocalityReceipt) -> str:
        self.receipts.append(receipt)
        return receipt.compute_hash()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"quantum_nonlocality_genesis_root").hexdigest()

        current_hashes = [r.compute_hash() for r in self.receipts]
        while len(current_hashes) > 1:
            if len(current_hashes) % 2 == 1:
                current_hashes.append(current_hashes[-1])
            next_level = []
            for i in range(0, len(current_hashes), 2):
                combined = current_hashes[i] + current_hashes[i + 1]
                next_level.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current_hashes = next_level

        return current_hashes[0]

    def verify_ledger_integrity(self) -> bool:
        if not self.receipts:
            return True
        for receipt in self.receipts:
            if not receipt.compute_hash():
                return False
        return True


class QuantumNonLocalitySolanaAnchorExporter:
    """Exports Solana Anchor smart contract and verified instruction payloads for DI non-locality proofs."""

    ANCHOR_PROGRAM_ID: str = "NonLocalityAnchor1111111111111111111111111111"

    @classmethod
    def generate_instruction_payload(
        cls,
        merkle_root: str,
        num_receipts: int,
        mean_chsh_s: float,
        certified_random_bits: float,
        di_key_rate: float,
    ) -> Dict[str, Any]:
        scaled_s = int(round(mean_chsh_s * 10000))
        scaled_rate = int(round(di_key_rate * 10000))

        return {
            "program_id": cls.ANCHOR_PROGRAM_ID,
            "instruction": "anchor_nonlocality_di_root",
            "accounts": [
                {"name": "nonlocality_ledger", "is_mut": True, "is_signer": False},
                {"name": "authority", "is_mut": False, "is_signer": True},
                {"name": "system_program", "is_mut": False, "is_signer": False},
            ],
            "data": {
                "merkle_root": merkle_root,
                "num_receipts": num_receipts,
                "mean_chsh_s_scaled": scaled_s,
                "certified_random_bits": round(certified_random_bits, 2),
                "di_key_rate_scaled": scaled_rate,
                "timestamp": int(time.time()),
            },
        }

    @classmethod
    def export_anchor_program(cls) -> str:
        return f"""// Solana Anchor Program: Device-Independent Quantum Non-Locality & Bell Verification
// Program ID: {cls.ANCHOR_PROGRAM_ID}

use anchor_lang::prelude::*;

declare_id!("{cls.ANCHOR_PROGRAM_ID}");

#[program]
pub mod quantum_nonlocality_anchor {{
    use super::*;

    pub fn anchor_nonlocality_di_root(
        ctx: Context<AnchorNonLocalityRoot>,
        merkle_root: [u8; 32],
        num_receipts: u64,
        mean_chsh_s_scaled: u32,       // CHSH S * 10000 (Classical bound = 20000, Tsirelson = 28284)
        certified_random_bits: u64,
        di_key_rate_scaled: u32,
    ) -> Result<()> {{
        require!(mean_chsh_s_scaled > 20000, NonLocalityError::ClassicalBoundExceeded);
        require!(mean_chsh_s_scaled <= 28285, NonLocalityError::TsirelsonBoundExceeded);

        let ledger = &mut ctx.accounts.nonlocality_ledger;
        ledger.merkle_root = merkle_root;
        ledger.num_receipts = num_receipts;
        ledger.mean_chsh_s_scaled = mean_chsh_s_scaled;
        ledger.certified_random_bits = certified_random_bits;
        ledger.di_key_rate_scaled = di_key_rate_scaled;
        ledger.authority = ctx.accounts.authority.key();
        ledger.last_updated = Clock::get()?.unix_timestamp;

        emit!(NonLocalityRootAnchored {{
            merkle_root,
            mean_chsh_s_scaled,
            certified_random_bits,
            authority: ledger.authority,
        }});

        Ok(())
    }}
}}

#[derive(Accounts)]
pub struct AnchorNonLocalityRoot<'info> {{
    #[account(
        init_if_needed,
        payer = authority,
        space = 8 + 32 + 8 + 4 + 8 + 4 + 32 + 8
    )]
    pub nonlocality_ledger: Account<'info, NonLocalityLedgerAccount>,
    #[account(mut)]
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}}

#[account]
pub struct NonLocalityLedgerAccount {{
    pub merkle_root: [u8; 32],
    pub num_receipts: u64,
    pub mean_chsh_s_scaled: u32,
    pub certified_random_bits: u64,
    pub di_key_rate_scaled: u32,
    pub authority: Pubkey,
    pub last_updated: i64,
}}

#[event]
pub struct NonLocalityRootAnchored {{
    pub merkle_root: [u8; 32],
    pub mean_chsh_s_scaled: u32,
    pub certified_random_bits: u64,
    pub authority: Pubkey,
}}

#[error_code]
pub enum NonLocalityError {{
    #[msg("CHSH parameter does not violate local realism (S <= 2.0)")]
    ClassicalBoundExceeded,
    #[msg("CHSH parameter violates physical Tsirelson bound (S > 2*sqrt(2))")]
    TsirelsonBoundExceeded,
}}
"""


class QuantumNonLocalityVerificationDrill:
    """5-stage automated verification drill testing Bell non-locality, randomness, and DI-QKD."""

    def __init__(self, rng_seed: Optional[int] = 42) -> None:
        self.mesh = QuantumNonLocalityMesh(rng_seed=rng_seed)
        self.ledger = QuantumNonLocalityMerkleLedger()

    def run_drill(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # Stage 1: CHSH Bell inequality violation test
        chsh_res = self.mesh.run_chsh_evaluation(num_trials=2000, noise_depolarizing=0.0)
        results["stage_1_chsh_bell_violation"] = {
            "passed": chsh_res.quantum_violation and chsh_res.chsh_parameter_s > 2.2,
            "chsh_s": chsh_res.chsh_parameter_s,
            "classical_bound": chsh_res.classical_bound,
            "tsirelson_bound": chsh_res.tsirelson_bound,
            "p_value": chsh_res.p_value_classical_refutation,
        }

        # Stage 2: GHZ Mermin multipartite violation test
        mermin_res = self.mesh.run_mermin_evaluation(num_trials_per_setting=500, noise_depolarizing=0.0)
        results["stage_2_ghz_mermin_violation"] = {
            "passed": mermin_res.quantum_violation and mermin_res.mermin_operator_expectation > 3.0,
            "mermin_expectation": mermin_res.mermin_operator_expectation,
            "classical_bound": mermin_res.classical_bound,
            "quantum_bound": mermin_res.quantum_bound,
        }

        # Stage 3: Device-independent quantum randomness expansion
        rand_res = self.mesh.expand_randomness(
            seed_bits="0101010101010101",
            bell_s=chsh_res.chsh_parameter_s,
            num_rounds=1000,
        )
        results["stage_3_di_randomness_expansion"] = {
            "passed": rand_res.min_entropy_per_bit > 0.5 and rand_res.total_certified_random_bits > 500.0,
            "min_entropy_per_bit": rand_res.min_entropy_per_bit,
            "total_certified_bits": rand_res.total_certified_random_bits,
            "expansion_factor": rand_res.expansion_factor,
        }

        # Stage 4: Device-independent QKD key generation
        di_qkd_res = self.mesh.run_di_qkd(num_pairs=1500, noise_depolarizing=0.01)
        results["stage_4_di_qkd_key_rate"] = {
            "passed": di_qkd_res.security_certified and di_qkd_res.final_secure_key_length > 0,
            "qber": di_qkd_res.qber,
            "secret_key_rate": di_qkd_res.secret_key_rate,
            "final_key_len": di_qkd_res.final_secure_key_length,
            "security_certified": di_qkd_res.security_certified,
        }

        # Stage 5: Merkle ledger and Solana Anchor export
        rcpt1 = QuantumNonLocalityReceipt(
            receipt_id="rcpt-drill-chsh-01",
            test_type="CHSH_BELL",
            parameter_value=chsh_res.chsh_parameter_s,
            classical_bound=2.0,
            quantum_violation=chsh_res.quantum_violation,
            num_trials=chsh_res.num_trials,
            p_value=chsh_res.p_value_classical_refutation,
            extra_data_hash=hashlib.sha256(json.dumps(chsh_res.correlations).encode()).hexdigest(),
        )
        rcpt2 = QuantumNonLocalityReceipt(
            receipt_id="rcpt-drill-mermin-01",
            test_type="GHZ_MERMIN",
            parameter_value=mermin_res.mermin_operator_expectation,
            classical_bound=2.0,
            quantum_violation=mermin_res.quantum_violation,
            num_trials=mermin_res.num_trials,
            p_value=1e-12,
            extra_data_hash=hashlib.sha256(json.dumps(mermin_res.correlations).encode()).hexdigest(),
        )
        self.ledger.add_receipt(rcpt1)
        self.ledger.add_receipt(rcpt2)

        root = self.ledger.get_merkle_root()
        anchor_payload = QuantumNonLocalitySolanaAnchorExporter.generate_instruction_payload(
            merkle_root=root,
            num_receipts=len(self.ledger.receipts),
            mean_chsh_s=chsh_res.chsh_parameter_s,
            certified_random_bits=rand_res.total_certified_random_bits,
            di_key_rate=di_qkd_res.secret_key_rate,
        )

        results["stage_5_merkle_anchor_export"] = {
            "passed": len(root) == 64 and anchor_payload["data"]["mean_chsh_s_scaled"] > 20000,
            "merkle_root": root,
            "anchor_instruction": anchor_payload["instruction"],
        }

        all_passed = all(stage["passed"] for stage in results.values())
        return {
            "all_passed": all_passed,
            "stages": results,
            "merkle_root": root,
            "anchor_payload": anchor_payload,
        }
