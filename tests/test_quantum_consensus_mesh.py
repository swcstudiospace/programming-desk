"""Unit and integration tests for Distributed Quantum Consensus & Byzantine Agreement (Phase 76)."""

import pytest

from desk_gateway.quantum_consensus_mesh import (
    ConsensusPhase,
    QuantumByzantineAgreementEngine,
    QuantumCoinFlipper,
    QuantumConsensusRound,
)


def test_quantum_coin_flipper():
    flipper = QuantumCoinFlipper(default_fidelity=0.99)
    nodes = ["desk-alpha", "desk-beta", "desk-gamma"]
    coin = flipper.flip_quantum_coin("round-1", nodes)

    assert coin.round_id == "round-1"
    assert coin.coin_value in (0, 1)
    assert len(coin.entropy_bits) == 32
    assert coin.fidelity == 0.99
    assert coin.participating_nodes == nodes


def test_quantum_byzantine_agreement_honest_majority():
    engine = QuantumByzantineAgreementEngine()
    nodes = ["desk-alpha", "desk-beta", "desk-gamma", "desk-delta"]
    rnd = engine.start_round(nodes)

    assert rnd.phase == ConsensusPhase.PROPOSE

    # 3 honest nodes propose "PROPOSAL_A", 1 adversarial node proposes "PROPOSAL_B"
    engine.submit_proposal(rnd.round_id, "desk-alpha", "PROPOSAL_A")
    engine.submit_proposal(rnd.round_id, "desk-beta", "PROPOSAL_A")
    engine.submit_proposal(rnd.round_id, "desk-gamma", "PROPOSAL_A")
    engine.submit_proposal(rnd.round_id, "desk-delta", "PROPOSAL_B")

    resolved = engine.execute_agreement_step(rnd.round_id)

    assert resolved.phase == ConsensusPhase.DECIDE
    assert resolved.decision == "PROPOSAL_A"
    assert len(resolved.node_votes) == 4
    for v in resolved.node_votes.values():
        assert v == "PROPOSAL_A"


def test_quantum_byzantine_agreement_split_fallback_to_quantum_coin():
    engine = QuantumByzantineAgreementEngine()
    nodes = ["desk-alpha", "desk-beta", "desk-gamma", "desk-delta"]
    rnd = engine.start_round(nodes)

    # 2 vs 2 split -> no strict majority (> 2) -> fallback to quantum coin
    engine.submit_proposal(rnd.round_id, "desk-alpha", "OPTION_0")
    engine.submit_proposal(rnd.round_id, "desk-beta", "OPTION_0")
    engine.submit_proposal(rnd.round_id, "desk-gamma", "OPTION_1")
    engine.submit_proposal(rnd.round_id, "desk-delta", "OPTION_1")

    resolved = engine.execute_agreement_step(rnd.round_id)

    assert resolved.phase == ConsensusPhase.DECIDE
    assert resolved.quantum_coin is not None
    assert resolved.decision == resolved.quantum_coin.coin_value
