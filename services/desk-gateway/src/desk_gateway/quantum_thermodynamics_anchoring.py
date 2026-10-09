"""Quantum Thermodynamic Resource Ledger & Solana Landauer Anchor (Milestone v6.6 - Phase 99).

Implements:
- QuantumThermodynamicReceipt: Cryptographic receipt capturing work extraction,
  ergotropy, Maxwell demon feedback, Landauer erasure dissipation, and Otto efficiency.
- QuantumThermodynamicMerkleLedger: Binary Merkle tree generating state roots for
  thermodynamic proofs, second law compliance, and energy conservation.
- QuantumThermodynamicSolanaAnchorExporter: Generates on-chain Solana Anchor program and instruction
  payloads verifying thermodynamic bounds.
- QuantumThermodynamicVerificationDrill: 5-stage automated verification drill testing:
  1. Gibbs canonical distribution and passivity invariance.
  2. Ergotropy work extraction non-negativity.
  3. Maxwell's demon information-to-work fidelity.
  4. Landauer erasure heat lower bound satisfaction (Q >= k_B * T * ln(2)).
  5. Quantum Otto engine Carnot limit compliance (eta_Otto <= eta_Carnot).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_thermodynamics_mesh import (
    DemonFeedbackResult,
    HeatEngineCycleResult,
    LandauerErasureEngine,
    LandauerErasureResult,
    MaxwellQuantumDemon,
    QuantumHeatEngineCycle,
    QuantumThermalReservoir,
    QuantumThermodynamicMesh,
    QuantumWorkExtractionEngine,
    WorkExtractionResult,
)


@dataclasses.dataclass
class QuantumThermodynamicReceipt:
    receipt_id: str
    cycle_type: str
    temperature: float
    work_extracted: float
    heat_dissipated: float
    entropy_delta: float
    efficiency: float
    second_law_satisfied: bool
    landauer_bound_satisfied: bool
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.cycle_type}:{self.temperature:.4f}:"
            f"{self.work_extracted:.6f}:{self.heat_dissipated:.6f}:{self.entropy_delta:.6f}:"
            f"{self.efficiency:.6f}:{self.second_law_satisfied}:{self.landauer_bound_satisfied}:{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "cycle_type": self.cycle_type,
            "temperature": round(self.temperature, 4),
            "work_extracted": round(self.work_extracted, 6),
            "heat_dissipated": round(self.heat_dissipated, 6),
            "entropy_delta": round(self.entropy_delta, 6),
            "efficiency": round(self.efficiency, 6),
            "second_law_satisfied": self.second_law_satisfied,
            "landauer_bound_satisfied": self.landauer_bound_satisfied,
            "created_at": self.created_at,
            "receipt_hash": self.compute_hash(),
        }


class QuantumThermodynamicMerkleLedger:
    """Binary Merkle tree ledger tracking thermodynamic transformations and Landauer erasure proofs."""

    def __init__(self) -> None:
        self.receipts: List[QuantumThermodynamicReceipt] = []

    def add_receipt(self, receipt: QuantumThermodynamicReceipt) -> str:
        self.receipts.append(receipt)
        return receipt.compute_hash()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"empty_thermo_ledger").hexdigest()

        current_level = [r.compute_hash() for r in self.receipts]
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level

        return current_level[0]

    def verify_ledger_integrity(self) -> bool:
        if not self.receipts:
            return True
        for r in self.receipts:
            if not r.compute_hash():
                return False
        return len(self.get_merkle_root()) == 64


class QuantumThermodynamicSolanaAnchorExporter:
    """Solana Anchor smart contract exporter for quantum thermodynamic bounds and Landauer dissipation."""

    ANCHOR_PROGRAM_ID = "ThermoLandauerLedger111111111111111111111"

    @classmethod
    def generate_instruction_payload(
        cls,
        merkle_root: str,
        num_receipts: int,
        mean_temperature: float = 1.0,
        total_work_extracted: float = 0.0,
        total_heat_dissipated: float = 0.0,
    ) -> Dict[str, Any]:
        return {
            "program_id": cls.ANCHOR_PROGRAM_ID,
            "instruction": "anchor_thermodynamic_landauer_root",
            "accounts": {
                "thermo_state": "8ThermodynamicStateAccount11111111111111111",
                "authority": "AuthorityPubkey111111111111111111111111111",
                "system_program": "11111111111111111111111111111111",
            },
            "data": {
                "merkle_root": merkle_root,
                "num_receipts": num_receipts,
                "mean_temperature": round(mean_temperature, 4),
                "total_work_extracted": round(total_work_extracted, 6),
                "total_heat_dissipated": round(total_heat_dissipated, 6),
                "timestamp": int(time.time()),
            },
        }

    @classmethod
    def export_anchor_program(cls) -> str:
        return f"""// Quantum Thermodynamic Resource & Landauer Erasure Solana Anchor Program
use anchor_lang::prelude::*;

declare_id!("{cls.ANCHOR_PROGRAM_ID}");

#[program]
pub mod quantum_thermodynamics_anchor {{
    use super::*;

    pub fn anchor_thermodynamic_landauer_root(
        ctx: Context<AnchorThermoRecord>,
        merkle_root: [u8; 32],
        num_receipts: u64,
        mean_temperature_scaled: u64,
        total_work_extracted_scaled: u64,
        total_heat_dissipated_scaled: u64,
        timestamp: i64,
    ) -> Result<()> {{
        let thermo_state = &mut ctx.accounts.thermo_state;
        thermo_state.merkle_root = merkle_root;
        thermo_state.num_receipts = num_receipts;
        thermo_state.mean_temperature_scaled = mean_temperature_scaled;
        thermo_state.total_work_extracted_scaled = total_work_extracted_scaled;
        thermo_state.total_heat_dissipated_scaled = total_heat_dissipated_scaled;
        thermo_state.last_anchor_timestamp = timestamp;
        thermo_state.authority = ctx.accounts.authority.key();
        Ok(())
    }}
}}

