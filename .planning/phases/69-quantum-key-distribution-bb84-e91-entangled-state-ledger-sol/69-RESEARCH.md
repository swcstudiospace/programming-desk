# Phase 69: QKD, Entangled State Ledger & Solana Devnet Anchoring — Research

**Researched:** 2026-10-09
**Domain:** Distributed numerical BB84/E91 simulation, private node keys, durable Merkle receipts, real Devnet SPL Memo publication
**Confidence:** LOW under the installed research-confidence classifier; direct source observations and official citations are identified separately below. This is a prescriptive builder proposal, not executed acceptance evidence.

<user_constraints>
## User Constraints (from CONTEXT.md)

The following source text is copied verbatim from the phase context. [VERIFIED: 69-CONTEXT.md:16-32,62-63]

### Locked Decisions

### Execution and publication contracts
- **D-01 — User selected “Faithful distributed simulator”.** Reuse phase 68 numerical Bell states and node ownership. No physical quantum-hardware or quantum-security claims.
- **D-02 — User selected “Approve SPL Memo publisher”.** This explicitly authorizes the standard existing SPL Memo program as the real Devnet publication alternative. Construct and sign a genuine transaction, submit to a verified Devnet RPC, and observe confirmation and matching on-chain memo content. A local hash, fabricated slot, mock response or pending transaction is not confirmation evidence.
- Publish a versioned compact Merkle root and genuine execution-receipt inclusion proof within Solana transaction limits. No private key, QKD key, key prefix, raw sifted key bits or bearer token may enter responses, logs, receipts or the chain.
- Signing credentials must be securely stored outside the repository. Reference resource paths/environment-variable names only. Use a dedicated ephemeral Devnet-only fee payer for the drill when funding is available; do not access an unrelated wallet or network.
- **Reversibility: one-way.** Confirmed Memo transactions cannot be erased. Only non-secret simulator commitments may be published. Correct a bad attestation with a later explicit superseding record; never claim a destructive rollback of chain history. The user authorized this publisher, not production program deployment.

### Protocol and persistence acceptance
- Bob derives and reconciles his own candidate key; do not manufacture equality by copying Alice's key. Disclosed sample/parity/verification leakage and statistical uncertainty constrain extraction length. Short/empty/insufficient-entropy exchanges must be safe aborts, not crashes or expanded “256-bit keys”.
- E91 must consume the actual Bell resources and exercise appropriate entanglement correlations/witnesses. Intercept-resend must be numerical measurement/resend, not a hand-written QBER answer.
- QBER > 11% aborts the channel and withholds keys. Failure/abort status must be represented honestly in session, ledger, API and drill results.
- Ledger events are durable and immutable through the application API, with replay/tamper checks, historical roots and verifiable inclusion proofs. Public commitments may describe private key state but never contain key material.
- Reuse gateway seat authorization and storage conventions; do not add an unauthenticated control plane. Key handoff must be scoped to the intended simulator node and excluded from ordinary REST session serialization.

### Lifecycle boundaries and discretion
- Independent receipt approval and QUALITY/LEAD disposition are not granted by this decision. Keep draft PRs; do not archive the milestone until genuine evidence and required review gates are met. Do not merge, enable auto-merge, force-push or delete branches.
- Numerical QKD/reconciliation design, append-only persistence mechanism, compact proof wire format, operator configuration and route validation are builder decisions constrained by the original requirements and existing patterns. No unrelated retry/telemetry/API expansion.

### Claude's Discretion

The context does not have a separately named discretion section; its discretion statement is copied here. [VERIFIED: 69-CONTEXT.md:32]

- Numerical QKD/reconciliation design, append-only persistence mechanism, compact proof wire format, operator configuration and route validation are builder decisions constrained by the original requirements and existing patterns. No unrelated retry/telemetry/API expansion.

### Deferred Ideas (OUT OF SCOPE)

None. Real publication, secure key handling and original numerical acceptance are required. Other milestones' simulated exporters are outside this repair.
</user_constraints>

## Project Constraints (from CLAUDE.md)

No CLAUDE.md was returned by discovery at the worktree root or the configured alternate location; no directives can be attributed to an unread CLAUDE.md. The assignment and ownership manifest control this research. Last-match ownership explicitly says `pattern: ".planning/**"` and `owner: bot-00-programming-lead`; therefore only this planning artifact is written. No product changes, commits, pushes, PR changes, tests, or agents are part of this slice. [VERIFIED: ownership.yaml:8-15,403-406; session glob and assignment]

Phase 68 explicitly requires “Exercise separate simulator-node processes, not merely a single object with different node labels.” It also requires `F >= 0.95` and single-use resources. Reuse its joint-state kernel, Bell pool, node transport and lifecycle sink; do not fork a second simulated mesh. [VERIFIED: ../68-inter-cluster-quantum-teleportation-protocol-entanglement-sw/68-CONTEXT.md:17-24]

<phase_requirements>
## Phase Requirements

Descriptions below are verbatim from the original requirements. [VERIFIED: .planning/REQUIREMENTS.md:15-20]

| ID | Description | Research Support |
|---|---|---|
| REQ-QTELEPORT-006 | BB84 & E91 Quantum Key Distribution Engine (`QKDProtocolEngine`, `QKDProtocolType`, `QuantumBasis`, `QKDKeyExchangeSession`) executing polarized photon/qubit basis preparation (Rectilinear \(+\) and Diagonal \(\times\)), sifting, QBER (quantum bit error rate) calculation, error correction, and privacy amplification. | Actual projective measurement; separate Bob bits; leakage-counted reconciliation; finite-key universal extraction. |
| REQ-QTELEPORT-007 | Eavesdropping & Intercept-Resend Detector (`EavesdropDetector`, `QuantumChannelInterception`) measuring eavesdropper disturbance threshold (\(QBER > 11\%\)) and issuing automatic quantum channel aborts. | Measurement/resend disturbance, random sampled QBER, strict greater-than predicate and withholding. |
| REQ-QTELEPORT-008 | Cryptographic Entanglement & QKD Session Merkle Receipt Ledger (`QuantumTeleportationReceiptLedger`, `QuantumQKDReceipt`) maintaining an append-only binary Merkle tree of verified teleportation sessions, entangled Bell pairs, and sifted symmetric key roots. | Durable SQLite prefix snapshots, canonical complete leaves, Bell/session/key commitments, historical proofs and replay. |
| REQ-QTELEPORT-009 | External Solana Devnet Quantum Teleportation Exporter (`QuantumTeleportationAnchorExporter`) publishing Merkle roots and quantum execution proofs to Solana devnet targets. | Standard Memo transaction, externally configured signer, genesis pin, genuine inclusion proof, actual confirmation/readback. |
| REQ-QTELEPORT-010 | End-to-End Inter-Cluster Quantum Teleportation & QKD Verification Drill Simulator (`QuantumTeleportationDrillSimulator`) verifying Bell state generation, entanglement swapping across repeaters, state teleportation, BB84 key exchange, eavesdropping detection aborts, and Solana anchoring. | Five-stage injected-runtime drill requiring every prerequisite and real chain outcome. |
| REQ-QTELEPORT-011 | Quantum Phase 69 REST API endpoints under `/v1/quantum/qkd/*`, `/v1/quantum/teleportation/ledger/*`, `/v1/quantum/teleportation/anchor/*`, and `/v1/quantum/teleportation/drill/simulate` in `services/desk-gateway/src/desk_gateway/server.py`. | Explicit route auth, request validation, safe DTOs, ledger family and honest operational errors. |
</phase_requirements>

## Summary

The current implementation computes BB84 measurement outcomes from basis labels, takes a prefix sample, hashes only Alice's remaining bits into a fixed-length digest, and never reconciles Bob's key. E91 does not use the supplied mesh: its receiver outcomes come from classical equality/noise branches. Both methods index a minimum-size sample without checking enough sifted bits. These are source observations, not newly executed failure reports. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:98-176,178-235]

The existing ledger holds mutable lists, hashes only a subset of event metadata, and has neither persistent replay nor an inclusion-proof API in its complete class body. The exporter sets `"status": "confirmed"` and manufactures `"slot": 298471000 + len(self.commitments)` without a network operation. The drill constructs fresh runtime objects, admits teleport fidelity `>= 0.85`, and exposes `"clean_key_hex"`. Replace these behaviors, not their symptoms. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:265-306,316-334,340-347,390-423]

**Primary recommendation:** keep the public phase symbols, use the phase 68 numerical and authenticated node contracts, separate private node key state from public session DTOs, implement an independent append-only SQLite ledger, and publish one signed standard Memo transaction using existing cryptography/httpx plus a tightly bounded documented wire codec. Treat confirmation, funding and distributed transport as evidence obligations rather than configuration-derived booleans. The parent selected this no-new-package publisher and permitted a fixed necessary ComputeBudget limit instruction; this is a builder decision, not a cryptographic or live-success claim. [ASSUMED: proposed implementation contract; parent decision in this session]

## Architectural Responsibility Map

All tier assignments are proposals constrained by the context. [ASSUMED]

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Joint numerical state and resource ownership | API/backend coordinator | Authenticated node workers | Central simulator maintains correlations; pool owns allocation/consumption; workers act only for their allocations. |
| BB84/E91 bit records, reconciliation, extracted keys | Node workers | Backend protocol coordinator | Bob retains his own candidate and derives his own result; coordinator exchanges only scoped classical protocol messages. |
| Session public DTO and admission | API/backend | — | Seat auth, finite validated parameters, bounded CPU/resource work and safe projections. |
| Append-only events and prefix roots | Database/storage | Backend event sink | Transaction commits before a public receipt is returned. |
| Devnet signer | Backend private signer adapter | External private resource | Only public signing identity/result leaves signer; unrelated wallets are never consulted. |
| Solana publication and readback | External Devnet RPC | Backend publisher | RPC processing and matching transaction data, not a local digest, establish observed chain outcome. |
| Drill aggregation | Backend shared runtime | Workers, ledger, Devnet | No alternate pool, hidden isolated ledger or fake exporter. |

