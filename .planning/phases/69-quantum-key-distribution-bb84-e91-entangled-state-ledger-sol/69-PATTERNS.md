# Phase 69: QKD, Entangled State Ledger & Solana Devnet Anchoring — Pattern Map

**Mapped:** 2026-10-09
**Files classified:** 13 implementation/documentation targets, including phase 68 dependencies and one optional endpoint-test split
**Targets with structural analogs:** 11 / 13; structural similarity does not certify domain correctness
**Source checkout:** `/tmp/desk-v51-implementation`, supplied baseline main 2229570

## Scope and Evidence

Inputs: 69-CONTEXT.md, 69-RESEARCH.md, `local://v51-execution-layout.md`, and the subsequently supplied authoritative parent selection `local://v51-sdk-contract.md`. Research is technical evidence/proposals; parent selection controls conflicts. In particular: mutation seats are **lead/systems**, the event sink is async, SQLite uses an incremental frontier, commitments are independently blinded at each node, and no new top-level design document is assigned.

Five useful pattern families: private storage/file descriptors; injected async transport and allowlisted DTOs; authenticated custom routes/problem responses/lifespan; environment Settings; isolated behavioral HTTP tests. Every existing analog named below was returned by `git ls-files -- <paths>`, including both workbench private-file examples. No install/runtime mirror is an analog. Borrow small patterns without importing the separate workbench package into the gateway.

Only this PATTERNS.md is written. No product edits, tests/build/lint/smokes, installs, signer reads, funding/RPC writes, commits or independent approvals. Last-match ownership: `.planning/**` bot00; gateway source/docs and Python tests bot01. Shared contracts/OpenAPI are outside authorization. Supplied instructions are complete; no context/agent-file hunt was undertaken.

## File Classification

`G` means `services/desk-gateway/src/desk_gateway/`. New files are selected/proposed targets, not analogs observed on disk.

| New/Modified File | Role | Data Flow | Closest Usable Analog | Match Quality |
|---|---|---|---|---|
| `G/quantum_qkd_mesh.py` | service/model | async request-response + event-driven | `G/federation.py` injection/explicit DTO | role-match; old QKD math not reusable |
| `G/quantum_key.py` (new) | utility/private model | synchronous transform | none for reconciliation/finite entropy/Toeplitz | none |
| `G/quantum_ledger.py` (new) | service/model | file-I/O + append/transform | `src/desk/telemetry/audit_tracer.py`; `G/store.py` | partial; no SQLite/Merkle proof analog |
| `G/quantum_anchor.py` (new) | service | async request-response + private file-I/O | `G/federation.py`; pinned loader in audit_tracer | role-match; no genuine Solana publisher analog |
| `G/quantum_node.py` (phase 68 new file, phase 69 extensions) | service/controller/private store | async request-response + transform | `G/federation.py` operator peer lookup | role-match; key capabilities are new |
| `G/quantum_transport.py` (phase 68 dependency, phase 69 QKD actions) | service | async request-response | `G/federation.py` client injection/ownership | role-match; inherit selected phase 68 transport |
| `G/quantum_teleportation.py` (phase 68 dependency/integration) | service | transform + async resource/event-driven | none for required numerical/resource sink | none in this map; consume phase 68 contract |
| `G/server.py` | controller/config | async request-response + lifecycle | same file WAN auth/upstream shutdown | exact structural role, not existing quantum auth |
| `G/config.py` | config | environment/file-I/O transform | same file Settings/from_env | exact |
| `tests/test_quantum_qkd_mesh.py` | test | transform + async request-response + persistence | service `tests/test_federation.py` | role-match for injected transport; replace false assertions |
| `tests/test_quantum_teleportation_endpoints.py` | test | request-response | existing file plus service conftest isolation/lifespan | exact role; unsafe existing fixture |
| `tests/test_quantum_qkd_endpoints.py` (research-proposed optional split) | test | request-response | teleportation endpoints plus service conftest | role-match; omit if existing file covers phase69 |
| `services/desk-gateway/README.md` | config/documentation | operator request-response/file-I/O | same file endpoint/config tables | exact |

Keep domain tests in the existing root QKD file unless a split improves maintenance. The optional new endpoint file is not an obligation to duplicate coverage. The operator ledger database under DATA_DIR is runtime data, not another tracked source/migration target. `quantum_state.py` is the selected phase 68 synchronous dependency, not a phase 69 file or an existing analog. No second design document is assigned.

