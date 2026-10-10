"""Faithful distributed-simulator resource and protocol tier (phase 68-02).

Cutover from the audited metadata/scalar defects (amplitude-copy
reconstruction, always-success purification, rejection fallback reuse, the
.85 threshold) to measured joint-state evolution across real worker
leases with a fixed authenticated classical transport.

Math lives in :mod:`desk_gateway.quantum_state` (imported as a namespace;
this module defines no state-vector helpers and re-exports nothing).
All 2/3/4-qubit evolution here uses the frozen kernel
(``tensor`` / ``apply_single`` / ``apply_cnot`` / ``branches_z`` /
``partial_trace`` / ``permute`` / ``fidelity_pure``) with big-endian order.

Causal seams (parent-directed):

- BBPSSW measures the two target qubits *sequentially*: worker A samples
  the first target branch, the joint state is conditioned on that outcome,
  and only then worker B samples the second target. Two independent
  unconditioned I/2 draws would give P_accept=.5 instead of the
  Bennett et al. quant-ph/9511027 value (.887111111111 for .90/.92).
- Teleport / swap BSM branches are sampled by the actual sender /
  repeater worker through ``transport.measure``; the coordinator never
  takes a second unrelated sample to "match" worker evidence.
- The receiver gets only the computed conditional rho (staged to its own
  worker lease) plus two classical bits; it computes
  ``x = m_x ^ frame_x`` / ``z = m_z ^ frame_z`` and applies real X/Z
  worker-side. Original amplitudes never cross the wire.

Conventions: BSM bit order is ``(m_z, m_x)`` — the qubit carrying H is
measured first. Correction order is X-then-Z wherever both apply.
Teleport success is strict raw ``F >= .95`` with no tolerance or clamp;
a .90 Werner resource yields ``(2F+1)/3 = .933333...`` and success False
with the resource still consumed.
"""

from __future__ import annotations

import asyncio
import enum
import math
import re
import secrets
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Mapping, Sequence

from desk_gateway import quantum_state
from desk_gateway.quantum_transport import (
    NodeCommandFailed,
    NodeTransportAmbiguous,
    NodeTransportError,
    NodeTransportUnavailable,
)

__all__ = [
    "BellPairPool",
    "BellStateType",
    "ClassicalCorrection",
    "EntangledBellPair",
    "EntanglementPurifier",
    "EntanglementSwapper",
    "PairSnapshot",
    "PairStatus",
    "PurificationProtocol",
    "PurificationResult",
    "QuantumRepeaterMesh",
    "QuantumRepeaterNode",
    "QuantumResourceError",
    "QuantumTeleportationProtocol",
    "SwapResult",
    "TeleportationResult",
    "TeleportationSession",
    "TeleportOutput",
]

#: Teleport success predicate: strict raw overlap, no tolerance, no clamp.
TELEPORT_FIDELITY_THRESHOLD = 0.95
#: Longest repeater route (nodes) admitted by the mesh.
MAX_ROUTE_NODES = 16

AppendEvent = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]

#: Pool-side codes that mark a worker mutation as possibly applied. Any
#: failure carrying one of these quarantines the affected pairs instead of
#: releasing them back to active; anything else pre-mutation releases.
_AMBIGUOUS_CODES = frozenset({"transport_ambiguous", "evidence_mismatch", "correction_failed"})


@dataclass(frozen=True, slots=True)
class TeleportOutput:
    """Session-scoped ownership of one completed receiver-side output.

    A successful teleport parks the corrected state on the receiver worker
    lease; this record binds that lease (plus the original pinned instance)
    to the session and receiver until the owner releases it. Only IDs and
    status travel here, never credentials or amplitudes.
    """

    session_id: str
    receiver: str
    resource_id: str
    lease_id: str
    instance_id: str
    status: str  # "available" | "released" | "quarantined"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "receiver": self.receiver,
            "resource_id": self.resource_id,
            "lease_id": self.lease_id,
            "instance_id": self.instance_id,
            "status": self.status,
        }


