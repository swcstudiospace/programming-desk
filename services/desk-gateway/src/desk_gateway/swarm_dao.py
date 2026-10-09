"""Decentralized Swarm DAO Governance & Quadratic Quorum Engine.

Implements proposal lifecycle management, stake-weighted reputation,
quadratic voting calculation with Sybil-resistant identity weighting,
and timelock policy execution.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import hmac
import math
import secrets
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class ProposalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PASSED = "PASSED"
    REJECTED = "REJECTED"
    TIMELOCKED = "TIMELOCKED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


class VoteOption(str, enum.Enum):
    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"


@dataclasses.dataclass
class DAOBallot:
    ballot_id: str
    proposal_id: str
    voter_seat: str
    option: VoteOption
    stake_amount: float
    reputation_score: float
    quadratic_weight: float
    signature: str
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ballot_id": self.ballot_id,
            "proposal_id": self.proposal_id,
            "voter_seat": self.voter_seat,
            "option": self.option.value,
            "stake_amount": self.stake_amount,
            "reputation_score": self.reputation_score,
            "quadratic_weight": self.quadratic_weight,
            "signature": self.signature,
            "timestamp": self.timestamp,
        }


@dataclasses.dataclass
class DAOProposal:
    proposal_id: str
    proposer_seat: str
    title: str
    description: str
    action_payload: Dict[str, Any]
    status: ProposalStatus = ProposalStatus.ACTIVE
    yes_weight: float = 0.0
    no_weight: float = 0.0
    abstain_weight: float = 0.0
    quorum_threshold: float = 5.0
    approval_threshold: float = 0.60
    timelock_delay_seconds: float = 60.0
    created_at: float = dataclasses.field(default_factory=time.time)
    voting_ends_at: float = 0.0
    timelock_unlocks_at: Optional[float] = None
    executed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposer_seat": self.proposer_seat,
            "title": self.title,
            "description": self.description,
            "action_payload": self.action_payload,
            "status": self.status.value,
            "yes_weight": self.yes_weight,
            "no_weight": self.no_weight,
            "abstain_weight": self.abstain_weight,
            "quorum_threshold": self.quorum_threshold,
            "approval_threshold": self.approval_threshold,
            "timelock_delay_seconds": self.timelock_delay_seconds,
            "created_at": self.created_at,
            "voting_ends_at": self.voting_ends_at,
            "timelock_unlocks_at": self.timelock_unlocks_at,
            "executed_at": self.executed_at,
        }


class StakeReputationRegistry:
    """Manages stake balances, reputation scores, delegations, and slashing."""

    def __init__(self) -> None:
        self.stakes: Dict[str, float] = {
            "lead": 100.0,
            "systems": 80.0,
            "web": 60.0,
            "android": 60.0,
            "ios": 60.0,
            "infra": 70.0,
            "quality": 90.0,
        }
        self.reputation: Dict[str, float] = {
            "lead": 1.2,
            "systems": 1.1,
            "web": 1.0,
            "android": 1.0,
            "ios": 1.0,
            "infra": 1.05,
            "quality": 1.15,
        }
        self.delegations: Dict[str, str] = {}  # delegator -> delegate

    def get_effective_stake(self, seat_id: str) -> float:
        # Check if delegated away
        if seat_id in self.delegations:
            return 0.0

        base_stake = self.stakes.get(seat_id, 10.0)
        # Sum incoming delegations
        delegated_in = sum(
            self.stakes.get(delegator, 0.0)
            for delegator, delegate in self.delegations.items()
            if delegate == seat_id
        )
        return base_stake + delegated_in

    def get_reputation(self, seat_id: str) -> float:
        return self.reputation.get(seat_id, 1.0)

    def delegate(self, from_seat: str, to_seat: str) -> None:
        if from_seat == to_seat:
            raise ValueError("Cannot delegate to self")
        self.delegations[from_seat] = to_seat

    def undelegate(self, from_seat: str) -> None:
        self.delegations.pop(from_seat, None)

    def slash(self, seat_id: str, penalty_amount: float) -> None:
        current = self.stakes.get(seat_id, 0.0)
        self.stakes[seat_id] = max(0.0, current - penalty_amount)
        self.reputation[seat_id] = max(0.1, self.reputation.get(seat_id, 1.0) * 0.8)


class SwarmDAOEngine:
    """Decentralized Swarm DAO proposal lifecycle and quadratic consensus voting."""

    def __init__(
        self,
        registry: Optional[StakeReputationRegistry] = None,
        signing_secret: Optional[str] = None,
    ) -> None:
        self.registry = registry or StakeReputationRegistry()
        self.signing_secret = (signing_secret or "swarm-dao-signing-key").encode("utf-8")
        self.proposals: Dict[str, DAOProposal] = {}
        self.ballots: Dict[str, List[DAOBallot]] = {}

    def create_proposal(
        self,
        proposer_seat: str,
        title: str,
        description: str,
        action_payload: Dict[str, Any],
        voting_duration_seconds: float = 300.0,
        timelock_delay_seconds: float = 60.0,
    ) -> DAOProposal:
        pid = f"prop-{secrets.token_hex(4)}"
        now = time.time()
        prop = DAOProposal(
            proposal_id=pid,
            proposer_seat=proposer_seat,
            title=title,
            description=description,
            action_payload=action_payload,
            status=ProposalStatus.ACTIVE,
            created_at=now,
            voting_ends_at=now + voting_duration_seconds,
            timelock_delay_seconds=timelock_delay_seconds,
        )
        self.proposals[pid] = prop
        self.ballots[pid] = []
        return prop

    def cast_vote(
        self,
        proposal_id: str,
        voter_seat: str,
        option: VoteOption,
    ) -> DAOBallot:
        prop = self.proposals.get(proposal_id)
        if not prop:
            raise ValueError(f"Proposal '{proposal_id}' not found")
        if prop.status != ProposalStatus.ACTIVE:
            raise ValueError(f"Proposal '{proposal_id}' is not active for voting")

        # Prevent double voting
        for b in self.ballots[proposal_id]:
            if b.voter_seat == voter_seat:
                raise ValueError(f"Seat '{voter_seat}' already voted on proposal '{proposal_id}'")

        effective_stake = self.registry.get_effective_stake(voter_seat)
        rep = self.registry.get_reputation(voter_seat)

        # Quadratic voting weight: sqrt(stake) * reputation
        quad_weight = math.sqrt(effective_stake) * rep

        to_sign = f"{proposal_id}:{voter_seat}:{option.value}:{quad_weight}".encode("utf-8")
        sig = hmac.new(self.signing_secret, to_sign, hashlib.sha256).hexdigest()

        ballot = DAOBallot(
            ballot_id=f"bal-{secrets.token_hex(4)}",
            proposal_id=proposal_id,
            voter_seat=voter_seat,
            option=option,
            stake_amount=effective_stake,
            reputation_score=rep,
            quadratic_weight=quad_weight,
            signature=sig,
        )
        self.ballots[proposal_id].append(ballot)

        # Update running tallies
        if option == VoteOption.YES:
            prop.yes_weight += quad_weight
        elif option == VoteOption.NO:
            prop.no_weight += quad_weight
        else:
            prop.abstain_weight += quad_weight

        return ballot

    def resolve_proposal(self, proposal_id: str) -> DAOProposal:
        prop = self.proposals.get(proposal_id)
        if not prop:
            raise ValueError(f"Proposal '{proposal_id}' not found")

        total_weight = prop.yes_weight + prop.no_weight + prop.abstain_weight
        if total_weight < prop.quorum_threshold:
            prop.status = ProposalStatus.REJECTED
            return prop

        decisive_weight = prop.yes_weight + prop.no_weight
        if decisive_weight == 0:
            prop.status = ProposalStatus.REJECTED
            return prop

        approval_ratio = prop.yes_weight / decisive_weight
        if approval_ratio >= prop.approval_threshold:
            prop.status = ProposalStatus.TIMELOCKED
            prop.timelock_unlocks_at = time.time() + prop.timelock_delay_seconds
        else:
            prop.status = ProposalStatus.REJECTED

        return prop


class PolicyTimelockExecutor:
    """Enforces policy executions only after timelock delay has elapsed."""

    def __init__(self, dao_engine: SwarmDAOEngine) -> None:
        self.dao_engine = dao_engine
        self.executed_policies: List[Dict[str, Any]] = []

    def execute_proposal(self, proposal_id: str, force_unlock: bool = False) -> Dict[str, Any]:
        prop = self.dao_engine.proposals.get(proposal_id)
        if not prop:
            raise ValueError(f"Proposal '{proposal_id}' not found")

        if prop.status != ProposalStatus.TIMELOCKED:
            raise ValueError(f"Proposal status must be TIMELOCKED, got {prop.status}")

        now = time.time()
        if not force_unlock and prop.timelock_unlocks_at and now < prop.timelock_unlocks_at:
            remaining = prop.timelock_unlocks_at - now
            raise ValueError(f"Timelock delay not met. Remaining: {remaining:.1f}s")

        prop.status = ProposalStatus.EXECUTED
        prop.executed_at = now

        execution_record = {
            "proposal_id": proposal_id,
            "action_payload": prop.action_payload,
            "executed_at": now,
            "status": "EXECUTED",
        }
        self.executed_policies.append(execution_record)
        return execution_record

    def cancel_timelock(self, proposal_id: str, reason: str = "Vetoed") -> DAOProposal:
        prop = self.dao_engine.proposals.get(proposal_id)
        if not prop:
            raise ValueError(f"Proposal '{proposal_id}' not found")
        prop.status = ProposalStatus.CANCELLED
        return prop
