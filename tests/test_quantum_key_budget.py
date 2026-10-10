"""Locked numerical budget and real-engine minimum-yield boundaries.

Independent stdlib arithmetic, not production epsilon/entropy helpers. The
short BB84 cases prepare and measure genuine independent worker candidates;
no mocked budgets, tag replies, key material or success sessions.
"""

import asyncio
import math
import random
import secrets
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "services" / "desk-gateway" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from desk_gateway.quantum_key import finite_sample_budget
from desk_gateway.quantum_node import QuantumNodeWorker
from desk_gateway.quantum_qkd_mesh import QKDProtocolEngine
from desk_gateway.quantum_teleportation import BellPairPool
from desk_gateway.quantum_transport import LocalNodeTransport


def _locked_budget(n, k, phase_error, syndrome, requested=256):
    mu = math.sqrt((n + k) / (n * k) * (k + 1) / k * math.log(4 / 1e-9))
    upper = min(0.5, phase_error + mu)
    entropy = -upper * math.log2(upper) - (1 - upper) * math.log2(1 - upper)
    estimated = n * (1 - entropy)
    # Locked public leakage policy: syndrome plus 32 verification-tag bits
    # and 48 branch/domain bits; privacy amplification uses eps_pa=1e-9.
    after = estimated - syndrome - 32 - 48
    maximum = math.floor(after - 2 * math.log2(1 / 1e-9))
    candidate = max(0, min(requested, 256, maximum) // 8 * 8)
    return {
        "mu": mu, "q_upper": upper, "h_est": estimated, "h_after": after,
        "ell_max": maximum, "ell": candidate,
    }


@pytest.mark.parametrize(
    ("maximum", "candidate"),
    ((127, 120), (128, 128), (135, 128), (136, 136), (255, 248), (256, 256), (257, 256)),
)
def test_locked_finite_key_yield_byte_and_request_boundaries(maximum, candidate):
    uncharged = _locked_budget(6000, 4000, 0.0, 0)
    syndrome = uncharged["ell_max"] - maximum
    expected = _locked_budget(6000, 4000, 0.0, syndrome)
    actual = finite_sample_budget(6000, 4000, 0.0, syndrome, 256)
    for field in ("mu", "q_upper", "h_est", "h_after"):
        assert actual[field] == pytest.approx(expected[field], abs=1e-9, rel=0)
    assert actual["ell_max"] == expected["ell_max"] == maximum
    assert actual["ell"] == expected["ell"] == candidate


@pytest.mark.parametrize("requested", (128, 136, 248, 256))
def test_locked_budget_never_extracts_beyond_explicit_request(requested):
    expected = _locked_budget(6000, 4000, 0.0, 574, requested)
    actual = finite_sample_budget(6000, 4000, 0.0, 574, requested)
    assert actual["ell_max"] == expected["ell_max"]
    assert actual["ell"] == expected["ell"] == requested


@pytest.mark.parametrize(("n", "k"), ((0, 4000), (6000, 0), (0, 0)))
def test_empty_candidate_or_phase_sample_has_no_estimated_bound_or_key(n, k):
    budget = finite_sample_budget(n, k, 0.0, 574, 256)
    assert budget["mu"] is None and budget["q_upper"] is None
    assert budget["h_est"] == 0
    assert budget["h_after"] == -574 - 32 - 48
    assert budget["ell"] == 0


@pytest.mark.parametrize(
    "phase_error",
    (math.nan, math.inf, -math.inf, -0.01, 1.01, True, False, "0", None, 10**400, -(10**400)),
    ids=("nan", "infinity", "negative-infinity", "negative", "above-one", "true", "false", "text", "missing", "huge-integer", "huge-negative-integer"),
)
def test_invalid_phase_probability_raises_domain_value_error(phase_error):
    with pytest.raises(ValueError):
        finite_sample_budget(6000, 4000, phase_error, 574, 256)


@pytest.mark.parametrize(("raw_count", "candidate"), ((4900, 120), (5000, 128)))
def test_real_worker_candidates_enforce_minimum_128_bit_yield(raw_count, candidate):
    class ObservedTransport(LocalNodeTransport):
        def __init__(self, workers):
            super().__init__(workers)
            self.extractions = 0
            self.observed_candidate_length = None

        async def qkd_step(self, node, **kwargs):
            if kwargs["action"] == "extract":
                self.extractions += 1
            reply = await super().qkd_step(node, **kwargs)
            if node == "alice" and kwargs["action"] == "lengths":
                self.observed_candidate_length = reply["key_length"]
            return reply

    async def body():
        workers = {
            "alice": QuantumNodeWorker("alice", token=secrets.token_urlsafe(24), rng=random.Random(1001)),
            "bob": QuantumNodeWorker("bob", token=secrets.token_urlsafe(24), rng=random.Random(1002)),
        }
        transport = ObservedTransport(workers)
        pool = BellPairPool(transport=transport)
        engine = QKDProtocolEngine(pool=pool, transport=transport, rng=random.Random(1003))
        session = await engine.run_bb84("alice", "bob", raw_count)
        n = transport.observed_candidate_length
        k = session.phase_test_count
        expected = _locked_budget(n, k, session.phase_error_count / k, session.syndrome_bits)
        for field in ("mu", "q_upper", "h_est", "h_after"):
            assert session.entropy_budget[field] == pytest.approx(expected[field], abs=1e-9, rel=0)
        assert session.entropy_budget["ell_max"] == expected["ell_max"]
        assert expected["ell"] == candidate
        lengths = [
            await transport.qkd_step(
                node, operation_id=f"{node}-observe-minimum", session_id=session.session_id,
                action="lengths", payload={}, instance=workers[node].instance_id,
            )
            for node in ("alice", "bob")
        ]
        if candidate < 128:
            assert session.status == "aborted" and session.reason == "insufficient_entropy"
            assert session.extracted_bits == 0 and session.keys_agreed is False
            assert session.commitment_alice_hex is None and session.commitment_bob_hex is None
            assert transport.extractions == 0
            assert all(item["state"] == "aborted" and item["key_available"] is False for item in lengths)
        else:
            assert session.status == "established" and session.reason is None
            assert session.extracted_bits == candidate and session.keys_agreed is True
            assert transport.extractions == 2
            assert all(item["state"] == "established" and item["key_available"] is True for item in lengths)
            assert await engine.release_session_keys(session.session_id, operation="drill_release")

    asyncio.run(body())
