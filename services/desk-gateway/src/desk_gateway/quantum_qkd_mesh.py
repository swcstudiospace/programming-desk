"""Quantum Key Distribution (BB84 / E91), Entangled State Ledger & Solana Anchoring (Milestone v5.1 - Phase 69).

Implements:
- QuantumBasis: Computational Rectilinear basis (+) and Diagonal basis (x).
- QKDProtocolType: BB84 (prepare-and-measure) and E91 (EPR entanglement-based).
- QKDProtocolEngine: Simulates basis selection, qubit transmission, basis sifting,
  Quantum Bit Error Rate (QBER) calculation, error correction, and privacy amplification.
- QuantumTeleportationDrillSimulator: one shared-runtime pass whose all_passed flag is the
  confirmed-publication conjunction, never a stand-in for an unfunded signer.
"""

from __future__ import annotations

import asyncio
import enum
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .quantum_key import (
    EPS_COR,
    EPS_PA,
    EPS_PE,
    EPS_W,
    L_BRANCH_TOTAL,
    L_TAG32,
    MIN_EXTRACT_BITS,
    aggregate_commitment,
    bb84_state,
    estimate_chsh,
    finite_sample_budget,
    qber_exceeds,
    sample_chsh_outcome,
    validate_count,
    validate_requested_bits,
)
from .quantum_node import (
    QKD_ABORT_REASONS,
    QuantumNodeError,
    decode_bits,
    decode_signals,
    encode_density,
    encode_indices,
    encode_signals,
)
from .quantum_state import BellState, H, X, Z
from .quantum_teleportation import (
    MAX_ROUTE_NODES,
    BellPairPool,
    BellStateType,
    QuantumRepeaterMesh,
    QuantumResourceError,
)
from .quantum_transport import NodeCommandFailed, NodeTransportAmbiguous


class QuantumBasis(str, enum.Enum):
    RECTILINEAR = "+"  # {|0>, |1>}
    DIAGONAL = "x"     # {|+>, |->}


class QKDProtocolType(str, enum.Enum):
    BB84 = "BB84"  # Prepare-and-measure protocol (Bennett & Brassard 1984)
    E91 = "E91"    # Entanglement-based protocol (Ekert 1991)


_QKD_MODEL = "trusted-device-simulator-v1"

_NODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def _check_endpoint(value: object, name: str) -> str:
    if not isinstance(value, str) or _NODE_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must match [A-Za-z0-9._-]{{1,64}}")
    return value


class _ResourceCleanupUnconfirmed(Exception):
    """A routed round cannot be safely retired; extraction is forbidden."""


class _WorkerPlaneUnavailable(Exception):
    """No QKD transport is bound (fail-closed, no key)."""


_ABORT_MAP = {"entanglement_witness_failed": "witness_failed"}


def _worker_abort_reason(session_reason: Optional[str]) -> str:
    """Map an engine session reason onto a fixed worker abort code."""
    if session_reason is not None:
        mapped = _ABORT_MAP.get(session_reason, session_reason)
        if mapped in QKD_ABORT_REASONS:
            return mapped
    return "protocol_error"


@dataclass(frozen=True, slots=True)
class QKDKeyExchangeSession:
    """Public QKD session projection: aggregates only, never key material.

    Faithful trusted-device simulator record (``trusted-device-simulator-v1``);
    no physical, device-independent, or production-secrecy claim. ``qber`` is
    JSON null when not estimated, never 0 as a stand-in for missing.
    """

    session_id: str
    protocol: str
    model: str = _QKD_MODEL
    status: str = "failed"
    reason: Optional[str] = None
    sender: str = ""
    receiver: str = ""
    raw_count: int = 0
    sifted_count: int = 0
    test_count: int = 0
    error_count: int = 0
    phase_test_count: int = 0
    phase_error_count: int = 0
    qber: Optional[float] = None
    phase_error_bound: Optional[float] = None
    syndrome_bits: int = 0
    branch_bits: int = 0
    tag_bits: int = 0
    entropy_budget: Dict[str, Any] = field(default_factory=dict)
    extracted_bits: int = 0
    keys_agreed: bool = False
    key_id: Optional[str] = None
    commitment_alice_hex: Optional[str] = None
    commitment_bob_hex: Optional[str] = None
    key_commitment_hex: Optional[str] = None
    duration_ms: float = 0.0
    receipt_id: Optional[str] = None

    def __repr__(self) -> str:
        return f"QKDKeyExchangeSession({self.session_id})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "protocol": self.protocol,
            "model": self.model,
            "status": self.status,
            "reason": self.reason,
            "sender": self.sender,
            "receiver": self.receiver,
            "raw_count": self.raw_count,
            "sifted_count": self.sifted_count,
            "test_count": self.test_count,
            "error_count": self.error_count,
            "phase_test_count": self.phase_test_count,
            "phase_error_count": self.phase_error_count,
            "qber": self.qber,
            "phase_error_bound": self.phase_error_bound,
            "syndrome_bits": self.syndrome_bits,
            "branch_bits": self.branch_bits,
            "tag_bits": self.tag_bits,
            "entropy_budget": dict(self.entropy_budget),
            "extracted_bits": self.extracted_bits,
            "keys_agreed": self.keys_agreed,
            "key_id": self.key_id,
            "commitment_alice_hex": self.commitment_alice_hex,
            "commitment_bob_hex": self.commitment_bob_hex,
            "key_commitment_hex": self.key_commitment_hex,
            "duration_ms": self.duration_ms,
            "receipt_id": self.receipt_id,
        }