## Pattern Assignments

### `quantum_qkd_mesh.py` — REQ-QTELEPORT-006, 007, 010

**Preserve meaningful enum values, not old algorithms.** `G/quantum_qkd_mesh.py:39–46`:

```python
class QuantumBasis(str, enum.Enum):
    RECTILINEAR = "+"  # {|0>, |1>}
    DIAGONAL = "x"     # {|+>, |->}


class QKDProtocolType(str, enum.Enum):
    BB84 = "BB84"  # Prepare-and-measure protocol (Bennett & Brassard 1984)
    E91 = "E91"    # Entanglement-based protocol (Ekert 1991)
```

**Existing detector predicate**, class-body excerpt `84–88`:

```python
    ABORT_THRESHOLD_QBER = 0.110

    @classmethod
    def evaluate_eavesdropping(cls, qber: float) -> bool:
        return qber > cls.ABORT_THRESHOLD_QBER
```

Validate observed counts first and use selected exact `100 * errors > 11 * sample_count`; missing/invalid samples are not QBER zero. Exactly 11% is not greater than 11%.

**Constructor injection:** `G/federation.py:282–292`:

```python
class PeerDeskClient:
    """HTTP client to perform peer handshakes and route cross-desk requests."""

    def __init__(self, registry: FederationRegistry, http_client: httpx.AsyncClient | None = None) -> None:
        self.registry = registry
        self._http = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        return httpx.AsyncClient(timeout=10.0)
```

Inject one shared mesh/protocol/pool/ledger/node transport into QKD and drill. Resource/network workflows are async; bounded numerical kernels remain synchronous. No asyncio.run inside ASGI, no fresh drill-only objects, retry framework or success-hunting loop. There is no correct existing Bob reconciliation, Eve projective measurement/resend or finite-key implementation to copy.

**Public field selection:** opening of `G/federation.py:92–101`:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_id": self.desk_id,
            "url": self.url,
            "public_keys": {kid: f"KEY({kid})" for kid in self.public_keys},
            "capabilities": self.capabilities,
            "seats": self.seats,
            "status": self.status,
            "last_seen": self.last_seen,
```

This is an excerpt, not a complete dictionary. Copy explicit selection, not URL exposure, key placeholders or mutable list references. Public QKD/node DTOs contain only model/status/counts/errors/witness/entropy/handles and public commitments. Remove `final_shared_key_hex` and `clean_key_hex` from definitions, serializers and callers, not redaction after serialization. Frozen public records/immutable copies are new obligations.

**Selected commitment rule:** each node uses its own private blinding; commitments need not match. Agreement is established through the already required independent correctness/extraction operations. Aggregate two independently blinded ownership/key-state receipts publicly. Do not exchange new private blinding through public protocol, publish raw/unsalted key hashes, or invent key-prefix evidence. The research's shared-blinding proposal is superseded.

### `quantum_key.py`, `quantum_node.py`, `quantum_transport.py` — REQ-QTELEPORT-006, 007

**No mathematical analog:** inherit phase 68 64-bit actual state/rho kernels, big-endian tensor convention, dimensions 1–4 and exact untwirled Bell rho. New worker-private pure helpers implement bounded correction, independent verification, finite leakage-budget calculation and universal extraction over GF(2). Their separate module avoids node/engine circular imports. Never copy Alice-only SHA-256 extraction (`quantum_qkd_mesh.py:154–160,215–219`), copy Alice's candidate into Bob or allocate a dense Toeplitz matrix.

**Registered identity before transport:** `G/federation.py:351–353`:

```python
        peer = self.registry.get_peer(target_desk_id)
        if not peer:
            raise PeerNotFoundError(target_desk_id)
