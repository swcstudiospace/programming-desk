# Phase 68: Inter-Cluster Quantum Teleportation Protocol & Entanglement Swarm Routing — Pattern Map

**Mapped:** 2026-10-09
**Files classified:** 12 new/modified targets, including affected consumers and proposed test placements
**Usable analog assignments:** 10 / 12 (4 exact, 6 role-match, 2 without close analog)

Product paths are relative to `/tmp/desk-v51-implementation`. Proposed filenames are not claims that they exist. The mapper read CONTEXT/RESEARCH, `local://v51-execution-layout.md` and the authoritative parent-selected `local://v51-sdk-contract.md`. This is an implementation-pattern artifact, not a top-level plan or verification verdict. Parent owns scheduling, interfaces and verification.

**Ownership:** entire manifest read before writing. `.planning/**` is last-match bot00 (`ownership.yaml:428-429`); product gateway files/README and root Python tests are SYSTEMS-owned. Only this PATTERNS.md was written. No shared-contract changes are assigned.

## File Classification

| File | Status | Role | Data Flow | Closest Analog | Match / Limit |
|---|---|---|---|---|---|
| `services/desk-gateway/src/desk_gateway/quantum_state.py` | Parent-selected new | model, utility | transform | None | No faithful bounded quantum numerical kernel established |
| `services/desk-gateway/src/desk_gateway/quantum_node.py` | Parent-selected new | service, controller | request-response, event-driven | `services/desk-gateway/src/desk_gateway/tools/lead.py`, schema/problem helpers | role-match for locking/typed errors only; no complete distributed lease analog |
| `services/desk-gateway/src/desk_gateway/quantum_transport.py` | Parent-selected new | service | request-response | `services/desk-gateway/src/desk_gateway/upstreams.py` | role-match for reusable AsyncClient ownership, not generic upstream freedom |
| `services/desk-gateway/src/desk_gateway/quantum_teleportation.py` | Existing edit | service, model | transform, event-driven | Same file's injected graph + `tools/lead.py` | role-match; current algorithms are invalid cutover targets |
| `services/desk-gateway/src/desk_gateway/config.py` | Existing edit | config | transform | Same file | exact settings/env convention; new registration must validate strictly |
| `services/desk-gateway/src/desk_gateway/server.py` | Existing edit | controller, provider | request-response | Same file operator routes/lifespan | exact integration convention, not quantum handlers' current semantics |
| `services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py` | Existing affected consumer, phase69-owned cutover | service | event-driven, transform | `quantum_teleportation.py` injection pattern | role-match only; no QKD algorithm assignment here |
| `tests/test_quantum_teleportation.py` | Existing edit | test | transform, event-driven | Same file lifecycle invariant + service async tests | role-match; existing scalar/prefix assertions are not numeric evidence |
| `tests/test_quantum_teleportation_endpoints.py` | Existing edit | test | request-response | `services/desk-gateway/tests/conftest.py` | exact ASGI fixture role; fixtures not inherited across directories |
| `tests/test_quantum_node_transport.py` | Proposed placement | test | request-response, event-driven | `services/desk-gateway/tests/test_plane_budgets.py` | role-match for lifecycle/cancellation behavior |
| `tests/test_quantum_distributed_process.py` | Proposed placement | test | request-response, event-driven | None | In-process ASGI fixtures are not separate-worker socket/process harnesses |
| `services/desk-gateway/README.md` | Existing edit, final phase69 integration | config/documentation | request-response, file-I/O | Same file | exact endpoint/config/run/test documentation format |

The two new test filenames are placement proposals, not mandatory splitting. Numerical tests can stay in the existing quantum test file. Parent contract schedules 68-01 math, 68-02 resources/workers, 68-03 REST; final QKD graph/drill/README cutover is 69-03. Do not edit these later-stage consumers concurrently or create a sync/async shim between stages. Parent-selected `quantum_key.py`, `quantum_ledger.py` and `quantum_anchor.py` are phase69 dependencies, not extra phase68 assignments; the private key helper separation prevents circular worker/engine imports.

