# Phase 69 — Interface Contract Detail (converged with PlanTeleport)

Status: planning detail; no product code changed here. Parent SDK contract (`local://v51-sdk-contract.md`) authoritative on conflicts.

## 1. Shared sink / receipt / proof (fixed contract, duck-typed)

Phase 68 keeps the sink duck-typed (no import of the phase-69 ledger module); phase 69-01 lands parallel against this contract. Ordering guarantee asserted by 68: commit-then-receipt, frozen-copy receipt.

- `await append_event(event: Mapping) -> FrozenReceipt` — the ONLY append path.
  - `FrozenReceipt`: `receipt_id: str`, `seq: int`, `leaf_digest_hex: str`, `tree_size: int`, `prefix_root_hex: str`. Frozen copy, never a mutable internal reference.
- `snapshot(tree_size: int | None = None) -> FrozenSnapshot` — `tree_size`, `root_hex: str`, `receipts: tuple` (immutable).
- `inclusion_proof(receipt_id: str, tree_size: int) -> InclusionProof` / `verify_proof(proof: Mapping) -> bool`.
  - `InclusionProof`: `version`, `leaf_index`, `tree_size`, `leaf_preimage_bytes: bytes` (canonical typed), `siblings: list[(direction, digest32)]`, `expected_root_hex`.
  - Direction derived deterministically from (index, width); duplicate-last odd rule bound to index/tree_size; rejects changed node/time/outcome/session/resource/index/size/leaf/sibling/direction/root.

## 2. Event namespace (reserved split) + anchor eligibility

- 68-owned only: `bell.*`, `teleport.*`, `swap.*`, `purify.*` (payloads: op/pair ids, endpoints, transitions, branch bits/probs, fidelity, outcome; no key material).
- 69-owned only: `qkd.started/estimated/reconciled/established/aborted/failed`, `drill.summary`, `anchor.prepared/submitted/confirmed/failed/unknown`.
- Rules: aborted sessions never emit `*.established`; every lifecycle/abort emits exactly once through the same sink.
- Eligibility: `qkd.aborted` samples have durability only — they anchor nothing and establish no eligibility. Anchor-eligible leaves are ONLY a successful teleport event or a successful numerical-drill-summary recorded BEFORE the chain step. A numerical-drill-summary is eligible only when every actual physical-simulator stage passed, including the clean establishment, the Eve run, and both-nodes-keyless withholding. Chain confirmation is a separate later event (`anchor.confirmed`) and never retro-justifies the summary (no circular claim); `all_passed` still requires that anchor confirmation.

## 3. Canonical hashing (69-owned ledger detail, 68 treats sink opaque)

- Ordinary (non-eligible) events: canonical deterministic UTF-8 JSON with sorted keys covering version, event_type, seq, event_id, session, actor/nodes, resources, time, outcome, typed payload; ban NaN/Infinity and ambiguous encodings. Leaf `SHA256(0x00 || canonical_event_bytes)`; branch `SHA256(0x01 || left || right)` on bytes, never hex-concat.
- Eligible events: the canonical LEAF PREIMAGE is the versioned compact binary `encode_execution_leaf` output (see section 4), and the leaf is `SHA256(0x00 || binary)` in the SAME durable Merkle tree with the same branch rule. The SAME-preimage binding: the complete original public event metadata JSON (version/type/seq/eventID/session/actor/nodes/resources/time/predecessor/outcome/typed numerical payload) is stored canonically AND SHA256-committed in the mandatory metadata/transcript-commitment field of the binary leaf, derived internally by the ledger — never caller-provided, never self-referential. The binary leaf ALSO directly carries the numeric outcome/correction/fidelity/error/key counts (never opaque hash-only). REST JSON is a projection only and never a second Merkle preimage.
- Replay recomputes the full metadata commitment AND the exact binary bytes/hash/checkpoint, so ANY metadata alteration fails verification. The Memo attestation carries THAT exact binary leaf, the full siblings, leaf_index/tree_size, and root. No raw keys or private blinds anywhere; predecessor stays committed inside the metadata.
- Versioned empty-root constant; 68 never second-encodes (REST JSON is a projection only).

## 4. Execution-leaf binary codec + attestation (69-owned)

- `encode_execution_leaf(summary: Mapping) -> bytes` / `decode_execution_leaf(bytes) -> Mapping`: model_version, seq/time, public session/resource/node-id digests, BSM/correction bits, fidelity/error/sample counts, outcome flags, transcript_commitment_hex (mandatory metadata commitment per section 3). No key bytes, prefixes, or signer material.
- Compact layout is <=191B for drill summaries (fits depth 16), ideally 150B (fits depth 17). Reference layout totalling 150B: fixed header (version 1B, type 1B, flags 2B, seq 8B, eventUUID 16B, full_metadata_commit 32B) = 60B; teleport payload (frame/BSM flags 1B, gate flags 1B, node count 1B, F64 fidelity-error) = 11B; drill extension (purif baseline/output/swap 3xF64 = 24B; clean sifted/test/errors 3xu32 + output u16 = 14B; Eve test/errors 2xu32 + basis 1B = 9B; aggregate-of-independent-node key commitment 32B). Precise per-field flags/encoding carry meaningful typed content; no padding bytes, no fake-event eligibility.
- Wire: ASCII `QTELEPORT1:` (11 bytes) + base64url(`u16 version`, `u64 tree_size`, `u64 leaf_index`, `root32`, `u16 leaf_len + leaf_bytes`, `u16 path_len + siblings32...`). Binary envelope is 2+8+8+32+2+leaf+2+32*pathlen. Full path, no truncation/subtree/root substitution, no tiny-tree substitution (proof tree_size must equal the frozen committed size), no padding. Plans prove the cap on a REAL depth-16 full-sibling proof with byte-measured Memo/packet and a verifying root, plus an over-cap full-path attestation rejected 413 before signing.
- Anchor-eligible only: teleport success or all-stages-passed numerical drill summary (per section 2). Memo UTF-8 bytes = attestation string; Memo <= 1021 B so the actual legacy wire (211 + memo) <= 1232 B.

