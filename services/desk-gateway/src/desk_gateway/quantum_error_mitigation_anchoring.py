"""Quantum Error Mitigation (QEM) Merkle Ledger & Solana Anchor Exporter (Milestone v6.1 - Phase 89).

Implements:
- QEMReceipt: Cryptographic receipt of error mitigation runs (ZNE, PEC, Readout calibration).
- QEMMerkleLedger: Binary Merkle tree recording error-mitigated execution runs with SHA256 integrity proofs.
- QEMSolanaAnchorExporter: Produces deterministic Solana devnet Anchor program payloads and instructions.
- QEMVerificationDrillSimulator: 5-stage automated verification pipeline validating zero-noise convergence,
  quasi-probability invariance, readout calibration, Merkle root consistency, and Anchor payload integrity.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from desk_gateway.quantum_error_mitigation_mesh import (
    ExtrapolationModel,
    NoiseScalePoint,
    ProbabilisticErrorCanceller,
    ReadoutErrorMitigator,
    ZeroNoiseExtrapolator,
    ZNEResult,
)


@dataclasses.dataclass
class QEMReceipt:
    receipt_id: str
    circuit_id: str
    mitigation_technique: str
    raw_expectation: float
    mitigated_expectation: float
    error_reduction_pct: float
    timestamp: float
    receipt_hash: str

    @classmethod
    def create(
        cls,
        circuit_id: str,
        mitigation_technique: str,
        raw_expectation: float,
        mitigated_expectation: float,
        error_reduction_pct: float,
    ) -> QEMReceipt:
        ts = time.time()
        payload = f"{circuit_id}:{mitigation_technique}:{raw_expectation:.6f}:{mitigated_expectation:.6f}:{ts}"
        r_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        receipt_id = f"qem-rcpt-{r_hash[:12]}"
        return cls(
            receipt_id=receipt_id,
            circuit_id=circuit_id,
            mitigation_technique=mitigation_technique,
            raw_expectation=raw_expectation,
            mitigated_expectation=mitigated_expectation,
            error_reduction_pct=error_reduction_pct,
            timestamp=ts,
            receipt_hash=r_hash,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "circuit_id": self.circuit_id,
            "mitigation_technique": self.mitigation_technique,
            "raw_expectation": round(self.raw_expectation, 6),
            "mitigated_expectation": round(self.mitigated_expectation, 6),
            "error_reduction_pct": round(self.error_reduction_pct, 2),
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }


class QEMMerkleLedger:
    """Cryptographic binary Merkle ledger storing QEM execution receipts."""

    def __init__(self) -> None:
        self.receipts: List[QEMReceipt] = []

    def append_receipt(self, receipt: QEMReceipt) -> None:
        self.receipts.append(receipt)

    def get_root_hash(self) -> str:
        if not self.receipts:
            return hashlib.sha256(b"EMPTY_QEM_LEDGER").hexdigest()
        nodes = [r.receipt_hash for r in self.receipts]
        while len(nodes) > 1:
            if len(nodes) % 2 == 1:
                nodes.append(nodes[-1])
            new_nodes = []
            for i in range(0, len(nodes), 2):
                combined = hashlib.sha256((nodes[i] + nodes[i + 1]).encode("utf-8")).hexdigest()
                new_nodes.append(combined)
            nodes = new_nodes
        return nodes[0]


class QEMSolanaAnchorExporter:
    """Exports QEM Merkle state to Solana Anchor on-chain commitment format."""

    @classmethod
    def export(
        cls,
        ledger: QEMMerkleLedger,
        program_id: str = "QEMMitig11111111111111111111111111111111111",
    ) -> Dict[str, Any]:
        root_hash = ledger.get_root_hash()
        account_data = {
            "authority": "DeskQEMAuthority11111111111111111111111111",
            "merkle_root": root_hash,
            "total_receipts": len(ledger.receipts),
            "latest_receipt_id": ledger.receipts[-1].receipt_id if ledger.receipts else None,
            "timestamp": int(time.time()),
        }
        instruction_data = {
            "program_id": program_id,
            "instruction_name": "commit_qem_root",
            "accounts": [
                {"name": "state_account", "is_mut": True, "is_signer": False},
                {"name": "authority", "is_mut": False, "is_signer": True},
            ],
            "data": account_data,
        }
        return {
            "status": "ANCHOR_PAYLOAD_GENERATED",
            "merkle_root": root_hash,
            "total_receipts": len(ledger.receipts),
            "instruction": instruction_data,
        }


class QEMVerificationDrillSimulator:
    """Executes a 5-point verification drill testing complete QEM pipelines."""

    @classmethod
    def run_drill(cls) -> Dict[str, Any]:
        results: Dict[str, Any] = {"passed": False, "stages": {}}

        # Stage 1: Zero-Noise Extrapolation (ZNE) with Richardson extrapolation
        scale_points = [
            NoiseScalePoint(scale_factor=1.0, measured_expectation=0.82),
            NoiseScalePoint(scale_factor=2.0, measured_expectation=0.71),
            NoiseScalePoint(scale_factor=3.0, measured_expectation=0.62),
        ]
        ideal_target = 0.95
        zne_result = ZeroNoiseExtrapolator.extrapolate(
            scale_points=scale_points,
            model=ExtrapolationModel.RICHARDSON,
            ideal_target=ideal_target,
        )
        s1_pass = zne_result.mitigated_zero_noise_value > zne_result.unmitigated_value
        results["stages"]["stage_1_zne"] = {
            "passed": s1_pass,
            "mitigated_value": zne_result.mitigated_zero_noise_value,
            "error_reduction_pct": zne_result.error_reduction_pct,
        }

        # Stage 2: SPAM Readout Error Inversion
        mitigator = ReadoutErrorMitigator(p0_given_1=0.04, p1_given_0=0.03)
        raw_counts = {"0": 900, "1": 100}
        mitigated_counts = mitigator.mitigate_readout_counts(raw_counts)
        # Raw p0 was 0.90; because p0|1 > p1|0, ideal p0 should be corrected upward
        s2_pass = mitigated_counts["p0"] >= 0.90
        results["stages"]["stage_2_readout"] = {
            "passed": s2_pass,
            "mitigated_counts": mitigated_counts,
        }

        # Stage 3: Probabilistic Error Cancellation (PEC)
        pec = ProbabilisticErrorCanceller(depolarizing_rate=0.03)
        pec_val, gamma = pec.cancel_error(0.85)
        s3_pass = pec_val > 0.85 and gamma > 1.0
        results["stages"]["stage_3_pec"] = {
            "passed": s3_pass,
            "pec_value": pec_val,
            "gamma_overhead": gamma,
        }

        # Stage 4: Cryptographic Merkle Ledger Storage
        ledger = QEMMerkleLedger()
        rcpt1 = QEMReceipt.create("circuit-bell-01", "ZNE_RICHARDSON", 0.82, zne_result.mitigated_zero_noise_value, zne_result.error_reduction_pct)
        rcpt2 = QEMReceipt.create("circuit-ghz-02", "READOUT_INVERSION", 0.90, mitigated_counts["p0"], 15.0)
        ledger.append_receipt(rcpt1)
        ledger.append_receipt(rcpt2)
        root = ledger.get_root_hash()
        s4_pass = len(root) == 64 and root != hashlib.sha256(b"EMPTY_QEM_LEDGER").hexdigest()
        results["stages"]["stage_4_merkle"] = {
            "passed": s4_pass,
            "root_hash": root,
            "receipt_count": len(ledger.receipts),
        }

        # Stage 5: Solana Devnet Anchor Payload Generation
        anchor_export = QEMSolanaAnchorExporter.export(ledger)
        s5_pass = anchor_export["merkle_root"] == root and anchor_export["status"] == "ANCHOR_PAYLOAD_GENERATED"
        results["stages"]["stage_5_anchor"] = {
            "passed": s5_pass,
            "program_id": anchor_export["instruction"]["program_id"],
        }

        results["passed"] = all([s1_pass, s2_pass, s3_pass, s4_pass, s5_pass])
        return results
