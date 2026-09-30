from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

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


def test_store_records_ack_delivery_separately_from_the_advance(tmp_path: Path):
    """The delivery record has to survive a failed advance, which is the whole point of it.

    tools.lead.intake_ack posts the origin reply before advancing, so a failed advance asks
    LEAD to call again; only a record written before the post can tell that second call a
    comment may already exist. Per ack key, so a later ack is its own delivery.
    """
    store = Store(tmp_path)
    created = store.intake_create({"origin": "github", "title": "t", "ask": "do the thing"})
    intake_id = created["intake_id"]

    assert store.intake_delivery_get(created, "accepted:abc") == {}
    store.intake_delivery(intake_id, "accepted:abc", "attempted")
    first = store.intake_delivery_get(store.intake_get(intake_id), "accepted:abc")
    assert first["state"] == "attempted" and first["first_at"] == first["at"]

    # A second attempt keeps first_at: it is the moment a recovery lookup searches from, and
    # moving it forward would move the window past the comment it is looking for.
    store.intake_delivery(intake_id, "accepted:abc", "attempted")
    second = store.intake_delivery_get(store.intake_get(intake_id), "accepted:abc")
    assert second["first_at"] == first["first_at"]

    store.intake_delivery(intake_id, "accepted:abc", "delivered")
    reread = store.intake_get(intake_id)
    assert store.intake_delivery_get(reread, "accepted:abc")["state"] == "delivered"
    assert store.intake_delivery_get(reread, "done:xyz") == {}
    assert store.intake_delivery("in-nosuchintake", "accepted:abc", "attempted") is None

    # Nothing was sent, so the next attempt is a first attempt again rather than inheriting a
    # search window for a post that never happened.
    store.intake_delivery(intake_id, "done:xyz", "attempted")
    store.intake_delivery(intake_id, "done:xyz", "unconfigured")
    assert "first_at" not in store.intake_delivery_get(store.intake_get(intake_id), "done:xyz")


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


def _alive(pid: int) -> bool:
    import os

    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.split(") ", 1)[1].split()[0] != "Z"  # a zombie has been killed, just not reaped


async def test_run_command_kills_the_whole_tree_when_it_times_out(tmp_path: Path):
    """A timeout has to end the command, not just stop waiting for it.

    Returning exit 124 without killing left the child running with the pipes it had been
    given: a gate that hangs cost a process and two file descriptors per call, and its own
    children — git, above all, holding an index lock — outlived even that.
    """
    import asyncio
    import os

    from desk_gateway.upstreams import run_command

    pidfile = tmp_path / "pids"
    result = await run_command(
        ["bash", "-c", f"(echo $$ >> {pidfile}; exec sleep 60) & echo $$ >> {pidfile}; sleep 60"],
        timeout=1,
    )
    assert result["exit_code"] == 124 and "timed out" in result["stderr"]

    pids = [int(line) for line in pidfile.read_text().split()]
    assert len(pids) == 2, "the test's own child never started"
    assert not _alive(pids[1]), "the command itself is still running"

    for _ in range(30):                     # the grandchild is reparented; give it a moment
        if not any(_alive(pid) for pid in pids):
            break
        await asyncio.sleep(0.1)
    alive = [pid for pid in pids if _alive(pid)]
    assert not alive, f"{len(alive)} process(es) outlived the timeout"
    assert os.getpid() not in pids


@pytest.mark.parametrize("existing,expected", [
    # The release being staged replaces the one that carried its version code, and nothing else.
    ([{"versionCodes": ["7"], "status": "completed"}],
     [{"versionCodes": ["7"], "status": "completed"}, "STAGED"]),
    ([{"versionCodes": ["9"], "status": "inProgress"}], ["STAGED"]),
    ([{"versionCodes": ["7"], "status": "completed"}, {"versionCodes": ["9"], "status": "inProgress"}],
     [{"versionCodes": ["7"], "status": "completed"}, "STAGED"]),
    # A version code belongs to one release only, so it leaves the others.
    ([{"versionCodes": ["7", "9"], "status": "completed"}],
     [{"versionCodes": ["7"], "status": "completed"}, "STAGED"]),
    # Nothing on the track yet, and a release the API gave us with no version codes at all.
    ([], ["STAGED"]),
    ([{"name": "notes", "status": "draft"}], [{"name": "notes", "status": "draft"}, "STAGED"]),
])
def test_merge_release_never_drops_a_release_it_was_handed(existing, expected):
    from desk_gateway.tools.mobile import _merge_release

    staged = {"versionCodes": ["9"], "status": "inProgress", "userFraction": 0.1}
    merged = _merge_release([dict(e) for e in existing], staged, "9")
    assert merged == [staged if e == "STAGED" else e for e in expected]