#[derive(Accounts)]
pub struct AnchorThermoRecord<'info> {{
    #[account(init_if_needed, payer = authority, space = 8 + 32 + 8 + 8 + 8 + 8 + 8 + 32)]
    pub thermo_state: Account<'info, ThermoStateAccount>,
    #[account(mut)]
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}}

#[account]
pub struct ThermoStateAccount {{
    pub merkle_root: [u8; 32],
    pub num_receipts: u64,
    pub mean_temperature_scaled: u64,
    pub total_work_extracted_scaled: u64,
    pub total_heat_dissipated_scaled: u64,
    pub last_anchor_timestamp: i64,
    pub authority: Pubkey,
}}
"""


class QuantumThermodynamicVerificationDrill:
    """5-stage automated verification drill checking thermodynamic laws and Landauer bounds."""

    def __init__(self, default_temperature: float = 1.0) -> None:
        self.temperature = default_temperature
        self.mesh = QuantumThermodynamicMesh(default_temperature=default_temperature)
        self.ledger = QuantumThermodynamicMerkleLedger()

    def run_drill(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}

        # Stage 1: Gibbs state passivity invariance
        energy_levels = [0.0, 1.0, 2.5]
        th = self.mesh.thermalize(energy_levels, temperature=self.temperature)
        erg_th = self.mesh.extract_ergotropy(energy_levels, th.probabilities, temperature=self.temperature)
        results["stage_1_gibbs_passivity"] = {
            "passed": erg_th.is_passive and erg_th.extractable_ergotropy < 1e-6,
            "probabilities": [round(p, 4) for p in th.probabilities],
            "extractable_ergotropy": erg_th.extractable_ergotropy,
        }

        # Stage 2: Inverted population non-zero ergotropy
        inverted_probs = [0.1, 0.3, 0.6]  # Higher energy level has highest population
        erg_inverted = self.mesh.extract_ergotropy(energy_levels, inverted_probs, temperature=self.temperature)
        results["stage_2_ergotropy_extraction"] = {
            "passed": not erg_inverted.is_passive and erg_inverted.extractable_ergotropy > 0.0,
            "extractable_ergotropy": round(erg_inverted.extractable_ergotropy, 4),
            "bound_free_energy_work": round(erg_inverted.bound_free_energy_work, 4),
        }

        # Stage 3: Maxwell's demon information acquisition & Szilard work
        demon_res, erasure_res = self.mesh.run_demon_cycle(p0=0.8, p1=0.2, temperature=self.temperature)
        results["stage_3_demon_information_feedback"] = {
            "passed": demon_res.mutual_information_bits > 0 and demon_res.work_extracted > 0,
            "mutual_information_bits": round(demon_res.mutual_information_bits, 4),
            "work_extracted": round(demon_res.work_extracted, 4),
        }

        # Stage 4: Landauer erasure lower bound validation
        erasure_res_2 = LandauerErasureEngine.erase_memory(
            bits_to_erase=2.0,
            reservoir_temperature=self.temperature,
            dissipation_efficiency=1.1,
        )
        results["stage_4_landauer_erasure_bound"] = {
            "passed": erasure_res_2.landauer_bound_satisfied and erasure_res_2.actual_heat_dissipated >= erasure_res_2.theoretical_minimum_heat,
            "theoretical_min_heat": round(erasure_res_2.theoretical_minimum_heat, 4),
            "actual_dissipated": round(erasure_res_2.actual_heat_dissipated, 4),
        }

        # Stage 5: Quantum Otto cycle Carnot limit validation
        otto_res = self.mesh.run_heat_engine(th_cold=1.0, th_hot=4.0, omega_cold=1.0, omega_hot=2.0)
        results["stage_5_otto_carnot_efficiency"] = {
            "passed": otto_res.second_law_satisfied and otto_res.otto_efficiency <= otto_res.carnot_limit,
            "otto_efficiency": round(otto_res.otto_efficiency, 4),
            "carnot_limit": round(otto_res.carnot_limit, 4),
            "net_work_extracted": round(otto_res.net_work_extracted, 4),
        }

        # Record receipt into ledger
        rcpt = QuantumThermodynamicReceipt(
            receipt_id="rcpt-drill-thermo-01",
            cycle_type="FULL_5_STAGE_DRILL",
            temperature=self.temperature,
            work_extracted=otto_res.net_work_extracted + demon_res.work_extracted,
            heat_dissipated=erasure_res_2.actual_heat_dissipated,
            entropy_delta=otto_res.heat_rejected_qc / 1.0 - otto_res.heat_absorbed_qh / 4.0,
            efficiency=otto_res.otto_efficiency,
            second_law_satisfied=otto_res.second_law_satisfied,
            landauer_bound_satisfied=erasure_res_2.landauer_bound_satisfied,
        )
        self.ledger.add_receipt(rcpt)

        all_passed = all(stage["passed"] for stage in results.values())
        return {
            "all_passed": all_passed,
            "stages": results,
            "merkle_root": self.ledger.get_merkle_root(),
            "receipt": rcpt.to_dict(),
        }