class QuantumResourceError(Exception):
    """Fail-closed domain refusal with a stable machine-readable code."""

    def __init__(self, code: str, detail: str, *, status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": self.code, "detail": self.detail}


class BellStateType(str, enum.Enum):
    PHI_PLUS = "PHI_PLUS"    # (|00> + |11>) / sqrt(2)
    PHI_MINUS = "PHI_MINUS"  # (|00> - |11>) / sqrt(2)
    PSI_PLUS = "PSI_PLUS"    # (|01> + |10>) / sqrt(2)
    PSI_MINUS = "PSI_MINUS"  # (|01> - |10>) / sqrt(2)

class PairStatus(str, enum.Enum):
    ACTIVE = "active"
    RESERVED = "reserved"
    CONSUMED = "consumed"
    DISCARDED = "discarded"
    QUARANTINED = "quarantined"


class PurificationProtocol(str, enum.Enum):
    BBPSSW = "BBPSSW"


def _check_node(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise QuantumResourceError("invalid_node", f"{name} must be a 1..64 char string", status=400)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise QuantumResourceError("invalid_node", f"{name} holds illegal characters", status=400)
    return value


def _check_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise QuantumResourceError("invalid_id", f"{name} must be a 1..128 char string", status=400)
    return value


def _check_fidelity(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise QuantumResourceError("invalid_fidelity", f"{name} must be a finite number", status=400)
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise QuantumResourceError("invalid_fidelity", f"{name} must lie in [0, 1]", status=400)
    return result


def _check_kind(value: object) -> BellStateType:
    if isinstance(value, BellStateType):
        return value
    raise QuantumResourceError("invalid_bell_kind", "state_type must be a BellStateType member", status=400)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _sample_branches(branches: Sequence[Any], rng: Any) -> Any:
    """Coordinator-side cumulative draw; mirrors the kernel convention."""
    total = math.fsum(branch.probability for branch in branches)
    drawn = rng.random()
    if isinstance(drawn, bool) or not isinstance(drawn, (int, float)) or not 0.0 <= float(drawn) < 1.0:
        raise QuantumResourceError("rng_failure", "RNG draw outside [0, 1)", status=503)
    cutoff = float(drawn) * total
    cumulative = 0.0
    for branch in branches:
        cumulative += branch.probability
        if cutoff < cumulative:
            return branch
    return branches[-1]


@dataclass(frozen=True, slots=True)
class EntangledBellPair:
    """Authoritative pair: ordered endpoints, exact untwirled two-qubit rho.

    ``fidelity`` is always derived from ``rho``; there is no writable
    scalar. Only :class:`BellPairPool` records may be consumed.
    """

    pair_id: str
    state_type: BellStateType
    node_a: str
    node_b: str
    rho: Any

    def __post_init__(self) -> None:
        _check_id(self.pair_id, "pair_id")
        _check_node(self.node_a, "node_a")
        _check_node(self.node_b, "node_b")
        if self.node_a == self.node_b:
            raise QuantumResourceError("invalid_endpoints", "pair endpoints must differ", status=400)
        _check_kind(self.state_type)
        if not isinstance(self.rho, quantum_state.QuantumDensityMatrix) or self.rho.qubits != 2:
            raise QuantumResourceError("invalid_state", "pair rho must be a two-qubit density", status=400)

    @property
    def frame(self) -> tuple[int, int]:
        return quantum_state.BellState(self.state_type.value).frame

    @property
    def fidelity(self) -> float:
        ideal = quantum_state.BellState(self.state_type.value).ideal_vector()
        return self.rho.fidelity_pure(ideal)

    def oriented(self, first: str, second: str) -> Any:
        """Return ``rho`` ordered as ``(first, second)`` (either orientation)."""
        if (self.node_a, self.node_b) == (first, second):
            return self.rho
        if (self.node_a, self.node_b) == (second, first):
            return self.rho.permute((1, 0))
        raise QuantumResourceError("endpoint_mismatch", "pair does not link these endpoints")

    def to_dict(self, status: str | None = None) -> dict[str, Any]:
        body = {
            "pair_id": self.pair_id,
            "state_type": self.state_type.value,
            "node_a": self.node_a,
            "node_b": self.node_b,
            "fidelity": self.fidelity,
        }
        if status is not None:
            body["status"] = status
        return body


@dataclass(frozen=True, slots=True)
class PairSnapshot:
    """Immutable public read view: allocation / lifecycle / frame / fidelity."""

    pair_id: str
    state_type: BellStateType
    node_a: str
    node_b: str
    fidelity: float
    status: PairStatus
    leases: tuple = ()


@dataclass
class _PairRecord:
    pair: EntangledBellPair
    status: PairStatus = PairStatus.ACTIVE
    holder: str | None = None
    leases: dict[str, str] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)


class BellPairPool:
    """Sole lifecycle authority for Bell resources (async; lock-guarded).

    Capacity lives in the workers: every pair holds one lease per
    endpoint. ``transport=None`` is explicit unit-math mode with no
    worker enforcement. ``append_event`` is the duck-typed async sink;
    when present, lifecycle events are emitted exactly once.
    """

    def __init__(
        self,
        *,
        rng: Any | None = None,
        transport: Any | None = None,
        append_event: AppendEvent | None = None,
    ) -> None:
        import secrets as _secrets

        self._rng = rng if rng is not None else _secrets.SystemRandom()
        self._transport = transport
        self._append_event = append_event
        self._records: dict[str, _PairRecord] = {}
        self._lock = asyncio.Lock()
        # Uncertain worker reserves keyed by (operation ID, resource ID):
        # an ambiguous reserve reply leaves the worker-side effect unknown,
        # so the uncertainty is preserved here until a read-only inspection
        # reclaims (adopts) or refutes it. Mutations are never retried.
        self._uncertain: dict[tuple[str, str], dict[str, Any]] = {}

    # -- reads (synchronous, immutable) -----------------------------------

    def get_pair(self, pair_id: str) -> EntangledBellPair | None:
        record = self._records.get(pair_id)
        return record.pair if record is not None else None

    def status_of(self, pair_id: str) -> PairStatus | None:
        record = self._records.get(pair_id)
        return record.status if record is not None else None

    def snapshot(self, pair_id: str) -> PairSnapshot | None:
        record = self._records.get(pair_id)
        if record is None:
            return None
        pair = record.pair
        return PairSnapshot(
            pair_id=pair.pair_id,
            state_type=pair.state_type,
            node_a=pair.node_a,
            node_b=pair.node_b,
            fidelity=pair.fidelity,
            status=record.status,
            leases=tuple(sorted(record.leases.items())),
        )

    def list_active_pairs(self, node_a: str | None = None, node_b: str | None = None) -> list[PairSnapshot]:
        out: list[PairSnapshot] = []
        for record in self._records.values():
            if record.status is not PairStatus.ACTIVE:
                continue
            pair = record.pair
            if node_a is not None and node_b is not None:
                if {pair.node_a, pair.node_b} != {node_a, node_b}:
                    continue
            snapshot = self.snapshot(pair.pair_id)
            if snapshot is not None:
                out.append(snapshot)
        return out

    # -- events --------------------------------------------------------------

    async def _emit(
        self,
        event_type: str,
        *,
        session_id: str,
        actor: str,
        nodes: Sequence[str],
        resources: Sequence[str],
        outcome: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if self._append_event is None:
            return None
        event = {
            "event_type": event_type,
            "session_id": session_id,
            "actor": actor,
            "nodes": list(nodes),
            "resources": list(resources),
            "outcome": outcome,
            "payload": dict(payload),
        }
        return await self._append_event(event)

    # -- worker plumbing -------------------------------------------------------

    async def _instances(self, nodes: Sequence[str]) -> dict[str, str]:
        if self._transport is None:
            return {}
        out: dict[str, str] = {}
        for node in nodes:
            try:
                info = await self._transport.inspect(node)
            except NodeTransportUnavailable as exc:
                raise QuantumResourceError(
                    "worker_unavailable", f"worker {node} unavailable for inspect: {exc}", status=503,
                ) from exc
            except NodeTransportError as exc:
                raise QuantumResourceError(
                    "worker_refused", f"worker {node} refused inspect: {exc}",
                ) from exc
            out[node] = info["instance_id"]
        return out

    async def _reserve_worker(
        self, node: str, *, operation_id: str, resource_id: str, count: int,
        session_id: str | None, instances: Mapping[str, str],
    ) -> list[str]:
        if self._transport is None:
            return []
        try:
            response = await self._transport.reserve(
                node, operation_id=operation_id, resource_id=resource_id,
                count=count, session_id=session_id, instance=instances.get(node),
            )
        except NodeTransportUnavailable as exc:
            raise QuantumResourceError(
                "worker_unavailable", f"worker {node} unavailable for reserve: {exc}", status=503,
            ) from exc
        except NodeTransportAmbiguous as exc:
            # The reserve may have applied: reclaim through a read-only
            # inspection, never by retrying the mutation.
            return await self._reclaim_uncertain_reserve(
                node, operation_id=operation_id, resource_id=resource_id,
                count=count, session_id=session_id, cause=exc, instance=instances[node],
            )
        except (NodeCommandFailed, NodeTransportError) as exc:
            raise QuantumResourceError("worker_refused", f"worker {node} refused reserve: {exc}") from exc
        return list(response["leases"])

    async def _release_worker(
        self, node: str, *, operation_id: str, lease_ids: Sequence[str],
        instances: Mapping[str, str],
    ) -> None:
        if self._transport is None:
            return
        try:
            await self._transport.release(
                node, operation_id=operation_id, lease_ids=list(lease_ids),
                instance=instances.get(node),
            )
        except NodeCommandFailed as exc:
            if exc.code in ("already_released", "unknown_lease"):
                return
            raise QuantumResourceError("worker_refused", f"worker {node} refused release") from exc
        except NodeTransportAmbiguous as exc:
            raise QuantumResourceError("transport_ambiguous", f"worker {node} release is ambiguous") from exc
        except NodeTransportUnavailable as exc:
            raise QuantumResourceError("worker_unavailable", f"worker {node} unavailable for release", status=503) from exc
        except NodeTransportError as exc:
            raise QuantumResourceError("worker_refused", f"worker {node} refused release") from exc

    async def _reclaim_uncertain_reserve(
        self, node: str, *, operation_id: str, resource_id: str, count: int,
        session_id: str | None, cause: BaseException, instance: str,
    ) -> list[str]:
        """Adopt positively identified leases; never refute a pending effect."""
        key = (operation_id, resource_id)
        try:
            info = await self._transport.inspect(node, instance=instance, resource_ids=[resource_id])
            if info.get("instance_id") != instance:
                raise NodeTransportAmbiguous("reserve inspection changed worker instance")
        except NodeTransportError as exc:
            async with self._lock:
                self._uncertain[key] = {
                    "node": node, "instance_id": instance, "count": count,
                    "session_id": session_id, "status": "unresolved",
                }
            raise QuantumResourceError(
                "transport_ambiguous",
                f"worker {node} reserve ambiguous and inspection failed: {cause}",
            ) from cause
        found = [
            entry.get("lease_id") for entry in info.get("leases", [])
            if isinstance(entry, Mapping)
            and entry.get("resource_id") == resource_id
            and entry.get("session_id") == session_id
            and entry.get("lease_id")
        ]
        if len(found) == count:
            adopted = list(found[:count])
            async with self._lock:
                self._uncertain[key] = {
                    "node": node, "instance_id": instance, "count": count, "session_id": session_id,
                    "status": "adopted", "lease_ids": list(adopted),
                }
            return adopted
        async with self._lock:
            self._uncertain[key] = {
                "node": node, "instance_id": instance, "count": count, "session_id": session_id,
                "status": "partial" if found else "unresolved",
                "lease_ids": list(found),
            }
        raise QuantumResourceError(
            "transport_ambiguous", f"worker {node} reserve remains unconfirmed for {resource_id}",
        ) from cause

    def uncertain_reserves(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Copy of the (operation ID, resource ID) uncertainty ledger."""
        return {key: dict(entry) for key, entry in self._uncertain.items()}

    async def _release_reservation_quiet(self, pair_ids: Sequence[str], *, operation_id: str) -> None:
        try:
            await self.release_reservation(pair_ids, operation_id=operation_id)
        except (QuantumResourceError, NodeTransportError):
            pass

    async def _quarantine_quiet(self, pair_ids: Sequence[str], *, reason: str) -> None:
        try:
            await self.quarantine_pairs(pair_ids, reason=reason)
        except (QuantumResourceError, NodeTransportError):
            pass

    async def _release_granted_quiet(
        self, granted: Sequence[tuple[str, str]], *, operation_id: str,
        instances: Mapping[str, str],
    ) -> None:
        """Best-effort terminal cleanup of worker leases this operation owns."""
        for index, (node, lease_id) in enumerate(granted):
            try:
                await self._release_worker(
                    node, operation_id=f"{operation_id}-cleanup-{index}",
                    lease_ids=[lease_id], instances=instances,
                )
            except Exception:
                pass

    async def detach_lease(self, pair_id: str, node: str) -> str | None:
        """Move one node's lease off a terminal record to an output owner.

        Infallible by construction: a missing record or lease yields None so
        the caller never leaks a live worker lease on a bookkeeping miss.
        """
        async with self._lock:
            record = self._records.get(pair_id)
            if record is None:
                return None
            return record.leases.pop(node, None)

    async def _worker_branch(
        self, *, node: str, operation_id: str, lease_ids: Sequence[str],
        branches: Sequence[Any], instances: Mapping[str, str], rng: Any | None = None,
    ) -> Any:
        """One worker draw selects the joint-registry branch. No second sample."""
        if self._transport is None or not lease_ids:
            return _sample_branches(branches, rng if rng is not None else self._rng)
        try:
            response = await self._transport.measure(
                node, operation_id=operation_id, lease_ids=list(lease_ids),
                branch_probabilities=[branch.probability for branch in branches],
                branch_bits=[list(branch.bits) for branch in branches],
                instance=instances.get(node),
            )
        except NodeTransportAmbiguous as exc:
            raise QuantumResourceError("transport_ambiguous", f"worker {node} measurement ambiguous: {exc}") from exc
        except (NodeCommandFailed, NodeTransportError) as exc:
            raise QuantumResourceError("worker_refused", f"worker {node} refused measure: {exc}") from exc
        got = tuple(response["bits"])
        for branch in branches:
            if branch.bits == got:
                return branch
        raise QuantumResourceError("measurement_mismatch", "worker returned bits outside the joint branches")

    # -- lifecycle ---------------------------------------------------------------

    async def create_pair(
        self,
        node_a: str,
        node_b: str,
        state_type: BellStateType = BellStateType.PHI_PLUS,
        fidelity: float = 0.99,
        *,
        operation_id: str | None = None,
    ) -> EntangledBellPair:
        _check_node(node_a, "node_a")
        _check_node(node_b, "node_b")
        if node_a == node_b:
            raise QuantumResourceError("invalid_endpoints", "pair endpoints must differ", status=400)
        kind = _check_kind(state_type)
        fidelity = _check_fidelity(fidelity, "fidelity")
        pair_id = _new_id("bell")
        rho = quantum_state.BellState(kind.value).density(fidelity)
        pair = EntangledBellPair(pair_id=pair_id, state_type=kind, node_a=node_a, node_b=node_b, rho=rho)
        op_id = operation_id or _new_id("op")
        instances = await self._instances((node_a, node_b)) if self._transport is not None else {}
        leases: dict[str, str] = {}
        granted: list[tuple[str, str]] = []
        try:
            for node in (node_a, node_b):
                held = await self._reserve_worker(
                    node, operation_id=f"{op_id}-{node}", resource_id=pair_id,
                    count=1, session_id=None, instances=instances,
                )
                if held:
                    leases[node] = held[0]
                    granted.append((node, held[0]))
        except BaseException:
            await self._release_granted_quiet(granted, operation_id=op_id, instances=instances)
            raise
        async with self._lock:
            self._records[pair_id] = _PairRecord(pair=pair, status=PairStatus.ACTIVE, leases=leases, history=["created"])
            for key, entry in self._uncertain.items():
                if key[1] == pair_id and entry.get("status") == "adopted":
                    self._records[pair_id].history.append(f"uncertain-reserve-adopted:{key[0]}")
        try:
            await self._emit(
                "bell.created", session_id=op_id, actor="pool",
                nodes=[node_a, node_b], resources=[pair_id], outcome="created",
                payload={"state_type": kind.value, "fidelity": pair.fidelity},
            )
        except BaseException as exc:
            async with self._lock:
                self._records.pop(pair_id, None)
            await self._release_granted_quiet(granted, operation_id=op_id, instances=instances)
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, QuantumResourceError):
                raise
            raise QuantumResourceError("receipt_failed", f"event sink refused bell.created: {exc}") from exc
        return pair

    async def reserve_pairs(
        self, pair_ids: Sequence[str], *, operation_id: str, session_id: str | None = None,
    ) -> list[EntangledBellPair]:
        _check_id(operation_id, "operation_id")
        if not pair_ids or len(set(pair_ids)) != len(list(pair_ids)) or len(pair_ids) > 4:
            raise QuantumResourceError("invalid_selection", "select 1..4 distinct pair IDs", status=400)
        for pair_id in pair_ids:
            _check_id(pair_id, "pair_id")
        async with self._lock:
            records = []
            for pair_id in pair_ids:
                record = self._records.get(pair_id)
                if record is None:
                    raise QuantumResourceError("unknown_pair", f"pair {pair_id} is unknown", status=404)
                if record.status is not PairStatus.ACTIVE:
                    raise QuantumResourceError(
                        "pair_unavailable", f"pair {pair_id} is {record.status.value}, not active", status=409,
                    )
                records.append(record)
            for record in records:
                record.status = PairStatus.RESERVED
                record.holder = operation_id
                record.history.append(f"reserved:{operation_id}")
            return [record.pair for record in records]

    async def release_reservation(self, pair_ids: Sequence[str], *, operation_id: str) -> None:
        ids = list(pair_ids)
        async with self._lock:
            for pair_id in ids:
                record = self._records.get(pair_id)
                if record is None or record.status is not PairStatus.RESERVED or record.holder != operation_id:
                    raise QuantumResourceError("pair_unavailable", f"pair {pair_id} is not reserved by this operation")
            for pair_id in ids:
                record = self._records[pair_id]
                record.status = PairStatus.ACTIVE
                record.holder = None
                record.history.append(f"released:{operation_id}")

    async def _retire_locked(
        self, pair_ids: Sequence[str], *, operation_id: str, terminal: PairStatus, verb: str,
    ) -> None:
        ids = list(pair_ids)
        if len(set(ids)) != len(ids):
            raise QuantumResourceError("invalid_selection", "retirement needs distinct pair IDs", status=400)
        for pair_id in ids:
            record = self._records.get(pair_id)
            if record is None or record.status is not PairStatus.RESERVED or record.holder != operation_id:
                raise QuantumResourceError("pair_unavailable", f"pair {pair_id} is not reserved by this operation")
        for pair_id in ids:
            record = self._records[pair_id]
            record.status = terminal
            record.holder = None
            record.history.append(f"{verb}:{operation_id}")

    async def consume_pairs(self, pair_ids: Sequence[str], *, operation_id: str) -> None:
        async with self._lock:
            await self._retire_locked(pair_ids, operation_id=operation_id, terminal=PairStatus.CONSUMED, verb="consumed")

    async def discard_pairs(self, pair_ids: Sequence[str], *, operation_id: str) -> None:
        async with self._lock:
            await self._retire_locked(pair_ids, operation_id=operation_id, terminal=PairStatus.DISCARDED, verb="discarded")

    async def quarantine_pairs(self, pair_ids: Sequence[str], *, reason: str) -> None:
        async with self._lock:
            for pair_id in pair_ids:
                record = self._records.get(pair_id)
                if record is None:
                    continue
                record.status = PairStatus.QUARANTINED
                record.holder = None
                record.history.append(f"quarantined:{reason}")

    async def register_output(
        self, pair: EntangledBellPair, *, input_ids: Sequence[str], leases: Mapping[str, str],
        operation_id: str, terminal: PairStatus = PairStatus.CONSUMED,
    ) -> None:
        async with self._lock:
            if pair.pair_id in self._records:
                raise QuantumResourceError("duplicate_pair", f"pair {pair.pair_id} already exists")
            await self._retire_locked(
                list(input_ids), operation_id=operation_id,
                terminal=terminal, verb="consumed" if terminal is PairStatus.CONSUMED else "discarded",
            )
            # Survivor transfer: leases moving to the output leave the retired
            # inputs at registration time, so each lease has exactly one
            # owning live record and a later input cleanup can never release
            # a live output lease.
            transferred = set(dict(leases).values())
            for input_id in set(input_ids):
                record = self._records.get(input_id)
                if record is not None:
                    record.leases = {
                        node: lease_id for node, lease_id in record.leases.items()
                        if lease_id not in transferred
                    }
            self._records[pair.pair_id] = _PairRecord(
                pair=pair, status=PairStatus.ACTIVE, leases=dict(leases), history=["created"],
            )

    async def release_pair_leases(self, pair_id: str, *, operation_id: str) -> None:
        _check_id(operation_id, "operation_id")
        async with self._lock:
            record = self._records.get(pair_id)
            if record is None:
                raise QuantumResourceError("unknown_pair", f"pair {pair_id} is unknown", status=404)
            if record.status in (PairStatus.ACTIVE, PairStatus.RESERVED):
                raise QuantumResourceError("pair_unavailable", "only terminal pairs release worker leases")
            leases = dict(record.leases)
        if self._transport is None:
            return
        instances = await self._instances(tuple(leases))
        for node, lease_id in leases.items():
            await self._release_worker(
                node, operation_id=f"{operation_id}-{node}", lease_ids=[lease_id], instances=instances,
            )

    def leases_of(self, pair_id: str) -> dict[str, str]:
        record = self._records.get(pair_id)
        if record is None:
            raise QuantumResourceError("unknown_pair", f"pair {pair_id} is unknown", status=404)
        return dict(record.leases)


def _canonicalize_to_phi_plus(rho: Any, kind: BellStateType) -> Any:
    """Real local frame gates mapping ``kind`` to |Phi+> (density: order-free)."""
    x, z = quantum_state.BellState(kind.value).frame
    if x:
        rho = rho.apply_single(quantum_state.X, 1)
    if z:
        rho = rho.apply_single(quantum_state.Z, 1)
    return rho


@dataclass(frozen=True, slots=True)
class PurificationResult:
    protocol: str
    accepted: bool
    pair_ids: tuple
    output_pair_id: str | None
    p_accept: float
    branch_bits: tuple
    branch_probability: float
    output_fidelity: float | None
    reason: str
    receipt: Any = None


class EntanglementPurifier:
    """Pool-mediated 2-to-1 BBPSSW distillation with genuine rejection."""

    def __init__(self, pool: BellPairPool, *, rng: Any | None = None) -> None:
        import secrets as _secrets

        self.pool = pool
        self._rng = rng if rng is not None else _secrets.SystemRandom()

    async def purify(
        self, pair_id_1: str, pair_id_2: str, *, operation_id: str | None = None,
    ) -> PurificationResult:
        _check_id(pair_id_1, "pair_id_1")
        _check_id(pair_id_2, "pair_id_2")
        if pair_id_1 == pair_id_2:
            raise QuantumResourceError("same_resource", "purification needs two distinct pairs", status=400)
        op_id = operation_id or _new_id("op")
        pairs = await self.pool.reserve_pairs((pair_id_1, pair_id_2), operation_id=op_id)
        first, second = pairs
        if {first.node_a, first.node_b} != {second.node_a, second.node_b}:
            await self.pool._release_reservation_quiet((pair_id_1, pair_id_2), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise QuantumResourceError("endpoint_mismatch", "purification needs equal unordered endpoint sets")
        node_a, node_b = first.node_a, first.node_b
        rho1 = _canonicalize_to_phi_plus(first.oriented(node_a, node_b), first.state_type)
        rho2 = _canonicalize_to_phi_plus(second.oriented(node_a, node_b), second.state_type)
        ideal = quantum_state.BellState("PHI_PLUS").ideal_vector()
        # Joint order (A_keep, B_keep, A_target, B_target); bilateral CNOTs.
        joint = rho1.tensor(rho2).apply_cnot(0, 2).apply_cnot(1, 3)
        # Actual-state acceptance odds: total probability of the equal-bit
        # target branches of the evolved joint state. This coincides with the
        # Werner-only closed form on Werner inputs and stays truthful for
        # untwirled survivors, where the isotropic formula no longer applies.
        p_accept = math.fsum(
            branch.probability for branch in joint.branches_z((2, 3)) if branch.bits[0] == branch.bits[1]
        )
        leases = {pair_id_1: self.pool.leases_of(pair_id_1), pair_id_2: self.pool.leases_of(pair_id_2)}
        try:
            instances = await self.pool._instances((node_a, node_b))  # noqa: SLF001 - pool-owned plumbing
        except (QuantumResourceError, NodeTransportError):
            await self.pool._release_reservation_quiet((pair_id_1, pair_id_2), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        # Worker leases this operation currently owns; cleared only by an
        # explicit worker release or by register_output moving ownership to
        # the pool. Anything left here on failure is terminal-cleaned.
        granted: list[tuple[str, str]] = [
            (node, lease_id)
            for pid in (pair_id_1, pair_id_2) for node, lease_id in leases[pid].items()
            if lease_id
        ]
        worker_mutated = False
        output_id: str | None = None
        output_registered = False
        try:
            first_branches = joint.branches_z((2,))
            first_pick = await self.pool._worker_branch(  # noqa: SLF001 - pool-owned plumbing
                node=node_a, operation_id=f"{op_id}-meas-a",
                lease_ids=[leases[pair_id_2][node_a]] if leases[pair_id_2].get(node_a) else [],
                branches=first_branches, instances=instances, rng=self._rng,
            )
            worker_mutated = True
            conditioned = first_pick.state
            second_branches = conditioned.branches_z((3,))
            second_pick = await self.pool._worker_branch(  # noqa: SLF001 - pool-owned plumbing
                node=node_b, operation_id=f"{op_id}-meas-b",
                lease_ids=[leases[pair_id_2][node_b]] if leases[pair_id_2].get(node_b) else [],
                branches=second_branches, instances=instances, rng=self._rng,
            )
            bit_a = first_pick.bits[0]
            bit_b = second_pick.bits[0]
            branch_probability = first_pick.probability * second_pick.probability
            accepted = bit_a == bit_b
            if accepted:
                retained = second_pick.state.partial_trace((0, 1))
                output_fidelity = retained.fidelity_pure(ideal)
                output_id = _new_id("purified")
                output = EntangledBellPair(
                    pair_id=output_id, state_type=BellStateType.PHI_PLUS,
                    node_a=node_a, node_b=node_b, rho=retained,
                )
                # Survivor transfer: keep-side (pair 1) leases move to the output.
                transport = self.pool._transport  # noqa: SLF001 - pool-owned plumbing
                if transport is not None:
                    try:
                        for node in (node_a, node_b):
                            await transport.transfer(
                                node, operation_id=f"{op_id}-xfer-{node}",
                                lease_ids=[leases[pair_id_1][node]],
                                from_resource=pair_id_1, to_resource=output_id,
                                instance=instances.get(node),
                            )
                    except (NodeCommandFailed, NodeTransportError) as exc:
                        raise QuantumResourceError(
                            "transport_ambiguous", f"survivor transfer failed: {exc}",
                        ) from exc
                    for node in (node_a, node_b):
                        await self.pool._release_worker(  # noqa: SLF001 - pool-owned plumbing
                            node, operation_id=f"{op_id}-rel-{node}",
                            lease_ids=[leases[pair_id_2][node]], instances=instances,
                        )
                await self.pool.register_output(
                    output, input_ids=(pair_id_1, pair_id_2),
                    leases={node: leases[pair_id_1][node] for node in (node_a, node_b)
                            if leases[pair_id_1].get(node)},
                    operation_id=op_id, terminal=PairStatus.CONSUMED,
                )
                output_registered = True
                granted.clear()
                try:
                    receipt = await self.pool._emit(  # noqa: SLF001 - pool-owned plumbing
                        "purify.accepted", session_id=op_id, actor="purifier",
                        nodes=[node_a, node_b], resources=[pair_id_1, pair_id_2, output_id],
                        outcome="accepted",
                        payload={"protocol": PurificationProtocol.BBPSSW.value,
                                 "branch_bits": [bit_a, bit_b],
                                 "branch_probability": branch_probability,
                                 "p_accept": p_accept, "output_fidelity": output_fidelity},
                    )
                except Exception:
                    receipt = None
                if self.pool._append_event is not None and receipt is None:  # noqa: SLF001 - pool-owned plumbing
                    await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-receipt-failed")  # noqa: SLF001 - pool-owned plumbing
                    raise QuantumResourceError("receipt_failed", "event sink refused purify.accepted")
                return PurificationResult(
                    protocol=PurificationProtocol.BBPSSW.value, accepted=True,
                    pair_ids=(pair_id_1, pair_id_2), output_pair_id=output_id,
                    p_accept=p_accept, branch_bits=(bit_a, bit_b),
                    branch_probability=branch_probability, output_fidelity=output_fidelity,
                    reason="parity_accept", receipt=receipt,
                )
            for node in (node_a, node_b):
                await self.pool._release_worker(  # noqa: SLF001 - pool-owned plumbing
                    node, operation_id=f"{op_id}-rel-{node}",
                    lease_ids=[lid for pid in (pair_id_1, pair_id_2) for lid in [leases[pid].get(node)] if lid],
                    instances=instances,
                )
            granted.clear()
            async with self.pool._lock:  # noqa: SLF001 - terminal transition under pool lock
                await self.pool._retire_locked(  # noqa: SLF001 - pool-owned plumbing
                    [pair_id_1, pair_id_2], operation_id=op_id,
                    terminal=PairStatus.DISCARDED, verb="discarded",
                )
            try:
                receipt = await self.pool._emit(  # noqa: SLF001 - pool-owned plumbing
                    "purify.rejected", session_id=op_id, actor="purifier",
                    nodes=[node_a, node_b], resources=[pair_id_1, pair_id_2],
                    outcome="rejected",
                    payload={"protocol": PurificationProtocol.BBPSSW.value,
                             "branch_bits": [bit_a, bit_b],
                             "branch_probability": branch_probability, "p_accept": p_accept},
                )
            except Exception:
                receipt = None
            if self.pool._append_event is not None and receipt is None:  # noqa: SLF001 - pool-owned plumbing
                raise QuantumResourceError("receipt_failed", "event sink refused purify.rejected")
            return PurificationResult(
                protocol=PurificationProtocol.BBPSSW.value, accepted=False,
                pair_ids=(pair_id_1, pair_id_2), output_pair_id=None,
                p_accept=p_accept, branch_bits=(bit_a, bit_b),
                branch_probability=branch_probability, output_fidelity=None,
                reason="parity_reject", receipt=receipt,
            )
        except asyncio.CancelledError:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-cancelled")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated:
                await self.pool._quarantine_quiet((pair_id_1, pair_id_2), reason=f"{op_id}-cancelled")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_1, pair_id_2), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        except (QuantumResourceError, NodeTransportAmbiguous) as exc:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            code = exc.code if isinstance(exc, QuantumResourceError) else "transport_ambiguous"
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-failed")  # noqa: SLF001 - pool-owned plumbing
            elif code in _AMBIGUOUS_CODES:
                await self.pool._quarantine_quiet((pair_id_1, pair_id_2), reason=f"{op_id}-ambiguous")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated or code == "measurement_mismatch":
                await self.pool._quarantine_quiet((pair_id_1, pair_id_2), reason=f"{op_id}-failed")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_1, pair_id_2), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            if code in _AMBIGUOUS_CODES:
                raise QuantumResourceError("transport_ambiguous", f"purify ambiguous: {exc}") from exc
            raise
        except Exception:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-unknown")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated:
                await self.pool._quarantine_quiet((pair_id_1, pair_id_2), reason=f"{op_id}-unknown")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_1, pair_id_2), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise


@dataclass(frozen=True, slots=True)
class SwapResult:
    accepted: bool
    input_ids: tuple
    output_pair_id: str | None
    bsm_bits: tuple
    bsm_probability: float
    correction_x: int
    correction_z: int
    gate_x: bool
    gate_z: bool
    correction_origin: str
    output_fidelity: float | None
    reason: str
    receipt: Any = None


class EntanglementSwapper:
    """Pool-mediated four-qubit swap BSM with endpoint corrections."""

    def __init__(self, pool: BellPairPool, *, rng: Any | None = None) -> None:
        import secrets as _secrets

        self.pool = pool
        self._rng = rng if rng is not None else _secrets.SystemRandom()

    async def swap(
        self, pair_id_ab: str, pair_id_bc: str, *, operation_id: str | None = None,
    ) -> SwapResult:
        _check_id(pair_id_ab, "pair_id_ab")
        _check_id(pair_id_bc, "pair_id_bc")
        if pair_id_ab == pair_id_bc:
            raise QuantumResourceError("same_resource", "swap needs two distinct pairs", status=400)
        op_id = operation_id or _new_id("op")
        pairs = await self.pool.reserve_pairs((pair_id_ab, pair_id_bc), operation_id=op_id)
        first, second = pairs
        shared = {first.node_a, first.node_b} & {second.node_a, second.node_b}
        outers_first = {first.node_a, first.node_b} - shared
        outers_second = {second.node_a, second.node_b} - shared
        if len(shared) != 1 or len(outers_first) != 1 or len(outers_second) != 1:
            await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise QuantumResourceError(
                "endpoint_mismatch", "swap needs exactly one shared repeater and distinct outers",
            )
        repeater = next(iter(shared))
        node_a = next(iter(outers_first))
        node_c = next(iter(outers_second))
        if node_a == node_c:
            await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise QuantumResourceError("endpoint_mismatch", "swap outer endpoints must differ")
        rho_ab = first.oriented(node_a, repeater)
        rho_bc = second.oriented(repeater, node_c)
        # Joint order (A, B_left, B_right, C); CNOT(1->2), H(1); BSM on (1,2).
        joint = rho_ab.tensor(rho_bc).apply_cnot(1, 2).apply_single(quantum_state.H, 1)
        branches = joint.branches_z((1, 2))
        leases = {pair_id_ab: self.pool.leases_of(pair_id_ab), pair_id_bc: self.pool.leases_of(pair_id_bc)}
        try:
            instances = await self.pool._instances((node_a, repeater, node_c))  # noqa: SLF001
        except (QuantumResourceError, NodeTransportError):
            await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        # Worker leases this operation currently owns; cleared only by an
        # explicit worker release or by register_output moving ownership to
        # the pool. Anything left here on failure is terminal-cleaned.
        granted: list[tuple[str, str]] = [
            (node, lease_id)
            for pid in (pair_id_ab, pair_id_bc) for node, lease_id in leases[pid].items()
            if lease_id
        ]
        worker_mutated = False
        output_id: str | None = None
        output_registered = False
        try:
            repeater_leases = [lid for lid in (leases[pair_id_ab].get(repeater), leases[pair_id_bc].get(repeater)) if lid]
            pick = await self.pool._worker_branch(  # noqa: SLF001 - pool-owned plumbing
                node=repeater, operation_id=f"{op_id}-bsm",
                lease_ids=repeater_leases, branches=branches, instances=instances, rng=self._rng,
            )
            worker_mutated = True
            m_z, m_x = pick.bits
            x1, z1 = first.frame
            x2, z2 = second.frame
            correction_x = m_x ^ x1 ^ x2
            correction_z = m_z ^ z1 ^ z2
            retained = pick.state.partial_trace((0, 3))
            gate_x = bool(correction_x)
            gate_z = bool(correction_z)
            transport = self.pool._transport  # noqa: SLF001 - pool-owned plumbing
            origin = "coordinator"
            if transport is not None and leases[pair_id_bc].get(node_c):
                # The swapped output is bipartite across A/C, so no single worker
                # can hold it: the actual X/Z unitaries act on the registry joint
                # state below while the outer worker authorizes them against its
                # owned lease (ownership / instance / replay checked, acked).
                operations = []
                if gate_x:
                    operations.append({"gate": "X", "target": 0})
                if gate_z:
                    operations.append({"gate": "Z", "target": 0})
                if operations:
                    try:
                        evidence = await transport.apply_circuit(
                            node_c, operation_id=f"{op_id}-correct",
                            lease_ids=[leases[pair_id_bc][node_c]], operations=operations,
                            instance=instances.get(node_c),
                        )
                    except (NodeCommandFailed, NodeTransportError) as exc:
                        raise QuantumResourceError("transport_ambiguous", f"endpoint authorization failed: {exc}") from exc
                    if not evidence.get("transcript") == operations:
                        raise QuantumResourceError("correction_failed", "outer worker did not authorize endpoint gates")
                    origin = "worker-authorized"
            corrected = retained
            if gate_x:
                corrected = corrected.apply_single(quantum_state.X, 1)
            if gate_z:
                corrected = corrected.apply_single(quantum_state.Z, 1)
            output_id = _new_id("swapped")
            output = EntangledBellPair(
                pair_id=output_id, state_type=BellStateType.PHI_PLUS,
                node_a=node_a, node_b=node_c, rho=corrected,
            )
            if transport is not None:
                try:
                    await transport.transfer(
                        node_a, operation_id=f"{op_id}-xfer-a", lease_ids=[leases[pair_id_ab][node_a]],
                        from_resource=pair_id_ab, to_resource=output_id, instance=instances.get(node_a),
                    )
                    await transport.transfer(
                        node_c, operation_id=f"{op_id}-xfer-c", lease_ids=[leases[pair_id_bc][node_c]],
                        from_resource=pair_id_bc, to_resource=output_id, instance=instances.get(node_c),
                    )
                except (NodeCommandFailed, NodeTransportError) as exc:
                    raise QuantumResourceError(
                        "transport_ambiguous", f"survivor transfer failed: {exc}",
                    ) from exc
                for node, pid in ((repeater, pair_id_ab), (repeater, pair_id_bc)):
                    await self.pool._release_worker(  # noqa: SLF001 - pool-owned plumbing
                        node, operation_id=f"{op_id}-rel-{pid}", lease_ids=[leases[pid][node]], instances=instances,
                    )
            await self.pool.register_output(
                output, input_ids=(pair_id_ab, pair_id_bc),
                leases={node_a: leases[pair_id_ab][node_a], node_c: leases[pair_id_bc][node_c]}
                if leases[pair_id_ab].get(node_a) and leases[pair_id_bc].get(node_c) else {},
                operation_id=op_id, terminal=PairStatus.CONSUMED,
            )
            output_registered = True
            granted.clear()
            try:
                receipt = await self.pool._emit(  # noqa: SLF001 - pool-owned plumbing
                    "swap.completed", session_id=op_id, actor="swapper",
                    nodes=[node_a, repeater, node_c], resources=[pair_id_ab, pair_id_bc, output_id],
                    outcome="completed",
                    payload={"bsm_bits": [m_z, m_x], "bsm_probability": pick.probability,
                             "correction_x": correction_x, "correction_z": correction_z,
                             "gate_x": gate_x, "gate_z": gate_z, "correction_origin": origin,
                             "output_fidelity": output.fidelity},
                )
            except Exception:
                receipt = None
            if self.pool._append_event is not None and receipt is None:  # noqa: SLF001 - pool-owned plumbing
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-receipt-failed")  # noqa: SLF001 - pool-owned plumbing
                raise QuantumResourceError("receipt_failed", "event sink refused swap.completed")
            return SwapResult(
                accepted=True, input_ids=(pair_id_ab, pair_id_bc), output_pair_id=output_id,
                bsm_bits=(m_z, m_x), bsm_probability=pick.probability,
                correction_x=correction_x, correction_z=correction_z,
                gate_x=gate_x, gate_z=gate_z, correction_origin=origin,
                output_fidelity=output.fidelity, reason="bsm_completed", receipt=receipt,
            )
        except asyncio.CancelledError:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-cancelled")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated:
                await self.pool._quarantine_quiet((pair_id_ab, pair_id_bc), reason=f"{op_id}-cancelled")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        except (QuantumResourceError, NodeTransportAmbiguous) as exc:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            code = exc.code if isinstance(exc, QuantumResourceError) else "transport_ambiguous"
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-failed")  # noqa: SLF001 - pool-owned plumbing
            elif code in _AMBIGUOUS_CODES:
                await self.pool._quarantine_quiet((pair_id_ab, pair_id_bc), reason=f"{op_id}-ambiguous")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated or code == "measurement_mismatch":
                await self.pool._quarantine_quiet((pair_id_ab, pair_id_bc), reason=f"{op_id}-failed")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            if code in _AMBIGUOUS_CODES:
                raise QuantumResourceError("transport_ambiguous", f"swap ambiguous: {exc}") from exc
            raise
        except Exception:
            await self.pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if output_registered:
                await self.pool._quarantine_quiet((output_id,), reason=f"{op_id}-unknown")  # noqa: SLF001 - pool-owned plumbing
            elif worker_mutated:
                await self.pool._quarantine_quiet((pair_id_ab, pair_id_bc), reason=f"{op_id}-unknown")  # noqa: SLF001 - pool-owned plumbing
            else:
                await self.pool._release_reservation_quiet((pair_id_ab, pair_id_bc), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise


@dataclass
class QuantumRepeaterNode:
    node_id: str
    cluster_region: str
    qubit_capacity: int = 16

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "cluster_region": self.cluster_region,
            "qubit_capacity": self.qubit_capacity,
        }


class QuantumRepeaterMesh:
    """Registered topology plus multi-hop routing over pool resources."""

    def __init__(
        self, bell_pool: BellPairPool, *, rng: Any | None = None,
        purifier: EntanglementPurifier | None = None,
        swapper: EntanglementSwapper | None = None,
    ) -> None:
        import secrets as _secrets

        self.bell_pool = bell_pool
        self.nodes: dict[str, QuantumRepeaterNode] = {}
        self.links: set[frozenset] = set()
        self._rng = rng if rng is not None else _secrets.SystemRandom()
        self.swapper = swapper if swapper is not None else EntanglementSwapper(bell_pool, rng=self._rng)
        self.purifier = purifier if purifier is not None else EntanglementPurifier(bell_pool, rng=self._rng)

    def register_node(self, node_id: str, cluster_region: str, qubit_capacity: int = 16) -> QuantumRepeaterNode:
        _check_node(node_id, "node_id")
        if not isinstance(cluster_region, str) or not cluster_region:
            raise QuantumResourceError("invalid_node", "cluster_region must be non-empty", status=400)
        if isinstance(qubit_capacity, bool) or not isinstance(qubit_capacity, int) or qubit_capacity < 1:
            raise QuantumResourceError("invalid_capacity", "qubit_capacity must be a positive integer", status=400)
        if node_id in self.nodes:
            raise QuantumResourceError("duplicate_node", "duplicate registration never resets node state")
        node = QuantumRepeaterNode(node_id, cluster_region, qubit_capacity)
        self.nodes[node_id] = node
        return node

    def register_link(self, node_a: str, node_b: str) -> None:
        _check_node(node_a, "node_a")
        _check_node(node_b, "node_b")
        if node_a == node_b:
            raise QuantumResourceError("invalid_link", "links need distinct endpoints", status=400)
        if node_a not in self.nodes or node_b not in self.nodes:
            raise QuantumResourceError("unknown_node", "links need registered endpoints", status=404)
        self.links.add(frozenset((node_a, node_b)))

    async def _cleanup_hops(self, hop_ids: Sequence[str], *, operation_id: str) -> None:
        seen: set[str] = set()
        for index, pair_id in enumerate(hop_ids):
            if pair_id in seen:
                continue
            seen.add(pair_id)
            cleanup_op = f"{operation_id}-cleanup-{index}"
            try:
                await self.bell_pool.reserve_pairs((pair_id,), operation_id=cleanup_op)
                await self.bell_pool.discard_pairs((pair_id,), operation_id=cleanup_op)
            except (QuantumResourceError, NodeTransportError):
                pass
            # Quarantined or already-terminal hops skip the reservation above
            # but still hold worker leases; release those resource-bound.
            try:
                await self.bell_pool.release_pair_leases(pair_id, operation_id=cleanup_op)
            except (QuantumResourceError, NodeTransportError):
                pass

    async def establish_multi_hop_entanglement(
        self,
        node_path: Sequence[str],
        base_fidelity: float = 0.98,
        purify_hops: bool = True,
        *,
        operation_id: str | None = None,
    ) -> tuple[bool, EntangledBellPair | None, list[str]]:
        op_id = operation_id or _new_id("op")
        logs: list[str] = []
        if not isinstance(node_path, (list, tuple)) or not 2 <= len(node_path) <= MAX_ROUTE_NODES:
            return False, None, ["Route must list 2..16 nodes"]
        if any(not isinstance(node, str) or node not in self.nodes for node in node_path):
            return False, None, ["Route uses unregistered nodes"]
        if len(set(node_path)) != len(node_path):
            return False, None, ["Route must not repeat nodes"]
        for left, right in zip(node_path, node_path[1:]):
            if frozenset((left, right)) not in self.links:
                return False, None, [f"No registered link {left} <-> {right}"]
        try:
            base_fidelity = _check_fidelity(base_fidelity, "base_fidelity")
        except QuantumResourceError as exc:
            return False, None, [exc.detail]
        if not isinstance(purify_hops, bool):
            return False, None, ["purify_hops must be a boolean"]

        hop_pairs: list[EntangledBellPair] = []
        hop_ids: list[str] = []
        try:
            for index in range(len(node_path) - 1):
                left, right = node_path[index], node_path[index + 1]
                if purify_hops:
                    first = await self.bell_pool.create_pair(
                        left, right, BellStateType.PHI_PLUS, base_fidelity, operation_id=f"{op_id}-hop-{index}-a",
                    )
                    hop_ids.append(first.pair_id)
                    second = await self.bell_pool.create_pair(
                        left, right, BellStateType.PHI_PLUS, base_fidelity * 0.96,
                        operation_id=f"{op_id}-hop-{index}-b",
                    )
                    hop_ids.append(second.pair_id)
                    result = await self.purifier.purify(first.pair_id, second.pair_id, operation_id=f"{op_id}-pur-{index}")
                    if not result.accepted or result.output_pair_id is None:
                        await self._cleanup_hops(hop_ids, operation_id=op_id)
                        return False, None, logs + [f"Purification rejected hop {left} <-> {right}; route aborted"]
                    resolved = self.bell_pool.get_pair(result.output_pair_id)
                    if resolved is None:  # pragma: no cover - register_output guarantees presence
                        await self._cleanup_hops(hop_ids, operation_id=op_id)
                        return False, None, logs + ["Purified hop vanished; route aborted"]
                    hop_pairs.append(resolved)
                    hop_ids.append(resolved.pair_id)
                    logs.append(f"Purified hop {left} <-> {right}")
                else:
                    pair = await self.bell_pool.create_pair(
                        left, right, BellStateType.PHI_PLUS, base_fidelity, operation_id=f"{op_id}-hop-{index}",
                    )
                    hop_pairs.append(pair)
                    hop_ids.append(pair.pair_id)
        except asyncio.CancelledError:
            await self._cleanup_hops(hop_ids, operation_id=op_id)
            raise
        except QuantumResourceError as exc:
            await self._cleanup_hops(hop_ids, operation_id=op_id)
            return False, None, logs + [f"Route allocation failed: {exc.code}"]

        current = hop_pairs[0]
        swap_outputs: list[str] = []
        try:
            for swap_index, nxt in enumerate(hop_pairs[1:]):
                swapped = await self.swapper.swap(
                    current.pair_id, nxt.pair_id, operation_id=f"{op_id}-swap-{swap_index}",
                )
                if not swapped.accepted or swapped.output_pair_id is None:
                    raise QuantumResourceError("swap_failed", "entanglement swapping failed")
                resolved = self.bell_pool.get_pair(swapped.output_pair_id)
                if resolved is None:  # pragma: no cover - register_output guarantees presence
                    raise QuantumResourceError("swap_failed", "swapped pair vanished")
                logs.append(f"Swapped entanglement linking {resolved.node_a} <-> {resolved.node_b}")
                swap_outputs.append(resolved.pair_id)
                current = resolved
        except asyncio.CancelledError:
            await self._cleanup_hops([*hop_ids, *swap_outputs], operation_id=op_id)
            raise
        except QuantumResourceError as exc:
            # Swap consumes its inputs and quarantines on ambiguity; the
            # finished swap outputs and any unlinked hops still need cleanup.
            remaining = [pair.pair_id for pair in hop_pairs if pair.pair_id != current.pair_id]
            await self._cleanup_hops([*hop_ids, *swap_outputs, *remaining], operation_id=op_id)
            return False, None, logs + [f"Entanglement swapping failed at repeater: {exc.code}"]
        return True, current, logs


@dataclass(frozen=True, slots=True)
class TeleportationSession:
    session_id: str
    source_node: str
    target_node: str
    pair_id: str


@dataclass(frozen=True, slots=True)
class ClassicalCorrection:
    """Wire-safe correction: IDs and bits only, never amplitudes."""

    session_id: str
    resource_id: str
    lease_id: str
    bsm_x: int
    bsm_z: int
    frame_x: int
    frame_z: int
    correction_x: int
    correction_z: int


@dataclass(frozen=True, slots=True)
class TeleportationResult:
    session_id: str
    source_node: str
    target_node: str
    pair_id: str
    bsm_bits: tuple
    bsm_probability: float
    frame: tuple
    correction: ClassicalCorrection
    gate_x: bool
    gate_z: bool
    correction_applied: bool
    acknowledged: bool
    input_destroyed: bool
    resource_consumed: bool
    fidelity: float
    success: bool
    reason: str
    receiver_matrix: Any = None
    receipt: Any = None
    output: TeleportOutput | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "pair_id": self.pair_id,
            "bsm_bits": list(self.bsm_bits),
            "bsm_probability": self.bsm_probability,
            "frame": list(self.frame),
            "correction": {
                "session_id": self.correction.session_id,
                "resource_id": self.correction.resource_id,
                "lease_id": self.correction.lease_id,
                "bsm_x": self.correction.bsm_x,
                "bsm_z": self.correction.bsm_z,
                "frame_x": self.correction.frame_x,
                "frame_z": self.correction.frame_z,
                "correction_x": self.correction.correction_x,
                "correction_z": self.correction.correction_z,
            },
            "gate_x": self.gate_x,
            "gate_z": self.gate_z,
            "correction_applied": self.correction_applied,
            "acknowledged": self.acknowledged,
            "input_destroyed": self.input_destroyed,
            "resource_consumed": self.resource_consumed,
            "fidelity": self.fidelity,
            "success": self.success,
            "reason": self.reason,
            "receiver_matrix": self.receiver_matrix,
            "output": self.output.to_dict() if self.output is not None else None,
        }


class QuantumTeleportationProtocol:
    """Three-qubit teleportation with receiver-side Pauli correction.

    ``bell_pair`` selects an explicit pool pair ID. ``None`` without
    ``intermediate_hops`` is the documented explicit-allocation mode: a
    fresh managed pair is created for the session. Supplying both is
    rejected; an invalid selection never summons a hidden replacement.
    """

    def __init__(
        self,
        repeater_mesh: QuantumRepeaterMesh | None = None,
        *,
        pool: BellPairPool | None = None,
        transport: Any | None = None,
        rng: Any | None = None,
        append_event: AppendEvent | None = None,
    ) -> None:
        import secrets as _secrets

        if repeater_mesh is not None:
            self.repeater_mesh = repeater_mesh
            self.pool = repeater_mesh.bell_pool
        elif pool is not None:
            self.repeater_mesh = None
            self.pool = pool
        else:
            raise QuantumResourceError("missing_pool", "a mesh or pool is required", status=400)
        self._transport = transport if transport is not None else self.pool._transport  # noqa: SLF001
        self._rng = rng if rng is not None else _secrets.SystemRandom()
        self._append_event = append_event if append_event is not None else self.pool._append_event  # noqa: SLF001
        self.sessions: dict[str, TeleportationResult] = {}
        # Successful receiver outputs keyed by session: explicit session
        # ownership plus receiver scope. Successful outputs persist until
        # the owner releases them; failed outputs are reclaimed, never stored.
        self.outputs: dict[str, TeleportOutput] = {}
        # Saved release acknowledgements keyed by (session, operation):
        # a same-operation retry replays its ack without another mutation.
        self._release_acks: dict[tuple[str, str], dict[str, Any]] = {}

    async def teleport_qubit(
        self,
        source_node: str,
        target_node: str,
        alpha: complex,
        beta: complex,
        bell_pair: str | None = None,
        intermediate_hops: Sequence[str] | None = None,
        *,
        operation_id: str | None = None,
        session_id: str | None = None,
    ) -> TeleportationResult:
        _check_node(source_node, "source_node")
        _check_node(target_node, "target_node")
        if source_node == target_node:
            raise QuantumResourceError("invalid_endpoints", "teleport endpoints must differ", status=400)
        if bell_pair is not None and intermediate_hops is not None:
            raise QuantumResourceError(
                "invalid_selection", "supply a selected pair or hops, never both", status=400,
            )
        if bell_pair is not None and not isinstance(bell_pair, str):
            # Authoritative pool objects only: forged dataclasses fail closed.
            raise QuantumResourceError("invalid_selection", "bell_pair must be a pool pair ID string", status=400)
        try:
            input_state = quantum_state.QuantumStateVector.from_qubit(alpha, beta)
        except (TypeError, ValueError) as exc:
            raise QuantumResourceError("invalid_input", f"input amplitudes rejected: {exc}", status=400) from exc

        op_id = operation_id or _new_id("op")
        session = session_id or _new_id("teleport")

        # -- resolve the selected resource -----------------------------------
        if bell_pair is not None:
            _check_id(bell_pair, "bell_pair")
            pair = self.pool.get_pair(bell_pair)
            if pair is None:
                raise QuantumResourceError("unknown_pair", "selected pair is unknown", status=404)
            if {pair.node_a, pair.node_b} != {source_node, target_node}:
                raise QuantumResourceError("endpoint_mismatch", "selected pair links other endpoints")
            status = self.pool.status_of(bell_pair)
            if status is not PairStatus.ACTIVE:
                raise QuantumResourceError("pair_unavailable", f"selected pair is {status.value if status else 'gone'}")
        elif intermediate_hops is not None:
            if self.repeater_mesh is None:
                raise QuantumResourceError("missing_mesh", "multi-hop teleport needs a mesh", status=400)
            route = [source_node, *list(intermediate_hops), target_node]
            ok, pair, logs = await self.repeater_mesh.establish_multi_hop_entanglement(route, operation_id=f"{op_id}-route")
            if not ok or pair is None:
                raise QuantumResourceError("route_failed", f"route failed: {'; '.join(logs)}")
        else:
            pair = await self.pool.create_pair(
                source_node, target_node, BellStateType.PHI_PLUS, 0.99, operation_id=f"{op_id}-alloc",
            )

        # -- atomic reservation: pair + sender input slot, before any gate ---
        await self.pool.reserve_pairs((pair.pair_id,), operation_id=op_id)
        pool = self.pool
        transport = self._transport
        instances: dict[str, str] = {}
        input_lease: str | None = None
        # Worker leases this operation currently owns; cleared only by an
        # explicit worker release or by output registration moving ownership
        # to the session. Anything left here on failure is terminal-cleaned.
        granted: list[tuple[str, str]] = []
        try:
            if transport is not None:
                instances = await pool._instances((source_node, target_node))  # noqa: SLF001
                held = await pool._reserve_worker(  # noqa: SLF001 - pool-owned plumbing
                    source_node, operation_id=f"{op_id}-input", resource_id=f"input-{session}",
                    count=1, session_id=session, instances=instances,
                )
                if held:
                    input_lease = held[0]
                    granted.append((source_node, input_lease))
        except asyncio.CancelledError:
            await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            await pool._release_reservation_quiet((pair.pair_id,), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        except (QuantumResourceError, NodeTransportError):
            await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            await pool._release_reservation_quiet((pair.pair_id,), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise

        pair_leases = pool.leases_of(pair.pair_id)
        sender_half = pair_leases.get(source_node)
        receiver_half = pair_leases.get(target_node)
        for node, lease_id in ((source_node, sender_half), (target_node, receiver_half)):
            if lease_id is not None:
                granted.append((node, lease_id))
        worker_mutated = False

        try:
            # -- joint evolution: (input, sender-half, receiver-half) --------
            oriented = pair.oriented(source_node, target_node)
            joint = input_state.density().tensor(oriented)
            joint = joint.apply_cnot(0, 1).apply_single(quantum_state.H, 0)
            branches = joint.branches_z((0, 1))
            sender_leases = [lid for lid in (input_lease, sender_half) if lid]
            pick = await pool._worker_branch(  # noqa: SLF001 - pool-owned plumbing
                node=source_node, operation_id=f"{op_id}-bsm",
                lease_ids=sender_leases, branches=branches, instances=instances, rng=self._rng,
            )
            worker_mutated = True
            m_z, m_x = pick.bits
            conditional = pick.state.partial_trace((2,))
            frame_x, frame_z = pair.frame
            correction_x = m_x ^ frame_x
            correction_z = m_z ^ frame_z

            # -- stage the conditional rho; receiver corrects worker-side ----
            acknowledged = False
            corrected = conditional
            gate_x = bool(correction_x)
            gate_z = bool(correction_z)
            receiver_matrix = conditional.to_public_matrix()
            if transport is not None and receiver_half is not None:
                await transport.stage_conditional_state(
                    target_node, operation_id=f"{op_id}-stage", lease_id=receiver_half,
                    session_id=session, rho_matrix=conditional.to_public_matrix(),
                    instance=instances.get(target_node),
                )
                answer = await transport.correct(
                    target_node, operation_id=f"{op_id}-correct", lease_id=receiver_half,
                    session_id=session, bsm_x=m_x, bsm_z=m_z,
                    frame_x=frame_x, frame_z=frame_z,
                    instance=instances.get(target_node),
                )
                if answer.get("correction_x") != correction_x or answer.get("correction_z") != correction_z:
                    raise QuantumResourceError("evidence_mismatch", "receiver correction bits disagree")
                if not answer.get("acknowledgement") or not answer.get("correction_applied"):
                    raise QuantumResourceError("correction_failed", "receiver correction unacknowledged")
                rows = answer["rho_matrix"]
                rebuilt = quantum_state.QuantumDensityMatrix(
                    tuple(tuple(complex(cell[0], cell[1]) for cell in row) for row in rows)
                )
                expected = conditional
                if gate_x:
                    expected = expected.apply_single(quantum_state.X, 0)
                if gate_z:
                    expected = expected.apply_single(quantum_state.Z, 0)
                worst = max(
                    abs(rebuilt.rows[i][j] - expected.rows[i][j]) for i in range(2) for j in range(2)
                )
                if worst > 1e-9:
                    raise QuantumResourceError("evidence_mismatch", "receiver rho diverges from staged evolution")
                corrected = rebuilt
                receiver_matrix = answer["rho_matrix"]
                acknowledged = True
            else:
                if gate_x:
                    corrected = corrected.apply_single(quantum_state.X, 0)
                if gate_z:
                    corrected = corrected.apply_single(quantum_state.Z, 0)
                # Mathematical mode has no worker acknowledgement: the
                # reported receiver matrix is the locally corrected state,
                # never the pre-correction conditional.
                receiver_matrix = corrected.to_public_matrix()

            fidelity = corrected.fidelity_pure(input_state)

            await pool.consume_pairs((pair.pair_id,), operation_id=op_id)
            resource_consumed = True
            if transport is not None:
                release_index = 0
                for node, lease_id in ((source_node, input_lease), (source_node, sender_half)):
                    if lease_id is None:
                        continue
                    await pool._release_worker(  # noqa: SLF001 - pool-owned plumbing
                        node, operation_id=f"{op_id}-rel-{release_index}",
                        lease_ids=[lease_id], instances=instances,
                    )
                    granted[:] = [item for item in granted if item[1] != lease_id]
                    release_index += 1

            receipt: Any = None
            receipt_failed = False
            if self._append_event is not None:
                try:
                    receipt = await self._append_event(
                        {
                            "event_type": "teleport.completed",
                            "session_id": session,
                            "actor": "teleport",
                            "nodes": [source_node, target_node],
                            "resources": [pair.pair_id],
                            "outcome": "success" if fidelity >= TELEPORT_FIDELITY_THRESHOLD else "below_threshold",
                            "payload": {
                                "model_version": 1,
                                "frame_x": frame_x, "frame_z": frame_z,
                                "bsm_x": m_x, "bsm_z": m_z,
                                "correction_x": correction_x, "correction_z": correction_z,
                                "gate_x": gate_x, "gate_z": gate_z,
                                "correction_applied": True, "acknowledged": acknowledged,
                                "input_destroyed": True, "resource_consumed": True,
                                "fidelity": fidelity,
                            },
                        }
                    )
                except Exception:
                    receipt_failed = True
                if receipt is None:
                    receipt_failed = True

            sink_ok = self._append_event is None or (receipt is not None and not receipt_failed)
            success = (
                fidelity >= TELEPORT_FIDELITY_THRESHOLD
                and acknowledged
                and resource_consumed
                and sink_ok
            )
            if success:
                reason = "teleported"
            elif receipt_failed:
                reason = "receipt_failed"
            elif fidelity < TELEPORT_FIDELITY_THRESHOLD:
                reason = "below_threshold"
            else:
                reason = "unacknowledged"
            if success:
                # Ownership transfer: the receiver lease leaves the consumed
                # record and lives under this session until owner release.
                if transport is not None and receiver_half is not None:
                    await pool.detach_lease(pair.pair_id, target_node)
                self.outputs[session] = TeleportOutput(
                    session_id=session, receiver=target_node, resource_id=pair.pair_id,
                    lease_id=receiver_half or "", instance_id=instances.get(target_node, ""),
                    status="available",
                )
                granted.clear()
            else:
                # Failed and below-threshold outputs are reclaimed
                # worker-side; the pair record stays consumed, never active.
                await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
                granted.clear()
            correction = ClassicalCorrection(
                session_id=session, resource_id=pair.pair_id, lease_id=receiver_half or "",
                bsm_x=m_x, bsm_z=m_z, frame_x=frame_x, frame_z=frame_z,
                correction_x=correction_x, correction_z=correction_z,
            )
            result = TeleportationResult(
                session_id=session, source_node=source_node, target_node=target_node,
                pair_id=pair.pair_id, bsm_bits=(m_z, m_x), bsm_probability=pick.probability,
                frame=(frame_x, frame_z), correction=correction,
                gate_x=gate_x, gate_z=gate_z, correction_applied=True,
                acknowledged=acknowledged, input_destroyed=True,
                resource_consumed=resource_consumed, fidelity=fidelity,
                success=success, reason=reason, receiver_matrix=receiver_matrix, receipt=receipt,
                output=self.outputs.get(session),
            )
            self.sessions[session] = result
            return result
        except asyncio.CancelledError:
            await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if worker_mutated:
                await pool._quarantine_quiet((pair.pair_id,), reason=f"{op_id}-cancelled")  # noqa: SLF001 - pool-owned plumbing
            else:
                await pool._release_reservation_quiet((pair.pair_id,), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        except (NodeTransportAmbiguous, QuantumResourceError) as exc:
            await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            code = exc.code if isinstance(exc, QuantumResourceError) else "transport_ambiguous"
            if code in _AMBIGUOUS_CODES:
                await pool._quarantine_quiet((pair.pair_id,), reason=f"{op_id}-ambiguous")  # noqa: SLF001 - pool-owned plumbing
                try:
                    await pool._emit(  # noqa: SLF001 - pool-owned plumbing
                        "pair.quarantined", session_id=session, actor="teleport",
                        nodes=[source_node, target_node], resources=[pair.pair_id],
                        outcome="quarantined", payload={"reason": str(exc)},
                    )
                except Exception:
                    pass
                raise QuantumResourceError("transport_ambiguous", f"teleport ambiguous: {exc}") from exc
            if worker_mutated or code == "measurement_mismatch":
                await pool._quarantine_quiet((pair.pair_id,), reason=f"{op_id}-failed")  # noqa: SLF001 - pool-owned plumbing
            else:
                await pool._release_reservation_quiet((pair.pair_id,), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise
        except Exception:
            # Unknown failure: never resurrect inputs; mutated state quarantines.
            await pool._release_granted_quiet(granted, operation_id=op_id, instances=instances)  # noqa: SLF001 - pool-owned plumbing
            if worker_mutated:
                await pool._quarantine_quiet((pair.pair_id,), reason=f"{op_id}-unknown")  # noqa: SLF001 - pool-owned plumbing
            else:
                await pool._release_reservation_quiet((pair.pair_id,), operation_id=op_id)  # noqa: SLF001 - pool-owned plumbing
            raise

    def _set_output_status(self, record: TeleportOutput, status: str) -> TeleportOutput:
        updated = replace(record, status=status)
        self.outputs[record.session_id] = updated
        previous = self.sessions.get(record.session_id)
        if previous is not None:
            self.sessions[record.session_id] = replace(previous, output=updated)
        return updated

    async def release_teleport_output(
        self, session_id: str, receiver: str, operation_id: str,
    ) -> dict[str, Any]:
        """Release one successful teleport output back to its receiver worker.

        Ownership-checked owner release: the output persists under its
        session until this call. Unknown sessions report 404, a receiver
        that does not own the session reports 403, and a second release
        under a new operation reports 409. A same-operation retry returns
        its saved acknowledgement without another worker mutation. The
        worker release reuses ``operation_id`` verbatim so an ambiguous
        first attempt replays instead of double-applying.

        Returns ``{"ok": True, "acknowledgement": ..., "output": {...}}``
        with ``output={session_id, receiver, resource_id, lease_id,
        instance_id, status}`` carrying IDs only, never credentials.
        """
        _check_id(session_id, "session_id")
        _check_node(receiver, "receiver")
        _check_id(operation_id, "operation_id")
        record = self.outputs.get(session_id)
        if record is None:
            raise QuantumResourceError("unknown_session", f"session {session_id} has no teleport output", status=404)
        if record.receiver != receiver:
            raise QuantumResourceError(
                "receiver_mismatch", f"session {session_id} output belongs to {record.receiver}", status=403,
            )
        if record.status == "released":
            saved = self._release_acks.get((session_id, operation_id))
            if saved is not None:
                return {"ok": True, "acknowledgement": saved["acknowledgement"], "output": dict(saved["output"])}
            raise QuantumResourceError(
                "already_released", f"session {session_id} output is already released", status=409,
            )
        if record.status == "quarantined":
            raise QuantumResourceError(
                "output_quarantined", f"session {session_id} output release remains unconfirmed", status=409,
            )
        transport = self._transport
        if transport is not None and record.lease_id:
            try:
                await transport.release(
                    receiver, operation_id=operation_id, lease_ids=[record.lease_id],
                    instance=record.instance_id or None,
                )
            except NodeTransportAmbiguous as exc:
                self._set_output_status(record, "quarantined")
                raise QuantumResourceError(
                    "transport_ambiguous", f"output release ambiguous: {exc}",
                ) from exc
            except NodeCommandFailed as exc:
                if exc.code not in ("already_released", "unknown_lease"):
                    self._set_output_status(record, "quarantined")
                    raise QuantumResourceError("worker_refused", f"output release refused: {exc}") from exc
            except NodeTransportError as exc:
                self._set_output_status(record, "quarantined")
                raise QuantumResourceError("worker_refused", f"output release refused: {exc}") from exc
        released = self._set_output_status(record, "released")
        result = {
            "ok": True,
            "acknowledgement": f"ack-{operation_id}",
            "output": released.to_dict(),
        }
        self._release_acks[(session_id, operation_id)] = result
        return {"ok": True, "acknowledgement": result["acknowledgement"], "output": dict(result["output"])}
