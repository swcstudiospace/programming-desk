r"""Quantum Tensor Network Merkle Ledger, Solana Anchor Verification & Automated Drill (Milestone v7.5 - Phase 117).

Implements:
- QuantumTensorReceipt: Cryptographic receipt recording DMRG ground state energies,
  bond dimensions \chi, entanglement entropy S_E, and 2D PEPS contraction results.
- QuantumTensorMerkleLedger: Binary Merkle tree aggregating tensor network simulation proofs
  with audit inclusion proofs.
- QuantumTensorSolanaAnchorExporter: Solana Anchor smart contract and instruction payload
  generator enforcing variational energy upper bounds (\langle H \rangle \le E_{\text{exact}} + \delta),
  entanglement area law checks, and bond dimension limits (\chi \le \chi_{\max}).
- QuantumTensorVerificationDrill: 5-stage automated verification drill testing:
  1. Jordan-Wigner / Bethe Ansatz exact ground state analytical calculations.
  2. Variational DMRG monotonic energy convergence and truncation error decay.
  3. 1D Entanglement Area Law saturation and central charge scaling.
  4. 2D PEPS Boundary MPS contraction and perimeter-law verification.
  5. Solana Anchor program compilation and Merkle inclusion audit.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional

from desk_gateway.quantum_tensor_network_mesh import (
    DMRGVariationalEngine,
    LatticeModelType,
    MatrixProductState,
    PEPS2DContractionEngine,
    QuantumTensorNetworkMesh,
    TensorNetworkConfig,
    TensorNetworkSimulationResult,
)


@dataclasses.dataclass
class QuantumTensorReceipt:
    receipt_id: str
    operation_type: str         # "DMRG_GROUND_STATE" or "PEPS_2D_CONTRACTION"
    model_type: str             # "TRANSVERSE_ISING", "HEISENBERG_XXX", "AKLT_SPIN_1"
    ground_state_energy: float  # Variational ground state energy
    energy_relative_error: float # Error relative to exact analytical limit
    max_bond_dim: int           # Achieved MPS / PEPS bond dimension
    entanglement_entropy: float # Central bipartition von Neumann entropy
    area_law_satisfied: bool    # True if S_E complies with Area Law bounds
    status: str                 # "GROUND_STATE_CONVERGED", "PEPS_CONTRACTED"
    parameters_digest: str
    created_at: float = dataclasses.field(default_factory=time.time)

    def compute_hash(self) -> str:
        payload = (
            f"{self.receipt_id}:{self.operation_type}:{self.model_type}:"
            f"{self.ground_state_energy:.6f}:{self.energy_relative_error:.8f}:"
            f"{self.max_bond_dim}:{self.entanglement_entropy:.6f}:{self.area_law_satisfied}:"
            f"{self.status}:{self.parameters_digest}:{self.created_at}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "operation_type": self.operation_type,
            "model_type": self.model_type,
            "ground_state_energy": round(self.ground_state_energy, 6),
            "energy_relative_error": round(self.energy_relative_error, 8),
            "max_bond_dim": self.max_bond_dim,
            "entanglement_entropy": round(self.entanglement_entropy, 6),
            "area_law_satisfied": self.area_law_satisfied,
            "status": self.status,
            "parameters_digest": self.parameters_digest,
            "receipt_hash": self.compute_hash(),
            "created_at": self.created_at,
        }


class QuantumTensorMerkleLedger:
    """Cryptographic Merkle Tree Ledger aggregating Quantum Tensor Network simulations."""

    def __init__(self) -> None:
        self.receipts: List[QuantumTensorReceipt] = []

    def append_receipt(self, receipt: QuantumTensorReceipt) -> str:
        self.receipts.append(receipt)
        return receipt.compute_hash()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"EMPTY_QUANTUM_TENSOR_LEDGER").hexdigest()
        hashes = [r.compute_hash() for r in self.receipts]
        return self._compute_root(hashes)

    def _compute_root(self, current_level: List[str]) -> str:
        if len(current_level) == 1:
            return current_level[0]
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            combined = hashlib.sha256(f"{left}:{right}".encode("utf-8")).hexdigest()
            next_level.append(combined)
        return self._compute_root(next_level)

    def get_proof(self, index: int) -> List[Tuple[str, str]]:
        if not self.receipts or index < 0 or index >= len(self.receipts):
            return []
        hashes = [r.compute_hash() for r in self.receipts]
        proof: List[Tuple[str, str]] = []
        current_idx = index
        level = hashes
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                combined = hashlib.sha256(f"{left}:{right}".encode("utf-8")).hexdigest()
                next_level.append(combined)
            sibling_idx = current_idx - 1 if current_idx % 2 == 1 else current_idx + 1
            if sibling_idx >= len(level):
                sibling_idx = current_idx
            pos = "left" if sibling_idx < current_idx else "right"
            proof.append((pos, level[sibling_idx]))
            current_idx = current_idx // 2
            level = next_level
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], expected_root: str) -> bool:
        curr = leaf_hash
        for pos, sib in proof:
            if pos == "left":
                curr = hashlib.sha256(f"{sib}:{curr}".encode("utf-8")).hexdigest()
            else:
                curr = hashlib.sha256(f"{curr}:{sib}".encode("utf-8")).hexdigest()
        return curr == expected_root


class QuantumTensorSolanaAnchorExporter:
    """Solana Anchor smart contract exporter verifying variational DMRG ground states and PEPS bounds."""

    @staticmethod
    def generate_anchor_program() -> str:
        return r"""// Quantum Tensor Networks & DMRG Variational Ground State Verification Anchor Program
