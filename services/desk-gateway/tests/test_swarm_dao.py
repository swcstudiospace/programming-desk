"""Unit tests for Phase 48: Decentralized Swarm DAO Governance & Quadratic Quorum Engine."""

import pytest
from desk_gateway.swarm_dao import (
    SwarmDAOEngine,
    StakeReputationRegistry,
    PolicyTimelockExecutor,
    ProposalStatus,
    VoteOption,
)


def test_stake_reputation_and_delegation():
    reg = StakeReputationRegistry()

    # Initial stake
    lead_stake = reg.get_effective_stake("lead")
    assert lead_stake == 100.0

    # Delegation: systems delegates to lead
    reg.delegate("systems", "lead")
    assert reg.get_effective_stake("systems") == 0.0
    assert reg.get_effective_stake("lead") == 180.0

    # Undelegate
    reg.undelegate("systems")
    assert reg.get_effective_stake("systems") == 80.0
    assert reg.get_effective_stake("lead") == 100.0

    # Slashing
    reg.slash("infra", 30.0)
    assert reg.get_effective_stake("infra") == 40.0


def test_dao_proposal_quadratic_voting_and_resolution():
    reg = StakeReputationRegistry()
    engine = SwarmDAOEngine(registry=reg)

    prop = engine.create_proposal(
        proposer_seat="lead",
        title="Upgrade Memory Limits",
        description="Raise limit to 4GB",
        action_payload={"mem_limit_mb": 4096},
        timelock_delay_seconds=10.0,
    )
    assert prop.status == ProposalStatus.ACTIVE

    # Vote
    b1 = engine.cast_vote(prop.proposal_id, "lead", VoteOption.YES)
    assert b1.quadratic_weight > 0
    assert b1.signature != ""

    # Double voting rejected
    with pytest.raises(ValueError, match="already voted"):
        engine.cast_vote(prop.proposal_id, "lead", VoteOption.YES)

    # Resolve proposal
    engine.cast_vote(prop.proposal_id, "systems", VoteOption.YES)
    engine.cast_vote(prop.proposal_id, "quality", VoteOption.YES)

    resolved = engine.resolve_proposal(prop.proposal_id)
    assert resolved.status == ProposalStatus.TIMELOCKED
    assert resolved.timelock_unlocks_at is not None


def test_policy_timelock_executor():
    reg = StakeReputationRegistry()
    engine = SwarmDAOEngine(registry=reg)
    executor = PolicyTimelockExecutor(engine)

    prop = engine.create_proposal(
        proposer_seat="lead",
        title="Param Change",
        description="test",
        action_payload={"fee": 0.05},
        timelock_delay_seconds=100.0,
    )
    engine.cast_vote(prop.proposal_id, "lead", VoteOption.YES)
    engine.resolve_proposal(prop.proposal_id)

    # Executing before delay fails without force_unlock
    with pytest.raises(ValueError, match="Timelock delay not met"):
        executor.execute_proposal(prop.proposal_id, force_unlock=False)

    # Force unlock succeeds
    res = executor.execute_proposal(prop.proposal_id, force_unlock=True)
    assert res["status"] == "EXECUTED"
    assert res["action_payload"]["fee"] == 0.05