class QKDProtocolEngine:
    """Faithful BB84/E91 numerical engine on the shared kernel and pool.

    Trusted-device simulator numerical budget only: no physical,
    device-independent, or production-secrecy claim. ``QKDProtocolEngine(mesh)``
    constructs without running a session, without I/O, and without raising.
    All endpoint work runs through the shared ``qkd_step``/``qkd_owner``
    transport; this object holds no worker references and supplies no
    private endpoint draws. ``rng`` is the channel/test RNG only (Eve
    resend, public index shuffles, disclosed CHSH/phase test rounds);
    raw bits, bases, outcomes, and blinding are worker-local.
    """

    def __init__(
        self,
        mesh: Optional[QuantumRepeaterMesh] = None,
        *,
        pool: Optional[BellPairPool] = None,
        transport: Any = None,
        rng: Any = None,
        append_event: Any = None,
    ) -> None:
        self.mesh = mesh
        self.repeater_mesh = mesh
        resolved = pool
        if resolved is None and mesh is not None:
            resolved = getattr(mesh, "bell_pool", None)
        if resolved is None:
            resolved = (
                BellPairPool(transport=transport) if transport is not None else BellPairPool()
            )
        self.pool: BellPairPool = resolved
        if transport is None:
            transport = getattr(resolved, "_transport", None)
        self.transport = transport
        self._rng = rng if rng is not None else secrets.SystemRandom()
        self._append_event = append_event
        self.sessions: Dict[str, QKDKeyExchangeSession] = {}
        self._session_instances: Dict[str, Dict[str, str]] = {}
        self._quarantined_sessions: Dict[str, Dict[str, str]] = {}

    def _require_transport(self) -> Any:
        transport = self.transport
        if transport is None:
            raise _WorkerPlaneUnavailable("no QKD transport bound")
        return transport

    def _e91_route(self, sender: str, receiver: str) -> list[str] | None:
        """Shortest registered simple path, with lexical ties and no effects."""
        mesh = self.mesh
        if mesh is None or mesh.bell_pool is not self.pool:
            return None
        if sender not in mesh.nodes or receiver not in mesh.nodes:
            return None
        adjacency: dict[str, list[str]] = {node: [] for node in mesh.nodes}
        for link in mesh.links:
            if len(link) != 2 or not link.issubset(mesh.nodes):
                continue
            left, right = sorted(link)
            adjacency[left].append(right)
            adjacency[right].append(left)
        queue = deque([[sender]])
        seen = {sender}
        while queue:
            path = queue.popleft()
            if path[-1] == receiver:
                if (
                    2 <= len(path) <= MAX_ROUTE_NODES
                    and len(set(path)) == len(path)
                    and all(node in mesh.nodes for node in path)
                    and all(
                        frozenset((left, right)) in mesh.links
                        for left, right in zip(path, path[1:])
                    )
                ):
                    return path
                return None
            if len(path) >= MAX_ROUTE_NODES:
                continue
            for node in sorted(adjacency[path[-1]]):
                if node not in seen:
                    seen.add(node)
                    queue.append([*path, node])
        return None

    async def _discover(self, sender: str, receiver: str) -> Dict[str, str]:
        """Pin both nodes' original instances once per session.

        Authenticated read-only discovery runs before any RNG draw or
        worker effect; every later step reuses these pinned instances.
        """
        transport = self._require_transport()
        instances: Dict[str, str] = {}
        for node in (sender, receiver):
            info = await transport.inspect(node)
            instances[node] = info["instance_id"]
        return instances

    async def _step(
        self,
        node: str,
        session_id: str,
        operation_id: str,
        action: str,
        payload: Mapping[str, Any],
        instances: Mapping[str, str],
    ) -> Dict[str, Any]:
        """One coordinator step over the shared transport (same Local/Remote codec)."""
        transport = self._require_transport()
        return await transport.qkd_step(
            node,
            operation_id=operation_id,
            session_id=session_id,
            action=action,
            payload=payload,
            instance=instances.get(node),
        )

    async def _bind(
        self, session_id: str, sender: str, receiver: str, protocol: QKDProtocolType, instances: Mapping[str, str]
    ) -> bool:
        """Bind role/session/ownership on both endpoint workers."""
        try:
            for node, role, peer in (
                (sender, "alice", receiver),
                (receiver, "bob", sender),
            ):
                await self._step(
                    node, session_id, f"{session_id}-begin-{node}", "begin",
                    {"protocol": protocol.value, "role": role, "peer": peer},
                    instances,
                )
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", instances)
            raise
        except Exception:
            return False
        return True

    async def _abort_workers(
        self,
        sender: str,
        receiver: str,
        session_id: str,
        reason: str,
        instances: Optional[Mapping[str, str]] = None,
    ) -> bool:
        """Destroy owned buffers or retain the original scope as quarantined."""
        pinned = dict(instances) if instances else {}
        if not pinned:
            return True  # No endpoint effects preceded authenticated discovery.
        unconfirmed: Dict[str, str] = {}
        transport = self.transport
        for node in (sender, receiver):
            cleared = False
            if transport is not None:
                try:
                    await transport.qkd_step(
                        node, operation_id=f"{session_id}-abort-{node}",
                        session_id=session_id, action="abort", payload={"reason": reason},
                        instance=pinned.get(node),
                    )
                    cleared = True
                except NodeCommandFailed as exc:
                    cleared = exc.code in ("unknown_session", "already_aborted", "already_used")
                except Exception:
                    pass
                if not cleared:
                    try:
                        state = await transport.qkd_step(
                            node, operation_id=f"{session_id}-abort-state-{node}",
                            session_id=session_id, action="lengths", payload={},
                            instance=pinned.get(node),
                        )
                        cleared = (
                            state["state"] in ("used", "aborted")
                            and state["key_available"] is False
                            and state["key_length"] == 0
                            and state["phase_length"] == 0
                        )
                    except Exception:
                        pass
            if not cleared:
                unconfirmed[node] = pinned[node]
        if unconfirmed:
            self._quarantined_sessions[session_id] = unconfirmed
            return False
        self._quarantined_sessions.pop(session_id, None)
        return True

    async def _emit(self, session: QKDKeyExchangeSession) -> Optional[str]:
        if self._append_event is None:
            return None
        event = {
            "event_type": f"qkd.{session.status}",
            "session_id": session.session_id,
            "actor": session.sender,
            "nodes": [session.sender, session.receiver],
            "resources": [],
            "outcome": session.status,
            "payload": session.to_dict(),
        }
        result = await self._append_event(event)
        receipt_id = getattr(result, "receipt_id", None)
        if receipt_id is None and isinstance(result, Mapping):
            receipt_id = result.get("receipt_id")
        return str(receipt_id) if receipt_id is not None else None

    def _budget_dict(self, budget: Optional[Dict[str, Any]] = None, chsh: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "eps_pe": EPS_PE,
            "eps_pa": EPS_PA,
            "eps_cor": EPS_COR,
            "eps_w": EPS_W,
            "mu": None,
            "q_upper": None,
            "h_est": None,
            "h_after": None,
            "ell_max": None,
        }
        if budget is not None:
            for key in ("mu", "q_upper", "h_est", "h_after", "ell_max"):
                body[key] = budget.get(key)
        if chsh is not None:
            body["chsh_S"] = chsh.get("S")
            body["chsh_S_lower"] = chsh.get("S_lower")
            body["chsh_counts"] = {str(key): value for key, value in dict(chsh.get("counts", {})).items()}
        return body

    async def _abort(
        self,
        sender: str,
        receiver: str,
        protocol: str,
        raw_count: int,
        reason: str,
        requested_bits: int,
        t0: float,
        *,
        prefix: str,
        bound: bool = False,
        sifted_count: int = 0,
        test_count: int = 0,
        error_count: int = 0,
        qber: Optional[float] = None,
        phase_error_bound: Optional[float] = None,
        syndrome_bits: int = 0,
        tag_bits: int = 0,
        budget: Optional[Dict[str, Any]] = None,
        chsh: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        instances: Optional[Mapping[str, str]] = None,
    ) -> QKDKeyExchangeSession:
        sid = session_id or f"{prefix}-{secrets.token_hex(8)}"
        cleanup_confirmed = not bound or await self._abort_workers(
            sender, receiver, sid, _worker_abort_reason(reason), instances,
        )
        session = QKDKeyExchangeSession(
            session_id=sid,
            protocol=protocol,
            status="aborted" if cleanup_confirmed else "failed",
            reason=reason if cleanup_confirmed else "key_cleanup_unconfirmed",
            sender=sender,
            receiver=receiver,
            raw_count=raw_count,
            sifted_count=sifted_count,
            test_count=test_count,
            error_count=error_count,
            phase_test_count=test_count,
            phase_error_count=error_count,
            qber=qber,
            phase_error_bound=phase_error_bound,
            syndrome_bits=syndrome_bits,
            branch_bits=0,
            tag_bits=tag_bits,
            entropy_budget=self._budget_dict(budget, chsh),
            extracted_bits=0,
            keys_agreed=False,
            key_id=None,
            commitment_alice_hex=None,
            commitment_bob_hex=None,
            key_commitment_hex=None,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
        receipt_id = await self._emit(session)
        session = replace(session, receipt_id=receipt_id)
        self.sessions[sid] = session
        return session

    async def _fail(
        self,
        sender: str,
        receiver: str,
        protocol: str,
        raw_count: int,
        t0: float,
        *,
        prefix: str,
        session_id: Optional[str] = None,
        instances: Optional[Mapping[str, str]] = None,
        reason: Optional[str] = None,
    ) -> QKDKeyExchangeSession:
        sid = session_id or f"{prefix}-{secrets.token_hex(8)}"
        cleanup_confirmed = await self._abort_workers(sender, receiver, sid, "protocol_error", instances)
        session = QKDKeyExchangeSession(
            session_id=sid,
            protocol=protocol,
            status="failed",
            reason=reason if cleanup_confirmed or reason == "resource_cleanup_unconfirmed" else "key_cleanup_unconfirmed",
            sender=sender,
            receiver=receiver,
            raw_count=raw_count,
            entropy_budget=self._budget_dict(),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
        receipt_id = await self._emit(session)
        session = replace(session, receipt_id=receipt_id)
        self.sessions[sid] = session
        return session

    async def run_bb84(
        self,
        sender: str,
        receiver: str,
        bit_length: int,
        *,
        intercept: bool = False,
        requested_bits: int = 256,
    ) -> QKDKeyExchangeSession:
        """Run one BB84 session over the shared transport.

        Alice prepares private bits/bases, Bob independently chooses and
        measures his bases; the engine sifts on the returned public bases
        and both endpoints adopt disjoint phase/key indices. Bob reconciles
        his own candidate; nothing is copied from Alice.
        """
        t0 = time.perf_counter()
        sender = _check_endpoint(sender, "sender")
        receiver = _check_endpoint(receiver, "receiver")
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        bit_length = validate_count("bit_length", bit_length)
        requested_bits = validate_requested_bits(requested_bits)
        if not isinstance(intercept, bool):
            raise ValueError("intercept must be a bool")
        if bit_length == 0:
            return await self._abort(
                sender, receiver, QKDProtocolType.BB84.value, 0, "insufficient_sample",
                requested_bits, t0, prefix="qkd-bb84",
            )
        session_id = f"qkd-bb84-{secrets.token_hex(8)}"
        try:
            instances = await self._discover(sender, receiver)
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, QKDProtocolType.BB84.value, bit_length, t0, prefix="qkd-bb84", session_id=session_id)
        if not await self._bind(session_id, sender, receiver, QKDProtocolType.BB84, instances):
            return await self._fail(sender, receiver, QKDProtocolType.BB84.value, bit_length, t0, prefix="qkd-bb84", session_id=session_id, instances=instances)
        self._session_instances[session_id] = dict(instances)
        rng = self._rng
        try:
            prepared = await self._step(
                sender, session_id, f"{session_id}-prepare", "prepare_bb84",
                {"count": bit_length}, instances,
            )
            signals_dto = prepared["signals"]
            bases_a = decode_bits(prepared["bases"], "bases")
            if intercept:
                # Numerical intercept-resend on the encoded signals. Eve's
                # click is the attack sample; Alice's bits stay in her vault.
                raw = decode_signals(signals_dto, "signals")
                resent = []
                for value in raw:
                    basis = QuantumBasis.RECTILINEAR if value < 2 else QuantumBasis.DIAGONAL
                    vec = bb84_state(value & 1, basis.value)
                    eve_basis = rng.choice(tuple(QuantumBasis))
                    probed = vec.apply_single(H, 0) if eve_basis is QuantumBasis.DIAGONAL else vec
                    eve_bit = int(probed.density().measure_z((0,), rng).bits[0])
                    resent.append(eve_bit + (0 if eve_basis is QuantumBasis.RECTILINEAR else 2))
                signals_dto = encode_signals(resent)
            measured = await self._step(
                receiver, session_id, f"{session_id}-measure", "measure_bb84",
                {"signals": signals_dto}, instances,
            )
            bases_b = decode_bits(measured["bases"], "bases")
            # Sift on basis match. The matching indices are shuffled before the
            # Z/X split so the phase sample is not a first-N prefix.
            sifted = [i for i in range(bit_length) if bases_a[i] == bases_b[i]]
            order = list(sifted)
            rng.shuffle(order)
            key_idx = [i for i in order if bases_a[i] == 0]
            phase_idx = [i for i in order if bases_a[i] == 1]
            keep_dto = encode_indices(key_idx)
            phase_dto = encode_indices(phase_idx)
            part_a = await self._step(
                sender, session_id, f"{session_id}-sift-a", "adopt_indices",
                {"keep": keep_dto, "phase": phase_dto}, instances,
            )
            part_b = await self._step(
                receiver, session_id, f"{session_id}-sift-b", "adopt_indices",
                {"keep": keep_dto, "phase": phase_dto}, instances,
            )
            phase_a = decode_bits(part_a["phase_sample"], "phase_sample")
            phase_b = decode_bits(part_b["phase_sample"], "phase_sample")
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", instances)
            raise
        except Exception:
            return await self._fail(sender, receiver, QKDProtocolType.BB84.value, bit_length, t0, prefix="qkd-bb84", session_id=session_id, instances=instances)
        return await self._finish(
            sender=sender,
            receiver=receiver,
            protocol=QKDProtocolType.BB84.value,
            session_id=session_id,
            raw_count=bit_length,
            sifted_count=len(sifted),
            phase_a=phase_a,
            phase_b=phase_b,
            requested_bits=requested_bits,
            t0=t0,
            instances=instances,
        )

    async def run_e91(
        self,
        sender: str,
        receiver: str,
        pair_count: int,
        *,
        requested_bits: int = 256,
    ) -> QKDKeyExchangeSession:
        """Run one E91 session: worker-owned key rounds plus a CHSH witness.

        Key rounds are role-scoped: Alice measures her half of an owned
        actual Bell lease and keeps only her click, forwarding the
        conditional density; Bob measures that conditional with his own
        worker RNG and keeps only his click. The coordinator never holds
        both round bits. CHSH witness and X/X phase-test rounds are
        disjoint, deliberately public samples over their own consumed
        pool pairs with the channel/test RNG.
        """
        t0 = time.perf_counter()
        sender = _check_endpoint(sender, "sender")
        receiver = _check_endpoint(receiver, "receiver")
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        pair_count = validate_count("pair_count", pair_count)
        requested_bits = validate_requested_bits(requested_bits)
        if pair_count == 0:
            return await self._abort(
                sender, receiver, QKDProtocolType.E91.value, 0, "insufficient_sample",
                requested_bits, t0, prefix="qkd-e91",
            )
        # Short samples are rejected before topology discovery or private begin.
        n_chsh = pair_count // 2
        rest = pair_count - n_chsh
        n_key = rest * 3 // 5
        n_phase = rest - n_key
        if n_key == 0 or n_phase == 0 or finite_sample_budget(n_key, n_phase, 0.0, 0, requested_bits)["mu"] >= 0.5:
            return await self._abort(
                sender, receiver, QKDProtocolType.E91.value, pair_count, "insufficient_sample",
                requested_bits, t0, prefix="qkd-e91",
            )
        mesh = self.mesh
        path = self._e91_route(sender, receiver)
        if path is None or mesh is None:
            return await self._fail(
                sender, receiver, QKDProtocolType.E91.value, pair_count, t0,
                prefix="qkd-e91", reason="route_unavailable",
            )
        session_id = f"qkd-e91-{secrets.token_hex(8)}"
        try:
            instances = await self._discover(sender, receiver)
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, QKDProtocolType.E91.value, pair_count, t0, prefix="qkd-e91", session_id=session_id)
        if not await self._bind(session_id, sender, receiver, QKDProtocolType.E91, instances):
            return await self._fail(sender, receiver, QKDProtocolType.E91.value, pair_count, t0, prefix="qkd-e91", session_id=session_id, instances=instances)
        self._session_instances[session_id] = dict(instances)
        rng = self._rng
        # Pre-randomized disjoint round classes: CHSH witness, key (Z/Z),
        # and phase-test (X/X). pair_count is not simultaneous qubit count:
        # pairs stream one at a time inside worker capacity.
        order = list(range(pair_count))
        rng.shuffle(order)
        kinds: Dict[int, str] = {}
        for pos, idx in enumerate(order):
            if pos < n_chsh:
                kinds[idx] = "chsh"
            elif pos < n_chsh + n_key:
                kinds[idx] = "key"
            else:
                kinds[idx] = "phase"
        chsh_settings = {i: rng.choice((0, 1, 2, 3)) for i in range(pair_count) if kinds[i] == "chsh"}
        phase_a: List[int] = []
        phase_b: List[int] = []
        chsh_records: List[tuple] = []
        key_seq = 0
        try:
            for i in range(pair_count):
                ok, pair, _ = await mesh.establish_multi_hop_entanglement(
                    path, base_fidelity=1.0, purify_hops=False,
                    operation_id=f"{session_id}-route-{i}",
                )
                if not ok or pair is None:
                    # The mesh owns partial-route cleanup/quarantine. Do not
                    # retry it or fabricate a direct resource.
                    raise _ResourceCleanupUnconfirmed
                retire_op = f"{session_id}-retire-{i}"
                try:
                    rho = pair.oriented(sender, receiver)
                    # Normalize non-Phi+ frames with local Paulis before sampling.
                    frame_x, frame_z = BellState(pair.state_type.value).frame
                    if frame_x:
                        rho = rho.apply_single(X, 1)
                    if frame_z:
                        rho = rho.apply_single(Z, 1)
                    kind = kinds[i]
                    basis = QuantumBasis.RECTILINEAR if kind == "key" else QuantumBasis.DIAGONAL
                    if kind == "chsh":
                        setting = chsh_settings[i]
                        a_bit, b_bit = sample_chsh_outcome(rho, setting // 2, setting % 2, rng)
                        chsh_records.append((setting, a_bit, b_bit))
                    elif kind == "key":
                        leases = self.pool.leases_of(pair.pair_id)
                        setting = 0 if basis is QuantumBasis.RECTILINEAR else 1
                        alice_round = await self._step(
                            sender, session_id, f"{session_id}-key-{i}-a", "measure_e91",
                            {"round_index": key_seq, "pair_id": pair.pair_id,
                             "lease_id": leases[sender], "setting": setting,
                             "state": encode_density(rho)},
                            instances,
                        )
                        await self._step(
                            receiver, session_id, f"{session_id}-key-{i}-b", "measure_e91",
                            {"round_index": key_seq, "pair_id": pair.pair_id,
                             "lease_id": leases[receiver], "setting": setting,
                             "state": alice_round["conditional"]},
                            instances,
                        )
                        key_seq += 1
                    else:
                        evolved = (
                            rho.apply_single(H, 0).apply_single(H, 1)
                            if basis is QuantumBasis.DIAGONAL else rho
                        )
                        branch = evolved.measure_z((0, 1), rng)
                        pa, pb = (int(v) for v in branch.bits)
                        phase_a.append(pa)
                        phase_b.append(pb)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    await self._retire_pair(pair.pair_id, operation_id=retire_op, quarantine=True)
                    raise
                except Exception as exc:
                    confirmed = await self._retire_pair(
                        pair.pair_id, operation_id=retire_op,
                        quarantine=isinstance(exc, NodeTransportAmbiguous),
                    )
                    if not confirmed:
                        raise _ResourceCleanupUnconfirmed from exc
                    raise
                if not await self._retire_pair(pair.pair_id, operation_id=retire_op):
                    raise _ResourceCleanupUnconfirmed
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", instances)
            raise
        except _ResourceCleanupUnconfirmed:
            return await self._fail(
                sender, receiver, QKDProtocolType.E91.value, pair_count, t0,
                prefix="qkd-e91", session_id=session_id, instances=instances,
                reason="resource_cleanup_unconfirmed",
            )
        except Exception:
            return await self._fail(
                sender, receiver, QKDProtocolType.E91.value, pair_count, t0,
                prefix="qkd-e91", session_id=session_id, instances=instances,
                reason="resource_cleanup_unconfirmed",
            )
        try:
            empty = encode_indices([])
            await self._step(
                sender, session_id, f"{session_id}-adopt-a", "adopt_indices",
                {"keep": empty, "phase": empty}, instances,
            )
            await self._step(
                receiver, session_id, f"{session_id}-adopt-b", "adopt_indices",
                {"keep": empty, "phase": empty}, instances,
            )
            held = await self._step(
                sender, session_id, f"{session_id}-len", "lengths", {}, instances,
            )
            sifted_count = int(held["key_length"]) + len(phase_a)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", instances)
            raise
        except Exception:
            return await self._fail(sender, receiver, QKDProtocolType.E91.value, pair_count, t0, prefix="qkd-e91", session_id=session_id, instances=instances)
        try:
            chsh = estimate_chsh(chsh_records)
        except ValueError:
            return await self._abort(
                sender, receiver, QKDProtocolType.E91.value, pair_count, "insufficient_sample",
                requested_bits, t0, prefix="qkd-e91", bound=True,
                sifted_count=sifted_count, session_id=session_id, instances=instances,
            )
        if not chsh["passed"]:
            return await self._abort(
                sender, receiver, QKDProtocolType.E91.value, pair_count, "entanglement_witness_failed",
                requested_bits, t0, prefix="qkd-e91", bound=True,
                sifted_count=sifted_count, chsh=chsh, session_id=session_id, instances=instances,
            )
        return await self._finish(
            sender=sender,
            receiver=receiver,
            protocol=QKDProtocolType.E91.value,
            session_id=session_id,
            raw_count=pair_count,
            sifted_count=sifted_count,
            phase_a=phase_a,
            phase_b=phase_b,
            requested_bits=requested_bits,
            t0=t0,
            chsh=chsh,
            instances=instances,
        )

    async def _finish(
        self,
        *,
        sender: str,
        receiver: str,
        protocol: str,
        session_id: str,
        raw_count: int,
        sifted_count: int,
        phase_a: Sequence[int],
        phase_b: Sequence[int],
        requested_bits: int,
        t0: float,
        chsh: Optional[Dict[str, Any]] = None,
        instances: Optional[Mapping[str, str]] = None,
    ) -> QKDKeyExchangeSession:
        """Reconcile and extract on the workers. This object never keeps key bytes.

        Alice announces the public syndrome and generates one fresh public
        Toeplitz seed per tag/extraction operation; the engine transports
        that SAME seed to Bob, who hashes his own independently reconciled
        candidate. Blinding stays worker-local. A sink failure or
        cancellation during emission destroys both endpoint keys (or leaves
        explicit quarantine) before propagating; cancellation re-raises.
        """
        pinned = dict(instances) if instances else {}
        prefix = "qkd-bb84" if QKDProtocolType(protocol) is QKDProtocolType.BB84 else "qkd-e91"
        rng = self._rng
        k = len(phase_a)
        errors = sum(1 for a, b in zip(phase_a, phase_b) if a != b)
        if k == 0:
            return await self._abort(
                sender, receiver, protocol, raw_count, "insufficient_sample",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, chsh=chsh, session_id=session_id, instances=pinned,
            )
        try:
            held = await self._step(
                sender, session_id, f"{session_id}-keylen", "lengths", {}, pinned,
            )
            n = int(held["key_length"])
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", pinned)
            raise
        except Exception:
            return await self._fail(
                sender, receiver, protocol, raw_count, t0, prefix=prefix,
                session_id=session_id, instances=pinned,
            )
        # A trivial confidence bound cannot estimate phase error even with
        # zero observed errors; report an unestimated, keyless short sample.
        if n == 0 or finite_sample_budget(n, k, 0.0, 0, requested_bits)["mu"] >= 0.5:
            return await self._abort(
                sender, receiver, protocol, raw_count, "insufficient_sample",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, chsh=chsh, session_id=session_id, instances=pinned,
            )
        qber = errors / float(k)
        # Exact integer admission before any float serialization.
        if qber_exceeds(errors, k):
            return await self._abort(
                sender, receiver, protocol, raw_count, "qber_exceeded",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, test_count=k, error_count=errors,
                qber=qber, chsh=chsh, session_id=session_id, instances=pinned,
            )
        try:
            perm = list(range(n))
            rng.shuffle(perm)
            order_dto = encode_indices(perm)
            syn = await self._step(
                sender, session_id, f"{session_id}-syn", "syndrome",
                {"order": order_dto}, pinned,
            )
            await self._step(
                receiver, session_id, f"{session_id}-correct", "correct",
                {"order": order_dto, "syndrome": syn["syndrome"]}, pinned,
            )
            syndrome_len = int(syn["leaked"])
            tag_a = await self._step(
                sender, session_id, f"{session_id}-tag-a", "tag",
                {"seed": None}, pinned,
            )
            tag_b = await self._step(
                receiver, session_id, f"{session_id}-tag-b", "tag",
                {"seed": tag_a["seed"]}, pinned,
            )
            if tag_a["tag"] != tag_b["tag"]:
                return await self._abort(
                    sender, receiver, protocol, raw_count, "reconciliation_failed",
                    requested_bits, t0, prefix=prefix, bound=True,
                    sifted_count=sifted_count, test_count=k, error_count=errors,
                    qber=qber, syndrome_bits=syndrome_len, chsh=chsh, session_id=session_id, instances=pinned,
                )
            budget = finite_sample_budget(n, k, errors / float(k), syndrome_len, requested_bits)
            ell = int(budget["ell"])
            if ell < MIN_EXTRACT_BITS:
                return await self._abort(
                    sender, receiver, protocol, raw_count, "insufficient_entropy",
                    requested_bits, t0, prefix=prefix, bound=True,
                    sifted_count=sifted_count, test_count=k, error_count=errors,
                    qber=qber, phase_error_bound=budget["q_upper"],
                    syndrome_bits=syndrome_len, tag_bits=L_TAG32,
                    budget=budget, chsh=chsh, session_id=session_id, instances=pinned,
                )
            ext_a = await self._step(
                sender, session_id, f"{session_id}-extract-a", "extract",
                {"output_length": ell, "seed": None}, pinned,
            )
            ext_b = await self._step(
                receiver, session_id, f"{session_id}-extract-b", "extract",
                {"output_length": ell, "seed": ext_a["seed"]}, pinned,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", pinned)
            raise
        except Exception:
            return await self._fail(sender, receiver, protocol, raw_count, t0, prefix=prefix, session_id=session_id, instances=pinned)
        commit_a = ext_a["commitment"]
        commit_b = ext_b["commitment"]
        aggregate = aggregate_commitment(commit_a, commit_b)
        key_id = secrets.token_hex(8)
        session = QKDKeyExchangeSession(
            session_id=session_id,
            protocol=protocol,
            status="established",
            reason=None,
            sender=sender,
            receiver=receiver,
            raw_count=raw_count,
            sifted_count=sifted_count,
            test_count=k,
            error_count=errors,
            phase_test_count=k,
            phase_error_count=errors,
            qber=qber,
            phase_error_bound=budget["q_upper"],
            syndrome_bits=syndrome_len,
            branch_bits=L_BRANCH_TOTAL,
            tag_bits=L_TAG32,
            entropy_budget=self._budget_dict(budget, chsh),
            extracted_bits=ell,
            keys_agreed=True,
            key_id=key_id,
            commitment_alice_hex=commit_a,
            commitment_bob_hex=commit_b,
            key_commitment_hex=aggregate,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
        try:
            receipt_id = await self._emit(session)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._abort_workers(sender, receiver, session_id, "protocol_error", pinned)
            raise
        except Exception:
            await self._abort_workers(sender, receiver, session_id, "protocol_error", pinned)
            return await self._abort(
                sender, receiver, protocol, raw_count, "receipt_failed",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, test_count=k, error_count=errors,
                qber=qber, phase_error_bound=budget["q_upper"],
                syndrome_bits=syndrome_len, tag_bits=L_TAG32,
                budget=budget, chsh=chsh, session_id=session_id, instances=pinned,
            )
        session = replace(session, receipt_id=receipt_id)
        self.sessions[session_id] = session
        return session

    async def _retire_pair(self, pair_id: str, *, operation_id: str, quarantine: bool = False) -> bool:
        """Confirm sole-authority consumption and both releases, never retry.

        Refusal or ambiguity retains a quarantined record even if the
        remaining terminal cleanup succeeds. No such round may reach finish.
        """
        confirmed = not quarantine
        if not quarantine:
            try:
                await self.pool.reserve_pairs([pair_id], operation_id=operation_id)
                await self.pool.consume_pairs([pair_id], operation_id=operation_id)
            except (asyncio.CancelledError, KeyboardInterrupt):
                await self.pool.quarantine_pairs([pair_id], reason=f"{operation_id}-cancelled")
                try:
                    await self.pool.release_pair_leases(pair_id, operation_id=operation_id)
                except Exception:
                    # Quarantine already records the unconfirmed cleanup.
                    pass
                raise
            except Exception:
                confirmed = False
        if not confirmed:
            await self.pool.quarantine_pairs([pair_id], reason=operation_id)
        try:
            await self.pool.release_pair_leases(pair_id, operation_id=operation_id)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self.pool.quarantine_pairs([pair_id], reason=f"{operation_id}-release-unconfirmed")
            raise
        except Exception:
            await self.pool.quarantine_pairs([pair_id], reason=f"{operation_id}-release-unconfirmed")
            return False
        return confirmed


    async def release_session_keys(self, session_id: str, *, operation: str) -> bool:
        """Consume owned demo keys; confirm terminal cleanup or quarantine."""
        session = self.sessions.get(session_id)
        if session is None:
            return True
        instances = self._session_instances.get(session_id, {})
        transport = self.transport
        if transport is not None:
            for node in (session.sender, session.receiver):
                try:
                    capability = await transport.qkd_owner(
                        node, operation_id=f"{session_id}-{operation}-{node}-cap",
                        session_id=session_id, action="capability", payload={},
                        instance=instances.get(node),
                    )
                    await transport.qkd_owner(
                        node, operation_id=f"{session_id}-{operation}-{node}-use",
                        session_id=session_id, action="use",
                        payload={"operation": operation, "capability": capability["capability"]},
                        instance=instances.get(node),
                    )
                except Exception:
                    pass
        return await self._abort_workers(
            session.sender, session.receiver, session_id, "user_abort", instances,
        )





class DrillBusy(Exception):
    """Another drill is already running on this runtime."""


class QuantumTeleportationDrillSimulator:
    """One pass over the shared pool, engine, ledger, and publisher.

    ``all_passed`` is true only after a confirmed Devnet readback of an
    eligible drill summary. A missing signer or an unfunded payer keeps it
    false. This is a trusted-device numerical simulator: no physical or
    device-independent claim.
    """

    def __init__(self, pool: Any, mesh: Any, protocol: Any, engine: Any, ledger: Any, exporter: Any) -> None:
        self.pool = pool
        self.mesh = mesh
        self.protocol = protocol
        self.engine = engine
        self.ledger = ledger
        self.exporter = exporter
        self._gate = asyncio.Lock()
        self._running = False
        self._round = 0

    async def run(self) -> Dict[str, Any]:
        async with self._gate:
            if self._running:
                raise DrillBusy()
            self._running = True
        try:
            return await self._run()
        finally:
            async with self._gate:
                self._running = False

    async def _run(self) -> Dict[str, Any]:
        stages: Dict[str, Any] = {}
        self._round += 1
        tag = f"drill-{self._round}"
        owned_pairs: List[str] = []
        owned_sessions: List[str] = []
        owned_teleport: List[tuple] = []
        names = list(getattr(self.mesh, "nodes", {}))
        if self.ledger is None:
            return _drill_report(False, "ledger_unavailable", stages)
        if len(names) < 3:
            return _drill_report(False, "route_needs_three_nodes", stages)
        left, repeater, right = names[0], names[1], names[2]
        if getattr(self.engine, "transport", None) is None:
            return _drill_report(False, "worker_plane_unavailable", stages)

        try:
            purify = await self._purify(left, repeater, tag, owned_pairs)
            stages["purify"] = purify
            swap = await self._swap(left, repeater, right, tag, owned_pairs)
            stages["swap"] = swap
            teleport = await self._teleport(left, right, swap.get("pair_id"), tag, owned_pairs, owned_teleport)
            stages["teleport"] = teleport
            clean = await self._bb84(left, right, tag, owned_sessions, intercept=False)
            stages["clean_bb84"] = clean
            eve = await self._bb84(left, right, tag, owned_sessions, intercept=True)
            stages["eve"] = eve
            numerical = all(stage.get("passed") for stage in (purify, swap, teleport, clean, eve))
            if not numerical:
                await self._cleanup_owned(tag, owned_pairs, owned_sessions, owned_teleport)
                await self._emit_failed("numerical_stage_failed")
                return _drill_report(False, "numerical_stage_failed", stages)
            # Demonstration resources are released once observed: public
            # commitments stay in the ledger summary, keys/outputs do not.
            if not await self._cleanup_owned(tag, owned_pairs, owned_sessions, owned_teleport):
                await self._emit_failed("cleanup_unconfirmed")
                return _drill_report(False, "cleanup_unconfirmed", stages)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self._cleanup_owned(tag, owned_pairs, owned_sessions, owned_teleport)
            raise
        except Exception as exc:
            await self._cleanup_owned(tag, owned_pairs, owned_sessions, owned_teleport)
            await self._emit_failed("drill_failed")
            return _drill_report(False, getattr(exc, "code", "drill_failed"), stages)

        try:
            receipt = await self.ledger.append_event(_drill_summary_event(
                nodes=[left, repeater, right],
                teleport=teleport["payload"],
                purify=purify,
                swap=swap,
                clean=clean["session"],
                eve=eve["session"],
            ))
        except (ValueError, LedgerShapeError) as exc:
            stages["ledger"] = {"passed": False, "reason": "summary_rejected"}
            return _drill_report(False, "summary_rejected", stages)
        stages["ledger"] = {
            "passed": True,
            "receipt_id": receipt.receipt_id,
            "tree_size": receipt.tree_size,
            "root_hex": receipt.prefix_root_hex,
        }
        if self.exporter is None:
            return _drill_report(False, "publisher_unavailable", stages)
        anchor = await self.exporter.export_commitment(receipt.receipt_id, tree_size=receipt.tree_size)
        stages["anchor"] = {
            "status": anchor.status,
            "error_code": anchor.error_code,
            "signature": anchor.signature,
            "slot": anchor.slot,
            "anchored_root_hex": anchor.anchored_root_hex,
            "anchored_tree_size": anchor.anchored_tree_size,
            "leaf_index": anchor.leaf_index,
        }
        confirmed = (
            anchor.status == "confirmed"
            and anchor.slot is not None
            and anchor.anchored_root_hex == receipt.prefix_root_hex
            and anchor.anchored_tree_size == receipt.tree_size
            and anchor.leaf_index == receipt.seq - 1
        )
        code = None if confirmed else (anchor.error_code or anchor.status)
        return _drill_report(confirmed, code, stages)

    async def _discard_pairs(self, tag: str, pair_ids: Sequence[str]) -> bool:
        """Discard owned pairs; quarantine any unconfirmed lease cleanup."""
        confirmed = True
        for index, pair_id in enumerate(dict.fromkeys(pair_ids)):
            op = f"{tag}-discard-{index}-{pair_id[-8:]}"
            try:
                await self.pool.reserve_pairs([pair_id], operation_id=op)
            except Exception:
                pass  # Terminal inputs still need their resource-bound cleanup.
            else:
                try:
                    await self.pool.discard_pairs([pair_id], operation_id=op)
                except Exception:
                    await self.pool.quarantine_pairs([pair_id], reason=op)
            try:
                await self.pool.release_pair_leases(pair_id, operation_id=op)
            except Exception:
                confirmed = False
                await self.pool.quarantine_pairs([pair_id], reason=f"{op}-release-unconfirmed")
        return confirmed

    async def _cleanup_owned(
        self,
        tag: str,
        pair_ids: Sequence[str],
        session_ids: Sequence[str],
        teleport_outputs: Sequence[tuple],
    ) -> bool:
        """Release owned resources, retaining explicit quarantine on failure."""
        confirmed = await self._discard_pairs(tag, pair_ids)
        for session_id in dict.fromkeys(session_ids):
            if not await self.engine.release_session_keys(session_id, operation="drill_release"):
                confirmed = False
        for entry in teleport_outputs:
            try:
                output_session, receiver = entry
                await self.protocol.release_teleport_output(
                    output_session, receiver, operation_id=f"{tag}-rel-{output_session[-8:]}",
                )
            except Exception:
                confirmed = False
        return confirmed

    async def _purify(self, left: str, repeater: str, tag: str, owned: List[str]) -> Dict[str, Any]:
        try:
            first = await self.pool.create_pair(left, repeater, fidelity=0.90, operation_id=f"{tag}-pur-a")
            owned.append(first.pair_id)
            second = await self.pool.create_pair(left, repeater, fidelity=0.92, operation_id=f"{tag}-pur-b")
            owned.append(second.pair_id)
            result = await self.mesh.purifier.purify(first.pair_id, second.pair_id, operation_id=f"{tag}-purify")
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "purify_failed")}
        if not result.accepted or result.output_pair_id is None:
            return {"passed": False, "reason": "purify_rejected", "baseline_fidelity": 0.90, "output_fidelity": None}
        if not (result.output_fidelity > 0.90):
            return {
                "passed": False,
                "reason": "no_measured_improvement",
                "baseline_fidelity": 0.90,
                "output_fidelity": result.output_fidelity,
            }
        # The demonstration survivor is measured, then discarded at once so
        # no drill lease lingers; the end-of-run sweep covers any residue.
        owned.append(result.output_pair_id)
        await self._discard_pairs(tag, [result.output_pair_id])
        return {
            "passed": True,
            "reason": None,
            "baseline_fidelity": 0.90,
            "output_fidelity": result.output_fidelity,
        }

    async def _swap(self, left: str, repeater: str, right: str, tag: str, owned: List[str]) -> Dict[str, Any]:
        try:
            first = await self.pool.create_pair(left, repeater, fidelity=1.0, operation_id=f"{tag}-swap-a")
            owned.append(first.pair_id)
            second = await self.pool.create_pair(repeater, right, fidelity=1.0, operation_id=f"{tag}-swap-b")
            owned.append(second.pair_id)
            result = await self.mesh.swapper.swap(first.pair_id, second.pair_id, operation_id=f"{tag}-swap")
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "swap_failed")}
        fidelity = result.output_fidelity
        passed = bool(result.accepted) and isinstance(fidelity, float) and fidelity >= 0.95
        if result.output_pair_id is not None:
            owned.append(result.output_pair_id)
        return {
            "passed": passed,
            "reason": None if passed else "swap_below_threshold",
            "fidelity": fidelity,
            "pair_id": result.output_pair_id,
        }

    async def _teleport(
        self, source: str, target: str, pair_id: str | None, tag: str,
        owned: List[str], owned_outputs: List[tuple],
    ) -> Dict[str, Any]:
        if not pair_id:
            return {"passed": False, "reason": "no_swap_output", "payload": None}
        try:
            result = await self.protocol.teleport_qubit(
                source, target, 1 + 0j, 0j, bell_pair=pair_id, operation_id=f"{tag}-teleport",
            )
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "teleport_failed"), "payload": None}
        correction = result.correction
        payload = {
            "model_version": 1,
            "frame_x": int(correction.frame_x),
            "frame_z": int(correction.frame_z),
            "bsm_x": int(correction.bsm_x),
            "bsm_z": int(correction.bsm_z),
            "correction_x": int(correction.correction_x),
            "correction_z": int(correction.correction_z),
            "gate_x": bool(result.gate_x),
            "gate_z": bool(result.gate_z),
            "correction_applied": bool(result.correction_applied),
            "acknowledged": bool(result.acknowledged),
            "input_destroyed": bool(result.input_destroyed),
            "resource_consumed": bool(result.resource_consumed),
            "fidelity": result.fidelity,
        }
        passed = bool(result.success) and isinstance(result.fidelity, float) and result.fidelity >= 0.95
        if result.output is not None:
            owned_outputs.append((result.session_id, target))
        return {"passed": passed, "reason": None if passed else result.reason, "payload": payload, "fidelity": result.fidelity}

    async def _bb84(self, sender: str, receiver: str, tag: str, owned: List[str], *, intercept: bool) -> Dict[str, Any]:
        try:
            session = await self.engine.run_bb84(sender, receiver, 12000, intercept=intercept)
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "qkd_failed"), "session": None}
        owned.append(session.session_id)
        if intercept:
            passed = (
                session.status == "aborted"
                and session.reason == "qber_exceeded"
                and session.keys_agreed is False
                and session.key_commitment_hex is None
            )
        else:
            passed = (
                session.status == "established"
                and session.keys_agreed is True
                and session.extracted_bits >= 128
                and isinstance(session.key_commitment_hex, str)
                and len(session.key_commitment_hex) == 64
            )
        return {"passed": passed, "reason": session.reason, "session": session}

    async def _emit_failed(self, reason: str) -> None:
        if self.ledger is None:
            return
        try:
            await self.ledger.append_event({
                "event_type": "drill.summary",
                "session_id": "drill-failed",
                "actor": "drill",
                "nodes": [],
                "resources": [],
                "outcome": "failed",
                "payload": {"reason": reason},
            })
        except Exception:
            return


