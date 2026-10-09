# Phase 69: QKD, Entangled State Ledger & Solana Devnet Anchoring — Context

**Gathered:** 2026-10-09
**Status:** Ready for planning; acceptance reopened by the milestone audit
**Source:** Autonomous milestone execution; explicit user decisions in this conversation

<domain>
## Phase Boundary

Implement and verify original REQ-QTELEPORT-006–011: numerical BB84/E91 preparation/measurement, sifting, sampled QBER, actual receiver reconciliation and entropy-limited privacy amplification; intercept-resend aborts; a durable append-only Merkle receipt ledger with Bell/session/key-root events and proofs; real signed Devnet publication; all required REST route families; and the complete cross-node drill.
</domain>

<decisions>
## Implementation Decisions

### Execution and publication contracts
- **D-69-01 — User selected “Faithful distributed simulator”.** Reuse phase 68 numerical Bell states and node ownership. No physical quantum-hardware or quantum-security claims.
- **D-69-02 — User selected “Approve SPL Memo publisher”.** This explicitly authorizes the standard existing SPL Memo program as the real Devnet publication alternative. Construct and sign a genuine transaction, submit to a verified Devnet RPC, and observe confirmation and matching on-chain memo content. A local hash, fabricated slot, mock response or pending transaction is not confirmation evidence.
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
</decisions>

<canonical_refs>
## Canonical References
- `.planning/REQUIREMENTS.md` — original REQ-QTELEPORT-006–011.
- `.planning/ROADMAP.md`, `.planning/v5.1-MILESTONE-AUDIT.md` — acceptance boundaries and observed false confirmation.
- `.planning/phases/68-inter-cluster-quantum-teleportation-protocol-entanglement-sw/68-CONTEXT.md` — selected quantum model and shared numerical/node contracts.
- `services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py` — current QKD, ledger, exporter and drill.
- `services/desk-gateway/src/desk_gateway/quantum_teleportation.py` — actual Bell/repeater/teleportation dependencies.
- `services/desk-gateway/src/desk_gateway/server.py` — current phase 69 routes, lines 6355–6399 at main 2229570.
- `services/desk-gateway/src/desk_gateway/config.py`, `store.py`, `audit.py` — auth/environment/private JSON-file persistence patterns.
- `ownership.yaml`, `docs/cross-bot-protocol.md`, `skills/verification-receipts/SKILL.md` — ownership, contracts and evidence.
</canonical_refs>

<code_context>
## Existing Code Insights
- Keep the existing public QKD/ledger/exporter/drill symbols when meaningful; migrate every changed caller with no compatibility aliases.
- Locked gateway environment installed successfully with `uv sync --locked --group dev` in `/tmp/desk-v51-implementation/services/desk-gateway`; Python 3.14.2.
- Parent actually queried `https://api.devnet.solana.com` with `getGenesisHash`: returned Devnet genesis `EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG`. This is connectivity/network identity only, not funding or publication proof.
- Product worktree/branch: `/tmp/desk-v51-implementation`, `bot-01-systems-backend/v5.1-faithful-simulator`, main 2229570. LEAD-owned phase artifacts stay in `/tmp/desk-v51-audit`; no root-checkout edits.
- Current ordinary REST serialization exposes `final_shared_key_hex`; clean cutover must remove this secret exposure and update consumers/tests/docs.
</code_context>

<specifics>
## Specific Ideas
The user approved real SPL Memo publication. Funds/signature/slot/on-chain payload must be observed, not inferred. A proper publisher with unavailable funding still leaves live-publication and full drill acceptance blocked; finish all other reachable work and report that exact prerequisite.
</specifics>

<deferred>
## Deferred Ideas
None. Real publication, secure key handling and original numerical acceptance are required. Other milestones' simulated exporters are outside this repair.
</deferred>