# ---------------------------------------------------------------------------
# quality.receipt_approve / _commit_file — the C-1 (stamp) + C-2 (TOCTOU) path
#
# Against a real bare "origin" and a real gateway checkout, not mocks: _commit_file shells
# out to git clone/push, and the TOCTOU guard it exists for is exactly the kind of thing a
# mock would quietly assume away.
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_gateway_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A bare 'origin' plus a local gateway checkout of it.

    Repo.run_gate() reads ci/gates/*.py from the gateway's own checkout dir, never from the
    branch under review, so the checkout needs a real copy of the gate scripts to run G-2/G-3/
    G-5-6 at all.
    """
    bare = tmp_path / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--quiet", "--bare")
    # git init's default HEAD (master/main per this host's init.defaultBranch) is not "trunk",
    # and pushing to an empty bare repo does not repoint it — left alone, `gateway`'s clone
    # would check out an empty tree with no ci/gates/*.py in it at all.
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/trunk")

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--quiet")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    shutil.copytree(REPO / "ci", seed / "ci")
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "--quiet", "-m", "seed")
    _git(seed, "branch", "-M", "trunk")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "--quiet", "-u", "origin", "trunk")

    gateway = tmp_path / "gateway"
    _git(tmp_path, "clone", "--quiet", str(bare), str(gateway))
    return bare, gateway


_push_counter = 0


def _push_receipt(bare: Path, tmp_path: Path, branch: str, receipt_path: str, receipt: dict) -> str:
    """Commit `receipt` to `receipt_path` on `branch` of `bare`, creating the branch if needed.

    Returns the new commit sha, so a test can pin an earlier read against a later push.
    """
    global _push_counter
    _push_counter += 1
    work = tmp_path / f"push-{_push_counter}"
    _git(tmp_path, "clone", "--quiet", str(bare), str(work))
    exists = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", str(bare), branch],
        capture_output=True, text=True,
    ).returncode == 0
    if exists:
        _git(work, "checkout", "--quiet", "-B", branch, f"origin/{branch}")
    else:
        _git(work, "checkout", "--quiet", "-b", branch)
    target = work / receipt_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    _git(work, "add", "-f", receipt_path)
    _git(work, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "--quiet", "-m", "receipt")
    _git(work, "push", "--quiet", "origin", branch)
    return _git(work, "rev-parse", "HEAD")


def _receipt_on_remote(bare: Path, branch: str, receipt_path: str) -> dict:
    return json.loads(_git(bare, "show", f"{branch}:{receipt_path}"))


def _ctx(gateway_dir: Path, bot_id: str = "bot-06-quality-security") -> "ToolContext":
    from desk_gateway.repo import Repo
    from desk_gateway.tools import ToolContext

    settings = SimpleNamespace(repo_dir=gateway_dir, repo_remote="origin", repo_branch="trunk", gate_user="")
    repo = Repo(settings)
    return ToolContext(services=SimpleNamespace(repo=repo), seat=SimpleNamespace(bot_id=bot_id, short="quality"), spec=None)


async def test_receipt_approve_stamps_the_first_approval_and_pushes(tmp_path: Path):
    """First-stamp case: an unstamped receipt, gated post-stamp (C-1) and pushed (C-2)."""
    from desk_gateway.tools import quality

    bare, gateway = _make_gateway_repo(tmp_path)
    branch = "bot-01-systems-backend/receipt-first-stamp"
    receipt_path = ".receipts/bot-01-systems-backend/first-stamp.json"
    receipt = {
        "task_id": "first-stamp-regression",
        "bot": "bot-01-systems-backend",
        "commands": [{"cmd": "pytest -q services/desk-gateway/tests", "exit_code": 0}],
        "claims": [{"claim": "unit tests pass", "evidence_command_index": 0}],
        "unverified": ["no live run against the deployed gateway process"],
        "approved_by": "",
    }
    _push_receipt(bare, tmp_path, branch, receipt_path, receipt)

    ctx = _ctx(gateway)
    out = await quality.receipt_approve(ctx, {"branch": branch, "receipt_path": receipt_path})

    assert out["ok"] is True, out
    assert out["approved_by"] == ctx.bot_id

    stamped = _receipt_on_remote(bare, branch, receipt_path)
    assert stamped["approved_by"] == ctx.bot_id
    assert stamped["approved_at"]
    assert stamped["claims"][0]["evidence_command_index"] == 0


async def test_receipt_approve_rejects_a_claim_with_free_text_evidence(tmp_path: Path):
    """G-2 requires evidence_command_index; a prose 'evidence' string cites no command."""
    from desk_gateway.tools import quality

    bare, gateway = _make_gateway_repo(tmp_path)
    branch = "bot-01-systems-backend/receipt-free-text-evidence"
    receipt_path = ".receipts/bot-01-systems-backend/free-text.json"
    receipt = {
        "task_id": "free-text-regression",
        "bot": "bot-01-systems-backend",
        "commands": [{"cmd": "pytest -q", "exit_code": 0}],
        "claims": [{"claim": "unit tests pass", "evidence": "ran pytest, it was green"}],
        "unverified": ["nothing else"],
        "approved_by": "",
    }
    before = _push_receipt(bare, tmp_path, branch, receipt_path, receipt)

    ctx = _ctx(gateway)
    out = await quality.receipt_approve(ctx, {"branch": branch, "receipt_path": receipt_path})

    assert out.get("error") == "gate_failed", out
    # refused before ever touching the remote — the branch tip must not have moved
    assert _git(bare, "rev-parse", branch) == before


async def test_commit_file_refuses_a_stale_tip_and_leaves_the_branch_untouched(tmp_path: Path):
    """Tip-mismatch case: the branch moved after the read this push's expect_sha pins."""
    from desk_gateway.tools.quality import _commit_file

    bare, gateway = _make_gateway_repo(tmp_path)
    branch = "bot-01-systems-backend/receipt-tip-mismatch"
    receipt_path = ".receipts/bot-01-systems-backend/tip-mismatch.json"
    original = {
        "task_id": "tip-mismatch-regression", "bot": "bot-01-systems-backend",
        "commands": [], "claims": [], "unverified": [], "approved_by": "",
    }
    read_sha = _push_receipt(bare, tmp_path, branch, receipt_path, original)
    read_text = json.dumps(original, indent=2) + "\n"

    # Someone else pushes to the branch in the window between that read and this push —
    # exactly the race _commit_file's expect_sha/expect_content pair exists to catch.
    other = dict(original, approved_by="someone-else")
    current_sha = _push_receipt(bare, tmp_path, branch, receipt_path, other)
    assert current_sha != read_sha

    ctx = _ctx(gateway)
    stamped = dict(original, approved_by=ctx.bot_id)
    push = await _commit_file(
        ctx, branch, receipt_path, json.dumps(stamped, indent=2) + "\n", "QUALITY: approve (stale)",
        expect_sha=read_sha, expect_content=read_text,
    )

    assert push["pushed"] is False
    assert push["reason"] == "stale_read"
    assert push["expected"] == read_sha
    assert push["found"] == current_sha

    # left untouched: the remote still carries the other push, not a blind overwrite
    assert _receipt_on_remote(bare, branch, receipt_path)["approved_by"] == "someone-else"
    assert _git(bare, "rev-parse", branch) == current_sha


async def test_commit_file_refuses_a_rewind_between_its_own_clone_and_push(tmp_path: Path, monkeypatch):
    """Tip-rewind case: the branch is force-rewound to an ancestor after _commit_file's internal
    clone but before its push. A plain push would still be a fast-forward from the rewound tip
    (our commit descends from the old, pre-rewind sha) and would silently resurrect what the
    rewind removed. The push must be conditional on the tip _commit_file itself observed, not
    just the clone-time compare against the caller's expect_sha.
    """
    from desk_gateway.tools import quality
    from desk_gateway.tools.quality import _commit_file

    bare, gateway = _make_gateway_repo(tmp_path)
    branch = "bot-01-systems-backend/receipt-rewind-race"
    receipt_path = ".receipts/bot-01-systems-backend/rewind-race.json"
    original = {
        "task_id": "rewind-race-regression", "bot": "bot-01-systems-backend",
        "commands": [], "claims": [], "unverified": [], "approved_by": "",
    }
    sha_a = _push_receipt(bare, tmp_path, branch, receipt_path, original)
    grown = dict(original, approval_note="grown")
    sha_b = _push_receipt(bare, tmp_path, branch, receipt_path, grown)
    read_text = json.dumps(grown, indent=2) + "\n"

    real_run_command = quality.run_command
    rewound = {"done": False}

    async def spy(argv, **kwargs):
        result = await real_run_command(argv, **kwargs)
        if not rewound["done"] and len(argv) >= 2 and argv[0] == "git" and argv[1] == "clone":
            # Simulate someone force-rewinding the branch back to sha_a in the window between
            # _commit_file's clone (just completed) and its eventual push.
            rewind_work = tmp_path / "rewinder"
            await real_run_command(["git", "clone", "--quiet", str(bare), str(rewind_work)])
            await real_run_command(["git", "checkout", "--quiet", sha_a], cwd=str(rewind_work))
            await real_run_command(["git", "push", "--quiet", "--force", "origin", f"HEAD:{branch}"], cwd=str(rewind_work))
            rewound["done"] = True
        return result

    monkeypatch.setattr(quality, "run_command", spy)

    ctx = _ctx(gateway)
    stamped = dict(grown, approved_by=ctx.bot_id)
    push = await _commit_file(
        ctx, branch, receipt_path, json.dumps(stamped, indent=2) + "\n", "QUALITY: approve (rewind race)",
        expect_sha=sha_b, expect_content=read_text,
    )

    assert push["pushed"] is False
    assert push["reason"] == "stale_read"
    assert push["found"] == sha_a

    # left untouched: the remote still carries the rewind, not our resurrected commit
    assert _git(bare, "rev-parse", branch) == sha_a
