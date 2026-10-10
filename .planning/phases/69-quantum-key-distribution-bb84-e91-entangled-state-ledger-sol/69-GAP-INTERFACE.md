# Phase 69 Gap — Shared QKD Interface

Status: checked-plan input, not implementation or acceptance evidence. Runtime root `/tmp/desk-v51-implementation`; planning root `/tmp/desk-v51-audit`. This file replaces the contradictory draft sections in full. D-01/D-02 and REQ-QTELEPORT-006..011 remain unchanged: a faithful distributed classical numerical simulator, real SPL Memo Devnet publication, no physical/production/DI-security claim.

## 1. Fixed transport and authority

Add exactly two fixed worker paths: `POST /v1/node/qkd_step` for coordinator protocol work and `POST /v1/node/qkd_owner` for the private owning-node operator. Add their fixed actions to `NODE_ACTIONS`/`NODE_PATHS`; no arbitrary URL/path/getattr dispatch. The gateway NEVER proxies `qkd_owner` or capabilities into public REST.

- `LocalNodeTransport.qkd_step` and `RemoteNodeTransport.qkd_step(node_id, *, operation_id, session_id, action, payload, instance=None) -> dict` use the SAME request/reply codec. Local encodes/decodes exactly as remote; no in-process bypass of wire validation.
- `qkd_owner(node_id, *, operation_id, session_id, action, payload, instance=None) -> dict` similarly has the fixed `capability`/`use` actions below.
- Token comes only from the transport-selected Authorization header. Node and original instance bind every mutation. Owner identity derives from the authenticated worker node, not a body-supplied owner/seat; the session record binds that identity at begin. Wrong node/instance/session/capability fails closed. The configured per-node operator credential is the owning-node authority, not an arbitrary seat claim.
- Authenticate before body streaming/parse, and validate role/stage/replay before draws/effects under the worker lock. Request AND response are each at most65536 bytes. Error DTOs contain typed code/status only, no worker body/credentials/private data.
- Default inspect discovers the current instance read-only; established sessions retain their original pinned instance, never silently rebind. Read-only `lengths` has deadline semantics; mutating uncertainty aborts/quarantines, never retries.

## 2. Exact coordinator action DTOs

Each envelope has node, instance, operation_id, session_id, action, payload. Unknown fields/actions are400. No body token/owner/URL/RNG/private capability/blinding/key. Payload DTOs below use the codecs in section3.

| Action | Payload | Reply |
|---|---|---|
| begin | protocol BB84/E91, role alice/bob, peer node_id | ok, bound session_id |
| prepare_bb84 | count0..20000 | Signals(count), Bits(count) preparing bases; raw bits retained only at Alice |
| measure_bb84 | Signals(count), optional channel_basis_policy fixed Z/X-uniform | Bits(count) measured bases and count; outcomes retained only at Bob |
| adopt_indices | keep Indices(n), phase Indices(k) disjoint, full ordered lists | key_length, phase_sample Bits(k); remove disclosed phase bits from candidate |
| measure_e91 | round_index0..19999, pair_id, owned lease_id, role, Density and basis setting | Alice conditional Density(1) only; Bob stored-count only; no raw candidate click |
| lengths | empty | key_length, phase_length, key_available, terminal state (no keys) |
| syndrome | ordered Indices(key_length) | syndrome Bits(block_count), actual leaked count |
| correct | ordered Indices(key_length), syndrome Bits(block_count) | corrected_count, leakage counts only |
| tag | seed null for Alice generation OR public Bits(key_length+31) from Alice for Bob | public seed Bits(key_length+31), public tag Bits(32) |
| extract | output_length ell, seed null for Alice generation OR public Bits(key_length+ell-1) from Alice for Bob | public seed, independently blinded commitment, output_length; no key bytes/capability |
| abort | fixed reason code | acknowledged keyless/terminal state; raw/candidate/key/blinding/capability buffers cleared |

The engine may apply the numerical Eve measure/resend channel to Signals with its channel RNG; Eve's simulated disturbance is not a private endpoint draw. Worker bits, bases, outcome draws and blinding remain worker-local.

## 3. Bounded codecs and full-length accounting

Codec helpers live in the owned worker/transport modules, reuse existing numerical/key helpers, no new dependency/module convention.