## Pattern Assignments

### `quantum_state.py` — no mathematical analog

Existing `quantum_teleportation.py:35-43` offers ordinary dataclass packaging only:

```python
@dataclass
class EntangledBellPair:
    pair_id: str
    state_type: BellStateType
    node_a: str
    node_b: str
    fidelity: float
    created_at: float = field(default_factory=time.time)
    consumed: bool = False
```

**Copy only:** small explicit Python records/import conventions. **Never copy:** mutable scalar fidelity or externally writable consumption as authority. The parent-selected contract requires immutable finite normalized vectors/rho, synchronous 1–4-qubit math, big-endian indexing, actual gates/projective Born branches/partial traces and retained exact untwirled density. Current “quantum” module names do not establish a correct algorithm. Use RESEARCH mathematical procedures and frozen SDK methods with independent behavioral oracles; no HTTP or event I/O inside mathematical values.

### `quantum_node.py` — ownership locks plus existing validation/error utilities

**Closest partial analog:** `services/desk-gateway/src/desk_gateway/tools/lead.py:173-199`. Imports `asyncio`, `contextlib` and `AsyncIterator` (`5-10`). Bounded process-local keyed lock excerpt (`187-199`):

```python
lock = _ACK_LOCKS.setdefault(lock_key, asyncio.Lock())
_ACK_LOCK_USERS[lock_key] = _ACK_LOCK_USERS.get(lock_key, 0) + 1
try:
    async with lock:
        yield
finally:
    _ACK_LOCK_USERS[lock_key] -= 1
    if _ACK_LOCK_USERS[lock_key] <= 0:
        _ACK_LOCK_USERS.pop(lock_key, None)
        _ACK_LOCKS.pop(lock_key, None)
```

**Copy:** check/change authoritative state under a lock; cleanup bookkeeping in `finally`; no immortal lock table. **Adapt:** a simpler owner lock for short atomic multi-resource reservation is acceptable. This is not a distributed lock or lease implementation. Real worker instance identity, fixed capacity, resource/session/lease scope, one-shot correction, survivor transfer, measured release and quarantine after ambiguity require new behavior.

Use existing `schema.validate`/`SchemaError` and `problems.problem_response` (shared excerpts below), not a new validation framework. Worker authentication is independently scoped, not seat credentials. Worker process reads `QUANTUM_NODE_TOKEN`; no credential CLI argument. Public DTOs contain no keys/raw QKD bits; later QKD helpers remain worker-private.

### `quantum_transport.py` — reusable client and close ownership

**Analog:** `services/desk-gateway/src/desk_gateway/upstreams.py:154-225`. Imports use stdlib/typing, `httpx`, then absolute `desk_gateway.*` (`7-24`). Reuse excerpt (`187-195`):

```python
async def _acquire(self) -> _PooledClient:
    async with self._client_lock:
        pooled = self._pooled
        if pooled is None or pooled.retire or pooled.client.is_closed:
            pooled = _PooledClient(httpx.AsyncClient(timeout=self.timeout, headers=self.headers))
            self._pooled = pooled
        pooled.inflight += 1
        return pooled
```

Close excerpt (`214-225`):

```python
async def aclose(self) -> None:
    async with self._client_lock:
        pooled = self._pooled
        self._pooled = None
        client = None
        if pooled is not None and not pooled.closing and not pooled.client.is_closed:
            pooled.retire = True
            pooled.closing = True
            client = pooled.client
    if client is not None:
        await client.aclose()
```

Copy owned, reusable AsyncClient and awaited cleanup, not necessarily `_PooledClient` retirement complexity. One scoped lifespan-owned client can suffice. `upstreams.py:265-275` distinguishes `httpx.TimeoutException` from `httpx.HTTPError` and redacts exception text; preceding cancellation handling propagates `CancelledError`. Preserve failure/cancellation and resource cleanup, never invent a successful correction ack.