```

**Operator bootstrap opening:** `G/federation.py:117–121`:

```python
    def _bootstrap_peers(self) -> None:
        for desk_id, url in self.settings.federation_peers.items():
            if DESK_ID_REGEX.match(desk_id):
                self._peers[desk_id] = PeerGateway(
                    desk_id=desk_id,
```

Reuse lookup/injection, not federation's caller registration, permissive URL admission, arbitrary path/header forwarding, circuit breaker or fail-open behavior. Selected workers are fixed operator registrations; remote TLS, HTTP only literal loopback for local-process evidence, no redirects/proxy inheritance. Node tokens differ from seat credentials. Bind node identity/instance, operation/session/resource/lease/capability and one-shot state. Extend phase 68 selected fixed actions and transport, not another network.

Private records disable repr and have no ordinary serializer; buffers/keys/capabilities remain worker-private. Abort removes availability at both nodes. Internal key-use returns safe outcome, not bytes. Historical establishment does not imply a restarted worker retains keys. Stream E91 resources within actual capacity; pair_count is not simultaneous qubit capacity. Quarantine ambiguous transport, never fallback/retry/resurrect. No exact existing scoped-key protocol analog was found.

### `quantum_ledger.py` — REQ-QTELEPORT-008

**Operator placement/process lock:** `G/store.py:24–28`:

```python
class Store:
    def __init__(self, data_dir: Path) -> None:
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
```

**Private atomic JSON-write convention:** `G/store.py:42–47`:

```python
    def _write(self, name: str, payload: Any) -> None:
        path = self._path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
```

Copy DATA_DIR/private-mode intent, not the storage implementation. `_read` silently defaults on decode/I/O errors. `audit_append:302–306` is process lock plus JSONL append without explicit fsync/interprocess transaction. Neither supplies cryptographic durability. Selected new runtime database: `DATA_DIR/quantum_teleportation.sqlite3`; no request-controlled path.

**Strict replay precedent:** `src/desk/telemetry/audit_tracer.py:59–68`:

```python
    if not isinstance(entry, dict):
        return "truncated JSON"
    seq = entry.get("seq")
    if type(seq) is not int or seq != expected_seq:
        return "seq gap"
    if entry.get("prev_hash") != expected_prev:
        return "prev_hash mismatch"
    stored_hash = entry.get("record_hash")
    if not isinstance(stored_hash, str) or stored_hash != _record_hash(entry):
        return "bad hash"
```

Copy rejecting sequence/predecessor/hash mismatches, not rotated-head relaxation, quarantine/recovery or its hash format. No SQLite implementation was found in services/tests searches or repository-wide import discovery. New selected obligations: private SQLite DELETE+EXTRA; parameterized append-only transactions/triggers; monotonic complete canonical events/predecessors/domain-separated leaves and prefix roots committed atomically; startup integrity/replay fail-closed; frozen historical snapshots/proofs.

Use the selected **incremental Merkle frontier**, avoiding full O(n²) prefix rebuilding during E91 lifecycle events. Leaf SHA256(0x00 || canonical), branch SHA256(0x01 || left || right); duplicate-last odd rule bound to index/tree_size. Generic typed events and compact eligible execution summaries remain distinct; summarize actual numeric outcomes/corrections/errors/key counts plus transcript commitment, not opaque arbitrary payload hash. Emit lifecycle/abort events once through the common async sink. External checkpoints remain necessary against privileged whole-file rollback.

**Boundary:** async append_event is the public selected sink. A local SQLite transaction is a synchronous bounded serialized unit; if offloaded, its connection/transaction remains in its owning execution context. Never split a transaction across awaits/threads or await RPC under a transaction/process lock. Durable success follows commit. Disk/tamper failure rejects readiness and operations, never resets to empty. A process lock alone is not multiwriter durability.

### `quantum_anchor.py` — REQ-QTELEPORT-009

**Imports:** `G/federation.py:9–19` shows stdlib logging/threading/time/dataclasses/types, `import httpx`, then absolute gateway imports. Use installed dependencies and absolute package imports, no SDK installation.

**Client ownership:** borrow PeerDeskClient injection and its `should_close = self._http is None` / `finally: await client.aclose()` (`G/federation.py:305–307,330–332`). App clients close on shutdown; injected clients remain caller-owned. `G/upstreams.py:192–222` independently shows pooled-client/aclose ownership; do not transplant pooling machinery, ETags, circuit breaker or arbitrary-URL request support.

**Nofollow file descriptor:** `src/desk/telemetry/audit_tracer.py:148–153`:

```python
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    target: str | Path = path.name if dir_fd is not None else path
    try:
        fd = os.open(target, flags | nofollow, 0o600, dir_fd=dir_fd)
    except OSError as err:
        if nofollow and err.errno == errno.ELOOP:
```

**Pinned parent**, `src/desk/telemetry/audit_tracer.py:278–281,289–291`:

```python
        parent = self.log_path.parent
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        try:
            dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | nofollow)