- `Bits(n) = {encoding: bits-msb-v1, count:n, data:base64}`; strict base64 and exact `ceil(n/8)` bytes; reject nonzero unused trailing bits, booleans, mismatched count. Bases Z=0/X=1. Public seeds/tags/phase samples/syndromes use this codec.
- `Indices(n) = {encoding:u16be-v1,count:n,data:base64}`; exact2n bytes, ordered (preserves shuffle order), indices0..19999 with no duplicates; keep/phase disjoint. Two lists total at most20000 indices and fit below64KiB including the measured envelope. No JSON integer arrays of20000 entries.
- `Signals(n) = {encoding:bb84-signals-v1,count:n,data:base64}`; two bits each:0=|0>,1=|1>,2=|+>,3=|->. Strict exact byte count/padding. Decode to exact kernel representatives, never silently normalize non-ensemble input.20000 signals fit well below64KiB.
- `Density(q) = {encoding:density-v1,qubits:q,matrix:[[[real,imag]]...]}` for q1/2; exact dimensions, finite entries, direct QuantumDensityMatrix validation (trace/Hermiticity/PSD), no normalization or Werner replacement.
- Measure the actual serialized request/reply at admission, not an estimate. If a combined operation would exceed64KiB, use explicit indexed chunks with total/count/order retained and commit only after full validated assembly; incomplete/reordered/short chunks abort, never silently reduce the logical sample.
- Count admission is unchanged: zero returns aborted/insufficient_sample, qber null when unestimated, no keys/digest; negative/bool/string/>20000 is400. The full20000-signal/round session remains supported.

## 4. RNG and matching extraction

Private bits/bases/Born outcomes/blinding are sampled in each worker using its own `secrets.SystemRandom` by default; deterministic injection is test-only. Coordinator never supplies a private endpoint draw or copies Alice's candidate into Bob.

For tag and extraction, Alice generates ONE fresh PUBLIC Toeplitz seed for each operation and returns it; the engine transports that SAME seed to Bob. The two seeds are independent BETWEEN tag and extraction and independent of candidate bits, not independently different between endpoints. Alice and Bob hash their own independently reconciled candidates with identical public seeds. Both independently compute tag/extraction; agreement is proved without publishing keys. Per-node blinding is independently drawn and never exchanged.

Public: seeds,32-bit tag, disjoint phase-test samples, syndrome, counts/budget/witness buckets with string keys, node commitments and aggregate. Private: raw/sifted candidates, extracted bytes, blinding, capabilities (except the authenticated owner-private path in section5). No private values in gateway DTOs, receipts/Memo/logs/errors/repr.

## 5. Private owner capability/use and bounds

`qkd_owner` permits only:
- `capability`, payload empty: authenticated owning-node identity + pinned session returns the private capability. Available only for an established unused key; no owner body field. Public gateway callers cannot retrieve it. Wrong scope403; absent/terminal409. Same-operation replay is scoped and has no new effect.
- `use`, payload operation fixed supported label + capability string: verify session/node/instance and capability; replay digest includes its stable hash. Mark one-shot used and destroy raw/candidate/key/blinding/capability buffers. Return public use outcome/commitment only. Changed capability conflicts; a new-operation second use409.

At most64 nonterminal QKD records per worker (including established unused keys), each at most20000 signals/ordered E91 rounds. Refuse begin before effects at capacity, never evict a usable key. Used/aborted records retain only compact replay, no private arrays. Shared68-05 history keeps2048 replies and at most262144 exact effect-ID digest tombstones, never evicted.1088 slots are reserved for cleanup (1024 leases+64 sessions): unseen non-cleanup effects refuse at261056, terminal release/abort/use consumes reserved slots and records its tombstone. Cached replay/readonly inspect/lengths remains available. A20000-round E91 exchange fits with headroom; tests/smoke demonstrate bounds, buffer reclamation and cleanup under saturated admission.

## 6. Single E91 private-key mechanism

Delete `deposit_correlated_key_bits`, unused `_mirror`/`_WorkerBindingError`, and coordinator/wire `qkd_accept_bit` candidate imports after migrating all callers. No alternate joint/coordinator sampler remains.

1. Alice validates her owned active Bell lease, bound E91 role/session, actual pair rho and new ordered round. Rotate according to the agreed setting with the real kernel; sample Alice using her worker RNG, retain only her click. Return `branch.state.partial_trace((1,))` as Bob's conditional Density(1), not a raw click.
2. Engine forwards only the conditional density with the same session/round/pair and Bob's owned lease. Bob rotates according to his setting, independently samples with his worker RNG and retains only his own click; reply count only.
3. This implements `P(a,b)=P(a)P(b|a)` for ideal/nonideal joint density. Never return/copy Bob's candidate bit from the coordinator. Worker round/stage guards enforce one-shot even after reply-cache eviction. Consume/release the actual pool pair through sole-authority lifecycle; any failure/ambiguity/cancel cleans both endpoints or leaves explicit quarantine.

CHSH witness and complementary phase-test rounds are disjoint from private key rounds and consume their own actual Bell resources. Existing numerical public-test helpers may sample those deliberately disclosed test rounds with the channel/test RNG; they never import or reveal private candidate bits. Public evidence is counts/string-keyed buckets, S/lower bound and phase error. The coordinator computes the locked finite-key budget from these observed test counts, while endpoints independently reconcile/extract their own candidate and validate local length/output bounds. E91 witness acceptance is a separate run, NOT an extra conjunction in the five-stage BB84 drill.