**Do not blindly reuse generic HttpUpstream:** its request boundary permits absolute URLs and header overrides, has ETag/circuit-breaker behavior and lacks all quantum-specific destination restrictions. Parent contract requires fixed node-ID→operator URL resolution, fixed command paths, scoped tokens, redirects disabled, `trust_env=False`, verified TLS except literal-loopback HTTP, bounded bodies/concurrency and overall deadline. No request URLs/headers/token overrides, automatic retry framework or manufactured replacement resource.

### `quantum_teleportation.py` — structural reuse, algorithm replacement

**Dependency injection analog:** same file `199-207`:

```python
class QuantumRepeaterMesh:
    """Mesh of quantum repeater nodes coordinating multi-hop entanglement distribution."""

    def __init__(self, bell_pool: BellPairPool) -> None:
        self.bell_pool = bell_pool
        self.nodes: Dict[str, QuantumRepeaterNode] = {}
        self.swapper = EntanglementSwapper()
        self.purifier = EntanglementPurifier()
```

Protocol constructor (`309-311`):

```python
def __init__(self, repeater_mesh: QuantumRepeaterMesh) -> None:
    self.repeater_mesh = repeater_mesh
    self.sessions: Dict[str, TeleportationResult] = {}
```

Keep meaningful existing class names/Bell enum wire values and one injected pool/mesh/protocol, extended with frozen transport/RNG/async event-sink dependencies. Pool remains sole lifecycle authority; no direct `.consumed`/`pool.pairs` writes by controllers. Active→reserved transitions follow locking discipline above; immutable public snapshots prevent forged/unconsumed objects.

**Reject as patterns:** scalar purification (`108-140`), scalar swapping (`166-196`), rejected-pair fallback (`233-240`), zero-vector fallback and amplitude-copy teleportation (`323-390`), .85 threshold. Perform actual BBPSSW parity branches, BSM and three-qubit evolution; receiver worker stages the computed conditional rho, derives frame-aware X/Z bits and applies actual gates. Keep measured inputs retired on rejection/below-threshold results, transfer survivor leases and retain receiver output ownership until disposed. Success requires measured F >= .95, real acknowledgements and required event commits.

### `config.py` — startup settings and constant-time seat resolver

**Analog:** same file `1-45,147-155,171-275`: stdlib environment/dataclass/Path and `Settings.from_env()` factory. Helper (`39-40`):

```python
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()
```

Seat resolver (`147-155`):

```python
def seat_for_passphrase(self, passphrase: str) -> str | None:
    import secrets

    if not passphrase:
        return None
    for seat, expected in self.seat_passphrases.items():
        if expected and secrets.compare_digest(passphrase.encode(), expected.encode()):
            return seat
    return None
```

Copy environment-backed typed settings and injected constructors. Existing federation mapping (`197-201`) partitions CSV entries and silently overwrites/drops entries; copy the startup-mapping placement, **not permissive parsing**.

Frozen names: `QUANTUM_NODE_ENDPOINTS` (node→URL JSON), `QUANTUM_NODE_TOKENS` (node→token JSON), `QUANTUM_NODE_LINKS` (undirected node-pair JSON), with `QUANTUM_SOLANA_RPC_URL`/`QUANTUM_SOLANA_SIGNER_PATH` added in phase69. Validate duplicate identities, known topology endpoints, literal-loopback versus verified TLS and capacities; do not allow public node registration or duplicate registration resetting active counts. Values are never printed/logged/publicly serialized.

### `server.py` — operator routes and composed lifespan

Existing phase68 route/graph block (`6255-6399`) supplies route families and a single constructor graph; current unauthenticated permissive parsing/top-level green results are defects, not conventions. Await the approved async operations, honor selected pair IDs and inject one event sink; no hidden replacement pair on invalid selection.

**Operator auth reference** (`1989-1993`):

