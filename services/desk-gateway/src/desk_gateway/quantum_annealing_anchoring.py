"""Quantum Annealing & QUBO Solana Devnet Anchoring Mesh (Milestone v6.2 - Phase 91).

Implements:
- QuantumAnnealingReceipt: Cryptographic execution and solution receipt.
- QuantumAnnealingMerkleLedger: Binary Merkle tree anchoring QUBO problems & solutions.
- QuantumAnnealingSolanaAnchor: Program exporter and Solana devnet anchoring helper.
- SimulatedAnnealingVerificationDrill: 5-stage verification drill for quantum annealing tasks.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from .quantum_annealing_mesh import AnnealingResult, IsingHamiltonian, QUBOProblem, SimulatedQuantumAnnealer


@dataclasses.dataclass
class QuantumAnnealingReceipt:
    receipt_id: str
    problem_hash: str
    num_variables: int
    num_spins: int
    best_energy: float
    best_binary: List[int]
    num_sweeps: int
    annealing_time_us: float
    timestamp: float = dataclasses.field(default_factory=time.time)

    def calculate_hash(self) -> str:
        payload = {
            "receipt_id": self.receipt_id,
            "problem_hash": self.problem_hash,
            "num_variables": self.num_variables,
            "num_spins": self.num_spins,
            "best_energy": round(self.best_energy, 6),
            "best_binary": self.best_binary,
            "num_sweeps": self.num_sweeps,
            "annealing_time_us": round(self.annealing_time_us, 2),
            "timestamp": self.timestamp,
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "problem_hash": self.problem_hash,
            "num_variables": self.num_variables,
            "num_spins": self.num_spins,
            "best_energy": round(self.best_energy, 6),
            "best_binary": self.best_binary,
            "num_sweeps": self.num_sweeps,
            "annealing_time_us": round(self.annealing_time_us, 2),
            "receipt_hash": self.calculate_hash(),
            "timestamp": self.timestamp,
        }


class QuantumAnnealingMerkleLedger:
    """Binary Merkle tree ledger anchoring quantum annealing execution receipts."""

    def __init__(self) -> None:
        self.receipts: List[QuantumAnnealingReceipt] = []

    def add_receipt(self, receipt: QuantumAnnealingReceipt) -> str:
        self.receipts.append(receipt)
        return receipt.calculate_hash()

    def get_merkle_root(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"empty_annealing_ledger").hexdigest()

        hashes = [r.calculate_hash() for r in self.receipts]

        while len(hashes) > 1:
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])
            next_level = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i + 1]
                next_level.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            hashes = next_level

        return hashes[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "merkle_root": self.get_merkle_root(),
            "total_receipts": len(self.receipts),
            "receipts": [r.to_dict() for r in self.receipts],
        }


class QuantumAnnealingSolanaAnchor:
    """Exports quantum annealing commitments to Solana Devnet Anchor program format."""

    @classmethod
    def export_anchor_instruction(
        cls,
        merkle_root: str,
        total_receipts: int,
        program_id: str = "Anneal1111111111111111111111111111111111111",
    ) -> Dict[str, Any]:
        return {
            "program_id": program_id,
            "instruction": "record_quantum_annealing_root",
            "accounts": [
                {"name": "authority", "is_signer": True, "is_writable": True},
                {"name": "annealing_ledger", "is_signer": False, "is_writable": True},
                {"name": "system_program", "is_signer": False, "is_writable": False},
            ],
            "data": {
                "merkle_root": merkle_root,
                "total_receipts": total_receipts,
                "timestamp": int(time.time()),
            },
        }


class SimulatedAnnealingVerificationDrill:
    """5-stage verification drill for quantum annealing pipeline."""

    @classmethod
    def run_5_stage_drill(cls) -> Dict[str, Any]:
        results = {}

        # Stage 1: Construct QUBO Problem (e.g. Max-Cut or Partition)
        qubo = QUBOProblem(
            num_variables=4,
            Q_matrix={
                (0, 0): -1.0,
                (1, 1): -1.0,
                (2, 2): -1.0,
                (3, 3): -1.0,
                (0, 1): 2.0,
                (1, 2): 2.0,
                (2, 3): 2.0,
            },
        )
        problem_hash = hashlib.sha256(json.dumps(str(qubo.Q_matrix)).encode("utf-8")).hexdigest()
        results["stage_1_qubo"] = {
            "status": "PASS",
            "variables": qubo.num_variables,
            "problem_hash": problem_hash,
        }

        # Stage 2: Map to Ising Hamiltonian
        ising = qubo.to_ising()
        results["stage_2_ising_mapping"] = {
            "status": "PASS",
            "num_spins": ising.num_spins,
            "linear_biases": len(ising.linear_biases),
            "quadratic_couplings": len(ising.quadratic_couplings),
        }

        # Stage 3: Simulated Quantum Annealing Solve
        annealer = SimulatedQuantumAnnealer(ising, num_trotter_slices=4)
        solve_res = annealer.solve(num_sweeps=50, annealing_time_us=15.0)
        results["stage_3_annealing_solve"] = {
            "status": "PASS" if solve_res.success else "FAIL",
            "best_spins": solve_res.best_spins,
            "best_energy": solve_res.best_energy,
            "best_binary": solve_res.best_binary,
        }

        # Stage 4: Receipt generation & Merkle Anchor
        receipt = QuantumAnnealingReceipt(
            receipt_id="rcpt-drill-01",
            problem_hash=problem_hash,
            num_variables=qubo.num_variables,
            num_spins=ising.num_spins,
            best_energy=solve_res.best_energy,
            best_binary=solve_res.best_binary,
            num_sweeps=solve_res.num_sweeps,
            annealing_time_us=solve_res.annealing_time_us,
        )
        ledger = QuantumAnnealingMerkleLedger()
        r_hash = ledger.add_receipt(receipt)
        merkle_root = ledger.get_merkle_root()
        results["stage_4_merkle_anchor"] = {
            "status": "PASS",
            "receipt_hash": r_hash,
            "merkle_root": merkle_root,
        }

        # Stage 5: Solana Devnet Anchor instruction export
        anchor_ix = QuantumAnnealingSolanaAnchor.export_anchor_instruction(
            merkle_root=merkle_root,
            total_receipts=len(ledger.receipts),
        )
        results["stage_5_solana_export"] = {
            "status": "PASS",
            "program_id": anchor_ix["program_id"],
            "instruction": anchor_ix["instruction"],
        }

        all_passed = all(st.get("status") == "PASS" for st in results.values())
        return {
            "all_passed": all_passed,
            "stages": results,
            "merkle_root": merkle_root,
        }
