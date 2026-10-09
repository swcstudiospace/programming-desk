"""Tests for Homomorphic State Encapsulation & Multi-Party Private Inference (Milestone v4.4 - Phase 55)."""

import pytest

from desk_gateway.zk_privacy import (
    HomomorphicCipherEngine,
    PrivateZKAnchorExporter,
    SecureMPCInferenceCoordinator,
    ThresholdSecretSharing,
    ZKPrivacyAgentSwarmDrillSimulator,
)
from desk_gateway.zk_proving import ZKProofReceipt


def test_homomorphic_encryption_and_addition():
    engine = HomomorphicCipherEngine()
    c1 = engine.encrypt(150)
    c2 = engine.encrypt(250)

    c_sum = engine.add(c1, c2)
    decrypted_sum = engine.decrypt(c_sum)
    assert decrypted_sum == 400


def test_homomorphic_scalar_multiplication():
    engine = HomomorphicCipherEngine()
    c = engine.encrypt(45)

    c_mult = engine.multiply_scalar(c, 4)
    decrypted_mult = engine.decrypt(c_mult)
    assert decrypted_mult == 180


def test_threshold_secret_sharing_reconstruction():
    tss = ThresholdSecretSharing()
    secret = 8877665544332211
    shares = tss.split_secret(secret, threshold=3, total_shares=5)

    assert len(shares) == 5
    # Reconstruct with threshold shares
    rec_secret = tss.reconstruct_secret(shares[:3])
    assert rec_secret == secret

    # Reconstruct with different subset of 3 shares
    rec_secret_subset = tss.reconstruct_secret([shares[0], shares[2], shares[4]])
    assert rec_secret_subset == secret

    # Fails with fewer shares than threshold
    with pytest.raises(ValueError, match="Insufficient shares"):
        tss.reconstruct_secret(shares[:2])


def test_mpc_private_inference():
    coord = SecureMPCInferenceCoordinator(required_quorum=3)
    seat_inputs = {
        "lead": [1.0, 2.0],
        "systems": [3.0, 4.0],
        "infra": [2.0, 6.0],
    }
    weights = [0.5, 1.5]

    res = coord.run_mpc_inference("mpc-session-test", seat_inputs, weights)
    assert res.is_consensus_met is True
    assert len(res.participating_seats) == 3

    # Average inputs: [ (1+3+2)/3, (2+4+6)/3 ] = [2.0, 4.0]
    # Prediction: 0.5 * 2.0 + 1.5 * 4.0 = 1.0 + 6.0 = 7.0
    assert abs(res.aggregated_prediction - 7.0) < 1e-5


def test_zk_privacy_agent_swarm_drill_simulator():
    drill_res = ZKPrivacyAgentSwarmDrillSimulator.run_drill()
    assert drill_res["drill_status"] == "SUCCESS"
    assert drill_res["zk_verified"] is True
    assert drill_res["tamper_detected"] is True
    assert drill_res["homomorphic_addition_verified"] is True
    assert drill_res["tss_secret_recovered"] is True
    assert drill_res["anchored_root"] is not None