```python
auth = request.headers.get("authorization", "")
token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
seat = settings.seat_for_passphrase(token)
if seat not in {"lead", "infra", "systems"}:
    return problem_response(
```

Adapt to frozen quantum policy: mutation seats **lead/systems**, reads/proofs any authenticated seat subject to resource scope; missing/invalid credential401, valid denied role403. Auth precedes parsing/side effects. Do not copy edge's infra allowance or assume MCP middleware protects custom routes.

**Body/problem adapter** (`1293-1302`):

```python
try:
    raw = await request.body()
    body = json.loads(raw.decode("utf-8")) if raw else {}
except (ValueError, UnicodeDecodeError):
    return problem_response(
        status=400,
        title="Bad Request",
        detail="Invalid JSON payload for federation handshake.",
        error_code="invalid_json",
        instance=request.url.path,
    )
```

Copy exception→stable problem shape only; add bounds/object/schema/finite semantic checks. Federation's subsequent caller-provided URL registration is forbidden for this transport. `server.py:1327-1335` maps a domain exception's status/message/code to problem_response; use the same stable boundary rather than raw exceptions.

**Lifespan composition** (`10325-10342`; compact exact excerpts):

```python
previous = starlette_app.router.lifespan_context

@contextlib.asynccontextmanager
async def _close_upstreams_on_shutdown(app: Any):
```

```python
    try:
        async with previous(app) as state:
            yield state
    finally:
        await services.aclose()

starlette_app.router.lifespan_context = _close_upstreams_on_shutdown
```

Preserve MCP's previous session-manager context and guaranteed awaited close; place quantum runtime/client under an actual owner. Do not copy intervening Dragonfly fail-open startup behavior for required quantum resources. `build_app:10345-10450` constructs dependencies and installs this wrapper.

Supporting owner convention: `tools/__init__.py:37-81` is a typed Services dataclass/factory; `83-110` deduplicates closers and awaits them with asyncio.gather. No second generic container is needed. If its owner file must change, parent explicitly assigns scope; mapper is not proposing an unsolicited edit there.

### `quantum_qkd_mesh.py` — affected interface consumer only

Observed imports (`28-36`) include pool/Bell/purifier/swapper/mesh/protocol. The drill (`337-391`) privately constructs a graph and synchronously calls create/purify/route/teleport, then checks .85. These must cut over under phase69's parent-owned schedule: awaited APIs, shared injected live runtime, no private fallback pool, no alias/re-export or `asyncio.run` inside ASGI. Do not copy its QKD scalar logic/key-export or fake publication as algorithms. The durable async sink, SQLite incremental frontier, private key helpers and real publisher are phase69 contracts, not an in-memory phase68 substitute.

### `tests/test_quantum_teleportation.py` — lifecycle and numerical behavioral oracles

Useful invariant (`33-35`):

```python
ok_second = pool.consume_pair(pair.pair_id)
assert ok_second is False
assert len(pool.list_active_pairs("desk-alpha", "desk-beta")) == 0
```

Adapt to async managed-resource SDK/explicit nodes and observe documented conflict plus actual count/ownership. Do not pin old return shape if it changes. Replace unmanaged pair dataclasses, incidental prefixes/log counts, always-success stochastic purification, .85 route threshold and plus-only tests with deterministic RNG, all Bell frames/measurement branches, imaginary/asymmetric inputs, actual rho/receiver overlap, parity rejection, finite/nonzero validation, orientation/capacity and single-use behavior. Preserve untwirled mixture evidence, not just scalar improvement.

Concurrency analog `services/desk-gateway/tests/test_server.py:1267-1273`:

```python
first, second = await asyncio.gather(
    rpc.call("lead", "desk_intake_ack", args),
    rpc.call("lead", "desk_intake_ack", args),
)
assert len(issue.posted(MARKER)) == 1, f"both calls posted: {issue.bodies}"
assert first["ok"] is True and second["ok"] is True, (first, second)
assert {first["notify"]["posted"], second["notify"]["posted"]} == {True, False}
```

