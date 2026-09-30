from __future__ import annotations

from pathlib import Path

import pytest

from desk_gateway.config import SEATS
from desk_gateway.redact import contains_secret, redact_text, redact_value
from desk_gateway.rosters import RosterError, Rosters
from desk_gateway.schema import SchemaError, validate
from desk_gateway.store import Store

REPO = Path(__file__).resolve().parents[3]


def test_rosters_load_from_contracts():
    rosters = Rosters.load(REPO / "contracts")
    assert set(rosters.seats) == set(SEATS)
    for short, seat in rosters.seats.items():
        assert 10 <= len(seat.tools) <= 15, short
        assert seat.endpoint == f"/mcp/{short}"
        assert "desk_brief" in seat.tools and "desk_doctor" in seat.tools
    assert rosters.seats["lead"].tools["desk_intake_next"]
    assert "desk_intake_next" not in rosters.seats["ios"].tools
    assert set(rosters.packs) == {"kanbanos", "desklanes", "clippyos"}
    assert len(rosters.surface("ios", ["kanbanos"])) == 20


def test_roster_surface_ceiling_is_enforced():
    rosters = Rosters.load(REPO / "contracts")
    with pytest.raises(RosterError):
        rosters.surface("ios", ["kanbanos", "desklanes"])


def test_pack_surface_respects_declared_seats():
    rosters = Rosters.load(REPO / "contracts")
    assert set(rosters.pack_surface("android", "kanbanos")) == set(rosters.packs["kanbanos"].tools)
    assert rosters.pack_surface("infra", "kanbanos") == {}
    assert rosters.pack_surface("web", "nope") == {}


def test_gate_tags_require_fields():
    rosters = Rosters.load(REPO / "contracts")
    for seat in rosters.seats.values():
        for spec in seat.tools.values():
            required = set(spec.input_schema.get("required") or [])
            if "g5" in spec.gates:
                assert {"rollback_plan", "approval_id"} <= required, spec.name
            if "g6" in spec.gates:
                assert "approval_id" in required, spec.name


def test_schema_validator_defaults_required_and_extra():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": 5},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            "mode": {"type": "string", "enum": ["a", "b"]},
            "tags": {"type": "array", "maxItems": 2, "items": {"type": "string", "pattern": "^t"}},
        },
    }
    assert validate(schema, {"query": "abc"}) == {"query": "abc", "limit": 8}
    with pytest.raises(SchemaError, match="required"):
        validate(schema, {})
    with pytest.raises(SchemaError, match="not an accepted"):
        validate(schema, {"query": "abc", "nope": 1})
    with pytest.raises(SchemaError, match="longer"):
        validate(schema, {"query": "abcdefg"})
    with pytest.raises(SchemaError, match="one of"):
        validate(schema, {"query": "abc", "mode": "z"})
    with pytest.raises(SchemaError, match="above"):
        validate(schema, {"query": "abc", "limit": 99})
    with pytest.raises(SchemaError, match="expected integer"):
        validate(schema, {"query": "abc", "limit": True})
    with pytest.raises(SchemaError, match="pattern"):
        validate(schema, {"query": "abc", "tags": ["x"]})
    with pytest.raises(SchemaError, match="more than"):
        validate(schema, {"query": "abc", "tags": ["t1", "t2", "t3"]})


@pytest.mark.parametrize(
    "text",
    [
        "token ghp_abcdefghijklmnopqrstuvwxyz012345",
        "AKIAABCDEFGHIJKLMNOP",  # pragma: allowlist secret (redaction fixture)
        "postgresql://user:hunter2@host:5432/db",  # pragma: allowlist secret (redaction fixture)
        "api_key=sk-abcdefghijklmnopqrstuv",  # pragma: allowlist secret (redaction fixture)
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "xoxb-1234567890-abcdefghij",  # pragma: allowlist secret (redaction fixture)
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",  # pragma: allowlist secret (redaction fixture)
    ],
)
def test_redact_catches_secret_shapes(text: str):
    assert contains_secret(text)
    assert "<redacted>" in redact_text(text)


def test_redact_keeps_placeholders_and_plain_text():
    assert not contains_secret("SUBSTRATE_TOKEN=$SUBSTRATE_TOKEN and password: <fill-in>")
    assert not contains_secret("run pytest ci/tests -q")
    nested = redact_value({"a": ["ghp_abcdefghijklmnopqrstuvwxyz012345"], "b": {"c": "fine"}})
    assert nested == {"a": ["<redacted>"], "b": {"c": "fine"}}


def test_store_intake_is_idempotent_and_claimable(tmp_path: Path):
    store = Store(tmp_path)
    one = store.intake_create({"origin": "github", "title": "t", "ask": "do the thing", "idempotency_key": "k1"})
    two = store.intake_create({"origin": "github", "title": "t", "ask": "do the thing", "idempotency_key": "k1"})
    assert one["intake_id"] == two["intake_id"]
    assert store.intake_counts() == {"queued": 1}
    assert store.intake_next("slack") is None
    claimed = store.intake_next(None)
    assert claimed and claimed["state"] == "claimed"
    assert store.intake_next(None) is None
    acked = store.intake_ack(claimed["intake_id"], {"status": "accepted", "graph_id": "ut-abc-deadbeef", "by": "bot-00-programming-lead"})
    assert acked["state"] == "accepted" and acked["graph_id"] == "ut-abc-deadbeef"


def test_store_roster_and_packs(tmp_path: Path):
    store = Store(tmp_path)
    store.register_seat("ios", agent_uuid="a2d933ec-c6cf-43b7-a060-bec226475fb6", channel_id=None, tool_count=15)
    store.register_seat("lead", agent_uuid="8b8edded-d0ac-4dc7-ab89-d13ed150e656", channel_id="4d78b294-5b65-46a9-bec9-86cdbc54aa3e", tool_count=15)
    roster = store.roster()
    assert set(roster["seats"]) == {"ios", "lead"} and roster["channel_id"]
    store.load_pack("ios", "kanbanos", "task-1")
    assert store.packs_for("ios") == ["kanbanos"]
    store.unload_pack("ios", "kanbanos")
    assert store.packs_for("ios") == []
