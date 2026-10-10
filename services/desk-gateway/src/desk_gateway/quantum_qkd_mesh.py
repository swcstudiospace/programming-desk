"""Quantum Key Distribution (BB84 / E91), Entangled State Ledger & Solana Anchoring (Milestone v5.1 - Phase 69).

Implements:
- QuantumBasis: Computational Rectilinear basis (+) and Diagonal basis (x).
- QKDProtocolType: BB84 (prepare-and-measure) and E91 (EPR entanglement-based).
- QKDProtocolEngine: Simulates basis selection, qubit transmission, basis sifting,
  Quantum Bit Error Rate (QBER) calculation, error correction, and privacy amplification.
- QuantumTeleportationDrill: one shared-runtime pass whose all_passed flag is the
  confirmed-publication conjunction, never a stand-in for an unfunded signer.
"""

from __future__ import annotations

import asyncio
import enum
import re
import secrets
import time
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
    random_bits,
    sample_chsh_outcome,
    validate_count,
    validate_requested_bits,
)
from .quantum_node import QuantumNodeError, deposit_correlated_key_bits
from .quantum_state import BellState, H, X, Z
from .quantum_teleportation import (
    BellPairPool,
    BellStateType,
    QuantumRepeaterMesh,
    QuantumResourceError,
)


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


def _normalize_flips(value: object) -> tuple:
    """Test-hook flip positions (post-permutation candidate indices)."""
    if value is None:
        return ()
    try:
        items = tuple(value)
    except TypeError:
        raise ValueError("_flip_bob must be a sequence of candidate indices") from None
    for pos in items:
        if isinstance(pos, bool) or not isinstance(pos, int) or pos < 0:
            raise ValueError("_flip_bob entries must be non-negative integers")
    return items


class _WorkerBindingError(Exception):
    """No in-process worker is bound for an endpoint (fail-closed, no key)."""