```

```python
            info = os.fstat(dir_fd)
            if (info.st_dev, info.st_ino) != self._parent_pin:
```

Its helper closes fd-backed handles in finally (`170–173`). `src/desk/session/session_store.py:37–54` supplies a smaller nofollow/read/close example but unbounded reading. Copy fd pinning/ownership/cleanup, not workspace confinement for an explicitly external signer, path-containing errors, permissive nofollow fallback, unbounded reads or log rotation. New loader still needs opened regular-file/owner/mode/private-parent checks, bounded content, byte/range validity and derived public-half match. No complete secure Solana loader or real Ed25519 signer analog was found; name mentions in post_quantum/wan are not implementations. No real signer was opened.

**No Solana RPC analog:** conftest's MCP JSON-RPC envelope does not supply genesis/error/ID validation, wire serialization or readback. Build selected narrow Ed25519/httpx publisher: one dedicated external signer, fixed Devnet genesis, standard Memo plus fixed SetComputeUnitLimit400000 only, signed packet <=1232B with full actual inclusion path/tree_size/root/typed eligible leaf, one sign/send, preflight and maxRetries0, bounded observation of the same signature. Persist prepared public signature before send; no automatic resubmission.

Only err-null confirmed/finalized status **and exact successful actual transaction readback** establish confirmation: programs/payer/signature/Memo/proof/slot match frozen prefix. A context slot, local digest, processed status, null readback, pending/error/mismatch/expiry or funding intent is not success. Network awaits occur outside SQLite transactions; confirmation appends a later event and advances current root without changing anchored prefix. Do not truncate proofs or substitute another root/subtree to fit.

### `server.py` and `config.py` — REQ-QTELEPORT-011

**Auth before parsing/side effects:** `G/server.py:2212–2223`:

```python
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        seat = settings.seat_for_passphrase(token)
        if seat is None:
            return problem_response(
                status=401,
                title="Unauthorized",
                detail="Valid seat authentication required for WAN message routing.",
                error_code="unauthorized",
                instance=request.url.path,
            )
```

**Role-check shape:** `G/server.py:2305–2312` uses membership plus 403/problem_response for lead/infra/systems. Copy the structure only: **selected quantum mutation seats are lead/systems, not infra**. Read/proof access is any authenticated desk seat. Missing/invalid credentials 401, authenticated denied seat 403. No intake-token or localhost bypass. Explicit admission covers every route; MCP middleware is not evidence custom quantum routes are protected.

**Malformed JSON:** `G/server.py:2225–2236`:

```python
        try:
            raw = await request.body()
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return problem_response(
                status=400,
                title="Invalid JSON",
                detail="Request body must be valid JSON",
                error_code="invalid_json",
                instance=request.url.path,
            )
```

Add strict object/schema/unknown-field/type/finite/range/work-cap checks. Those are required behavior, not demonstrated by this excerpt. Never coerce bool to count or default invalid enums.

**Problem response/cache policy:** `G/problems.py:54–57`:

```python
    resp_headers = {"Content-Type": "application/problem+json", "Cache-Control": "no-store"}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(data, status_code=status, headers=resp_headers)
```

Return stable sanitized codes, not upstream text, exception repr, signer path or credential URL. Valid protocol abort is a safe ok=false result, not key establishment. Missing prerequisites/corrupt ledger unavailable; wrong readback upstream failure; deadline pending/unknown, never confirmed. Select route suffixes once across server/tests/docs. Add snapshot/receipt/proof family; no arbitrary append/edit/delete/raw-key endpoint.

**Shared graph/lifespan:** existing quantum construction and mcp._qteleport_* exposure `G/server.py:6272–6284` are migration points. Move imports to new owners without re-export shims. Shutdown preserves MCP lifecycle (`10325–10342`), including:

```python
        try:
            async with previous(app) as state:
                yield state
        finally:
            await services.aclose()