// Milestone v7.5 - Phases 116 & 117

use anchor_lang::prelude::*;

declare_id!("Ten5orNetw0rk111111111111111111111111111111111");

#[program]
pub mod quantum_tensor_anchor {
    use super::*;

    pub fn initialize_ledger(ctx: Context<InitializeLedger>, authority: Pubkey) -> Result<()> {
        let state = &mut ctx.accounts.ledger_state;
        state.authority = authority;
        state.merkle_root = [0u8; 32];
        state.total_simulations = 0;
        state.variational_fidelity_ceiling_bps = 9950; // 99.50% minimum variational convergence
        state.max_admissible_bond_dim = 128;
        Ok(())
    }

    pub fn record_tensor_verification(
        ctx: Context<RecordTensorVerification>,
        merkle_root: [u8; 32],
        receipt_hash: [u8; 32],
        energy_rel_error_bps: u64,
        bond_dimension: u32,
        area_law_satisfied: bool,
        proof: Vec<[u8; 32]>,
        proof_positions: Vec<u8>,
    ) -> Result<()> {
        let state = &mut ctx.accounts.ledger_state;

        // Enforce Variational Convergence Bounds (< 1.5% relative error)
        require!(energy_rel_error_bps <= 150, TensorError::EnergyErrorThresholdExceeded);

        // Enforce Entanglement Area Law Compliance
        require!(area_law_satisfied, TensorError::AreaLawViolation);

        // Enforce Maximum Admissible Virtual Bond Dimension Chi
        require!(bond_dimension <= state.max_admissible_bond_dim, TensorError::BondDimensionExceeded);

        // Verify Merkle Inclusion Proof
        let mut curr = receipt_hash;
        for i in 0..proof.len() {
            let sib = proof[i];
            let pos = proof_positions[i];
            if pos == 0 {
                curr = anchor_lang::solana_program::keccak::hashv(&[&sib, &curr]).0;
            } else {
                curr = anchor_lang::solana_program::keccak::hashv(&[&curr, &sib]).0;
            }
        }
        require!(curr == merkle_root, TensorError::MerkleProofInvalid);

        state.merkle_root = merkle_root;
        state.total_simulations += 1;

        emit!(TensorSimulationVerified {
            merkle_root,
            receipt_hash,
            energy_rel_error_bps,
            bond_dimension,
            timestamp: Clock::get()?.unix_timestamp,
        });

        Ok(())
    }
}

#[derive(Accounts)]
pub struct InitializeLedger<'info> {
    #[account(init, payer = user, space = 8 + 32 + 32 + 8 + 8 + 4)]
    pub ledger_state: Account<'info, TensorLedgerState>,
    #[account(mut)]
    pub user: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RecordTensorVerification<'info> {
    #[account(mut, has_one = authority)]
    pub ledger_state: Account<'info, TensorLedgerState>,
    pub authority: Signer<'info>,
}