Final integration closure69-08: `run_e91` keeps its public request fields but
resolves the supplied registered graph's shortest simple path before effects.
Each round uses real mesh routing with base_fidelity1.0/purify_hopsfalse and
consumes its returned density; no direct link bypass, shadow graph or pair reuse.
Checked final-pair retirement is a prerequisite to reconciliation/extraction.
Unconfirmed resource cleanup yields failed/resource_cleanup_unconfirmed and
both-node key destruction (or explicit key-cleanup quarantine), not established.
Existing topology/count/history limits remain; exhausted history fails keylessly,
never silently shortens the route or requested sample. Canonical active public
types are QKDKeyExchangeSession/QuantumTeleportationDrillSimulator; obsolete
QKDSession/QuantumTeleportationDrill names are removed with unchanged wire DTOs.

## 7. Locked finite-key policy (unchanged)

`EPS_PE=1e-9`, `EPS_PA=1e-9`, `EPS_COR=2**-32`, `EPS_W=1e-6`; total declared error budget is their bound sum.32-bit verification leakage counted ONCE. n is undisclosed candidates after k disjoint complementary phase-test bits; `mu=sqrt((n+k)/(n*k)*(k+1)/k*ln(4/EPS_PE))`; `q_upper=min(0.5,q_phase+mu)`; `H_est=n*(1-h(q_upper))`; `H_after=H_est-L_syndrome(actual)-32-L_branch(pre-bounded key-dependent disclosures)`; `ell_max=floor(H_after-2log2(1/EPS_PA))`; no combined log term or second EPS_COR subtraction. Byte-aligned `ell<=min(requested,256,ell_max)`, minimum128. Toeplitz `T[i,j]=seed[n-1+i-j]`, integer masks/bit_count parity, no dense allocation. No production composable/DI claim.

Exact abort is `100*errors >11*sample_count`; exactly11% passes this threshold only, not necessarily the independent entropy gate. Missing/invalid samples never become QBER0. CHSH requires all four buckets and `S_lower>2` under locked EPS_W, otherwise insufficient_witness.

## 8. Ledger, publisher and cross-phase integration

69-04 produces `list_receipts(limit:int) -> tuple[FrozenReceipt,...]`: first at mostlimit immutable receipts in sequence order, limit1..1000, no full snapshot/tree/history materialization. It wraps SQLite open errors as LedgerError and keeps corrupt/open distinctions available.68-07 depends69-04 and owns startup isolation (catch LedgerError base), listing integration, output-release route and streamed gateway helper.69-07 owns transport-readiness/config/caller cutover and final docs after68-07; it MUST preserve release/startup/listing behavior, not reimplement the same findings.

Frozen roots/tree sizes never mutate. Startup binds searchable columns to committed metadata; decoded leaves have exact type/numeric shape. Proof index/sequence/tree/odd-duplicate rule bind a trusted prefix checkpoint. Same-file appends refresh complete frontier/cache plus next sequence inside the serialized transaction; no stale-cache lost updates. Publisher claims per receipt atomically in SQLite BEFORE signing across exporter/process objects, complete indexed failclosed prepared lookup, historical signature status/readback, no resubmit. Existing fixed base58 cap remains untouched. Funding stays external; no live-chain/sign-off claim without genuine matching confirmed Devnet readback.

Shared teleport contract: `QuantumTeleportationProtocol.release_teleport_output(session_id, receiver, operation_id)` and `POST /v1/quantum/teleportation/outputs/release` from68-06/07 remain unchanged. Successful user outputs persist until explicit release. The drill releases only its own outputs and all acquired/surviving/partial pairs, never unrelated user resources; it destroys/consumes its demonstration keys after observed verification, retaining truthful public historical outcomes.

## 9. Clean transport-only cutover and evidence

Engine uses the supplied transport or pool transport, never `_workers`/`_scope`/engine-supplied private RNG. Remove workers/worker_tokens engine args and Settings.quantum_workers_override after migrating every test/caller. Public `run_bb84`/`run_e91` already match server calls (296367123 stale premise); no exchange-name shim. Readiness uses configured transport nodes plus authenticated original-instance discovery. Same shared pool/mesh/protocol/QKD/ledger/exporter graph drives gateway and drill; no shadow fallback.

Parent runs full six-file regression once after integration plus actual distinct-worker and real gateway TCP smoke using genuine operator env configuration. Clean BB84 must establish and numerical intercept-resend must abort with BOTH node keys unavailable; separate E91 must measure a valid witness and independent extraction, not accept an arbitrary non-witness abort. Restart/historical proofs and owner-use/release are exercised. An unfunded real publisher leaves all_passed false. Independent review/approval remains separate; no merge is authorized.
