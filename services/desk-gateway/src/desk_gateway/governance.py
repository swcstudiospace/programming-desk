"""Decentralized Multi-Desk Governance & Proposal State Machine (Phase 32).

Implements:
- REQ-GOV-001: Multi-desk proposal lifecycle engine with deterministic state machine
               (DRAFT -> ACTIVE -> VOTING -> APPROVED / REJECTED -> QUEUED -> EXECUTED / CANCELLED).
- REQ-GOV-002: Weighted multi-seat quorum evaluation supporting threshold governance,
               quadratic voting, and seat reputation multipliers.
- REQ-GOV-003: Cryptographic ballot signing and non-repudiable vote commitments with HMAC-SHA256 signatures.
- REQ-GOV-004: Proposal timelock buffer and execution delay enforcement preventing instant malicious parameter mutations.
- REQ-GOV-005: Autonomous emergency veto and circuit-breaker abort triggers for anomalous proposals.
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple


class ProposalStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    VOTING = "VOTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    VETOED = "VETOED"


class VoteChoice(str, enum.Enum):
    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"


class Ballot:
    def __init__(
        self,
        proposal_id: str,
        seat: str,
        desk_id: str,
        choice: VoteChoice,
        raw_votes: float = 1.0,
        reputation: float = 1.0,
        signature: str = "",
        timestamp: Optional[float] = None,
        reason: str = "",
    ) -> None:
        self.proposal_id = proposal_id
        self.seat = seat
        self.desk_id = desk_id
        self.choice = choice if isinstance(choice, VoteChoice) else VoteChoice(choice)
        self.raw_votes = max(0.0, float(raw_votes))
        self.reputation = max(0.1, float(reputation))
        self.timestamp = timestamp or time.time()
        self.reason = reason
        self.signature = signature

    @property
    def quadratic_voting_power(self) -> float:
        """Quadratic voting weight: sqrt(raw_votes) * reputation."""
        return math.sqrt(self.raw_votes) * self.reputation

    def digest(self) -> str:
        payload = f"{self.proposal_id}:{self.seat}:{self.desk_id}:{self.choice.value}:{self.raw_votes}:{self.reputation}:{self.timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def sign(self, secret_key: str) -> str:
        msg = self.digest().encode("utf-8")
        sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        self.signature = sig
        return sig

    def verify_signature(self, secret_key: str) -> bool:
        if not self.signature:
            return False
        expected = hmac.new(secret_key.encode("utf-8"), self.digest().encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "seat": self.seat,
            "desk_id": self.desk_id,
            "choice": self.choice.value,
            "raw_votes": self.raw_votes,
            "reputation": self.reputation,
            "quadratic_voting_power": self.quadratic_voting_power,
            "signature": self.signature,
            "timestamp": self.timestamp,
            "reason": self.reason,
            "digest": self.digest(),
        }


class Proposal:
    def __init__(
        self,
        proposal_id: str,
        proposer_seat: str,
        proposer_desk_id: str,
        title: str,
        description: str,
        action_payload: dict[str, Any],
        timelock_delay_seconds: float = 60.0,
        voting_period_seconds: float = 300.0,
        quorum_threshold: float = 0.5,
        approval_threshold: float = 0.66,
        tags: Optional[list[str]] = None,
    ) -> None:
        self.proposal_id = proposal_id
        self.proposer_seat = proposer_seat
        self.proposer_desk_id = proposer_desk_id
        self.title = title
        self.description = description
        self.action_payload = action_payload
        self.timelock_delay_seconds = max(0.0, float(timelock_delay_seconds))
        self.voting_period_seconds = max(1.0, float(voting_period_seconds))
        self.quorum_threshold = quorum_threshold
        self.approval_threshold = approval_threshold
        self.tags = tags or []

        self.status = ProposalStatus.DRAFT
        self.created_at = time.time()
        self.voting_started_at: Optional[float] = None
        self.voting_ended_at: Optional[float] = None
        self.queued_at: Optional[float] = None
        self.executed_at: Optional[float] = None

        self.ballots: dict[str, Ballot] = {}  # key: f"{desk_id}:{seat}"
        self.veto_reason: Optional[str] = None
        self.execution_receipt: Optional[dict[str, Any]] = None

    @property
    def content_hash(self) -> str:
        body = {
            "proposal_id": self.proposal_id,
            "proposer_seat": self.proposer_seat,
            "proposer_desk_id": self.proposer_desk_id,
            "title": self.title,
            "description": self.description,
            "action_payload": self.action_payload,
            "timelock_delay_seconds": self.timelock_delay_seconds,
            "tags": sorted(self.tags),
        }
        serialized = json.dumps(body, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposer_seat": self.proposer_seat,
            "proposer_desk_id": self.proposer_desk_id,
            "title": self.title,
            "description": self.description,
            "action_payload": self.action_payload,
            "status": self.status.value,
            "created_at": self.created_at,
            "voting_started_at": self.voting_started_at,
            "voting_ended_at": self.voting_ended_at,
            "queued_at": self.queued_at,
            "executed_at": self.executed_at,
            "timelock_delay_seconds": self.timelock_delay_seconds,
            "voting_period_seconds": self.voting_period_seconds,
            "quorum_threshold": self.quorum_threshold,
            "approval_threshold": self.approval_threshold,
            "tags": self.tags,
            "content_hash": self.content_hash,
            "ballots_count": len(self.ballots),
            "veto_reason": self.veto_reason,
            "execution_receipt": self.execution_receipt,
        }


class QuorumEvaluationResult:
    def __init__(
        self,
        proposal_id: str,
        quorum_reached: bool,
        approved: bool,
        total_participants: int,
        total_possible_seats: int,
        participation_rate: float,
        yes_weight: float,
        no_weight: float,
        abstain_weight: float,
        approval_ratio: float,
        details: dict[str, Any],
    ) -> None:
        self.proposal_id = proposal_id
        self.quorum_reached = quorum_reached
        self.approved = approved
        self.total_participants = total_participants
        self.total_possible_seats = total_possible_seats
        self.participation_rate = participation_rate
        self.yes_weight = yes_weight
        self.no_weight = no_weight
        self.abstain_weight = abstain_weight
        self.approval_ratio = approval_ratio
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "quorum_reached": self.quorum_reached,
            "approved": self.approved,
            "total_participants": self.total_participants,
            "total_possible_seats": self.total_possible_seats,
            "participation_rate": self.participation_rate,
            "yes_weight": self.yes_weight,
            "no_weight": self.no_weight,
            "abstain_weight": self.abstain_weight,
            "approval_ratio": self.approval_ratio,
            "details": self.details,
        }


class QuorumEngine:
    """Evaluates multi-seat quorums, threshold governance, and quadratic voting."""

    def __init__(self, seat_reputations: Optional[dict[str, float]] = None) -> None:
        self.seat_reputations: dict[str, float] = seat_reputations or {
            "lead": 1.5,
            "quality": 1.4,
            "infra": 1.3,
            "systems": 1.2,
            "security": 1.4,
            "frontend": 1.0,
            "backend": 1.0,
        }

    def get_reputation(self, seat: str) -> float:
        return self.seat_reputations.get(seat, 1.0)

    def set_reputation(self, seat: str, reputation: float) -> None:
        self.seat_reputations[seat] = max(0.1, float(reputation))

    def evaluate_quorum(
        self,
        proposal: Proposal,
        total_possible_seats: int = 7,
        use_quadratic: bool = True,
    ) -> QuorumEvaluationResult:
        participants = len(proposal.ballots)
        participation_rate = participants / max(1, total_possible_seats)
        quorum_reached = participation_rate >= proposal.quorum_threshold

        yes_weight = 0.0
        no_weight = 0.0
        abstain_weight = 0.0

        for ballot in proposal.ballots.values():
            weight = ballot.quadratic_voting_power if use_quadratic else ballot.raw_votes * ballot.reputation
            if ballot.choice == VoteChoice.YES:
                yes_weight += weight
            elif ballot.choice == VoteChoice.NO:
                no_weight += weight
            elif ballot.choice == VoteChoice.ABSTAIN:
                abstain_weight += weight

        effective_votes = yes_weight + no_weight
        approval_ratio = (yes_weight / effective_votes) if effective_votes > 0 else 0.0
        approved = quorum_reached and (approval_ratio >= proposal.approval_threshold)

        return QuorumEvaluationResult(
            proposal_id=proposal.proposal_id,
            quorum_reached=quorum_reached,
            approved=approved,
            total_participants=participants,
            total_possible_seats=total_possible_seats,
            participation_rate=round(participation_rate, 4),
            yes_weight=round(yes_weight, 4),
            no_weight=round(no_weight, 4),
            abstain_weight=round(abstain_weight, 4),
            approval_ratio=round(approval_ratio, 4),
            details={
                "use_quadratic": use_quadratic,
                "effective_votes": round(effective_votes, 4),
                "approval_threshold": proposal.approval_threshold,
                "quorum_threshold": proposal.quorum_threshold,
            },
        )


class TimelockExecutor:
    """Enforces execution delay buffer to prevent instant malicious mutations."""

    def __init__(self, default_min_delay: float = 30.0) -> None:
        self.default_min_delay = default_min_delay

    def can_execute(self, proposal: Proposal, current_time: Optional[float] = None) -> Tuple[bool, str]:
        now = current_time or time.time()
        if proposal.status != ProposalStatus.QUEUED:
            return False, f"Proposal status is {proposal.status.value}, expected QUEUED"

        if proposal.queued_at is None:
            return False, "Proposal queued_at timestamp is unset"

        elapsed = now - proposal.queued_at
        required_delay = max(proposal.timelock_delay_seconds, self.default_min_delay)
        if elapsed < required_delay:
            remaining = round(required_delay - elapsed, 2)
            return False, f"Timelock buffer active: {remaining}s remaining before execution is allowed"

        return True, "Timelock delay satisfied"


class EmergencyVetoCircuitBreaker:
    """Autonomous emergency veto and circuit-breaker abort triggers for anomalous proposals."""

    def __init__(self, veto_seats: Optional[Set[str]] = None, forbidden_actions: Optional[Set[str]] = None) -> None:
        self.veto_seats: Set[str] = veto_seats or {"security", "lead", "quality"}
        self.forbidden_actions: Set[str] = forbidden_actions or {
            "disable_zero_trust",
            "revoke_all_keys",
            "drain_funds",
            "bypass_auth",
            "erase_audit_log",
        }
        self.anomalous_payload_threshold_bytes: int = 1_000_000

    def check_anomaly(self, proposal: Proposal) -> Tuple[bool, Optional[str]]:
        """Inspects proposal for security anomalies or policy violations."""
        action = proposal.action_payload.get("action", "")
        if action in self.forbidden_actions:
            return True, f"Policy violation: Forbidden action '{action}' detected"

        payload_bytes = len(json.dumps(proposal.action_payload).encode("utf-8"))
        if payload_bytes > self.anomalous_payload_threshold_bytes:
            return True, f"Payload size {payload_bytes} exceeds safety threshold {self.anomalous_payload_threshold_bytes}"

        if "destructive_operation" in proposal.action_payload:
            if proposal.action_payload["destructive_operation"] and "quality" not in proposal.tags:
                return True, "Destructive operations require quality oversight tag"

        return False, None

    def can_seat_veto(self, seat: str) -> bool:
        return seat in self.veto_seats


class GovernanceStateMachine:
    """Multi-desk proposal lifecycle engine with deterministic state transitions."""

    def __init__(
        self,
        secret_key: str = "gov-mesh-master-key",
        quorum_engine: Optional[QuorumEngine] = None,
        timelock_executor: Optional[TimelockExecutor] = None,
        circuit_breaker: Optional[EmergencyVetoCircuitBreaker] = None,
    ) -> None:
        self.secret_key = secret_key
        self.quorum_engine = quorum_engine or QuorumEngine()
        self.timelock = timelock_executor or TimelockExecutor()
        self.circuit_breaker = circuit_breaker or EmergencyVetoCircuitBreaker()
        self.proposals: dict[str, Proposal] = {}

    def create_proposal(
        self,
        proposal_id: str,
        proposer_seat: str,
        proposer_desk_id: str,
        title: str,
        description: str,
        action_payload: dict[str, Any],
        timelock_delay_seconds: float = 60.0,
        voting_period_seconds: float = 300.0,
        quorum_threshold: float = 0.5,
        approval_threshold: float = 0.66,
        tags: Optional[list[str]] = None,
    ) -> Proposal:
        if proposal_id in self.proposals:
            raise ValueError(f"Proposal '{proposal_id}' already exists")

        prop = Proposal(
            proposal_id=proposal_id,
            proposer_seat=proposer_seat,
            proposer_desk_id=proposer_desk_id,
            title=title,
            description=description,
            action_payload=action_payload,
            timelock_delay_seconds=timelock_delay_seconds,
            voting_period_seconds=voting_period_seconds,
            quorum_threshold=quorum_threshold,
            approval_threshold=approval_threshold,
            tags=tags,
        )

        # Autonomous anomaly inspection on creation
        is_anomalous, anomaly_reason = self.circuit_breaker.check_anomaly(prop)
        if is_anomalous:
            prop.status = ProposalStatus.VETOED
            prop.veto_reason = f"Automated circuit-breaker veto: {anomaly_reason}"
        else:
            prop.status = ProposalStatus.ACTIVE

        self.proposals[proposal_id] = prop
        return prop

    def start_voting(self, proposal_id: str) -> Proposal:
        prop = self.get_proposal(proposal_id)
        if prop.status not in (ProposalStatus.ACTIVE, ProposalStatus.DRAFT):
            raise ValueError(f"Cannot start voting from status {prop.status.value}")

        prop.status = ProposalStatus.VOTING
        prop.voting_started_at = time.time()
        return prop

    def cast_vote(
        self,
        proposal_id: str,
        seat: str,
        desk_id: str,
        choice: VoteChoice | str,
        raw_votes: float = 1.0,
        reason: str = "",
        signature: Optional[str] = None,
    ) -> Ballot:
        prop = self.get_proposal(proposal_id)
        if prop.status != ProposalStatus.VOTING:
            raise ValueError(f"Proposal '{proposal_id}' is not in VOTING state (current: {prop.status.value})")

        # Check voting deadline
        if prop.voting_started_at and (time.time() - prop.voting_started_at > prop.voting_period_seconds):
            raise TimeoutError("Voting window has expired for this proposal")

        choice_enum = choice if isinstance(choice, VoteChoice) else VoteChoice(choice)
        reputation = self.quorum_engine.get_reputation(seat)

        ballot = Ballot(
            proposal_id=proposal_id,
            seat=seat,
            desk_id=desk_id,
            choice=choice_enum,
            raw_votes=raw_votes,
            reputation=reputation,
            reason=reason,
        )

        if signature:
            ballot.signature = signature
            if not ballot.verify_signature(self.secret_key):
                raise PermissionError("Ballot cryptographic signature verification failed")
        else:
            ballot.sign(self.secret_key)

        key = f"{desk_id}:{seat}"
        prop.ballots[key] = ballot
        return ballot

    def tally_and_resolve(self, proposal_id: str, total_possible_seats: int = 7) -> QuorumEvaluationResult:
        prop = self.get_proposal(proposal_id)
        if prop.status != ProposalStatus.VOTING:
            raise ValueError(f"Proposal '{proposal_id}' is not in VOTING state")

        prop.voting_ended_at = time.time()
        result = self.quorum_engine.evaluate_quorum(prop, total_possible_seats=total_possible_seats)

        if result.approved:
            prop.status = ProposalStatus.APPROVED
        else:
            prop.status = ProposalStatus.REJECTED

        return result

    def queue_for_execution(self, proposal_id: str) -> Proposal:
        prop = self.get_proposal(proposal_id)
        if prop.status != ProposalStatus.APPROVED:
            raise ValueError(f"Cannot queue proposal in status {prop.status.value}; must be APPROVED")

        prop.status = ProposalStatus.QUEUED
        prop.queued_at = time.time()
        return prop

    def execute_proposal(
        self,
        proposal_id: str,
        executor_seat: str,
        current_time: Optional[float] = None,
    ) -> dict[str, Any]:
        prop = self.get_proposal(proposal_id)
        ok, reason = self.timelock.can_execute(prop, current_time=current_time)
        if not ok:
            raise PermissionError(f"Execution rejected: {reason}")

        prop.status = ProposalStatus.EXECUTED
        prop.executed_at = current_time or time.time()

        receipt = {
            "proposal_id": prop.proposal_id,
            "status": prop.status.value,
            "executed_by": executor_seat,
            "executed_at": prop.executed_at,
            "content_hash": prop.content_hash,
            "action": prop.action_payload.get("action", "generic_execute"),
            "receipt_sig": hmac.new(
                self.secret_key.encode("utf-8"),
                f"{prop.proposal_id}:{prop.executed_at}:{prop.content_hash}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest(),
        }
        prop.execution_receipt = receipt
        return receipt

    def emergency_veto(self, proposal_id: str, veto_seat: str, reason: str) -> Proposal:
        prop = self.get_proposal(proposal_id)
        if not self.circuit_breaker.can_seat_veto(veto_seat):
            raise PermissionError(f"Seat '{veto_seat}' is not authorized to exercise emergency veto power")

        if prop.status in (ProposalStatus.EXECUTED, ProposalStatus.CANCELLED):
            raise ValueError(f"Cannot veto proposal in terminal status {prop.status.value}")

        prop.status = ProposalStatus.VETOED
        prop.veto_reason = f"Manual emergency veto by {veto_seat}: {reason}"
        return prop

    def cancel_proposal(self, proposal_id: str, requester_seat: str) -> Proposal:
        prop = self.get_proposal(proposal_id)
        if requester_seat != prop.proposer_seat and requester_seat != "lead":
            raise PermissionError("Only the original proposer or lead can cancel a proposal")

        if prop.status in (ProposalStatus.EXECUTED, ProposalStatus.VETOED):
            raise ValueError(f"Cannot cancel proposal in status {prop.status.value}")

        prop.status = ProposalStatus.CANCELLED
        return prop

    def get_proposal(self, proposal_id: str) -> Proposal:
        if proposal_id not in self.proposals:
            raise KeyError(f"Proposal '{proposal_id}' not found")
        return self.proposals[proposal_id]