```

Extend real lifecycle for quantum-owned client/storage cleanup without losing service cleanup. Replay ledger before work. Routes/drill share one runtime and async event sink. No extra client/ledger created solely for tests.

**Settings convention:** `G/config.py:39–44,54–59`:

```python
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]
```

```python
@dataclass
class Settings:
    public_host: str = "desk.swcstudio.space"
    host: str = "127.0.0.1"
    port: int = 8791
    data_dir: Path = Path("/var/lib/desk-gateway")
```

`147–155` compares nonempty passphrases with compare_digest; `172–200` parses env maps; `206` binds DATA_DIR. Selected names: QUANTUM_NODE_ENDPOINTS (node→URL JSON), QUANTUM_NODE_TOKENS (node→token JSON), QUANTUM_NODE_LINKS (undirected allowed-pair list JSON), QUANTUM_SOLANA_RPC_URL and QUANTUM_SOLANA_SIGNER_PATH. Worker reads its own QUANTUM_NODE_TOKEN; node/capacity/port CLI never contains credentials. Borrow Settings/from_env structure, not CSV splitting for these JSON maps. Keep private fields out of repr/public DTOs. Requests cannot choose URL/path/headers/token/program/signer/payer or override fixed genesis.

### Tests — REQ-QTELEPORT-006–011

**Lifespan and ASGI transport:** `services/desk-gateway/tests/conftest.py:88–102`:

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

Borrow temporary Settings, seat auth, actual lifespan/transport. Root tests do not automatically inherit service conftest; adapt their local fixture or deliberately share appropriate fixtures. Do not copy conftest's source-regex credential isolation or no-op fallback lifespan. Explicitly isolate operator quantum config/use dedicated harmless test credentials; no ambient signer/RPC.

**MockTransport injection:** `services/desk-gateway/tests/test_federation.py:537–540`:

```python
    mock_handler = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("Connection refused by peer")))
    async with httpx.AsyncClient(transport=mock_handler) as mock_http:
        client = PeerDeskClient(reg, http_client=mock_http)