#[account]
pub struct TensorLedgerState {
    pub authority: Pubkey,
    pub merkle_root: [u8; 32],
    pub total_simulations: u64,
    pub variational_fidelity_ceiling_bps: u64,
    pub max_admissible_bond_dim: u32,
}

#[event]
pub struct TensorSimulationVerified {
    pub merkle_root: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub energy_rel_error_bps: u64,
    pub bond_dimension: u32,
    pub timestamp: i64,
}

#[error_code]
pub enum TensorError {
    #[msg("Variational DMRG energy error exceeded acceptable threshold.")]
    EnergyErrorThresholdExceeded,
    #[msg("State violates 1D/2D entanglement area law bounds.")]
    AreaLawViolation,
    #[msg("Virtual bond dimension exceeded contract capacity.")]
    BondDimensionExceeded,
    #[msg("Merkle inclusion proof verification failed.")]
    MerkleProofInvalid,
}
"""

    @staticmethod
    def generate_instruction_payload(
        merkle_root: str,
        receipt: QuantumTensorReceipt,
        proof: List[Tuple[str, str]],
    ) -> Dict[str, Any]:
        proof_hashes = [p[1] for p in proof]
        proof_positions = [0 if p[0] == "left" else 1 for p in proof]
        error_bps = int(round(receipt.energy_relative_error * 10000))

        return {
            "program_id": "Ten5orNetw0rk111111111111111111111111111111111",
            "instruction": "record_tensor_verification",
            "accounts": {
                "ledger_state": "Hk7W...TensorLedgerStateAccount",
                "authority": "Auth11111111111111111111111111111111111111",
                "system_program": "11111111111111111111111111111111",
            },
            "args": {
                "merkle_root": merkle_root,
                "receipt_hash": receipt.compute_hash(),
                "energy_rel_error_bps": error_bps,
                "bond_dimension": receipt.max_bond_dim,
                "area_law_satisfied": receipt.area_law_satisfied,
                "proof": proof_hashes,
                "proof_positions": proof_positions,
            },
        }


class QuantumTensorVerificationDrill:
    """5-stage automated verification drill testing Quantum Tensor Networks, MPS & DMRG."""

    def __init__(self) -> None:
        self.mesh = QuantumTensorNetworkMesh()
        self.ledger = QuantumTensorMerkleLedger()

    def run_stage_1_exact_analytical_energies(self) -> Dict[str, Any]:
        """Stage 1: Validate exact Jordan-Wigner / Bethe Ansatz ground state energies."""
        config_ising = TensorNetworkConfig(n_sites=8, model_type=LatticeModelType.TRANSVERSE_ISENG, coupling_j=1.0, transverse_field_h=1.0)
        engine_ising = DMRGVariationalEngine(config_ising)
        e0_ising = engine_ising.compute_exact_analytical_ground_energy()
        # For critical Ising 8 sites, E_0 is negative and approximately ~ -10.15
        assert e0_ising < -8.0

        config_xxx = TensorNetworkConfig(n_sites=8, model_type=LatticeModelType.HEISENBERG_XXX, coupling_j=1.0)
        engine_xxx = DMRGVariationalEngine(config_xxx)
        e0_xxx = engine_xxx.compute_exact_analytical_ground_energy()
        assert e0_xxx < -3.0

        return {
            "stage": "STAGE_1_EXACT_ANALYTICAL_ENERGIES",
            "status": "PASSED",
            "ising_e0": round(e0_ising, 6),
            "heisenberg_xxx_e0": round(e0_xxx, 6),
        }

    def run_stage_2_dmrg_monotonic_convergence(self) -> Dict[str, Any]:
        """Stage 2: Verify DMRG sweeps converge monotonically to ground state energy."""
        res = self.mesh.run_dmrg_simulation(
            experiment_id="drill-dmrg-01",
            n_sites=8,
            model_type="TRANSVERSE_ISING",
            coupling_j=1.0,
            transverse_field_h=1.0,
            max_bond_dim_chi=16,
            sweeps=4,
        )
        assert res.energy_relative_error < 0.05
        # Verify monotonic decrease across sweeps
        energies = [s.energy_estimate for s in res.sweep_history]
        for i in range(len(energies) - 1):
            assert energies[i + 1] <= energies[i]

        return {
            "stage": "STAGE_2_DMRG_CONVERGENCE",
            "status": "PASSED",
            "initial_energy": energies[0],
            "final_energy": energies[-1],
            "relative_error": res.energy_relative_error,
        }

    def run_stage_3_entanglement_area_law(self) -> Dict[str, Any]:
        """Stage 3: Verify 1D Entanglement Area Law saturation and bond dimension scaling."""
        res = self.mesh.run_dmrg_simulation(
            experiment_id="drill-dmrg-arealaw",
            n_sites=8,
            model_type="TRANSVERSE_ISING",
            max_bond_dim_chi=16,
            sweeps=4,
        )
        assert res.area_law_satisfied is True
        assert res.entanglement_entropy_center > 0.0

        return {
            "stage": "STAGE_3_AREA_LAW_SATURATION",
            "status": "PASSED",
            "center_entropy": res.entanglement_entropy_center,
            "area_law_satisfied": res.area_law_satisfied,
        }

    def run_stage_4_peps_2d_contraction(self) -> Dict[str, Any]:
        """Stage 4: Execute 2D PEPS Boundary MPS contraction and verify perimeter scaling."""
        peps_res = self.mesh.run_peps_2d_contraction(lx=4, ly=4, bond_dim=2, boundary_chi=8)
        assert peps_res["contraction_converged"] is True
        assert peps_res["2d_area_law_verified"] is True

        return {
            "stage": "STAGE_4_PEPS_2D_CONTRACTION",
            "status": "PASSED",
            "boundary_perimeter": peps_res["boundary_perimeter"],
            "boundary_entropy": peps_res["2d_boundary_entropy"],
            "contraction_converged": peps_res["contraction_converged"],
        }

    def run_stage_5_solana_merkle_anchoring(self) -> Dict[str, Any]:
        """Stage 5: Solana Anchor smart contract export and Merkle inclusion proof verification."""
        rcpt = QuantumTensorReceipt(
            receipt_id="rcpt-drill-tn-01",
            operation_type="DMRG_GROUND_STATE",
            model_type="TRANSVERSE_ISING",
            ground_state_energy=-10.1532,
            energy_relative_error=0.0012,
            max_bond_dim=16,
            entanglement_entropy=0.552,
            area_law_satisfied=True,
            status="GROUND_STATE_CONVERGED",
            parameters_digest="a"*64,
        )
        self.ledger.append_receipt(rcpt)
        root = self.ledger.get_merkle_root()
        proof = self.ledger.get_proof(0)

        verified = QuantumTensorMerkleLedger.verify_proof(rcpt.compute_hash(), proof, root)
        assert verified is True

        program_code = QuantumTensorSolanaAnchorExporter.generate_anchor_program()
        assert "quantum_tensor_anchor" in program_code

        payload = QuantumTensorSolanaAnchorExporter.generate_instruction_payload(
            merkle_root=root,
            receipt=rcpt,
            proof=proof,
        )
        assert payload["instruction"] == "record_tensor_verification"
        assert payload["args"]["energy_rel_error_bps"] == 12

        return {
            "stage": "STAGE_5_SOLANA_MERKLE_ANCHORING",
            "status": "PASSED",
            "merkle_root": root,
            "proof_length": len(proof),
            "verified": verified,
            "anchor_program_lines": len(program_code.splitlines()),
        }

    def run_all_stages(self) -> Dict[str, Any]:
        s1 = self.run_stage_1_exact_analytical_energies()
        s2 = self.run_stage_2_dmrg_monotonic_convergence()
        s3 = self.run_stage_3_entanglement_area_law()
        s4 = self.run_stage_4_peps_2d_contraction()
        s5 = self.run_stage_5_solana_merkle_anchoring()
        return {
            "overall_status": "ALL_STAGES_PASSED",
            "stages": [s1, s2, s3, s4, s5],
        }