@dataclass(frozen=True, slots=True)
class QKDSession:
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
        return f"QKDSession({self.session_id})"

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
    Remote QKD transport is not in this slice; key delivery uses in-process
    worker references passed as ``workers={node_id: worker}``.
    """

    def __init__(
        self,
        mesh: Optional[QuantumRepeaterMesh] = None,
        *,
        pool: Optional[BellPairPool] = None,
        transport: Any = None,
        rng: Any = None,
        append_event: Any = None,
        workers: Optional[Mapping[str, Any]] = None,
        worker_tokens: Optional[Mapping[str, str]] = None,
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
        self.transport = transport
        self._rng = rng if rng is not None else secrets.SystemRandom()
        self._append_event = append_event
        self._workers: Dict[str, Any] = dict(workers) if workers else {}
        self._worker_tokens: Dict[str, str] = dict(worker_tokens) if worker_tokens else {}
        self.sessions: Dict[str, QKDSession] = {}

    def _scope(self, node: str) -> tuple:
        worker = self._workers.get(node)
        if worker is None:
            raise _WorkerBindingError(f"no worker bound for {node}")
        token = self._worker_tokens.get(node, getattr(worker, "_token", ""))
        return worker, token, worker.instance_id

    async def _bind(self, session_id: str, sender: str, receiver: str) -> bool:
        """Bind role/session/ownership on both endpoint workers."""
        try:
            for node, role, peer in (
                (sender, "alice", receiver),
                (receiver, "bob", sender),
            ):
                worker, token, instance = self._scope(node)
                await worker.begin_qkd(
                    operation_id=f"{session_id}-begin-{node}",
                    session_id=session_id,
                    role=role,
                    peer=peer,
                    owner=node,
                    token=token,
                    node=node,
                    instance=instance,
                )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return False
        return True

    async def _mirror(self, sender: str, receiver: str, session_id: str, op: str, method: str, **kwargs: Any) -> bool:
        """Invoke a session-scoped step on both endpoint workers."""
        try:
            for node in (sender, receiver):
                worker, token, instance = self._scope(node)
                await getattr(worker, method)(
                    operation_id=f"{session_id}-{op}-{node}",
                    session_id=session_id,
                    token=token,
                    node=node,
                    instance=instance,
                    **kwargs,
                )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return False
        return True

    async def _abort_workers(self, sender: str, receiver: str, session_id: str) -> None:
        """Best-effort key-availability destruction on both workers."""
        for node in (sender, receiver):
            try:
                worker, token, instance = self._scope(node)
                await worker.abort(
                    operation_id=f"{session_id}-abort-{node}",
                    session_id=session_id,
                    token=token,
                    node=node,
                    instance=instance,
                )
            except Exception:
                continue

    async def _emit(self, session: QKDSession) -> Optional[str]:
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
            body["chsh_counts"] = dict(chsh.get("counts", {}))
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
    ) -> QKDSession:
        sid = session_id or f"{prefix}-{secrets.token_hex(8)}"
        if bound:
            await self._abort_workers(sender, receiver, sid)
        session = QKDSession(
            session_id=sid,
            protocol=protocol,
            status="aborted",
            reason=reason,
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
    ) -> QKDSession:
        sid = session_id or f"{prefix}-{secrets.token_hex(8)}"
        await self._abort_workers(sender, receiver, sid)
        session = QKDSession(
            session_id=sid,
            protocol=protocol,
            status="failed",
            reason=None,
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
        _flip_bob: Optional[Sequence[int]] = None,
    ) -> QKDSession:
        """Run one BB84 session: kernel preparation, Born measurement, sifting."""
        t0 = time.perf_counter()
        sender = _check_endpoint(sender, "sender")
        receiver = _check_endpoint(receiver, "receiver")
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        bit_length = validate_count("bit_length", bit_length)
        requested_bits = validate_requested_bits(requested_bits)
        if not isinstance(intercept, bool):
            raise ValueError("intercept must be a bool")
        flips = _normalize_flips(_flip_bob)
        if bit_length == 0:
            return await self._abort(
                sender, receiver, "BB84", 0, "insufficient_sample",
                requested_bits, t0, prefix="qkd-bb84",
            )
        session_id = f"qkd-bb84-{secrets.token_hex(8)}"
        if not await self._bind(session_id, sender, receiver):
            return await self._fail(sender, receiver, "BB84", bit_length, t0, prefix="qkd-bb84", session_id=session_id)
        rng = self._rng
        try:
            alice, token_a, inst_a = self._scope(sender)
            bob, token_b, inst_b = self._scope(receiver)
            prepared = await alice.qkd_prepare_bb84(
                operation_id=f"{session_id}-prepare",
                session_id=session_id,
                count=bit_length,
                rng=rng,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            states = prepared["states"]
            bases_a = prepared["bases"]
            if intercept:
                # Numerical intercept-resend. Eve's click is the attack sample;
                # Alice's bits stay in her vault.
                resent = []
                for vec in states:
                    eve_basis = rng.choice(("+", "x"))
                    probed = vec.apply_single(H, 0) if eve_basis == "x" else vec
                    eve_bit = int(probed.density().measure_z((0,), rng).bits[0])
                    resent.append(bb84_state(eve_bit, eve_basis))
                states = resent
            bases_b = [rng.choice(("+", "x")) for _ in range(bit_length)]
            await bob.qkd_measure_bb84(
                operation_id=f"{session_id}-measure",
                session_id=session_id,
                states=states,
                bases=bases_b,
                rng=rng,
                token=token_b,
                node=receiver,
                instance=inst_b,
            )
            del states
            # Sift on basis match. The matching indices are shuffled before the
            # Z/X split so the phase sample is not a first-N prefix.
            sifted = [i for i in range(bit_length) if bases_a[i] == bases_b[i]]
            order = list(sifted)
            rng.shuffle(order)
            key_idx = [i for i in order if bases_a[i] == "+"]
            phase_idx = [i for i in order if bases_a[i] == "x"]
            part_a = await alice.qkd_adopt_indices(
                operation_id=f"{session_id}-sift-a",
                session_id=session_id,
                key_indices=key_idx,
                phase_indices=phase_idx,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            part_b = await bob.qkd_adopt_indices(
                operation_id=f"{session_id}-sift-b",
                session_id=session_id,
                key_indices=key_idx,
                phase_indices=phase_idx,
                token=token_b,
                node=receiver,
                instance=inst_b,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, "BB84", bit_length, t0, prefix="qkd-bb84", session_id=session_id)
        return await self._finish(
            sender=sender,
            receiver=receiver,
            protocol="BB84",
            session_id=session_id,
            raw_count=bit_length,
            sifted_count=len(sifted),
            phase_a=part_a["phase_bits"],
            phase_b=part_b["phase_bits"],
            requested_bits=requested_bits,
            flips=flips,
            t0=t0,
        )

    async def run_e91(
        self,
        sender: str,
        receiver: str,
        pair_count: int,
        *,
        requested_bits: int = 256,
    ) -> QKDSession:
        """Run one E91 session over real pool pairs with a CHSH witness."""
        t0 = time.perf_counter()
        sender = _check_endpoint(sender, "sender")
        receiver = _check_endpoint(receiver, "receiver")
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        pair_count = validate_count("pair_count", pair_count)
        requested_bits = validate_requested_bits(requested_bits)
        if pair_count == 0:
            return await self._abort(
                sender, receiver, "E91", 0, "insufficient_sample",
                requested_bits, t0, prefix="qkd-e91",
            )
        session_id = f"qkd-e91-{secrets.token_hex(8)}"
        if not await self._bind(session_id, sender, receiver):
            return await self._fail(sender, receiver, "E91", pair_count, t0, prefix="qkd-e91", session_id=session_id)
        rng = self._rng
        # Pre-randomized disjoint round classes: CHSH witness, key (Z/Z),
        # and phase-test (X/X). pair_count is not simultaneous qubit count:
        # pairs stream one at a time inside worker capacity.
        order = list(range(pair_count))
        rng.shuffle(order)
        n_chsh = pair_count // 2
        rest = pair_count - n_chsh
        n_key = rest * 3 // 5
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
        try:
            for i in range(pair_count):
                pair = await self.pool.create_pair(
                    sender, receiver, BellStateType.PHI_PLUS, 1.0,
                    operation_id=f"{session_id}-mk-{i}",
                )
                try:
                    rho = pair.oriented(sender, receiver)
                    # Normalize non-Phi+ frames with local Paulis before sampling.
                    frame_x, frame_z = BellState(pair.state_type.value).frame
                    if frame_x:
                        rho = rho.apply_single(X, 1)
                    if frame_z:
                        rho = rho.apply_single(Z, 1)
                    kind = kinds[i]
                    if kind == "chsh":
                        setting = chsh_settings[i]
                        a_bit, b_bit = sample_chsh_outcome(rho, setting // 2, setting % 2, rng)
                        chsh_records.append((setting, a_bit, b_bit))
                    elif kind == "key":
                        alice_w, token_a, inst_a = self._scope(sender)
                        bob_w, token_b, inst_b = self._scope(receiver)
                        await deposit_correlated_key_bits(
                            alice_w, bob_w, rho, session_id, rng,
                            f"{session_id}-key-{i}",
                            {"token": token_a, "node": sender, "instance": inst_a},
                            {"token": token_b, "node": receiver, "instance": inst_b},
                        )
                    else:
                        evolved = rho.apply_single(H, 0).apply_single(H, 1)
                        branch = evolved.measure_z((0, 1), rng)
                        pa, pb = (int(v) for v in branch.bits)
                        phase_a.append(pa)
                        phase_b.append(pb)
                finally:
                    # Every pair is consumed once, including aborts.
                    op = f"{session_id}-use-{i}"
                    await self.pool.reserve_pairs([pair.pair_id], operation_id=op)
                    await self.pool.consume_pairs([pair.pair_id], operation_id=op)
                    await self.pool.release_pair_leases(pair.pair_id, operation_id=op)
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, "E91", pair_count, t0, prefix="qkd-e91", session_id=session_id)
        try:
            alice_w, token_a, inst_a = self._scope(sender)
            held = await alice_w.qkd_lengths(
                operation_id=f"{session_id}-len",
                session_id=session_id,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            sifted_count = int(held["key_len"]) + len(phase_a)
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, "E91", pair_count, t0, prefix="qkd-e91", session_id=session_id)
        try:
            chsh = estimate_chsh(chsh_records)
        except ValueError:
            return await self._abort(
                sender, receiver, "E91", pair_count, "insufficient_sample",
                requested_bits, t0, prefix="qkd-e91", bound=True,
                sifted_count=sifted_count, session_id=session_id,
            )
        if not chsh["passed"]:
            return await self._abort(
                sender, receiver, "E91", pair_count, "entanglement_witness_failed",
                requested_bits, t0, prefix="qkd-e91", bound=True,
                sifted_count=sifted_count, chsh=chsh, session_id=session_id,
            )
        return await self._finish(
            sender=sender,
            receiver=receiver,
            protocol="E91",
            session_id=session_id,
            raw_count=pair_count,
            sifted_count=sifted_count,
            phase_a=phase_a,
            phase_b=phase_b,
            requested_bits=requested_bits,
            flips=(),
            t0=t0,
            chsh=chsh,
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
        flips: Sequence[int],
        t0: float,
        chsh: Optional[Dict[str, Any]] = None,
    ) -> QKDSession:
        """Reconcile and extract on the workers. This object never keeps key bytes."""
        prefix = "qkd-bb84" if protocol == "BB84" else "qkd-e91"
        rng = self._rng
        k = len(phase_a)
        errors = sum(1 for a, b in zip(phase_a, phase_b) if a != b)
        if k == 0:
            return await self._abort(
                sender, receiver, protocol, raw_count, "insufficient_sample",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, chsh=chsh, session_id=session_id,
            )
        qber = errors / float(k)
        # Exact integer admission before any float serialization.
        if qber_exceeds(errors, k):
            return await self._abort(
                sender, receiver, protocol, raw_count, "qber_exceeded",
                requested_bits, t0, prefix=prefix, bound=True,
                sifted_count=sifted_count, test_count=k, error_count=errors,
                qber=qber, chsh=chsh, session_id=session_id,
            )
        try:
            alice, token_a, inst_a = self._scope(sender)
            bob, token_b, inst_b = self._scope(receiver)
            held = await alice.qkd_lengths(
                operation_id=f"{session_id}-keylen",
                session_id=session_id,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            n = int(held["key_len"])
            if any(isinstance(pos, bool) or not isinstance(pos, int) or pos >= n for pos in flips):
                return await self._fail(sender, receiver, protocol, raw_count, t0, prefix=prefix, session_id=session_id)
            if n == 0:
                return await self._abort(
                    sender, receiver, protocol, raw_count, "insufficient_entropy",
                    requested_bits, t0, prefix=prefix, bound=True,
                    sifted_count=sifted_count, test_count=k, error_count=errors,
                    qber=qber, chsh=chsh, session_id=session_id,
                )
            perm = list(range(n))
            rng.shuffle(perm)
            syn = await alice.qkd_syndrome(
                operation_id=f"{session_id}-syn",
                session_id=session_id,
                order=perm,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            await bob.qkd_correct(
                operation_id=f"{session_id}-correct",
                session_id=session_id,
                order=perm,
                syndromes=syn["syndromes"],
                flip_positions=tuple(flips),
                token=token_b,
                node=receiver,
                instance=inst_b,
            )
            syndrome_len = int(syn["syndrome_bits"])
            tag_seed = random_bits(rng, n + L_TAG32 - 1)
            tag_a = await alice.qkd_tag(
                operation_id=f"{session_id}-tag-a",
                session_id=session_id,
                seed=tag_seed,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            tag_b = await bob.qkd_tag(
                operation_id=f"{session_id}-tag-b",
                session_id=session_id,
                seed=tag_seed,
                token=token_b,
                node=receiver,
                instance=inst_b,
            )
            if tag_a["tag"] != tag_b["tag"]:
                return await self._abort(
                    sender, receiver, protocol, raw_count, "reconciliation_failed",
                    requested_bits, t0, prefix=prefix, bound=True,
                    sifted_count=sifted_count, test_count=k, error_count=errors,
                    qber=qber, syndrome_bits=syndrome_len, chsh=chsh, session_id=session_id,
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
                    budget=budget, chsh=chsh, session_id=session_id,
                )
            pa_seed = random_bits(rng, n + ell - 1)
            ext_a = await alice.qkd_extract(
                operation_id=f"{session_id}-extract-a",
                session_id=session_id,
                seed=pa_seed,
                rng=rng,
                token=token_a,
                node=sender,
                instance=inst_a,
            )
            ext_b = await bob.qkd_extract(
                operation_id=f"{session_id}-extract-b",
                session_id=session_id,
                seed=pa_seed,
                rng=rng,
                token=token_b,
                node=receiver,
                instance=inst_b,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except Exception:
            return await self._fail(sender, receiver, protocol, raw_count, t0, prefix=prefix, session_id=session_id)
        commit_a = ext_a["commitment_hex"]
        commit_b = ext_b["commitment_hex"]
        aggregate = aggregate_commitment(commit_a, commit_b)
        key_id = secrets.token_hex(8)
        session = QKDSession(
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
        receipt_id = await self._emit(session)
        session = replace(session, receipt_id=receipt_id)
        self.sessions[session_id] = session
        return session





class DrillBusy(Exception):
    """Another drill is already running on this runtime."""


class QuantumTeleportationDrill:
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
        names = list(getattr(self.mesh, "nodes", {}))
        if self.ledger is None:
            return _drill_report(False, "ledger_unavailable", stages)
        if len(names) < 3:
            return _drill_report(False, "route_needs_three_nodes", stages)
        left, repeater, right = names[0], names[1], names[2]
        bound = getattr(self.engine, "_workers", {})
        if left not in bound or right not in bound:
            return _drill_report(False, "worker_plane_unavailable", stages)

        purify = await self._purify(left, repeater, tag)
        stages["purify"] = purify
        swap = await self._swap(left, repeater, right, tag)
        stages["swap"] = swap
        teleport = await self._teleport(left, right, swap.get("pair_id"), tag)
        stages["teleport"] = teleport
        clean = await self._bb84(left, right, intercept=False)
        stages["clean_bb84"] = clean
        eve = await self._bb84(left, right, intercept=True)
        stages["eve"] = eve
        numerical = all(stage.get("passed") for stage in (purify, swap, teleport, clean, eve))
        if not numerical:
            await self._emit_failed("numerical_stage_failed")
            return _drill_report(False, "numerical_stage_failed", stages)

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

    async def _purify(self, left: str, repeater: str, tag: str) -> Dict[str, Any]:
        try:
            first = await self.pool.create_pair(left, repeater, fidelity=0.90, operation_id=f"{tag}-pur-a")
            second = await self.pool.create_pair(left, repeater, fidelity=0.92, operation_id=f"{tag}-pur-b")
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
        return {
            "passed": True,
            "reason": None,
            "baseline_fidelity": 0.90,
            "output_fidelity": result.output_fidelity,
        }

    async def _swap(self, left: str, repeater: str, right: str, tag: str) -> Dict[str, Any]:
        try:
            first = await self.pool.create_pair(left, repeater, fidelity=1.0, operation_id=f"{tag}-swap-a")
            second = await self.pool.create_pair(repeater, right, fidelity=1.0, operation_id=f"{tag}-swap-b")
            result = await self.mesh.swapper.swap(first.pair_id, second.pair_id, operation_id=f"{tag}-swap")
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "swap_failed")}
        fidelity = result.output_fidelity
        passed = bool(result.accepted) and isinstance(fidelity, float) and fidelity >= 0.95
        return {
            "passed": passed,
            "reason": None if passed else "swap_below_threshold",
            "fidelity": fidelity,
            "pair_id": result.output_pair_id,
        }

    async def _teleport(self, source: str, target: str, pair_id: str | None, tag: str) -> Dict[str, Any]:
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
        return {"passed": passed, "reason": None if passed else result.reason, "payload": payload, "fidelity": result.fidelity}

    async def _bb84(self, sender: str, receiver: str, *, intercept: bool) -> Dict[str, Any]:
        try:
            session = await self.engine.run_bb84(sender, receiver, 12000, intercept=intercept)
        except (QuantumResourceError, QuantumNodeError, ValueError) as exc:
            return {"passed": False, "reason": getattr(exc, "code", "qkd_failed"), "session": None}
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