Copy overlapping public calls plus exactly one observable side effect. Quantum oracle differs: one reservation/consumer wins, second conflicts; both cannot report accepted teleportation. Intake idempotent-success semantics are not quantum single-use semantics. No source-text/prose/mock-echo assertions.

### `tests/test_quantum_teleportation_endpoints.py` — isolated fixtures

Analog `services/desk-gateway/tests/conftest.py:60-101` isolates temporary data/settings; context-managed client excerpt (`88-101`):

```python
@pytest.fixture
async def app(settings):
    from desk_gateway.server import build_app

    application, _ = build_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
```

Copy temporary storage, explicit settings/runtime, deliberate authenticated-seat requests and managed client. Root tests do not inherit service conftest; do not use ambient build_app() or add source-scanning fixtures. Do not copy credential literals.

**Caveat:** conftest `12-19` has an ImportError fallback that only yields app; this cannot prove lifespan execution. For lifecycle assertions, enter actual app.router.lifespan_context as below or use context-managed TestClient. ASGITransport contract tests are not distributed acceptance.

### Proposed `tests/test_quantum_node_transport.py` — lifetime/protocol effects

Analog `services/desk-gateway/tests/test_plane_budgets.py:352-361`:

```python
class _Services:
    async def aclose(self) -> None:
        await upstream.aclose()

app = Starlette()
_install_upstream_shutdown(app, _Services())
async with app.router.lifespan_context(app):
    assert made[0].is_closed is False
assert made[0].is_closed is True
```

Copy exercised lifespan and observable closure. MockTransport is suitable for fixed destination/timeout/cancellation/client-reuse unit checks, not separate-process proof. Worker ASGI tests must assert lease allocations/counts, actual X/Z receiver effects, instance/scope/replay refusal, transfer/release and conflict/error media type—not merely mocked payload echoes.

### Proposed `tests/test_quantum_distributed_process.py` — no process analog

Read fixtures are in-process; no faithful process/socket harness established. Implement bounded actual worker startup/readiness/deadlines and always-stop/reap cleanup from runtime obligations. Distinct worker PIDs/instances, sender/repeater acknowledgements, conditional-versus-corrected rho, real delivered bits and independent owned capacity are required evidence. Parent executes coverage, not mapper.

### `services/desk-gateway/README.md` — operator/runtime conventions

Copy endpoint table (`12-26`), env table (`44-74`), run section (`76-89`) and tests section (`99-110`) formatting. Final integration documents fixed registered worker topology/TLS/token names, auth/outcome semantics, startup/cleanup, explicit service interpreter and actual process drill commands, simulator limitations and real phase69 publication status. Do not copy credential-printing startup examples. Funding intent is not observed funded balance/chain confirmation; no physical quantum/security claims.

## Shared Patterns

### Strict Python types plus semantic validation

Source `services/desk-gateway/src/desk_gateway/schema.py:21-34`:

```python
if expected == "boolean":
    return isinstance(value, bool)
if expected == "integer":
    return isinstance(value, int) and not isinstance(value, bool)
if expected == "number":
    return isinstance(value, (int, float)) and not isinstance(value, bool)
```

`validate` (`37-82`) handles required keys, enum/list/string bounds and rejects unknown keys with `additionalProperties:false`. Reuse existing helper for fixed gateway/worker messages, not altered shared contracts. **Gap:** min/max alone admits NaN; explicitly enforce math.isfinite, nonzero state, valid density and contextual topology/resource relationships. `bool("false")`, float(True) and invalid Bell-label defaulting are not validation.

### Stable errors

Source `services/desk-gateway/src/desk_gateway/problems.py:54-57`:

```python
resp_headers = {"Content-Type": "application/problem+json", "Cache-Control": "no-store"}
if headers:
    resp_headers.update(headers)
return JSONResponse(data, status_code=status, headers=resp_headers)
```