class LedgerShapeError(ValueError):
    """Drill summary rejected by the ledger's public validators."""


def _drill_report(all_passed: bool, prerequisite: str | None, stages: Dict[str, Any]) -> Dict[str, Any]:
    public_stages = {}
    for name, stage in stages.items():
        if name in ("clean_bb84", "eve"):
            session = stage.get("session")
            public_stages[name] = {
                "passed": bool(stage.get("passed")),
                "reason": stage.get("reason"),
                "status": getattr(session, "status", None),
                "qber": getattr(session, "qber", None),
                "extracted_bits": getattr(session, "extracted_bits", None),
                "keys_agreed": getattr(session, "keys_agreed", None),
            }
        else:
            item = {key: value for key, value in stage.items() if key != "session"}
            public_stages[name] = item
    return {
        "all_passed": bool(all_passed),
        "prerequisite": prerequisite,
        "stages": public_stages,
    }


def _drill_summary_event(*, nodes, teleport, purify, swap, clean, eve) -> Dict[str, Any]:
    return {
        "event_type": "drill.summary",
        "session_id": "drill-summary",
        "actor": "drill",
        "nodes": list(nodes),
        "resources": [],
        "outcome": "success",
        "payload": {
            "teleport": dict(teleport),
            "purification": {
                "baseline_fidelity": purify["baseline_fidelity"],
                "output_fidelity": purify["output_fidelity"],
            },
            "swap": {"fidelity": swap["fidelity"]},
            "clean": {
                "sifted_count": int(clean.sifted_count),
                "test_count": int(clean.test_count),
                "error_count": int(clean.error_count),
                "output_bits": int(clean.extracted_bits),
                "established": True,
                "key_agreement": True,
            },
            "eve": {
                "test_count": int(eve.test_count),
                "error_count": int(eve.error_count),
                "basis": 2,
                "aborted": True,
                "both_keyless": True,
            },
            "key_commitment_hex": clean.key_commitment_hex,
        },
    }