## Standard Stack

Use the installed stack without dependency upgrades. The declared dependency strings are `"httpx>=0.28.1"`, `"pydantic>=2.11"`, `"pyjwt[crypto]>=2.8"`, `"pytest>=8.0"`, `"pytest-asyncio>=1.0"`, and `requires-python = ">=3.11"`. Installed metadata independently reports the versions below. [VERIFIED: services/desk-gateway/pyproject.toml:6-19,32-41; installed metadata probe]

| Component | Observed version | Use |
|---|---|---|
| Python | 3.14.2 | Existing gateway runtime; stdlib numerical math, secrets, hashlib, sqlite3, struct/base64. |
| SQLite | 3.50.4 | Separate append-only local receipt database with transaction durability and replay checks. |
| httpx | 0.28.1 | Existing asynchronous JSON-RPC and node transport. |
| cryptography | 50.0.1 | Existing Ed25519 signer and signature verification, not custom curve arithmetic. |
| pytest | 9.1.1 | Existing tests; main agent owns execution after all changes land. |
| Solana CLI | 4.2.2 | Independent native wire decode/operator tooling; no implicit CLI config wallet. |

Ed25519's official interface accepts a 32-byte private seed and produces a 64-byte signature; verification raises InvalidSignature on failure. Use this library operation directly. [CITED: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/]

Do not install Qiskit, solana-py or solders for this bounded repair. No NumPy requirement is established here; numerical kernels are shared with phase 68, not replicated. `solana transfer --with-memo` exists in installed CLI help, but it is a transfer command and is not the selected Memo-only publisher. [VERIFIED: session `solana transfer --help`; ASSUMED: selected minimal dependency plan]

### Package Legitimacy Audit

