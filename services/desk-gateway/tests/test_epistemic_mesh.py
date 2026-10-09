"""Unit tests for Continuous Epistemic Verification, Counter-Evidence Synthesis & Epistemic Audit Mesh (Phase 59)."""

import pytest

from desk_gateway.epistemic_mesh import (
    CounterEvidenceSynthesizer,
    EpistemicAnchorExporter,
    EpistemicConsistencyVerifier,
    EpistemicProofReceipt,
    EpistemicReceiptLedger,
    MetacognitiveEpistemicDrillSimulator,
    SocraticChallenge,
)


def test_counter_evidence_synthesizer_and_resolution():
    synthesizer = CounterEvidenceSynthesizer()
    challenge = synthesizer.synthesize_challenge(
        hypothesis_id="H_PARTITION_RESILIENT",
        hypothesis_description="Partition replication converges under 100ms",
        current_probability=0.92,
        probe_type="boundary_falsification",
    )
    assert isinstance(challenge, SocraticChallenge)
    assert challenge.target_hypothesis_id == "H_PARTITION_RESILIENT"
    assert challenge.is_refuted is False

    resolved = synthesizer.resolve_challenge(
        challenge_id=challenge.challenge_id,
        is_refuted=True,
        refutation_evidence="Tested under WAN latency injection drill; converged within 65ms.",
    )
    assert resolved.is_refuted is True
    assert resolved.refutation_evidence is not None


def test_epistemic_consistency_verifier_js_divergence():
    verifier = EpistemicConsistencyVerifier()

    # Identical distributions -> 0 JS divergence
    dist1 = {"H_A": 0.7, "H_B": 0.3}
    dist2 = {"H_A": 0.7, "H_B": 0.3}
    jsd_ident = verifier.compute_js_divergence(dist1, dist2)
    assert abs(jsd_ident) < 1e-4

    # Divergent distributions -> non-zero JS divergence
    dist3 = {"H_A": 0.1, "H_B": 0.9}
    jsd_div = verifier.compute_js_divergence(dist1, dist3)
    assert jsd_div > 0.1

    coherence = verifier.verify_coherence(
        seat_beliefs={"seat_1": dist1, "seat_2": dist3},
        divergence_threshold=0.15,
    )
    assert coherence["is_coherent"] is False
    assert len(coherence["divergence_violations"]) == 1


def test_epistemic_receipt_ledger_and_anchor_exporter():
    ledger = EpistemicReceiptLedger()
    r1 = ledger.append_receipt("net-1", "CALIBRATION", {"raw": 0.9, "calib": 0.82})
    r2 = ledger.append_receipt("net-1", "BELIEF_UPDATE", {"posterior": 0.75})

    assert isinstance(r1, EpistemicProofReceipt)
    assert len(ledger.receipts) == 2

    root = ledger.compute_merkle_root()
    assert len(root) == 64

    exporter = EpistemicAnchorExporter()
    anchor = exporter.export_epistemic_commitment(ledger.receipts)
    assert anchor["status"] == "CONFIRMED"
    assert anchor["merkle_root"] == root
    assert "sol-tx-" in anchor["transaction_signature"]


def test_metacognitive_epistemic_drill_simulator():
    drill = MetacognitiveEpistemicDrillSimulator.run_drill()
    assert drill["drill_status"] == "SUCCESS"
    assert drill["circular_reasoning_caught"] is True
    assert drill["socratic_challenge_refuted"] is True
    assert drill["cross_desk_coherent"] is True
    assert len(drill["merkle_root"]) == 64
    assert "sol-tx-" in drill["solana_commitment_signature"]