## 5. Cross-phase object ownership (no concurrent shared-file writes)

- 68-01: `quantum_state.py` (+ `tests/test_quantum_state_kernel.py`). `BellStateType` stays in `quantum_teleportation.py` (wire values PHI_PLUS/PHI_MINUS/PSI_PLUS/PSI_MINUS unchanged); new `quantum_state.BellState` takes validated kind STRING, never imports `BellStateType`. No re-export shims.
- Pool sole lifecycle authority: `async create_pair/consume_pair/reserve`, sync snapshots, immutable resources, fidelity derived from stored 2q rho. QKD consumes pool resources via these only.
- 68-02: `quantum_node.py` / `quantum_transport.py` + teleportation cutover (+ `tests/test_quantum_node_transport.py`). Transport fixed methods: `reserve/apply_circuit/measure/stage_conditional_state/correct/transfer/release/inspect`. Receiver correct computes `x = m_x ^ frame_x`, `z = m_z ^ frame_z`, applies real X/Z to STAGED conditional rho (never original amplitudes).
- 68-03: `config.py` / `server.py` deltas + migrates `tests/test_quantum_teleportation*.py`.
- 69-01: `quantum_ledger.py` / `quantum_anchor.py` (+ `tests/test_quantum_ledger_anchor.py`), parallel-safe with 68-01.
- 69-02: `quantum_key.py` + engine sections + node QKD extensions (+ `tests/test_quantum_qkd_mesh.py`); depends 68-02 + 69-01.
- 69-03: drill cutover + shared lifespan graph + routes + `tests/test_quantum_teleportation_endpoints.py` + README; removes old ledger/exporter definitions, migrates all consumers, no shims.
- RNG: `random() -> float` callable injected; default `secrets.SystemRandom`; scripted/deterministic in tests only. No seed hunting or retry loops.

## 6. Commitments (parent DTO rule)

Per-node separately blinded commitments; public aggregate references the two independent receipts. No exchanged private blinding, no raw/unsalted key hashes, no key-prefix evidence.

## 7. Source audit note

- Specless fallback: `workflow.specless_probe_fallback` key not found in actual config-get; reference default ON applies (no config write performed).
- Assumption-delta: both phases detected false.
- Edge probes: 31 phase-68 / 38 phase-69 applicable, all unresolved; every req x category is an explicit `must_haves` criterion or flagged unresolved backstop in 69-01..03 fronts. No silent drops.
- Verify commands: parent probes actual paths/failure directions before checker; plan `verify` blocks carry absolute service cwd with explicit `fails_when`.

## 8. Parent boundary decisions (applied to 69-02/69-03 fronts)

- BB84 `bit_length` / E91 `pair_count` zero is valid internally and over REST: returns 200 status `aborted` with reason `insufficient_sample`, `qber` null when not estimated, no keys, no crash, no digest. This makes the original zero-IndexError regression plus CONTEXT short/empty safe-abort explicit and overrides the research zero-400 proposal. Negative/bool/string/excessive counts are invalid 400. No omitted sample reported as QBER zero.
- Parent LSP root refs resolved: whole call sets (Pool 11, Mesh 11, `final_shared_key_hex` 10, Ledger 8, Exporter 6) live only in quantum/teleportation, quantum_qkd_mesh, server, and root quantum tests; normal modules hold no other consumers. Clean relocation migrates exactly those files, no aliases.

## 9. Locked finite-key/leakage policy (parent-selected single split; checker flag resolved)

- ONE explicit conservative accounting, fixed BEFORE any session, never fit after results: EPS_PE=1e-9 (phase estimation), EPS_PA=1e-9 (privacy amplification), EPS_COR=2**-32 (correctness; the 32-bit verification tag L_tag32=32 is counted ONCE), EPS_W=1e-6 (witness/bucket bound). The total declared error budget is the bound sum. Per session: n = remaining undisclosed candidate bits after removing k disjoint complementary phase-test bits; mu=sqrt((n+k)/(n*k)*(k+1)/k*ln(4/EPS_PE)); q_upper=min(0.5,q_phase+mu) for entropy; H_est=n*(1-h(q_upper)); L_syndrome = actual syndrome bits, L_tag32 = 32 ONCE, L_branch = every public key-dependent ack/correction-count/verification/extraction-admission disclosure against explicit fixed upper bounds declared before allocation; H_after=H_est-L_syndrome-L_tag32-L_branch; ell_max=floor(H_after-2log2(1/EPS_PA)). There is NO whole-paper combined log term and NO second EPS_COR subtraction. Test samples are removed from n and counted once; independent public Toeplitz seeds leak no key bits. Verification tag and extraction use fresh independent Toeplitz seeds; byte-aligned ell=min(requested,256,ell_max) with ell>=128 or abort. This is an explicit trusted-device SIMULATOR numerical budget, not a production composable/DI security theorem; clean large sessions MUST establish (never always-abort). The exact QBER threshold is unchanged: 100*errors>11*count aborts.
- Parent COVERAGE.md (phase 69) is now the authoritative RPC scope: full official HTTP inventory with explicit method opt-outs; 8 INTEGRATE methods (getGenesisHash, getLatestBlockhash, getBalance, getFeeForMessage, sendTransaction, getSignatureStatuses, getTransaction, getBlockHeight). Exact fee null or insufficient balance fails before send; expiry observation never resubmits. This is the selected Memo scope, not a whole-wallet SDK.