No external installation is recommended. The investigated `solders` candidate is **not approved for installation**. Official project docs confirm its identity and transaction interfaces, and PyPI reports version 0.29.0 with release upload 2026-08-13 and `requires_python: "<4.0,>=3.10"`; nevertheless the mandatory seam returned SUS for unknown downloads/no repository signal. Its repository URLs are actually present in PyPI metadata, so that signal does not prove maliciousness; do not overwrite the seam verdict or treat registry existence as approval. [CITED: https://kevinheavey.github.io/solders/tutorials/transactions.html; https://pypi.org/pypi/solders/json; VERIFIED: package-legitimacy and pip index commands]

| Candidate | Registry | Age observation | Downloads | Source repository | Verdict | Disposition |
|---|---|---|---|---|---|---|
| solders [WARNING: flagged as suspicious — verify before using.] | PyPI | First release metadata 2022-05-28; latest 2026-08-13 | Seam unknown | Official docs and PyPI name kevinheavey/solders | SUS | Not installed; use existing-dependency publisher. Human verification required if a later plan changes this decision. |

**Installation:** none. **Packages removed for SLOP:** none. **Investigated SUS packages:** solders, not an implementation dependency. These are observations of the audit command, not a supply-chain safety certification. [VERIFIED: session package-legitimacy command]

## Architecture Patterns

### System Architecture Diagram

Proposed data flow; arrows crossing the worker boundary are authenticated simulator transport, never proof of physical quantum transport. [ASSUMED]

```text
Authenticated seat request
  -> admission + node/resource validation
  -> shared numerical coordinator + authoritative Bell pool
       -> Alice worker: prepare/measure, private bit store
       -> Eve channel operation when selected: project/resend
       -> Bob worker: measure, private candidate store
  -> basis disclosure + random estimation/witness rounds
       -> disturbance/witness failure -> abort + destroy node keys
       -> pass -> public parity/syndrome reconciliation -> verification tag
            -> mismatch -> abort + destroy keys
            -> finite entropy budget -> insufficient -> abort
            -> independent universal extraction at both workers
  -> typed safe session + lifecycle events
  -> append-only SQLite commit -> immutable prefix root + execution leaf/path
  -> Devnet genesis pin + configured private signer
  -> signed Memo transaction -> ONE sendTransaction
  -> bounded status/readback -> confirmed matching proof OR honest non-success
  -> append publication outcome to ledger (new root, original prefix unchanged)
```

### Component Responsibilities and Shared API Recommendations

These are explicit **new contract proposals**, not existing exported definitions. Keep asynchronous resource/workflow operations consistently async; retain synchronous pure numerical/hash kernels. Do not wrap async transport in asyncio.run inside a live ASGI loop. [ASSUMED]

| Shared object / method | Required semantics |
|---|---|
| `QKDProtocolEngine(mesh, ledger, node_transport, rng=...)` | Inject existing runtime dependencies; default production RNG uses secrets, deterministic injected RNG is test-only. |
| `await engine.run_bb84_exchange(sender, receiver, bit_length, intercept_ratio)` | Validate first; numerical prepare/channel/measure; return only immutable public session. |
| `await engine.run_e91_exchange(sender, receiver, pair_count, noise_level, intercept_ratio=...)` | Consume actual pool allocations/rho, execute disjoint key/test/witness rounds; no synthetic copied bits. |
| `node_transport.begin_qkd(node_id, session_id, role)` | Authenticate configured worker and bind role, session and ownership. Never accept caller-selected worker URL. |
| worker `prepare/measure`, `disclose_sample`, `syndrome`, `reconcile`, `verify_tag`, `extract` | Private buffers stay in worker; messages disclose only authorized protocol values; count bit-dependent leakage. |
| worker `use_key(session_id, intended_node, operation, capability)` | Scoped internal simulator operation, not ordinary REST retrieval; return public outcome/commitment, not bytes. Invalid owner, aborted session, repeated one-shot use and stale capability fail closed. |
| `ledger.append_event(typed_public_event)` | Durable canonical event and root checkpoint atomically committed; return frozen receipt, not a mutable internal reference. |
| `ledger.snapshot(tree_size=None)` | Frozen prefix root and immutable receipt tuple; snapshot size is explicit. |
| `ledger.inclusion_proof(receipt_id, tree_size)` and `verify_proof(...)` | Exact historical-prefix membership, leaf preimage, index, size and directional path; invalid shape rejected. |
| `await exporter.export_commitment(snapshot, execution_receipt_id)` | Select eligible typed numerical receipt; verify local proof first; sign once, submit once, observe bounded confirmation plus matching readback. |
| `await QuantumTeleportationDrillSimulator(...shared runtime...).run_drill(...)` | Same engine/pool/protocol/ledger/publisher as routes; no classmethod creating replacements. |

### BB84 prepare/measure/intercept-resend

Use one-qubit projectors on the actual numerical state, with rectilinear states |0>, |1> and diagonal states (|0> ± |1>)/sqrt(2). In repo the exact basis values are `RECTILINEAR = "+"`, `DIAGONAL = "x"` and the exact protocol values are `BB84 = "BB84"`, `E91 = "E91"`; preserve these meaningful enums. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:39-46; CITED: https://arxiv.org/html/1103.4130, Device Model]

For selected interception, Eve chooses a basis independently, samples the Born probability, projects/normalizes and resends the resulting basis eigenstate. Bob applies his independently chosen projector to the received state. Noise is an explicit quantum channel/Pauli operation, not a fabricated final error percentage. Test the preparation and branch kernels independently; a clean matching-basis result is deterministic, mismatched basis outcomes have probability 1/2. This design follows projective measurement and must reuse phase 68 kernels. [ASSUMED: kernel integration and exact implementation proposal]

Keep Z/Z rounds as candidate key, X/X rounds for phase-error estimation, and remove an unbiased randomly chosen disclosed subset of Z/Z rounds for observed key-basis QBER. Retaining both bases is possible but needs two separate phase-error budgets; do not silently use one averaged QBER for both. Choose sample indices without replacement after measurement/basis agreement, not the first positions; select counts bounded by the available populations. Count and discard all disclosed key positions. Report missing estimation data as unknown/insufficient, never QBER 0. [ASSUMED: conservative sifting design; CITED: https://arxiv.org/html/1103.4130, Protocol Definition and Supplementary Note 2]

### E91 with real Bell resources and an actual witness

The E91 paper explicitly uses Bell's theorem to test for eavesdropping. Two-basis correlated random bits alone do not exercise that test. A measured CHSH witness has four correlations and a local bound of 2; the ideal quantum maximum is 2sqrt(2). [CITED: https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.67.661; https://quantum.cloud.ibm.com/docs/en/tutorials/chsh-inequality]

Prescribe an E91-style trusted-device simulator: key/test settings Z and X on both nodes, plus independent CHSH rounds with Alice A0=Z, A1=X and Bob B0=(Z+X)/sqrt(2), B1=(Z-X)/sqrt(2). Randomly choose the round class/settings before outcomes. Do not remeasure a consumed pair to manufacture all four correlations. This is a specified variant with explicit same-basis key rounds, not a claim that its exact setting probabilities reproduce the 1991 hardware arrangement. [ASSUMED: settings and scheduling proposal]

For a canonical Phi+ frame, let O(theta)=cos(theta)Z+sin(theta)X and P_b(theta)=(I+(-1)^b O(theta))/2. Evaluate p(a,b)=Tr[(P_a tensor P_b)rho] and actually sample/collapse; implement through basis rotation followed by the shared measurement kernel. Normalize another Bell frame through actual local Pauli operations before settings, not by overwriting state metadata. Compute S=E00+E01+E10-E11 from observed +/-1 products. For Phi+, the expected correlations give S=2sqrt(2); product/mixed resources must not pass. These are mathematical target derivations to validate independently, not observed runs of the product. [ASSUMED: numerical derivation and acceptance target]

Require all four witness buckets to have enough data and a lower statistical confidence bound S_lower > 2. One conservative proposal subtracts the sum of per-bucket Hoeffding radii `sqrt(2*ln(8/epsilon_witness)/m_bucket)` from |S|. Empty buckets or an inconclusive bound abort as insufficient witness; do not label every inconclusive sample as detected Eve. Phase-error estimation still uses disjoint X/X test rounds; CHSH passing alone does not justify an arbitrary key length. [ASSUMED: bounded simulator witness rule, requires independent mathematical review]

Eve intercepts Bob's half by a projective local measurement/resend channel on the actual Bell rho. Pair ownership is checked before allocating a round; measurement consumes it once, including failed/aborted sessions. Create/measure/release pairs incrementally so pair_count does not falsely require thousands of simultaneous qubits. Use pool event sink for generation, allocation, measurement, discard and release. Keep noisy density matrices; do not reconstruct a Werner state from a single fidelity after untwirled purification. [ASSUMED: phase 68 integration proposal; peer numerical contract provided in this session]

### Exact QBER boundary and independent reconciliation

The existing predicate is literally `ABORT_THRESHOLD_QBER = 0.110` and `return qber > cls.ABORT_THRESHOLD_QBER`. Preserve the strict greater-than boundary: exactly .11 is not an eavesdrop-triggered abort, .110000... above it is. For sampled integer counts, compare `100*errors > 11*sample_count` to avoid display rounding; compute serialized QBER only afterward. Test exact 11/100, 12/100 and the float nextafter boundary. NaN/inf/out-of-range estimates are invalid, not passing. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:84-88; ASSUMED: integer comparison/test design]

Use key-basis disclosed QBER as the primary published detector quantity; also disclose separate phase-basis error counts. Abort if either tested basis exceeds .11, recording which observation triggered it. A conservative uncertainty/entropy abort at a lower observed rate has a different reason and must not be mislabeled QBER-threshold detection. Never infer a sample answer from intercept_ratio; finite random sessions can miss disturbance, and the drill must fail rather than retry until it happens to detect Eve. [ASSUMED: conservative detector DTO design]

Bob starts with his measured remaining candidate bits. A small maintainable reconciliation option is a shuffled block Hamming syndrome of at most 63 bits per block: Alice discloses r=ceil(log2(block_length+1)) parity syndrome bits; Bob computes his own syndrome, XORs it with Alice's, and corrects the indicated in-range position. This corrects a single error in a block and does not promise multi-error decoding. A fresh universal verification tag catches residual/miscorrected candidates; tag mismatch aborts, never triggers copying Alice's candidate. A more capable Cascade implementation is unnecessary unless the acceptance evidence needs its greater noisy-channel robustness. [ASSUMED: bounded reconciliation proposal; CITED: https://arxiv.org/html/1103.4130, Error Correction permits a leakage-bounded reconciliation scheme]

Count the actual publicly disclosed syndrome/parity bits and all other bit-dependent reconciliation messages, including acknowledgments/branches that carry information. Use a fresh independent universal verification seed and t-bit tag with t=ceil(log2(1/epsilon_cor)); subtract t before extracting. Bob computes the verification hash independently. In private tests compare Alice/Bob candidates before correction, after correction and after extraction; the runtime control flow must not use an oracle comparison of hidden full vectors. Tests must inject a recoverable unsampled error and an uncorrectable pattern to demonstrate real correction and honest abort. [ASSUMED: transcript and test contract; CITED: https://arxiv.org/html/1103.4130, Table 1]

### Finite entropy budget and Toeplitz extraction

The primary finite-key paper gives an explicit bound, not a fixed digest size. For ideal preparation quality q=1, retained length n, complementary test length k, tolerated/observed bounded error Q and actual error-correction leakage L_EC, its equation (2) is:

`mu = sqrt((n+k)/(n*k) * (k+1)/k * ln(4/epsilon_sec))`

`ell <= n*(1 - h(Q+mu)) - L_EC - log2(2/(epsilon_sec**2 * epsilon_cor))`

Here h is binary entropy truncated to 1 above 1/2. Its protocol uses random disjoint basis samples and a correctness hash; do not blindly apply this theorem to pooled arbitrary data or a device-independent E91 claim. [CITED: https://arxiv.org/html/1103.4130, equation (2), Protocol Definition, Supplementary Notes 1–2]

For implementation choose one documented conservative accounting convention: treat the logarithmic term as including the correctness tag, or explicitly use `H_budget = n*(1-h(Q+mu)) - L_EC - t_verify - other_leakage` and subtract an independently derived leftover-hash margin. Never subtract the same verification leakage twice accidentally; conversely never omit it. The latter general extractor obeys `ell <= floor(H_budget - 2*log2(1/epsilon_PA))` as a conservative sufficient choice from the leftover-hash bound. E91 here uses a trusted qubit-device/basis model and disjoint complementary rounds, with an additional witness admission gate; it does not claim a DI entropy bound from S alone. [ASSUMED: accounting integration; CITED: https://arxiv.org/pdf/1002.2436, Lemma 2 and Theorem 6]

A usable-output proposal is byte-aligned ell=min(requested_bits,256,calculated_budget), rounded down to whole bytes, requiring ell >=128. Security/error parameters and this output policy are fixed operator/model parameters before running a session, not chosen after seeing results. A small/empty exchange, missing complementary sample, nonpositive budget or budget below the usable minimum returns an explicit insufficient-entropy abort and no node key. Large clean exchanges must be demonstrated to establish keys, so an always-abort implementation is not accepted. A working starting raw-size proposal is 16384 BB84 signals and a larger E91 pair budget; actual sample/budget values, not these defaults, determine success. [ASSUMED: builder defaults, not user-mandated security targets]

Use a uniformly random independent Toeplitz seed of n+ell-1 bits and multiply over GF(2): `T[i,j]=seed[n-1+i-j]`, output bit i is XOR_j(T[i,j] & input[j]). Alice and Bob run the same transform on their own reconciled vectors. Public seed length does not increase the input entropy. Do not hash a short raw vector to SHA-256 and label the resulting 256 bits a shared secret; the leftover-hashing paper explicitly bounds extractable randomness by conditional min-entropy. For bounded ell <=256, use integer masks and bit_count parity or a simple reference implementation in tests; do not allocate a full dense Toeplitz matrix. [ASSUMED: Toeplitz indexing/implementation proposal; CITED: https://arxiv.org/pdf/1002.2436, equations (5)–(6) and universal hashing result]

### Safe public DTO and private node interface

The existing secret is exactly `final_shared_key_hex: str`, exposed by `"final_shared_key_hex": self.final_shared_key_hex`; remove this field from the public session definition and every public serializer, not merely redact a string after serialization. The old drill field is exactly `"clean_key_hex": clean_qkd.final_shared_key_hex[:16] + "..."`; delete it too. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:49-74,417-423] <!-- pragma: allowlist secret — Historical code identifiers/attribute references only; no key bytes or secret values. -->

Proposed frozen public session fields: session_id, protocol, sender, receiver, numerical_model, status, abort_reason, raw/sifted/retained/disclosed counts, sample errors/counts, observed QBER, phase-error upper bound, witness statistics where applicable, reconciliation disclosure count, verification tag length/outcome, entropy_budget_bits, extracted_bits, keys_agreed, opaque key_id, public commitment, duration, receipt_id. Proposed statuses are `established`, `aborted`, `failed`; abort reasons distinguish `qber_exceeded`, `insufficient_entropy`, `insufficient_sample`, `entanglement_witness_failed`, `reconciliation_failed`, and node/resource failures. These values do not exist in current source and must be defined once in the new shared contract. On any non-established result key_id/commitment is absent and extracted_bits=0. [ASSUMED: new DTO values]

Private key buffers and any raw candidate/transcript bits live in worker-private state keyed by session/node. Disable dataclass repr for private records; no to_dict, log interpolation or ordinary GET-key endpoint. Extraction/abort consumes temporary buffers, and worker restart loses ephemeral secrets; a durable established receipt means historical establishment, not that a current key is recoverable. Python object deletion is not a promise of memory zeroization. The internal node interface must enforce node identity plus capability/session scope even when an HTTP peer can reach its port. [ASSUMED: key lifecycle proposal]

For sifted/key commitments use fresh node-held secret blinding and domain separation; do not publish raw sifted bits, unsalted sifted hashes, key hashes for tiny keys, or key prefixes. A public hash of a <=256-bit final secret is a guess-verification oracle and is not information-theoretically secret. Bind public ownership/length/key-handle state separately; require at least 128 entropy/output bits before publishing any key-establishment commitment. If a secret-blinded commitment is used, both nodes compute it independently using the agreed private blinding, which never enters the receipt or Memo. State the computational/simulator limits; no post-extraction public commitment is a proof of physical secrecy. [ASSUMED: proposed commitment construction and security analysis]

### Durable append-only ledger

Choose a separate stdlib SQLite ledger under the operator data directory; proposed new filename `quantum_teleportation.sqlite3` is not an existing created path. Borrow the Store's private-file/data-directory convention, not its recovery behavior: it creates `self.dir.mkdir(parents=True, exist_ok=True)`, assigns a process RLock, writes temporary files, `tmp.chmod(0o600)`, then replaces. Its `_read` returns default on OSError/JSONDecodeError; that is unacceptable for a cryptographic ledger. The audit path is created literally as `self.dir / "audit.jsonl"`, appending without explicit fsync or interprocess lock. [VERIFIED: services/desk-gateway/src/desk_gateway/store.py:24-47,302-306; ASSUMED: new ledger path proposal]

Use rollback DELETE with synchronous EXTRA for the smallest file/permission surface, or WAL with synchronous FULL if concurrency requires it. This research recommends DELETE+EXTRA with bounded transaction timeout, serialized app lock plus SQLite interprocess locking; reads obtain explicit prefix snapshots. Official SQLite states FULL alone may not provide power-loss durability in rollback mode, while EXTRA includes the journal directory sync; WAL+FULL is durable under functioning filesystem flush guarantees. Do not claim disk/controller guarantees stronger than SQLite's assumptions. [ASSUMED: selected settings; CITED: https://sqlite.org/pragma.html#pragma_synchronous; https://www.sqlite.org/atomiccommit.html]

Proposed schema: append-only events with monotonic sequence, version, typed canonical bytes, unique event identity, previous-event digest, leaf digest and checkpoint root/tree_size; immutable snapshots/root history; publication-attempt/outcome events referencing an exact prefix. Apply UPDATE/DELETE-rejecting triggers and expose no edit/delete method. Use parameterized SQL, BEGIN IMMEDIATE for append, commit event+root atomically, and return success only after commit. Ensure ledger directory is private and database/journal files are private (0700/0600 operator conventions); no request body controls paths. [ASSUMED: schema and transaction proposal]

Canonical hashing must cover every security-relevant field: version, event type, sequence, event ID, session, actor/nodes, resources, time, outcome and typed payload. Ban NaN/Infinity and ambiguous encodings. Use domain-separated leaf `SHA256(0x00 || canonical_event_bytes)` and branch `SHA256(0x01 || left_digest || right_digest)` with bytes, not concatenated hex text. Define one deterministic odd-leaf rule; preserving duplicate-last is maintainable if proofs verify its expected duplication and bind tree_size. Empty-root definition is versioned; no arbitrary root accepted. Frozen copies/tuples ensure a previously returned snapshot cannot change when the ledger appends. [ASSUMED: versioned hashing proposal]

Startup fully replays event sequence, predecessor linkage, canonical hashes and all stored prefix roots, with SQLite integrity check. Corruption/mismatch/gaps reject readiness and append/anchor operations; never reset to an empty tree, silently repair or continue from a cached root. Tests intentionally corrupt payload, sequence, leaf, checkpoint and truncated storage, then reopen. A process crash inside a transaction must either preserve the entire prior prefix or include the whole new event+checkpoint. Concurrent writers need unique monotonic sequence without lost updates. [ASSUMED: replay/tamper semantics]

Hash chains/SQLite triggers detect accidental or partial tampering, not an administrator replacing the entire file and recomputing every hash. Historical roots previously held by clients or confirmed on-chain provide an external checkpoint; compare replay to them to detect rollback/rewrite through that prefix. No unanchored local-only ledger can prove resistance to full privileged replacement. Preserve prefix size/root pairs forever through the application API; a later outcome event changes the current root but not the published prefix. [ASSUMED: threat-model inference]

Required event families: Bell created/allocated/measured/consumed/discarded/released including rejected purification/swap branches; teleport started/succeeded/failed with measured BSM/corrections/fidelity/resource references; QKD started/estimated/reconciled/established/aborted/failed with blinded sifted/key commitments only for eligible material; drill numerical summary; anchor prepared/submitted/confirmed/failed/unknown. These are proposed event types, not current enums. Events arise from the real pool/protocol/engine event sink once, not only from whichever REST route calls them. Aborted sessions never append a key-established event. [ASSUMED: new lifecycle contract]

### Inclusion proof and compact genuine execution proof

A proof must include canonical typed leaf preimage, leaf_index, tree_size, siblings with direction (or derive direction deterministically from index/width), tree/hash version and the expected immutable root. Verification checks index<size, expected depth/odd behavior, sibling lengths, exact canonical encoding and reconstructed root. It must reject changed node, event time, outcome, session/resource ID, index, size, leaf, sibling, direction and root; successful proof verification means membership, not that physics occurred. [ASSUMED: proof contract]

Use a compact **typed binary canonical execution leaf** for eligible teleport/drill summaries, with public REST JSON as a projection of the same schema. Generic events can have a different versioned canonical type. Suggested fields bind numerical-model version, sequence/time, public session/resource/node identity digests, actual BSM/correction bits, fidelity/error/sample counts and outcome flags. The exact digest IDs resolve to public ledger details. Do not replace the eligible execution preimage itself with an opaque payload_hash: a verifier needs the typed numerical summary to check its shape/outcome and bind it to the root. Include a commitment to the fuller numerical transcript when the leaf is a summary, explicitly naming that limitation. [ASSUMED: maintainable compact canonical encoding]

Versioned wire attestation proposal: ASCII prefix plus base64url of [schema/version, tree_size, leaf_index, root32, canonical_execution_leaf_length+bytes, path_length+sibling32...]. Direction follows the verified tree rule/index. Include all siblings: compressing digest strings to raw bytes before base64 is valid; replacing the path by a hash, truncating it or anchoring a different tiny tree is not. Scope the receipt to an actual successful teleport or numerical drill summary; arbitrary caller-defined event data is ineligible. No private amplitudes, bits, signer secret or key appears in this payload. [ASSUMED: new attestation schema]

The proof is an honest simulator execution attestation plus cryptographic inclusion path. It is **not** a zero-knowledge quantum-execution proof, hardware attestation or independent mathematical audit. SPL Memo validates/logs its UTF-8 data and signer accounts; it does not execute the Merkle verification. The application verifies before publishing; observers can independently decode and verify membership/numerical summary afterward. [CITED: https://www.solana-program.com/docs/memo; ASSUMED: attestation scope]

### Real standard SPL Memo publisher

Pin the actual standard program `MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr`, not the old fabricated program parameter. Require fixed expected Devnet genesis `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG`. The program ID is stated in official Memo logs; the genesis value is observed parent/session evidence and is written verbatim in the phase context. `getGenesisHash` officially reports connected-cluster identity. A caller cannot override the expected genesis to make mainnet/localnet pass. [CITED: https://www.solana-program.com/docs/memo; https://solana.com/docs/rpc/http/getgenesishash; VERIFIED: 69-CONTEXT.md:51]

Operator-only proposed settings names: `QUANTUM_SOLANA_RPC_URL`, `QUANTUM_SOLANA_SIGNER_PATH`, `QUANTUM_NODE_ENDPOINTS`, `QUANTUM_NODE_TOKEN`, plus existing `DATA_DIR`. These quantum setting names are proposals, not current environment declarations. Permit only configured HTTPS Devnet RPC target, no credentials echoed in errors; verify genesis before signing/submission, disable redirects, retain TLS validation. No caller-supplied URL, program ID, signer path, funding amount or network selection. [ASSUMED: new settings; VERIFIED: services/desk-gateway/src/desk_gateway/config.py:206,147-155,172]

Signer adapter opens only the configured external dedicated Devnet resource, verifies a regular non-symlink private file with restrictive ownership/mode and a private parent, reads bounded keypair content privately, and validates byte count/ranges plus derived public-key match before signing. A 64-byte Solana keypair representation is a proposed interoperability format to validate against native CLI; use the first 32-byte seed only through Ed25519.from_private_bytes and compare derived public bytes to the supplied public half. Never call CLI config default keypair or expose private file contents through file tools. No wallet discovery, token transfer, airdrop, program deployment or funding mutation belongs to exporter. [ASSUMED: private loader/interface proposal; CITED: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/; https://solana.com/docs/core/transactions/signing-in-production]

Parent chose a narrowly necessary fixed 400000-CU SetComputeUnitLimit instruction, with no priority-price instruction. Official ComputeBudget program is `ComputeBudget111111111111111111111111111111`; SetComputeUnitLimit discriminator is 2 with a u32 units parameter. This is bounded execution configuration, not a transfer/program deployment. Keep only one such instruction followed by one Memo instruction and one signer; any change to this narrow shape needs explicit contract revision. [CITED: https://solana.com/docs/core/fees/compute-budget; ASSUMED: fixed parent-approved instruction contract]

**Legacy wire layout:** header [required signatures=1, readonly signed=0, readonly unsigned=2], static account list [payer32, ComputeBudget32, Memo32], recent blockhash32, two compiled instructions. ComputeBudget references no account and contains [2]+little-endian u32(400000). Memo program index is 2 and its account list includes payer index 0 so Memo itself verifies signer approval. Sign the serialized Message exactly, not JSON or a prehashed digest. Transaction bytes are compact-u16 signature count 1 + signature64 + Message bytes. Verify signature locally through cryptography. Implement only needed shortvec/Base58 encode/decode with length limits and leading-zero preservation; reject unsupported transaction/account shapes rather than grow an SDK. [ASSUMED: selected codec derivation; CITED: https://solana.com/docs/core/transactions/transaction-structure; https://solana.com/docs/core/fees/compute-budget]

**Wire budget derivation:** for 128<=memo_bytes<16384, one payer+one Memo (without compute instruction) is 171+memo_bytes total; adding the fixed ComputeBudget account32 and instruction8 gives **211+memo_bytes**. Thus a 900-byte Memo is 1111 bytes, and the exact cap for this shape is **1021 Memo bytes** under the selected 1232-byte legacy packet limit. With memo_bytes<128, shortvec data length loses one byte. A base64-encoded transaction string can be larger than 1232 characters; the cap applies to decoded signed transaction bytes. Assertions must use actual serialized byte length, not estimates. These counts are a source-layout derivation, not a native-decode observation. [ASSUMED: byte-count calculation; CITED: https://solana.com/docs/core/transactions/transaction-structure]

Parent independently exercised the narrow public wire recipe using the installed service environment and native Solana CLI: 871-byte UTF-8 Memo, fixed 400000-CU instruction, 1082-byte signed packet, locally verified Ed25519 signature, matching Devnet genesis and decode exit0. CLI decode JSON contains `transaction` (including `message` and `signatures`), `meta`, `blockTime`, and `sigverifyStatus`; do not expect signatures at the outer JSON level. This corroborates the211-byte overhead for that exercised shape. The recipe used dummy padding, not an eligible execution receipt; no transaction was submitted and neither compute adequacy nor confirmation was observed. [VERIFIED: Main session message reporting actual `/tmp/v51-memo-wire-smoke.py` exercise; ASSUMED: full-proof preflight still required]

Memo's official documentation gives a historical v1.5.1 compute-limited example of 566 single-byte UTF-8 bytes with zero signer accounts; that is not proof of a present universal Memo size ceiling or of acceptance at 900 bytes. The fixed compute budget and real preflight must exercise the complete proof. A large ledger may exceed even the compact path budget; reject before submission with a clear payload-too-large outcome. Never truncate proof, drop Bell events, silently anchor another root, split into unrequested multiple transactions or increase limits until lucky. [CITED: https://www.solana-program.com/docs/memo; ASSUMED: honest size admission rule]

**Submit once, observe boundedly:** freeze the prefix; validate the local proof and sanitized eligible leaf; pin genesis; obtain actual `getLatestBlockhash` blockhash and lastValidBlockHeight; construct/sign/decode-check wire; persist prepared public signature/root/size; issue exactly one sendTransaction with base64 encoding, skipPreflight=false, preflightCommitment=confirmed and maxRetries=0. Compare returned signature to the locally signed transaction's first signature. This is not automatic resubmission policy. Bounded status polling and readback are observation of the same transaction, not retries of the write. [ASSUMED: publisher control flow; CITED: https://solana.com/docs/rpc/http/getlatestblockhash; https://solana.com/docs/rpc/http/sendtransaction]

Only classify publication confirmed after non-null getSignatureStatuses reports err=null and confirmationStatus confirmed/finalized **and** getTransaction at confirmed returns meta.err=null, the expected signature, payer and allowed instruction/program shape, observed execution slot and exact Memo bytes. Verify decoded proof/root/tree_size against the frozen prefix again. A status object's transaction slot is not its RPC context slot. Null readback, processed only, error, deadline expiry or expiry uncertainty is not success. Keep slot null unless observed. Never fabricate blockTime/confirmation count. [CITED: https://solana.com/docs/rpc/http/getsignaturestatuses; https://solana.com/docs/rpc/http/gettransaction; ASSUMED: matching readback admission checks]

Persist the public locally known signature before the send so an ambiguous send/crash can be inspected afterward without signing/sending again. Bounded deadlines should yield failed/unknown/pending explicitly, not implicitly retry. On restart reconcile observation of that same signature only when an operator requests it; do not auto-resubmit. Append anchor-confirmation as a new event after the immutable-prefix attestation, and return both anchored_root/tree_size and current_root so consumers cannot confuse them. [ASSUMED: publication crash/history contract]

## Five-Stage Drill

The following is the required implementation design, not a completed drill. Each stage records real shared-object results and prerequisite IDs. Stage failure prevents dependent success; skipped/unavailable states keep all_passed false. No RNG-seed hunting, hidden retry, fresh shadow runtime or fabricated chain outcome. [ASSUMED]

1. **Bell generation + purification:** shared pool generates actual states across authenticated configured nodes; compare actual density/state properties; execute bilateral operations and measurement branches. Both input resources consumed even on parity rejection; a claimed purification pass needs a real surviving output and measured improvement, not calculated p_success alone.
2. **Repeater distribution + swapping:** established configured Alice/repeater/Bob workers own allocations, real BSM branches extend entanglement and record derived state/frame/fidelity with consumption/release. Distinct labels alone do not pass distributed evidence.
3. **Teleportation:** consume the selected swapped resource, derive actual receiver conditional state and send only necessary classical correction inputs to the worker; worker performs correction; measured final fidelity >=.95, ownership and one-shot lifecycle validated. Append eligible typed execution receipt.
4. **QKD + interception abort:** same engine executes sufficiently large clean BB84 with independent worker reconciliation/extraction, demonstrates agreement through safe internal evidence and no REST key leak; separate real intercept-resend run produces observed QBER>.11 and abort, destroys/withholds keys at both nodes, and appends abort receipt. E91's actual Bell/witness/independent-key requirement needs its own acceptance run even though the original drill names BB84. A clean insufficient-entropy abort is not clean_success; detection without key withholding is not eavesdropped_aborted.
5. **Ledger proof + Devnet publication:** append a numerical drill-summary receipt covering stages 1–4, freeze actual ledger prefix, verify its genuine inclusion proof, sign using funded external dedicated fee payer, submit once and observe matching confirmed transaction/proof. Confirmed evidence carries actual signature/slot/prefix; no mocked publisher is live acceptance.

`all_passed` is the conjunction of Bell/purification success, remote resource/transport success, repeater success, F>=.95 teleportation, clean key establishment+independent agreement, interception detection+explicit abort+both nodes without keys, valid immutable ledger proof and actual confirmed matching publication. Ledger existence/root length alone is not a stage. Final output includes stage outcomes/reasons, resource/session/receipt identifiers, numerical model, public transport evidence and anchored/current roots, never keys/prefixes. [ASSUMED: drill DTO and conjunction]

## REST Admission, Authorization and Error Semantics

Seat auth in current config compares passphrases via compare_digest and maps exact seats `"lead"`, `"systems"`, `"web"`, `"android"`, `"ios"`, `"infra"`, `"quality"`. Existing REST handlers read Bearer and invoke settings.seat_for_passphrase. The generic seat middleware passes requests through when its seat-path regex does not match; the complete phase69 handler bodies contain no authorization checks. Thus do not assume MCP seat protection authenticates these custom quantum routes. [VERIFIED: services/desk-gateway/src/desk_gateway/config.py:9-17,147-155; services/desk-gateway/src/desk_gateway/server.py:423-426,1604-1618,6355-6399]

Use explicit authenticated-seat admission before body parsing/side effects for every phase68/69 route, including read-only ledger/session queries and drill/export. Proposed read access: authenticated appropriate desk seats; proposed mutation access: lead/systems/infra, with ownership-specific internal key operations remaining node-scoped. Disallow origin intake tokens as quantum control credentials; no loopback bypass. Missing/invalid credentials =>401; authenticated disallowed seat =>403. These permission sets are new shared policy choices, not existing route policy. [ASSUMED: authorization proposal]

Keep existing route families; add proposed ledger snapshot, receipt-list, receipt-get, proof-get and proof-verify operations plus public QKD session lookup. No ledger append arbitrary caller payload, ledger update/delete, public raw-key endpoint or caller network/signer selection. Resolve exact suffixes in the API contract before editing so server/tests/docs all use one convention. [ASSUMED: route completion proposal; VERIFIED: .planning/REQUIREMENTS.md:20 quotes `/v1/quantum/teleportation/ledger/*`]

| Condition | Proposed HTTP behavior |
|---|---|
| Invalid JSON/non-object, forbidden unknown fields, bad integer/enum, nonfinite floats, ratios outside [0,1], zero/negative or excessive work request | 400 with stable sanitized validation code; 415 for unsupported body media type. Reject booleans as integer counts and malformed strings rather than coercing. |
| Unknown registered node/session/receipt/pair | 404 after auth; no key/resource mutation. |
| Consumed pair, duplicate one-shot operation, incompatible ownership/state, concurrent drill admission conflict | 409; fail closed and preserve honest resource state. |
| Valid protocol completes with QBER/witness/entropy/reconciliation abort | 200 protocol result with ok=false, status=aborted and safe reason; not a transport exception and never established. |
| Proof request structurally invalid | 400; well-formed proof that does not verify returns explicit valid=false, no misleading success. |
| Publisher missing signer/configuration/funded prerequisite or node transport unavailable | 503 with public prerequisite code only; all_passed=false. Wrong genesis or unsafe signer is fail-closed, no send. |
| Proof exceeds selected packet allowance | 413 before signing/submission; no truncation. |
| Upstream RPC malformed/error/readback mismatch | 502 with sanitized stable reason; persist actual/unknown signature state. |
| Confirmation/readback deadline reached | 504 with pending/unknown public outcome, actual signature if known, no fake slot and no automatic resend. |
| Ledger corruption or persistent I/O failure | 503 ledger_unavailable/tamper code; do not reset/drop events or return green. |

All status/error names in this table are proposed new values. Bind checks to existing problem_response conventions without leaking raw exceptions, authorization headers, signer file contents, credential-bearing URLs or worker request bodies. Outcome ok must reflect protocol/drill/publisher outcome, not merely Python returning normally. [ASSUMED]

## Don't Hand-Roll

| Problem | Do not build | Use instead |
|---|---|---|
| Curve signatures | Custom Ed25519/math/seed derivation | Existing cryptography Ed25519 and native CLI independent wire decode. [CITED: cryptography Ed25519 docs] |
| General Solana SDK | Wallet discovery, ALT/versioned formats, RPC retry layers, account manager | One fixed legacy shape, documented compact wire codec, existing httpx, one actual submit. [ASSUMED: parent-selected bounded exception] |
| Durable multiwriter append/crash recovery | Unlocked/un-fsynced JSONL or mutable Store replacement | stdlib SQLite transactions and replayed prefix roots. [CITED: sqlite atomiccommit/pragma docs] |
| Quantum evolution | Second metadata-only Bell or basis-equality shortcut | Phase 68 state/rho kernels and authoritative resource pool. [ASSUMED: shared contract] |
| Entropy generation | SHA-256/KDF expansion presented as fresh 256-bit entropy | Finite-key budget and universal extraction; insufficient abort. [CITED: primary leftover-hashing paper] |
| Authorization/redaction | Separate unauthenticated control plane | Existing settings seat resolver, explicit route policy, allowlisted public DTO. [VERIFIED: config.py:147-155] |

## Runtime State Inventory

This is a repair/refactor of session/ledger/exporter contracts. All five categories are explicitly scoped; no live inventory is fabricated. [VERIFIED: inspected implementation bodies and parent resource observations]

| Category | Items found / observation | Required action |
|---|---|---|
| Stored data | Current phase69 ledger is lists `self.leaves` and `self.receipts`; sessions are a dict in the engine. Gateway Store persists unrelated state. No deployed phase69 database was inspected. | New durable ledger code; do not certify/migrate old fabricated confirmed anchors as genuine. Restart loses ephemeral old sessions/keys; record historical receipt versus current key availability. Inspect operator storage before any deployment migration. |
| Live service config | Parent confirmed Devnet genesis; no deployed quantum worker/RPC service configuration inspected by this research. | Operator supplies isolated authenticated workers and dedicated Devnet target; no unrelated platform mutations. |
| OS-registered state | CLI executable is installed; no systemd/pm2 registrations inspected for this phase. | Separate worker processes must be launched/observed by acceptance runner; no assumption of absent/live registrations. |
| Secrets/env vars | Existing env-backed seat auth; parent dedicated external signer metadata is available, but signer content was never read. Parent reported funding failure and zero balance. | Add settings references only, bind worker keys/capabilities and signer securely; no renaming/copying unrelated secrets. |
| Build artifacts/installed packages | Locked gateway venv observed; SDKs absent, CLI present. | No dependency bump/reinstall prescribed; rebuild/restart application under main-agent verification only. |

## Common Pitfalls and Broken Test Contracts

1. **Tiny sample crash / false entropy:** current sample_size=max(4,...) and prefix-indexing assume enough sifted entries, and SHA-256 expands the representation regardless of entropy. Existing tests demand a 64-character secret from 128 BB84 signals and 120 E91 pairs. Replace those assertions with independent private agreement and entropy accounting for sufficiently large sessions, plus explicit short-input abort tests. [VERIFIED: quantum_qkd_mesh.py:142-160,210-219; tests/test_quantum_qkd_mesh.py:19-48]
2. **Flaky detection:** current 256-bit/90% intercept test demands detection from a random prefix sample, with `qber > 0.10` rather than the actual .11 boundary. Use deterministic injected physical outcomes for exact boundaries; statistical kernel tests use confidence/tolerance and runtime drill records actual result without rerunning to get green. [VERIFIED: tests/test_quantum_qkd_mesh.py:31-38; ASSUMED: replacement design]
3. **E91 without entanglement:** engine accepts optional mesh but its full E91 body never reads it; tests instantiate no resources. Require actual resources, settings/witness correlations, consumed pairs and failed product-state witness. [VERIFIED: quantum_qkd_mesh.py:94-96,178-235; tests/test_quantum_qkd_mesh.py:41-48]
4. **Mutable unauthenticated ledger:** current leaf excludes target_nodes/receipt_id/timestamp and receipts are mutable. Test only root length/count is inadequate. Test immutable snapshots, committed metadata, restart/tamper/history/proofs and concurrent append. [VERIFIED: quantum_qkd_mesh.py:238-305; tests/test_quantum_qkd_mesh.py:51-75]
5. **Fake signature/slot acceptance:** test expects `len(commitment["commitment_tx"]) == 64` and unconditional confirmed. Actual txid is base58 of a 64-byte signature, not a 64-character hash. Replace with decoded-signature validity and actual readback; separate mocked RPC behavioral tests from live evidence. [VERIFIED: tests/test_quantum_qkd_mesh.py:78-93; CITED: Solana transaction-structure/sendTransaction docs]
6. **Private shadow drill:** current classmethod creates new pool/ledger/publisher; its success conjunct omits explicit abort/key withholding and accepts F>=.85. Tests demand all_passed on entirely unconfigured runtime. Replace with injected shared fixtures and no-success cases for every missing prerequisite; actual live drill is a separate required evidence run. [VERIFIED: quantum_qkd_mesh.py:340-347,390-423,435-453; tests/test_quantum_qkd_mesh.py:96-105]
7. **Auth assumption and JSON coercion:** handlers immediately parse/cast and serialize secrets, with no local auth. Add bad JSON/type/range/nonfinite/auth cases for every named route family, not just happy-path response codes. [VERIFIED: server.py:6355-6399]
8. **Tree root changes after publication:** a confirmed event appended after anchoring changes current root. Verify the exact anchored prefix size/root, never substitute latest. [ASSUMED: expected append-only consequence]
9. **Witness or commitment overstated:** classical-node simulation and SPL Memo cannot certify quantum secrecy/actual hardware; public low-entropy key hashes can be guessed. Explicit model/scope and safe commitment policy are required in response/docs/evidence. [ASSUMED: threat-model analysis]

## Code Examples

These are design skeletons, not code landed or exercised in this slice; values introduced here are proposed except the documented RPC parameters. [ASSUMED]

### Numerical measurement contract

```text
prepared = basis_eigenstate(alice_bit, alice_basis)
received = quantum_channel(prepared)
if intercepted:
    eve_bit, collapsed = projective_measure(received, independent_eve_basis, rng)
    received = collapsed               # numerical resend, not Alice bit copy
bob_bit, consumed_state = projective_measure(received, bob_basis, rng)
# Bob worker retains bob_bit; only later protocol-authorized values are disclosed.
```

### Universal extraction and safe public projection

```text
candidate_bob = bob_worker.reconcile(its_private_bits, disclosed_syndromes)
if independent_verification_tags_disagree:
    destroy_both_candidate_stores(); emit_aborted_session()
else:
    budget = finite_entropy_bound - counted_leakage - verification_leakage - PA_margin
    length = byte_aligned_min(requested_length, budget)
    if length < minimum_usable_length:
        destroy_both_candidate_stores(); emit_insufficient_entropy_session()
    else:
        alice_worker.extract(public_toeplitz_seed, length)
        bob_worker.extract(public_toeplitz_seed, length)
        emit_public_counts_handles_commitments_only()
```

### One signed submission and actual readback

```json
{"jsonrpc":"2.0","id":1,"method":"sendTransaction","params":["<base64 signed wire>",{"encoding":"base64","skipPreflight":false,"preflightCommitment":"confirmed","maxRetries":0}]}
```

This exact RPC method/config is documented; placeholder is not submitted evidence. Follow with bounded observation of the same actual signature and getTransaction matching Memo bytes/metadata. [CITED: https://solana.com/docs/rpc/http/sendtransaction; https://solana.com/docs/rpc/http/gettransaction]

## State of the Art

| Old approach in this phase | Required current approach | Evidence |
|---|---|---|
| Hash Alice alone and claim shared key | Bob reconciles/extracts independently; finite budget | Primary finite-key protocol and current source observations above. [CITED: https://arxiv.org/html/1103.4130] |
| Classical E91 correlated bits | Actual consumed Bell rho plus measured witness | E91 primary abstract and CHSH reference. [CITED: APS E91; IBM CHSH] |
| In-memory mutable Merkle root | Durable immutable prefix snapshots/replay/proofs | New design constrained by context. [ASSUMED] |
| Local digest says confirmed | Signed standard Memo + status and exact readback | Official RPC says send does not guarantee confirmation. [CITED: https://solana.com/docs/rpc/http/sendtransaction] |
| Large general SDK installation | Existing crypto/httpx with audited fixed legacy shape | Parent-selected bounded repair, not universal Solana-client advice. [ASSUMED] |

Do not upgrade to newly documented larger transaction formats to bypass size acceptance: selected wire is legacy and remains capped at1232 even though current Solana docs mention other format limits. No date/version of a protocol change is invented here. [CITED: https://solana.com/docs/core/transactions/transaction-structure; ASSUMED: selected scope]

## Environment Availability and Live Prerequisites

| Dependency | Observation | Availability / consequence |
|---|---|---|
| Gateway Python/httpx/crypto/SQLite/pytest | Metadata probe above | Installed; SDK installation unnecessary. [VERIFIED: session metadata probe] |
| Solana CLI/keygen | command -v plus CLI version/help; parent actual native decode exit0 | Available; parent exercised public1082-byte signed wire/signature successfully. No submission or complete numerical-proof execution is established by dummy Memo padding. [VERIFIED: session command outputs and Main message] |
| Devnet identity | Parent observed genesis matches fixed expected hash | Connectivity/identity only, not funding/confirmation. [VERIFIED: 69-CONTEXT.md:51] |
| Dedicated signer | Parent metadata records external private resource creation and modes | Resource content deliberately not opened; parent owns setup/evidence. [VERIFIED: local://v51-devnet-resource.md:3-4] |
| Funding | Parent observed requested .05 test SOL airdrop exit1; subsequent confirmed balance0 at context slot509319960 | Missing; exact error cause not proven. No publication proof exists from these observations. [VERIFIED: local://v51-devnet-resource.md:8-9] |
| Separate authenticated simulator workers | Required by phase68; no worker run observed in this slice | Main must launch/test actual processes; in-process tests are not distributed drill evidence. [VERIFIED: phase68 context:18] |
| Context7/ctx7 | No mounted Context7 route used; command -v did not return ctx7 | Official direct reads used as fallback. [VERIFIED: tool inventory/probe] |
| Web search | Parallel search returned HTTP402 insufficient credit | No search result obtained; primary documents were read directly instead. [VERIFIED: session search command] |

**Missing prerequisite with no acceptance fallback:** a funded isolated Devnet fee payer and matching actual publication. Local validator or mocks cannot replace Devnet acceptance. Finish publisher/numerical/auth/ledger work regardless. [ASSUMED: execution implication of locked acceptance]

**Documented funding alternatives, research only:** Solana's official guide lists Foundation/provider faucets and a linked proof-of-work faucet. The current Foundation page explicitly directs AI agents away from its human UI to CLI or POW; do not use human GitHub login, captcha or UI as a bypass. Parent inspected the linked POW `Mine` branch: it needs at least5000 lamports, otherwise invokes ordinary official request_airdrop before mining, so it does not remove the current zero-balance bootstrap prerequisite. No POW tool was installed or run. Parent also inspected DevnetFaucet.org: its flow requires GitHub authentication; its anonymous option hides identity, not authentication. No permitted unauthenticated funding flow or funded payer has been established. Do not repurpose a wallet, bypass site controls, install unverified tooling or repeat the failed airdrop merely to confirm it. [CITED: https://solana.com/developers/cookbook/development/airdrops-and-faucets; https://faucet.solana.com/; VERIFIED: local://v51-devnet-funding-alternatives.md:3-10 and Main's later DevnetFaucet inspection message]

## Validation Architecture

Config explicitly contains `"nyquist_validation": true`, `"security_enforcement": true`, `"security_asvs_level": 1`; both sections are required. This research runs no product verification. [VERIFIED: .planning/config.json:9-12]

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest9.1.1 installed; pytest-asyncio declared. [VERIFIED: installed probe; services/desk-gateway/pyproject.toml:35-36] |
| Config | `[tool.pytest.ini_options]`, `asyncio_mode = "auto"`, `testpaths = ["tests"]`. [VERIFIED: services/desk-gateway/pyproject.toml:39-41] |
| Existing test seam | Root tests include current phase69 unit/integration test body read above; explicitly include root tests because gateway default testpaths only selects service tests. [VERIFIED: tests/test_quantum_qkd_mesh.py:19-105; pyproject.toml:41] |
| Quick proposed command | In product gateway directory: `uv run pytest ../../tests/test_quantum_qkd_mesh.py -q`; migrate tests before running. [ASSUMED: planned check; existing invocation convention verified in services/desk-gateway/README.md:96-102] |
| Full proposed command | `uv run pytest tests ../../tests -q`; CPU/runtime budget not measured here. [ASSUMED] |

### Phase Requirements → Test Map

Commands below are proposed main-agent checks after implementation. New file/node IDs are not asserted to exist, and sub30-second execution has not been measured. Live chain and distributed drill cannot be reduced to a quick local unit command. [ASSUMED]

| Requirement | Required behavior/test type | Proposed command or evidence | Existing coverage/gap |
|---|---|---|---|
| REQ-QTELEPORT-006 | Numerical basis probabilities; Bob error correction; universal extraction vectors; length<=budget; short abort; consumed Bell witness | `uv run pytest ../../tests/test_quantum_qkd_mesh.py -q` | Existing file, old contracts broken; add all numerical/reconciliation/entropy cases. |
| REQ-QTELEPORT-007 | Exactly .11 accepted by detector, >.11 abort; numerical Eve disturbance; both keys withheld | Same targeted suite | Add deterministic count/nextafter tests and scoped worker absence checks. |
| REQ-QTELEPORT-008 | Restart/crash atomicity, immutable historical roots, concurrent append, tamper and complete inclusion proof | Same targeted suite or new dedicated ledger tests explicitly selected | Current root/count test insufficient. |
| REQ-QTELEPORT-009 | Codec decode, exact sizes, signature validation; mocked status/readback cases; actual live Devnet confirmed Memo | Unit suite + native CLI decode + real dedicated signed publication/readback | Replace fake64-character tx test. Live evidence is separate mandatory integration, not a mock. |
| REQ-QTELEPORT-010 | Each prerequisite independently fails conjunction; real node processes and actual chain confirmation | Targeted drill tests + separate main-run five-stage drill | Old all_passed test unconfigured; no live drill observed by this slice. |
| REQ-QTELEPORT-011 | Auth/role/body/ranges/errors for all route families; public payload secret exclusion and ledger proof endpoints | New proposed phase69 endpoint tests, explicitly selected via uv | Current phase69 route tests not found in scoped discovery; add Wave0 file. |

### Sampling and Wave 0 Gaps

Main runs one targeted pass after all sibling edits land, then the full affected suite and distributed/live acceptance; no subagent test storms. Per-commit numerical checks can be targeted when main requests them. Gate completion requires independent receipt/review disposition, not advisory agent approval. [VERIFIED: assignment and phase69 context:31]

- Replace the root QKD test's leaked-key/fake-confirmation requirements; preserve original numerical acceptance, not old unsafe behavior. [VERIFIED: tests/test_quantum_qkd_mesh.py:19-105]
- Add deterministic injected RNG/channel fixtures, separate node private-state assertions, universal-hash known vectors, complete historical-proof/tamper fixtures, and strict publication RPC fakes explicitly labeled unit-only. [ASSUMED]
- Add phase69 endpoint tests with actual app lifespan/seat fixtures, session DTO allowlist checks, unknown/consumed resource errors, missing configuration and no extra send assertions. [ASSUMED]
- Add independent native decoder check of the produced public signed wire and actual complete proof; save only sanitized message/tx evidence. No signer content in receipts. [ASSUMED]
- Actual funding/remote node processes/live confirmed publication are mandatory acceptance gaps, not optional future work. [VERIFIED: context constraints; ASSUMED: planned verification sequencing]

## Security Domain

Official current stable ASVS is5.0.0; category numbers differ from the research template's older V2-auth/V3-session/V4-access/V5-input/V6-crypto labels. Do not mix versionless IDs. Use actual ASVS5 categories alongside legacy topic labels below. This is a threat/test mapping, not a completed security audit or certification. [CITED: https://owasp.org/projects/asvs; inspected ASVS v5.0.0 source chapters]

| Topic / template legacy label | Actual ASVS5 category | Applicability and control proposal |
|---|---|---|
| Authentication / legacy V2 | V6 Authentication | Required existing seat resolver and separately scoped worker auth; invalid credentials rejected before side effects. [ASSUMED] |
| Session management / legacy V3 | V7 Session Management | Existing gateway bearer lifecycle plus internal key capability/session binding; no new browser login. [ASSUMED] |
| Access control / legacy V4 | V8 Authorization | Function, node/session/receipt scope and no raw-key field; test BOLA. Official8.2.1/8.2.2 are level1. [CITED: ASVS5 V8 chapter] |
| Validation / legacy V5 | V2 Validation and Business Logic, V1 Encoding/Sanitization, V4 API | Finite inputs, work caps, canonical proof/parser, parameterized SQL; no caller URL/path/program/signer. V1.2.4 SQL injection is level1. [CITED: ASVS5 V1 and V4 chapters; ASSUMED: implementation controls] |
| Cryptography / legacy V6 | V11 Cryptography | Existing validated Ed25519 implementation, entropy-constrained simulated keys, strong hashes and no private output. Do not declare simulated QKD an approved production security primitive. [CITED: ASVS5 V11; ASSUMED: application policy] |

Applicable threats and required verification proposals: [ASSUMED]

| Pattern | STRIDE | Required guard/evidence |
|---|---|---|
| Unauthenticated expensive exchange/drill or unauthorized signer spend | Spoofing/Elevation/DoS | Every route seat auth and mutation policy before parsing/allocation; bounded work/capacity; no localhost bypass. |
| Node impersonation/session key theft | Spoofing/Information disclosure | Operator endpoint allowlist, authenticated node capability, ownership scope, no private REST serializer/log repr. |
| Caller-provided RPC/node target/signer path | Elevation/Information disclosure | No request overrides; configured HTTPS target, no redirects, genesis pin before signing; strict file checks. |
| Candidate/key leakage through prefixes/hashes/transcripts | Information disclosure | DTO allowlist, count leakage before extraction, secret-blinded commitments after usable entropy, no raw/sifted/key bytes in ledger/Memo/errors. |
| Ledger mutation, rollback, proof substitution | Tampering/Repudiation | Append-only SQL API/triggers, canonical complete leaves, startup replay, external prefix checkpoints, historical size-bound proofs. |
| Fake status/wrong Memo/untrusted instruction shape | Tampering/Repudiation | Locally valid signed wire; one actual submit; confirmed err-null status + exact readback/payer/program/leaf/path/root check. |
| Request or RPC resource exhaustion | DoS | Positive capped integer counts, finite ratios, bounded proof depths/body sizes, deadlines, no write resubmissions or success-hunting loops. |
| Input/SQL/CLI injection | Tampering/Elevation | Typed schemas, parameterized SQL; SDK/native commands receive argument arrays, never shells built from caller strings. |

## Assumptions Log

Every paragraph labeled ASSUMED above is a proposal/derivation, not an observed product fact. The planner may select these within granted builder discretion; security-strength policy parameters and proof/model claims must be explicitly reviewed before locking. [ASSUMED]

| ID | Proposal/claim family | Sections | Risk if wrong |
|---|---|---|---|
| A1 | Async shared runtime and node-private key/capability protocol | Architecture, DTO, drill | Transport leaks keys or uses shadow/non-distributed objects. |
| A2 | Z-key/X-test split, unbiased sample selection, detector per-basis semantics | BB84/QBER | Invalid sampling/phase bound and false abort/pass. |
| A3 | E91 settings/projectors/CHSH confidence rule and trusted-device entropy reuse | E91 | Witness cannot justify stated model; no DI security inference allowed. |
| A4 | Bounded block syndrome correction and independent verification | Reconciliation | Residual errors pass without sufficient tag/leakage accounting. |
| A5 | Finite accounting integration, epsilon policy, usable min128/max256, proposed raw sizes, Toeplitz indexing | Entropy | Fictitious entropy, double/omitted leakage, always-abort or mismatched extraction. |
| A6 | Secret-blinded sifted/key commitment construction | Private DTO/security | Guess oracle or unjustified secrecy claims. |
| A7 | SQLite schema/settings, canonical leaf types, triggers, replay, external checkpoint strategy | Ledger/proofs | Incomplete tamper detection, durability loss, mutable historical root. |
| A8 | Typed compact attestation encoding, exact211+L wire derivation, actual compute adequacy | Publisher/proof | Packet/compute rejection or omitted genuine proof. Native decode/preflight still required. |
| A9 | Operator quantum setting names, permissions and proposed HTTP statuses/routes | REST/settings | Broken callers, auth gaps or unsafe capability exposure. |
| A10 | Proposed tests/commands/durations and unobserved workers/funding/live chain | Validation/environment | False acceptance if local mocks replace actual evidence. |

## Open Questions and Exact Remaining Prerequisites

1. **Live funding:** parent observed balance0 after one failed official airdrop; this research documents alternatives but performed no funding mutation. Confirmed publication is blocked until that exact dedicated resource is funded, not until a generic wallet exists. [VERIFIED: local://v51-devnet-resource.md:8-9]
2. **Complete typed-proof preflight/readback:** parent verified a871-byte dummy Memo/1082-byte packet, Ed25519 signature and native decode exit0. Actual eligible execution summary/path, compute preflight, signed submit, confirmation and exact readback remain unobserved. Dummy padding is not execution evidence. [VERIFIED: Main actual wire exercise message; ASSUMED: remaining full-proof checks]
3. **Shared numerical/node API finalization:** peer recommends actual Bell rho, pool lifecycle sink and async resource workflows; final implementation must converge on one contract and migrate server/tests/drill without shims. No product exports were edited here. [VERIFIED: peer communication in this session; ASSUMED: planned convergence]
4. **Finite-key/witness parameter review:** choose explicit model-bound epsilon policies and transcript leakage before running; no physical, device-independent or production confidentiality claim is supported by a classical simulator. [ASSUMED]
5. **Compact proof growth:** full Bell lifecycle can create a large tree. Test a representative full-drill prefix depth with actual eligible canonical summary; payload-too-large is honest but would leave live drill acceptance unsatisfied. Do not hide this with event omission. [ASSUMED]

## Sources and Research Execution Record

### Primary source files opened this session

- Phase69 and phase68 CONTEXT; original REQUIREMENTS; config and ownership ranges cited above. These are direct authoritative project decisions, not a Greptile inference. [VERIFIED: session reads]
- Complete relevant QKD/ledger/exporter/drill implementation, root QKD tests, phase68 numerical/resource interface, gateway route/auth/config, Store/Audit, pyproject and test conventions. Line citations above refer to the inspected pre-implementation worktree snapshot. [VERIFIED: session reads]
- Greptile repository index and gateway-service document were read after discovering repository namespace. They are synthesized/untrusted orientation and contain approximate/outdated path/line claims; source reads, not those claims, ground this artifact. [VERIFIED: session MCP results]

### Official/primary external sources read

- Solana transaction structure, Memo program, Compute Budget, getGenesisHash, getLatestBlockhash, sendTransaction, getSignatureStatuses, getTransaction, signing guidance and official faucet guide. [CITED: URLs above]
- Cryptography Ed25519 interface; solders official transaction docs and PyPI candidate metadata. [CITED: URLs above]
- SQLite atomic commit and synchronous pragma documentation. [CITED: URLs above]
- Tomamichel et al.1103.4130 (2011, revised2012),1002.2436 (2010) primary papers, Shor/Preskill quant-ph/0003004 primary abstract, Ekert APS primary abstract (1991); Ekert PDF returned401, so exact original measurement-setting details were not verified from that PDF. IBM official CHSH tutorial cross-checks witness concepts. [CITED: URLs above]
- OWASP ASVS5.0.0 official project and source chapters V1/V4/V8/V11; actual chapter names discovered through its source directory listing. [CITED: URLs above]

### Actual commands (research/probes only)

All GSD commands used absolute worktree root `/tmp/desk-v51-audit` as cwd, not a service subdirectory. No product tests/builds/linters/smokes were run. No signer file was read. [VERIFIED: session tool invocations]

```text
node /root/.claude/gsd-core/bin/gsd-tools.cjs query init.phase-op 69
command -v solana solana-keygen ctx7 uv node
solana --version
solana transfer --help
/tmp/desk-v51-implementation/services/desk-gateway/.venv/bin/python -c "import importlib.util,importlib.metadata as m,sys,sqlite3; print('python',sys.version.split()[0]); print('sqlite',sqlite3.sqlite_version); print({n:(m.version(n) if importlib.util.find_spec(n) else 'not installed') for n in ('solders','solana','httpx','cryptography','pytest')})"
node /root/.claude/gsd-core/bin/gsd-tools.cjs query research-plan --input /tmp/desk-v51-qkd-research-input.json
node /root/.claude/gsd-core/bin/gsd-tools.cjs query classify-confidence --provider webfetch --verified
node /root/.claude/gsd-core/bin/gsd-tools.cjs query classify-confidence --provider context7 --verified
node /root/.claude/gsd-core/bin/gsd-tools.cjs query classify-confidence --provider official --verified
node /root/.claude/gsd-core/bin/gsd-tools.cjs query classify-confidence --provider ref --verified
node /root/.claude/gsd-core/bin/gsd-tools.cjs query classify-confidence --provider codebase --verified
node /root/.claude/gsd-core/bin/gsd-tools.cjs query package-legitimacy check --ecosystem pypi solders
uv pip index versions solders                       # failed: unsupported subcommand; no install
python3 -m pip index versions solders              # success: registry version listing only
node /root/.claude/gsd-core/bin/gsd-tools.cjs query research-store put b0870ec7f7a95420736230bf5db45b0f60fea81a6c507b1c11eeb405b91b6a6d --content <digest abbreviated> --source curated --provider webfetch --confidence LOW --kind docs
node /root/.claude/gsd-core/bin/gsd-tools.cjs query research-store put 3cf5036e37e4b1ca3b12e3c89025c68d264eb935b0854b2442394ff4e396f24f --content <digest abbreviated> --source curated --provider webfetch --confidence LOW --kind web
node /root/.claude/gsd-core/bin/gsd-tools.cjs query research-store put 65036da3a8dc4684902c3e9b7f757126e07f4281f0c4cf7001041ed035b467be --content <digest abbreviated> --source curated --provider webfetch --confidence LOW --kind docs
```

The cache commands above abbreviate only their digest text. The search skill's script was also invoked and returned HTTP402, without search evidence; its executable path is not restated here. These probes used the installed service interpreter explicitly. Parent's independent decode used that same environment; a `uv run` at repository root is not a probe of the installed gateway environment. Proposed uv test commands must run in `/tmp/desk-v51-implementation/services/desk-gateway`, while GSD commands remain at `/tmp/desk-v51-audit`. [VERIFIED: session commands and Main runtime clarification]

Research-plan selected Context7 for Solana/SQLite and websearch for protocol literature; neither selected provider was directly available here. ctx7 discovery failed to find an executable and Parallel search failed402; official direct read was the reachable fallback. Actual classifier returned LOW for webfetch/official/codebase and MEDIUM for context7/ref. Since those MEDIUM providers were not used, this artifact keeps LOW overall rather than inventing HIGH or laundering confidence. Direct in-repo observations are still identified with explicit read citations/quotes; proposals remain assumed. Three source digests were cached using their real keys and LOW. [VERIFIED: session seam command outputs]

## Metadata

| Area | Confidence | Reason |
|---|---|---|
| Standard stack | LOW (classifier); directly observed versions | Installed metadata and official interfaces read, no package install/runtime signer validation. |
| Architecture/numerics | LOW | Clear project constraints and primary formulas; integration, witness/statistical policy and numerical proposals not implemented or independently reviewed here. |
| Persistence/publisher | LOW | Official contracts read; parent narrow dummy-Memo native decode/signature exercised; complete proof preflight/restart/live-chain acceptance still unobserved. |
| Pitfalls | LOW (classifier); source-grounded observations | Complete relevant class/test/route bodies read; no check was rerun to confirm user/parent-reported failures. |

**Research date:** 2026-10-09. **Recheck before execution:** current Devnet/resource funding, exact RPC readback and installed wire decoder; stable mathematical sources do not expire into a new acceptance model. No research commit is made because the assignment explicitly forbids commits. No completion, approval, merge-ready, archive or live-publication claim is made by this document. [VERIFIED: assignment; ASSUMED: recheck guidance]