```

Copy injection, not fail-open/circuit-breaker behavior. Use readable method/body-checking handlers with independent replies, not echo-only success mocks. Record RPC calls and assert one write. Wire tests independently decode/verify signature/packet length/full proof. Mock confirmation is unit-only, never live evidence.

Existing root QKD tests `19–48` demand short-input digest expansion/leaked secret; `78–105` accept fake anchors/unconfigured drill. Existing endpoint fixture `10–13` is unisolated and does not enter lifespan; `78–103` accepts 64-signal/pair success; `106–118` accepts unconditional anchor/drill success. They are caller migration targets, not acceptance patterns.

| Requirement | Consumer-visible checks/evidence to build; main executes |
|---|---|
| 006 | Born/basis outcomes, independent Bob candidate, recoverable correction and residual mismatch abort, extraction vectors, leakage/budget/output bounds, short/empty abort, real E91 ownership/consumption/complementary tests/CHSH witness. |
| 007 | Exactly 11/100 vs12/100 and validated float boundary, real measurement/resend disturbance, honest abort reasons, keys unavailable at both workers. |
| 008 | Commit/reopen/history, immutable snapshots, leaf/path/index/size tampering, readiness failure, crash atomicity, concurrent writers, incremental frontier/reference-root agreement, externally held checkpoints. |
| 009 | Loader rejection with throwaway keys, actual signed wire/full proof/size, wrong genesis/error/ID/signature/status/readback cases, processed/null/mismatch/expiry/deadline/cancellation, one send, no leaked secrets. Separate native decode and real funded Devnet submit/readback. |
| 010 | One shared runtime; each failed/missing prerequisite defeats all_passed; >=.95 teleport, clean independent usable BB84, numerical Eve QBER>.11 abort/withholding, durable full proof and genuine anchor. E91 acceptance is an additional run. Separate authenticated worker processes mandatory. |
| 011 | Every family: invalid/missing/disallowed auth, malformed/non-object/unknown/type/nonfinite/range/work-cap inputs, scoped lookups/conflicts, safe DTO/proof behavior, unavailable/deadline/upstream results. Mutation infra is forbidden by selection. |

No source-text/wiring/mock-echo/incidental-pin assertions are recommended. Parent reports pending VALIDATION.md drafts and unresolved edge probes (31 phase68/38 phase69 applicable): those are planning inputs, not passed tests or compliance. Resolve to explicit behavior checks/flagged assumptions; this mapper does not approve them.

### Gateway README

Existing `14–22` uses Path/Auth/Purpose; `48–68` uses Variable/Meaning. Extend these existing tables for selected routes/environment names. Describe private SQLite/signer placement, worker lifecycle, anchored-prefix/current-root distinction, independent blinded commitments, honest abort/unavailable/unknown states, 1232B/400000-CU constraint, exact readback and classical trusted-device simulator limits. No token/key/raw bits/key prefix/private internal host in examples. Update existing documentation; do not create a duplicate top-level design. External funding intent and dummy-wire native decode are not funded-publication evidence.

## Shared Patterns

- **Sync/async:** synchronous bounded 64-bit state/rho math and pure key/hash/proof/codec transforms; async pool/mesh/protocol/QKD/sink/transport/publisher/drill. SQLite transaction internals are bounded local storage units behind selected async sink. No network await under transaction/process lock or asyncio.run within ASGI.
- **Actual resource authority:** phase68 pool alone owns lifecycle, leases/capacity/reserve/retire. Preserve exact rho and failures; retire measured resources, release reversible allocations and quarantine ambiguous transport. No concurrent quantum_node writer.
- **Audit is not durability:** `G/audit.py:39–49` selects public fields, hashes redacted arguments (`20–22`), appends locally (`66`), then fire-and-forget mirror (`78–82`). Borrow allowlisting/logging only. Never route private QKD buffers through generic redaction or mistake background audit emission for required ledger/chain commit.
- **Sanitized boundaries:** problem_response plus auth/scope checks. Federation handshake response-text errors and upstream arbitrary-URL/body-return behavior must not migrate into signer/node/RPC boundaries.
- **Clean module cutover:** scoped services/root-test search found server/root QKD tests as old ledger/exporter importers. Migrate imports to new owners, remove obsolete class definitions/re-exports. Engine/drill stay quantum_qkd_mesh; private pure helpers quantum_key. No QuantumChannelInterception definition was found: requirement007 needs the actual numerical channel concept, not a naming alias.
- **DAG:** 69-01 ledger/Memo can parallel 68-01 numerical; 69-02 QKD/node extensions depends on68-02 and69-01; 69-03 shared graph/API/drill/README waits for all. Absent new phase68 files are dependencies, never claimed tracked analogs.

## No Exact Analog Found

| Capability / Target | Partial Precedent | Missing / Planning Consequence |
|---|---|---|
| quantum_key/QKD math | Enums/detector, old label simulation | Actual prepare/measure, independent reconciliation/finite budget/Toeplitz/witness require selected research/phase68 implementation. |
| SQLite ledger | Store modes/RLock and audit_tracer strict hash chain | No SQLite source found; incremental Merkle frontier/historical proofs/atomic checkpoints are new. Do not copy fake phase69 ledger. |
| Devnet publisher | Injected httpx/MCP JSON-RPC envelope | No genuine Solana RPC/wire/confirmed exact Memo publisher found. No simulated exporter reuse. |
| Secure signer | Tracked nofollow/pinned-parent helpers | No complete bounded owner/mode-checked Solana loader/Ed25519 signer; installed cryptography and throwaway fixtures, no operator signer read. |
| Node-private QKD | Registered peer lookup | No scoped key/capability/independent blinding analog; extend phase68 worker actions, no public key REST. |
| Distributed five-stage drill | Existing entry point/route/tests | Shadow runtime/fake anchor not usable; injected shared graph and truthful actual conjunction required. |
| quantum_teleportation numerical/sink | Named phase68 dependency | This map does not certify old metadata math; consume selected numerical/resource/async sink contract. |

## Metadata

**Search scope:** gateway source/service tests, root tests, README; repository-wide exact SQLite/nofollow/Ed25519/Solana-RPC discovery. All named existing analogs git-tracked. Existing source/test/doc files read:15 (13 gateway/root sources,2 workbench examples). Strong families:5. Coverage:4 exact structural matches,6 role-matches,1 partial,2 unmatched targets.

**Evidence:** static excerpts/tracked-origin discovery only. Parent owns integrated verification, real worker processes, native decode, dedicated funded Devnet send/readback and independent gates. No acceptance waiver, compliance, independent approval, merge-ready, archive or product-completion claim is made.
