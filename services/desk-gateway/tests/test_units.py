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


def test_store_intake_idempotency_is_scoped_by_origin(tmp_path: Path):
    """Two origins may pick the same key; neither may swallow the other's request.

    Intake tokens authenticate separate origins and each builds its own keys, so a
    collision is expected rather than exceptional. Deduplicating on the key alone told
    the second caller it had been accepted while queueing nothing.
    """
    store = Store(tmp_path)
    gh = store.intake_create({"origin": "github", "title": "t", "ask": "do the thing", "idempotency_key": "shared"})
    slack = store.intake_create({"origin": "slack", "title": "t", "ask": "do another thing", "idempotency_key": "shared"})
    assert gh["intake_id"] != slack["intake_id"]
    assert store.intake_counts() == {"queued": 2}

    # Still idempotent within one origin.
    again = store.intake_create({"origin": "github", "title": "t", "ask": "do the thing", "idempotency_key": "shared"})
    assert again["intake_id"] == gh["intake_id"]
    assert store.intake_counts() == {"queued": 2}


@pytest.mark.parametrize("surface", [
    "contracts/../../../etc/passwd",
    "contracts/../../root/.ssh/authorized_keys",
    "/etc/passwd",
    "contracts/ok/../../../../tmp/escaped.yaml",
])
def test_safe_path_rejects_the_escaping_surfaces(surface: str):
    """Unit-level check on the guard itself.

    Whether contract_propose actually *calls* it is a separate question, covered
    end-to-end by test_contract_propose_* in test_server.py. Both layers are needed:
    this one localises a change to the pattern, those catch the guard being dropped.
    """
    from desk_gateway.repo import safe_path
    assert not safe_path(surface), f"{surface!r} would be joined onto the proposal tree"


@pytest.mark.parametrize("surface", ["contracts/api/notifications.yaml", "openapi.yaml"])
def test_safe_path_still_accepts_legitimate_surfaces(surface: str):
    from desk_gateway.repo import safe_path
    assert safe_path(surface)


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


@pytest.mark.parametrize("sql", [
    "SELECT 'delete'",                              # write keyword inside a literal
    "SELECT * FROM t WHERE name LIKE '%create%'",   # ... and inside a LIKE pattern
    "SELECT 1 -- drop table x",                     # ... and inside a comment
    "/* note */ SELECT 1",
    "SELECT 'a;b'",                                 # semicolon inside a literal
    "WITH c AS (SELECT 1) SELECT * FROM c",
])
def test_read_only_sql_accepts_ordinary_reads(sql: str):
    """Scanning the raw text rejected these: the keyword pattern matched inside quotes."""
    from desk_gateway.upstreams import read_only_sql
    assert read_only_sql(sql) is None, f"{sql!r} was refused"


@pytest.mark.parametrize("sql", [
    "DELETE FROM t",
    "UPDATE t SET a = 1",
    "INSERT INTO t VALUES (1)",
    "SELECT 1; DROP TABLE t",                       # write smuggled after a read
    "SELECT 1 WHERE x = 'a'; DROP TABLE t",         # ... past a literal
    "SELECT 1; SELECT 2",                           # two statements
])
def test_read_only_sql_still_refuses_writes(sql: str):
    """The point of blanking literals is to keep this list rejected while reads pass."""
    from desk_gateway.upstreams import read_only_sql
    assert read_only_sql(sql) is not None, f"{sql!r} was accepted"


async def test_run_command_kills_the_child_on_timeout(monkeypatch):
    """asyncio.wait_for stops waiting; it does not stop the process.

    Left unreaped, a slow gate or git command outlives the call that reported a timeout,
    under the gateway's root service user and holding its export tree open.

    Identifies the child by the pid run_command actually started, not by matching process
    names: the gates run on a shared self-hosted runner, so another job's `sleep 30` would
    otherwise turn this red while this code was behaving correctly.
    """
    import asyncio
    import os
    from desk_gateway import upstreams

    started: list[asyncio.subprocess.Process] = []
    real_exec = asyncio.create_subprocess_exec

    async def capturing_exec(*args, **kwargs):
        proc = await real_exec(*args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(upstreams.asyncio, "create_subprocess_exec", capturing_exec)

    result = await upstreams.run_command(["sleep", "30"], timeout=0.5)
    assert result["exit_code"] == 124
    assert "timed out" in result["stderr"]

    assert len(started) == 1, f"expected one child, saw {len(started)}"
    child = started[0]

    # Reaped: returncode is set, so the process was waited on rather than left a zombie.
    assert child.returncode is not None, "child was not reaped; returncode is still None"

    # And genuinely gone: signal 0 probes for existence without delivering anything.
    with pytest.raises(ProcessLookupError):
        os.kill(child.pid, 0)


def test_settings_fixture_ignores_ambient_upstream_credentials(monkeypatch, settings):
    """The suite must not pick up whatever tokens the host happens to hold.

    An ambient GITHUB_TOKEN made the GitHub upstream `configured`, so tests issued live API
    calls and test_intake_flow_only_lead_can_drain passed or failed depending on the
    machine. On the persistent self-hosted runner the same leak covers Railway, Vercel,
    Play Console and App Store Connect.
    """
    assert settings.github_token == "", "ambient GITHUB_TOKEN reached Settings"
    assert settings.railway_api_token == ""
    assert settings.vercel_token == ""
    assert settings.play_access_token == ""
    assert settings.asc_private_key_path == ""


def test_settings_env_name_discovery_still_matches_config():
    """The isolation above is only as good as its list of variable names."""
    from tests.conftest import _settings_env_names
    names = _settings_env_names()
    for expected in ("GITHUB_TOKEN", "RAILWAY_API_TOKEN", "VERCEL_TOKEN",
                     "PLAY_ACCESS_TOKEN", "ASC_PRIVATE_KEY_PATH",  # pragma: allowlist secret (env var names, no values)
                     "HINDSIGHT_API_KEY"):
        assert expected in names, f"{expected} is no longer discovered; it would leak"