Use existing status/title/detail/error/instance shape. 400 input,401 authentication,403 authorization,404 absent resource,409 conflict/capacity,503 unavailable transport,504 deadline are research/contract error mappings. Completed parity rejection/below-threshold teleport return truthful unsuccessful protocol outcomes and consumed resources, not malformed-input claims or top-level green success.

### Unified async authority

Math stays sync; resource/transport/protocol workflows and affected callers become async. One pool/mesh/transport/event sink governs REST and final drill. Close owned clients, propagate cancellation, never restore measured input after irreversible failure. Phase69 sink is durable append-only SQLite with incremental Merkle frontier; no shadow phase68 ledger. Later public QKD DTOs must aggregate independently blinded node commitments, not expose private blinding/raw bits/keys or require equal independently blinded values.

## No Analog Found

| File / concern | Role | Data Flow | Reason / planner source |
|---|---|---|---|
| `quantum_state.py` | model, utility | transform | Current quantum code is scalar/metadata/copy logic, not faithful math. Use frozen numerical SDK + RESEARCH circuit procedures. |
| Proposed process test | test | request-response, event-driven | In-process fixture cannot supply genuine worker process/socket evidence. Use explicit runtime requirements. |
| Distributed leases/correction replay | service | event-driven | Local locking/client ownership analogs are partial; no verified complete worker-owned qubit lifecycle analog. |
| Durable quantum sink | service | file-I/O, event-driven | Phase69 dependency; no storage analog selected in bounded phase68 map. |

## Risks

- Keep names/dependency injection, not fake quantum scalar/amplitude-copy algorithms, hidden re-Wernerization, forced purification acceptance or .85 success.
- Cut over affected consumers without sync wrappers; phase69 graph scheduling is parent-owned. Reference lookup is partial, not an exhaustive caller proof.
- Process-local locks do not prove real capacity/single-use worker leases; measured failures retire/quarantine, never fallback/retry/resurrect.
- Reusable client must reach actual lifespan owner; preserve MCP context. Fallback fixture yield is not startup/shutdown evidence.
- Generic federation/upstream URL freedom is not allowed: fixed registered URLs/TLS/scoped tokens, no redirects/proxy/request overrides.
- Shared schema is useful but not finite/physical-state validation; bound JSON/circuits/route counts and validate auth before side effects.
- No public private-key buffers, raw QKD bits or new private-blinding exchange; phase69 private helper prevents circular imports.
- No source-text tests, prose/log/prefix pins, fake acknowledgements or in-process labels claimed as distributed acceptance.
- All phase VALIDATION items remain pending. No product tests/lint/build, worker drill, signer reads, funding/chain mutation, commits or PR changes performed; independent review/live publication remain parent-owned gates.

## Metadata

**Search scope:** product gateway Python source, root quantum tests, service fixture/lifecycle/concurrency tests and gateway README. Five strong convention families selected: REST/lifespan, settings, HTTP ownership, keyed serialization, behavioral fixtures; schema/problem utilities are shared helpers. **Source files read:**15. All 15 product source/analog references were confirmed tracked with `git ls-files -- <paths>` from the product root; no install/runtime mirror paths are emitted.

**LSP evidence:** mounted-device discovery omitted LSP; after parent supplied exact `xd://lsp`, a direct read returned `No such tool` in this mapper session (reported to automated tool QA). Fallback `/usr/bin/pyright-langserver` was discovered and bounded stdio JSON-RPC was exercised without source/helper-file edits. One gateway-import definition query resolved `QuantumTeleportationProtocol` to zero-based line290 columns6–34 in `quantum_teleportation.py` (source line291). First buffered initialize response hit a bounded deadline; reference result was null. A corrected unbuffered adapter initialized successfully, but unopened-document definition/reference results were null. Only the positive definition is relied on; null results are not absence/exhaustiveness evidence. Grep and targeted reads establish concrete imports/callers above. No product diagnostics or verification executed.

**Date:**2026-10-09. Advisory mapping only; not a completion/security/merge-readiness receipt.
