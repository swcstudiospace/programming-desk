# Phase 68: Inter-Cluster Quantum Teleportation Protocol & Entanglement Swarm Routing — Research

**Researched:** 2026-10-09
**Domain:** Bounded quantum-state simulation, resource ownership, authenticated classical node transport
**Confidence:** LOW under the installed provider classifier for direct `webfetch`; official references and independently executed numerical evidence are distinguished below. This is not a product verification verdict.

<user_constraints>
## User Constraints (from CONTEXT.md)

The following decisions/discretion/deferred text is copied verbatim. [VERIFIED: 68-CONTEXT.md:14-28,57-59]

DATA_6b17f03a_START
### Execution model
- **D-01 — User selected “Faithful distributed simulator”.** Numerically validated joint-state evolution, explicit node ownership, and classical transport are required. Metadata-only Bell labels and direct amplitude copying are unacceptable. Physical quantum-hardware or quantum-security claims are excluded.
- Exercise separate simulator-node processes, not merely a single object with different node labels. A central joint-state simulator may retain correlations while remote node workers own allocations and apply received classical corrections. No cloning of the input amplitudes as the receiver reconstruction.
- Use the existing Python gateway and existing public phase symbols where they remain meaningful. Cut over every affected caller; no deprecated aliases or re-export shims.

### Acceptance and repository boundaries
- F >= 0.95 is the teleport success predicate. Consumption is single-use; invalid endpoints, repeated inputs, consumed resources, invalid amplitudes and exhausted capacities cannot yield green outcomes.
- Purification must model actual bilateral gates and measurement branches, including parity-rejection consumption. Routing must track physical-model fidelity, allocations and releases; it must not reuse a discarded pair on failure.
- Explicitly distinguish ideal state-vector results from noisy density-matrix results and from remote-process transport evidence.
- Work only on isolated feature worktrees and draft PRs. Independent review remains a blocker; no merge, auto-merge, force-push, branch deletion or milestone archive is authorized by these choices.

### Builder discretion
- Numerical representation, gate kernels, deterministic test RNG injection, node transport implementation, and precise validated request shapes: choose the smallest maintainable design satisfying the original criteria and existing gateway patterns.

### Deferred Ideas
None. Physical QPU/channel integration is not selected. Original milestone acceptance, security review and live Devnet publication are not deferred or waived.
DATA_6b17f03a_END
</user_constraints>

## Summary

Use a small, explicit stdlib numerical kernel for one through four qubits, with pure state vectors for ideal demonstrations and density matrices for noisy resources. Store each Bell resource's actual two-qubit density matrix; derive fidelity from it, never maintain an independently mutable scalar. Implement gate evolution and projective measurements for three-qubit teleportation, four-qubit swapping, and four-qubit BBPSSW bilateral distillation. These procedures are specified by the IBM teleportation tutorial and the original Bennett et al. purification paper; this session independently checked the branch algebra. [CITED: https://quantum.cloud.ibm.com/learning/en/courses/basics-of-quantum-information/entanglement-in-action/quantum-teleportation] [CITED: https://arxiv.org/html/quant-ph/9511027] [VERIFIED: numerical probes recorded in the research receipt, commands 2-3]

The existing source's direct reconstruction assignment and success predicate are literally `rec_alpha, rec_beta = alpha, beta` and `success=fidelity >= 0.85`; these are the behavior to replace, not compatibility constraints. Existing purification computes a success probability but ends with `return True, purified_pair, p_succ` without a measurement branch. Existing routing's rejection fallback is `hop_pairs.append(pair1)`. The milestone audit already observed the defects; this researcher did not rerun those diagnostics. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_teleportation.py:352-390,120-140,233-240] [VERIFIED: .planning/v5.1-MILESTONE-AUDIT.md:189-193,248-256]

**Primary recommendation — proposed implementation decision:** preserve the meaningful existing domain classes, add the missing numerical/session/correction types, give the pool sole lifecycle authority, and implement a fixed-message node transport behind the same async workflow API. Separate real workers must own allocations and actually apply corrections. Do not equate a locally correct numerical result, a transport acknowledgement, or an HTTP 200 with accepted distributed teleportation.

## Architectural Responsibility Map

All tier assignments below are proposed within builder discretion, not claims about existing implementation.

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Joint correlated state, gates, Born probabilities, partial traces | API/backend numerical registry | Node workers | Central registry represents correlations; workers authorize ownership and execute their local operations |
| Qubit allocations and capacity enforcement | Node worker processes | Backend pool coordinator | The process owning a node must refuse exhausted capacity, not trust labels in requests |
| Bell creation, distillation, swapping and single-use lifecycle | Backend pool/mesh | Node workers; durable ledger | One lifecycle authority prevents double use and owns transitions/events |
| Teleport input validation and session orchestration | Backend protocol | Sender, receiver workers | Sender measurement destroys input; receiver correction reconstructs conditional state |
| Classical correction delivery | Authenticated worker transport | Backend protocol | Bits must cross a real process boundary and produce a receiver-side gate effect |
| Public REST authorization and safe DTOs | Gateway backend | Existing settings/auth | No browser authority, no caller-supplied worker URLs or credentials |
| Pair/session receipt persistence | Phase 69 storage/ledger | Phase 68 event sink | Same pool/mesh/protocol emits lifecycle evidence; no private drill state |

<phase_requirements>
## Phase Requirements

Descriptions below are copied from the unchanged requirements. [VERIFIED: .planning/REQUIREMENTS.md:7-11]

DATA_c02fe681_START
| ID | Description | Research Support |
|---|---|---|
| REQ-QTELEPORT-001 | Bell State Generator & Entanglement Swarm Pair Distribution (`BellPairPool`, `BellState`, `QuantumStateVector`) generating and distributing maximally entangled Bell states (\(\lvert\Phi^+\rangle, \lvert\Phi^-\rangle, \lvert\Psi^+\rangle, \lvert\Psi^-\rangle\)) across distributed desk cluster nodes. | Actual Bell vectors/density matrices, marginal checks and worker-owned allocations |
| REQ-QTELEPORT-002 | Multi-Hop Quantum Repeater & Entanglement Swapping Engine (`QuantumRepeaterNode`, `EntanglementSwapper`, `QuantumRepeaterMesh`) performing Bell state measurements (BSM) across intermediary repeaters to extend entanglement reach with fidelity degradation tracking. | Four-qubit BSM, orientation handling, density-derived fidelity and allocation-transfer invariants |
| REQ-QTELEPORT-003 | Inter-Cluster Quantum Teleportation Protocol (`QuantumTeleportationProtocol`, `TeleportationSession`, `ClassicalCorrection`) executing 3-qubit joint state evolution, Bell measurement, classical 2-bit channel communication, and Pauli unitary reconstruction with fidelity verification (\(F \ge 0.95\)). | Exact measured branches, receiver gates, pure-target overlap and distributed correction evidence |
| REQ-QTELEPORT-004 | Purified Quantum Link Telemetry & Decoherence Evaluator (`EntanglementPurifier`, `PurificationProtocol`) applying 2-to-1 Deutsch/Bennett entanglement purification distillation rounds to filter channel noise. | BBPSSW bilateral CNOT/measurement, parity reject and explicit optional twirl |
| REQ-QTELEPORT-005 | Quantum Phase 68 REST API endpoints under `/v1/quantum/teleportation/*` and `/v1/quantum/repeater/*` in `services/desk-gateway/src/desk_gateway/server.py`. | Existing route cutover, selected pair consumption, fail-closed auth and runtime REST tests |
DATA_c02fe681_END

The Bell notation in the table is typeset equivalently; the exact requirement source uses `\(|\Phi^+\rangle, |\Phi^-\rangle, |\Psi^+\rangle, |\Psi^-\rangle\)`.
</phase_requirements>

## Project Constraints and Evidence Boundaries

- No root-level CLAUDE.md was returned by the discovery glob. This is an observation of that lookup, not a claim about every machine or projection. Existing AGENTS directives require ownership resolution, feature branch/draft PR only, no forbidden git operations, receipts for completion claims, authentic command/exit-code evidence, independent approval, Greptile blockers treated as blockers, and no secret output. [VERIFIED: AGENTS.md:24-73]
- Planning ownership is the exact manifest rule `pattern: ".planning/**"`, `owner: bot-00-programming-lead`. Research receipt ownership is `pattern: ".receipts/bot-00-programming-lead/**"`, `owner: bot-00-programming-lead`; later manifest rules were read before writing. [VERIFIED: ownership.yaml:397-432,216-233]
- The config explicitly contains `"nyquist_validation": true`, `"security_enforcement": true`, `"security_asvs_level": 1`, and `"commit_docs": true`. This advisory assignment explicitly forbids commits, overriding the config's ordinary research-commit behavior. Do not change config/runtime/agent installation. [VERIFIED: .planning/config.json:4-12,29-32] [CITED: assignment and parent execution layout]
- Parent execution layout restricts changes to isolated worktrees; product source remains SYSTEMS-owned, public shared contract files cannot be silently amended, signed approval is unavailable, and the parent owns integration/verification. This artifact contains proposed SDK contracts, not implementation or approval. [CITED: local://v51-execution-layout.md]
- No product tests, build, linter, deployment, worker drill, or physical-security experiment was run by this researcher. Only source reads, runtime/package metadata probes, GSD research queries/cache writes, and standalone mathematical snippets were exercised. [VERIFIED: research receipt command record]

## Standard Stack

Use the installed locked stack; no new external package or numerical framework is needed for the proposed bounded kernel.

| Component | Locked/observed version | Purpose | Evidence |
|---|---|---|---|
| Python stdlib complex, math, dataclasses, enum, secrets, asyncio | Runtime probe: 3.14.2; project requirement `requires-python = ">=3.11"` | Small numerical operations, immutable records, RNG and orchestration | [VERIFIED: services/desk-gateway/pyproject.toml:6; research receipt command 1] |
| HTTPX | `name = "httpx"`, `version = "0.28.1"`; source upload 2024-12-06 | Reused async worker client | [VERIFIED: services/desk-gateway/uv.lock:335-347] [CITED: https://www.python-httpx.org/async/] |
| Starlette | `name = "starlette"`, `version = "1.7.0"`; source upload 2026-09-23 | Worker ASGI app; gateway already uses its request/response layer | [VERIFIED: services/desk-gateway/uv.lock:1062-1072] |
| Uvicorn | `name = "uvicorn"`, `version = "0.54.0"`; source upload 2026-09-25 | One process per node in acceptance drill | [VERIFIED: services/desk-gateway/uv.lock:1129-1139] [CITED: https://raw.githubusercontent.com/encode/uvicorn/master/docs/settings.md] |
| pytest / pytest-asyncio | `name = "pytest"`, `version = "9.1.1"`; `name = "pytest-asyncio"`, `version = "1.4.0"` | Existing automated test infrastructure | [VERIFIED: services/desk-gateway/uv.lock:745-771] |

The service's explicit interpreter successfully read the installed versions of all five packages. The retrieved PyPI metadata reports the same HTTPX, Starlette and Uvicorn latest versions; preserve the lock rather than broaden scope into dependency upgrades. Registry data is not a new-package legitimacy verdict. [VERIFIED: research receipt command 1] [CITED: https://pypi.org/pypi/httpx/json] [CITED: https://pypi.org/pypi/starlette/json] [CITED: https://pypi.org/pypi/uvicorn/json]

**Installation recommendation:** none for numerical/transport implementation; use the existing service environment. Do not recommend a new quantum simulator, ndarray package, remote service, queue, or alternate ASGI framework for fixed 1–4-qubit operations.

### Package Legitimacy Audit

Not applicable: this research proposes no external package install. No package-legitimacy check was run and no `OK` verdict is asserted. If execution adds an external package, the planner must first perform the official-source discovery, correct-ecosystem registry and GSD legitimacy checks; an unverified name is not approved simply because PyPI returns metadata.

## Architecture Patterns

### System Architecture Diagram

Proposed data flow; the branches are acceptance-relevant, not optional scaffolding.

```text
Authenticated gateway caller
        |
        v
Typed bounded request + seat/resource authorization
        | invalid/unauthorized -> problem response; no allocation
        v
Pool/mesh reserve real registered-node allocations
        | capacity/transport failure -> fail closed; release or quarantine
        v
Central correlated numerical state (2, 3 or 4 qubits)
        |
        +-- distillation bilateral gates -> target measurements
        |       | parity reject -> retire BOTH inputs; no output
        |       ` parity accept -> retain reduced rho; transfer survivor leases
        |
        +-- swap repeater BSM -> collapse -> endpoint correction gates
        |       ` output pair rho; release repeater's measured leases
        |
        `-- teleport sender CNOT/H/BSM -> conditional receiver rho
                |
                v
         Fixed authenticated classical correction message
                |
                v
         Separate receiver worker applies X/Z to its owned rho
                | timeout/refusal/mismatch -> no success
                v
         Returned corrected rho committed to registry; overlap measured
                | F < .95 -> failed-fidelity session, resource still consumed
                ` F >= .95 and lifecycle/transport complete -> success
                |
                v
         Shared lifecycle/session event sink -> phase69 durable Merkle ledger
```

### Component Responsibilities and Cutover

Proposed responsibility map, using existing files as edit targets rather than introducing a second domain convention:

| Component | Responsibility |
|---|---|
| Existing quantum teleportation module | Numerical types and kernels; Bell-state construction; pair/pool lifecycle; mesh/swap/purify/teleport domain types |
| Small worker/transport module(s), if separation improves reviewability | Fixed message schema, node-local lease/state ownership, authenticated Starlette app, reused HTTPX client |
| Existing gateway config | Operator-provided node registrations/topology/endpoints/capacities and environment-variable names only |
| Existing gateway server | Authenticated REST adapters, one runtime dependency graph, consistent errors, selected-resource wiring |
| Existing QKD module | Consume actual measured pool resources; shared runtime drill; no private substitute pool |
| Existing numerical/API tests, plus process test if needed | Public behavior, transition, numerical invariants and genuine multi-process acceptance |
| Gateway README | Simulator limitations, operator configuration, startup/cleanup and reproducible parent verification commands |

The source consumers import `BellPairPool`, `BellStateType`, `EntangledBellPair`, `EntanglementPurifier`, `EntanglementSwapper`, `QuantumRepeaterMesh`, `QuantumTeleportationProtocol`; the gateway constructs one pool, mesh, protocol, QKD engine and ledger. Those are the actual existing dependency boundaries. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py:28-36; services/desk-gateway/src/desk_gateway/server.py:6255-6284]

### Proposed numerical representation and indexing contract

Use big-endian qubit order: tensor operands appear left-to-right and qubit zero is the leftmost bit. Index bit mask is `1 << (n_qubits - 1 - qubit)`. This is a proposed internal convention; IBM's tutorial writes its tensor factors in another order, so explicitly translate instead of copying its bit labels blindly. [CITED: https://quantum.cloud.ibm.com/learning/en/courses/basics-of-quantum-information/entanglement-in-action/quantum-teleportation]

- `QuantumStateVector`: immutable tuple of length 2^n with finite complex amplitudes; public one-qubit construction rejects zero/nonfinite vectors and normalizes finite nonzero inputs using scale-first normalization to avoid overflow. Constructors used for internal gates require unit norm within tolerance. Do not replace invalid input with the zero basis state.
- `QuantumDensityMatrix`: immutable tuple-of-tuples, at most 16 by 16. Build from normalized vectors or explicit nonnegative Bell mixtures; transformations preserve positivity by construction. Require finite entries, Hermiticity and unit trace. Reject external arbitrary matrices in public REST. Worker import needs only bounded one-qubit density validation (real nonnegative diagonal, trace one, conjugate symmetry and nonnegative determinant within tolerance); never accept an arbitrary 16x16 caller matrix.
- Density evolution is `U rho U†`; measurement probability is `Tr(P rho)`, normalized branch is `P rho P / p`, and subsystem reconstruction is partial trace, not amplitude extraction from an entangled vector. These are standard density-matrix operations. [CITED: https://quantum.cloud.ibm.com/learning/en/courses/general-formulation-of-quantum-information/density-matrices/density-matrix-basics] [CITED: https://arxiv.org/html/quant-ph/9511027]
- For state vectors, gate updates touch amplitude pairs and CNOT is a bit permutation; for density matrices apply a 2x2 gate on row blocks and its adjoint on column blocks, and permute both row/column indices for CNOT. This proposed kernel avoids constructing a dense full-system unitary or generic eigensolver for each operation.
- Bound a route/session to locally factorized operations; reduce after each swap. A long route must not create an exponentially growing joint tensor over every hop. Four qubits is sufficient for each swap/distillation step; three for teleportation. [VERIFIED: independently executed numerical probes, commands 2-3]

### Proposed shared SDK contract for phase69 and REST

Names below marked proposed are new interfaces, not claims that these definitions already exist. Preserve meaningful existing class names, adding the requirement's missing concrete types rather than aliases.

| Type / operation | Proposed contract | Consumer obligations |
|---|---|---|
| `QuantumStateVector.from_qubit(alpha, beta)` | Validated normalized 1-qubit state; `tensor(other)`, `apply_single(qubit, gate)`, `apply_cnot(control,target)`, `density()` | Pure kernels synchronous, immutable results; no zero/nonfinite fallback |
| `QuantumDensityMatrix` | `from_statevector`, `bell_mixture`, `tensor`, `apply_single`, `apply_cnot`, `branches_z(qubits)`, `measure_z(qubits,rng)`, `partial_trace(keep)`, `permute(order)`, `fidelity_pure(vector)`, `to_public_matrix()` | Measurement result includes bits, probability and collapsed state; qubit order and keep order explicit |
| `BellState` | Numerical descriptor: existing `BellStateType`, ideal vector, target Pauli frame `(x,z)` and density construction | Actual states, not replacement enum aliases; pure source demonstration separate from noisy channel state |
| `EntangledBellPair` | Pair ID, ordered endpoints, immutable actual two-qubit density, ideal target Bell frame, qubit lease IDs, lifecycle/operation owner; fidelity is derived | No independently writable scalar fidelity, no outsider-created unmanaged pair accepted as consumable resource |
| `BellPairPool` | Registered-resource authority: async `create_pair`, async `consume_pair`/operation reservation, synchronous lookup/read-only snapshots, event sink injection | Two-endpoint allocation succeeds before publication; consumes at most once; shared handles for QKD/teleport |
| `QuantumRepeaterMesh` | Startup `register_node`/link registration; async `establish_multi_hop_entanglement`; central state registry; optional `NodeTransport` | Register nodes before creation; route validates known edges/capacities; local and remote transport return same records |
| `EntanglementSwapper` / `EntanglementPurifier` | Async pool-mediated operations returning explicit branch records, output pair or no pair, actual probabilities/fidelity | Cannot mutate standalone dataclass objects and bypass pool/events/capacity; rejection is a completed physical operation |
| `PurificationProtocol` | Proposed concrete enum with one implemented member `BBPSSW`; purifier result identifies the protocol and accepted/rejected measured branch | No alias pretending DEJMPS was implemented; preserve the actual retained density and distinguish optional finite twirl |
| `ClassicalCorrection` | Session ID, resource/receiver qubit identity, two sender measurement bits, known Bell frame, explicit x/z correction bits | Receiver evaluates and applies gates; same bit-order convention in worker and coordinator |
| `TeleportationSession` / existing result DTO | Pair ID, source/target, measurement bits/probability, gate/correction evidence, receiver density, measured fidelity, success/reason, transport mode and worker acknowledgements | Success requires F >= .95 plus applied correction and valid consumed resource; mixed receiver not serialized as fictitious amplitudes |
| RNG dependency | Minimal `random() -> float` protocol, used only for Born/measurement/channel sampling; default `secrets.SystemRandom`, seeded/scripted RNG in tests | Sample actual cumulative probabilities; skip zero-probability branches; reject invalid RNG outputs; no independent random BSM bits |
| Lifecycle event sink | Async `append_event(event: public immutable record) -> receipt`; inject into the one pool/runtime; use a durable phase69 implementation | Payload includes operation/pair IDs, parent pairs, endpoints, allocation transitions, state commitment, branch bits/probabilities, fidelity, outcome; no key material or arbitrary request bodies |
| `NodeTransport` | Async fixed `reserve`, `apply_circuit`, `measure`, `stage_conditional_state`, `correct`, `transfer`, `release`, `inspect` methods | Local implementation for unit tests is not distributed evidence; remote implementation operator-configured and authenticated |

**Async boundary decision:** make state math synchronous and resource/protocol workflows uniformly async. Cut over server handlers, QKD engine/drill and tests together; do not call `asyncio.run` from an ASGI handler and do not retain a second legacy sync workflow. Async client lifetime belongs to app lifespan. HTTPX explicitly recommends an async client with async frameworks and a scoped reused client rather than per-loop construction. [CITED: https://www.python-httpx.org/async/]

**Phase69-specific dependency contract, proposed with peer research:** E91 consumes and measures actual Bell density states from the shared pool, with bases/rotations supported by `apply_single`; process pairs sequentially or in capacity-bounded batches. Worker-local QKD session stores hold local raw/reconciled/extracted bit material. Public DTOs and ledger contain bases, disclosed sample indices/bits, counted parity/syndrome leakage, verification tags, extraction seed, commitments and agreement booleans only. Expose narrowly scoped node-local key-use/consume operations, not a REST key-export fallback. The drill uses the same injected mesh/pool/transport/ledger as REST. This interface enables, but does not itself prove, phase69 reconciliation/CHSH/privacy-amplification acceptance. [CITED: coordinated ResearchQkdPublication research message, 2026-10-09]

## Numerical Procedures and Fidelity Formulas

### Bell construction and Werner noise

The existing enum's exact values are quoted below; keep these wire values unless all callers are deliberately cut over. [VERIFIED: services/desk-gateway/src/desk_gateway/quantum_teleportation.py:27-31]

DATA_94a71fde_START
```python
PHI_PLUS = "PHI_PLUS"    # (|00> + |11>) / sqrt(2)
PHI_MINUS = "PHI_MINUS"  # (|00> - |11>) / sqrt(2)
PSI_PLUS = "PSI_PLUS"    # (|01> + |10>) / sqrt(2)
PSI_MINUS = "PSI_MINUS"  # (|01> - |10>) / sqrt(2)
```
DATA_94a71fde_END

Under the proposed big-endian basis `(00,01,10,11)`, the four ideal vectors are `(1,0,0,1)/sqrt(2)`, `(1,0,0,-1)/sqrt(2)`, `(0,1,1,0)/sqrt(2)`, `(0,1,-1,0)/sqrt(2)`. Generate them by H on the first zero qubit and CNOT to the second, followed by a local Pauli frame: `(x,z)=(0,0),(0,1),(1,0),(1,1)` respectively. Global sign does not distinguish physical states. [CITED: https://arxiv.org/html/quant-ph/9511027] [VERIFIED: command 2 exhaustive Bell/frame branch probe]

Let `P_B = |B><B|` and `F_B` denote overlap with the requested ideal Bell state. Use the locally rotated Werner/isotropic resource

`rho_B(F_B) = F_B P_B + ((1-F_B)/3)(I_4-P_B)`.

For `F_B=1`, this is a maximally entangled pure Bell pair; for `F_B<1`, it is a noisy mixed resource, not a claim that it is maximally entangled. Fidelity input is finite and in [0,1]; reject out-of-range instead of clipping. Both local marginal density matrices are I/2. In the equal-mixture case F_B=1/4, the resource is I_4/4; a fidelity floor of .50 would misreport it. Werner weights and overlap definition appear explicitly in the primary paper. [CITED: https://arxiv.org/html/quant-ph/9511027, equations (2) and (4)] [VERIFIED: command 2 mixed-state swap probe]

### True three-qubit teleportation

Proposed order is `(input, sender-half, receiver-half)`; initial state is `|psi><psi| tensor rho_pair`, with endpoint permutation when a selected pair is reversed. Apply CNOT(0→1), H(0), measure qubits (0,1), record `(m_z,m_x)`. Use the actual normalized branch and partial trace to keep qubit 2. Receiver applies X when `m_x xor frame_x` is one, then Z when `m_z xor frame_z` is one. Gate order differences in the both-one branch produce only global phase for ideal pure states, but fix one convention in implementation/tests. [CITED: https://quantum.cloud.ibm.com/learning/en/courses/basics-of-quantum-information/entanglement-in-action/quantum-teleportation] [VERIFIED: command 2 all-Bell teleport probe]

Compute **actual receiver fidelity** as `F_teleport = Re(<psi|rho_receiver|psi>)`; ideal pure comparison is `abs(<psi|psi_receiver>)**2`. Never report Bell-pair fidelity as the receiver fidelity. A noisy receiver is generally mixed and has no unique reconstructed amplitude vector. The fidelity convention here is squared overlap, not its square root. [CITED: https://arxiv.org/html/quant-ph/9511027, equation (2)] [VERIFIED: command 2 density-overlap probe]

For the specified Werner resource with ideal local operations and correct frame, the channel is

`rho_out = F_B rho_in + ((1-F_B)/3)(X rho_in X + Y rho_in Y + Z rho_in Z)`,

so for any normalized pure input `F_teleport=(2 F_B+1)/3`. Therefore the required .95 output threshold corresponds to `F_B >= .925` **only for this noise model**. For Bell-diagonal, untwirled or otherwise anisotropic noise, compute the overlap numerically; do not apply this scalar shortcut. Probe values: pair .99 → output .993333333333; pair .90 → output .933333333333; pair .25 → output .5. [VERIFIED: command 2 mathematical probe, independently evolved density branches] [CITED: https://quantum.cloud.ibm.com/learning/en/courses/basics-of-quantum-information/entanglement-in-action/quantum-teleportation]

Boundary policy is a proposed numerical decision: allow at most a documented floating-point tolerance such as 1e-12 in the acceptance comparison, report the uncloaked computed fidelity, and test a just-below value separated by much more than that tolerance. The mathematical .925 boundary produced .9499999999999997 in the probe. This is not permission to lower the .95 criterion or round six-place output before comparing. [VERIFIED: command 2 output]

### True four-qubit swapping

Proposed joint order is `(A, B_left, B_right, C)`. Require two distinct active registered resources sharing exactly one endpoint and having distinct outer endpoints; permute reversed source pairs into this order. Apply CNOT(1→2), H(1), measure (1,2), retain endpoints (0,3) by partial trace, and perform actual correction gates at an outer worker. For input Bell frames `(x1,z1),(x2,z2)`, correction bits to canonicalize output to Phi+ are `(m_x xor x1 xor x2, m_z xor z1 xor z2)`. All 16 Bell-pair combinations and all four BSM outcomes were checked independently. [VERIFIED: command 2 exhaustive 64-branch swap probe]

For Werner inputs and perfect operations, derive, rather than assert by metadata multiplication,

`F_swap = F_1 F_2 + ((1-F_1)(1-F_2))/3`.

Equivalently `p_i=(4F_i-1)/3`, `p_swap=p_1 p_2`, `F_swap=(1+3p_swap)/4`. Do not clamp at .50 or .999. Probe examples: .98/.98 → .960533333333; .25/.25 → .25; .99/.99 → .980133333333. These formulas are an independently substantiated model-specific oracle, not a substitute for BSM and retained-state computation. [VERIFIED: command 2 density evolution and formula assertions]

**Proposed BSM/classical-error model:** retain an existing error-rate parameter only if it gains an explicit channel meaning. Define probability `e` that the delivered correction is wrong, uniformly among its three nonzero two-bit masks; apply the corresponding actual Pauli channel on the surviving endpoint. For canonical Werner output, `F_after=(1-e)F_swap+e(1-F_swap)/3`. Alternatively choose a different documented channel and test it; the existing `F_ab*F_bc*(1-e)` is not the above physical-model fidelity. This proposed extension was not exercised by the mathematical probe; enumerate its Kraus/Pauli branches during implementation validation. No unrequested retries or independent loss model are needed.

### True two-to-one BBPSSW purification

Choose BBPSSW, not both BBPSSW and DEJMPS: the original requirement allows Bennett/Deutsch purification and BBPSSW is the smallest circuit matching the existing recurrence formula. Canonicalize both input target frames to Phi+ with real local gates; use joint order `(A_keep,B_keep,A_target,B_target)`. Apply bilateral CNOT(0→2) and CNOT(1→3), measure target qubits (2,3) separately, communicate/compare the bits, and retain (0,1) **only when bits agree**. Both original pair resources are retired after any measured outcome. Accepted output transfers the surviving physical leases to a new pair ID; rejected output releases all four leases. [CITED: https://arxiv.org/html/quant-ph/9511027, steps A1-A3] [VERIFIED: command 2 four-qubit measurement probe]

For two canonical Werner inputs, with `a=(1-F1)/3`, `b=(1-F2)/3`,

`P_accept = (F1+a)(F2+b)+4ab = F1F2 + F1(1-F2)/3 + (1-F1)F2/3 + 5(1-F1)(1-F2)/9`,

`F_accepted = (F1F2+ab)/P_accept`.

Measure the evolved density state to choose an actual branch. Report both the branch probability and total theoretical acceptance probability. No always-success result, success-probability floor, or fidelity cap is justified. The primary paper supplies the equal-input recurrence; this session verified the unequal-input generalization by all four actual density branches. [CITED: https://arxiv.org/html/quant-ph/9511027, equation (7)] [VERIFIED: command 2]

Concrete independently observed oracles:

| F1 / F2 | P_accept | F_accepted | P(00)=P(11) | P(01)=P(10), rejected |
|---|---:|---:|---:|---:|
| .90 / .92 | .887111111111 | .934368737475 | .443555555556 | .056444444444 |
| .91 / .93 | .898933333333 | .942227825571 | .449466666667 | .050533333333 |
| .50 / .50 | .555555555556 | .50 | .277777777778 | .222222222222 |
| .40 / .40 | .52 | .384615384615 | .26 | .24 |
| 1 / 1 | 1 | 1 | .50 | 0 |

[VERIFIED: command 2 output]

Improvement is not unconditional: equal Werner inputs improve for .5 < F < 1 under the recurrence; .4 degrades and .5 is a fixed point. With unequal inputs the output is not guaranteed to exceed the better input. The useful acceptance claim is demonstrated noise filtering in its documented domain, not "every pair becomes better." [CITED: https://arxiv.org/html/quant-ph/9511027] [VERIFIED: command 2 boundary probes]

**Important retained-state pitfall:** successful bilateral CNOT without twirling does **not** return a Werner state. At .90/.92 the retained Bell weights (Phi+,Phi-,Psi+,Psi-) are approximately `(.934368737475,.061623246493,.002004008016,.002004008016)`. Keep that density matrix for later operations; do not silently replace it with `rho_B(F_accepted)`. [VERIFIED: command 2 output]

**Proposed explicit recurrent BBPSSW twirl:** when an isotropic output is desired, perform the legitimate ensemble channel `average_U [(U tensor U*) rho (U tensor U*)†]` with six single-qubit Clifford representatives `I,H,S,HS,SH,HSH`, where `S=diag(1,i)`. These six fix Phi+ and permute the other three Bell states in all six ways; they suffice for the Bell-diagonal input/output family here, not arbitrary-state full twirling. The independent twirl probe produced equal error weights .02187708750835 while preserving .93436873747495 target overlap. This is a defined local-unitary ensemble channel, not scalar reconstruction; distinguish ensemble averaging from a sampled trajectory. To twirl a different Bell target, first canonicalize its frame and restore it after the channel if preserving that label. [VERIFIED: command 3 finite-channel probe] [CITED: https://arxiv.org/html/quant-ph/9511027, step A3]

## Resource, Endpoint and Capacity Invariants

The rules below are proposed acceptance-critical contracts. The audit already requires endpoint/resource/capacity repair. [VERIFIED: .planning/v5.1-MILESTONE-AUDIT.md:189-193]

1. **Registered identity and topology:** require nonempty distinct known endpoints; node registration is startup/operator configuration, not implicit allocation by public requests. Reject duplicate registration that would reset active counts. Use explicit undirected allowed links. A path has at least two nodes, no repeats, only registered nodes/links, and a proposed upper bound of 16 nodes; longer routes do not bypass bounds by concatenating intermediate lists.
2. **Managed identities:** every consumed pair must be the authoritative pool resource, not a forged same-ID dataclass. Purification/swap inputs are distinct IDs/leases and distinct objects. Purification requires equal unordered endpoint sets and compatible frames after real gate canonicalization. Swapping requires exactly one shared repeater and two distinct outer nodes. Teleport source/target must equal the selected pair's endpoint set in either orientation.
3. **Atomic reservation:** reserve all required logical inputs and node leases before the first gate; concurrent callers cannot both win. Read-only getters must not hand out mutable state that lets a caller unconsume a pair. Proposed lifecycle states are active, reserved, consumed, discarded, quarantined; these are new contract values, not existing enum claims.
4. **Physical counts:** each active pair holds one physical qubit at each endpoint. Swapping requires two distinct local qubits at the repeater; endpoints retain one each. Purification requires two qubits per endpoint, then retains one per endpoint on acceptance or zero on rejection. Teleport source needs its half plus the input qubit (two local slots), target needs its half (one). The receiver output remains a real owned lease until explicitly released or transferred; do not report all capacities free while holding an output.
5. **Transfer, not reallocate:** output pair IDs can be new while outer/surviving physical leases persist. Perform an atomic lease transfer from retired input resource to output, avoiding temporary double counting and fictitious free/reallocate cycles. Measured qubits release once. Never count output plus its retired inputs as simultaneously active.
6. **Failure cleanup:** before any irreversible operation, failed allocation releases all successfully reserved new leases and preserves existing untouched pair inputs. After gates/measurements start, fail closed and retire/discard affected inputs; never resurrect them or fall back to a consumed pair. Transport ambiguity quarantines affected leases/resources, exposes a failure, and requires bounded operator reconciliation; no automatic retry-until-green.
7. **Pool closure:** intermediate, purified and swapped output resources are always registered, and every retired pair is visible in lifecycle history. Routing aborts on purification rejection; it does not reuse either input. Session/resource/event commits must not report success before all relevant acknowledgements and durable event appends succeed.
8. **Numerical requests:** validate JSON type, finite real/imaginary parts, nonzero vector, enum values, [0,1] fidelity/error rates, booleans as booleans, bounded lists/counts, and no unknown URL/credential fields. Reject malformed data, never substitute a requested unknown Bell label with the default label.

## Proposed Distributed Worker Protocol

Use separate worker processes with node identity, process instance identity, configured capacity and private lease/state dictionaries. Keep the correlated joint-state registry central; workers maintain ownership and actually run their local gate kernels. A worker is not allowed to claim a qubit belonging to another node. Every worker command names a bounded operation ID, expected node/instance, resource/session ID and specific owned leases.

### Fixed messages

All message names/fields/limits here are proposed internal SDK values, not existing wire enums.

| Message | Bounded input | Observable effect / output |
|---|---|---|
| reserve | Operation/resource IDs <=128 characters; node ID <=64; count 1–4; capacity fixed at startup | Actual worker lease IDs and active count; refuse over capacity |
| apply_circuit | One to four owned lease IDs; at most eight allowlisted H/S/X/Z/CNOT or fixed-parameter validated rotation operations | Worker validates ownership and gates; for central correlated operations returns local gate authorization/transcript rather than inventing an independent entangled state |
| measure | Owned local leases, agreed basis/circuit; measured bits from the shared joint-state measurement record | Worker destroys/measures owned leases; returns operation-bound acknowledgement, not random independent replacement bits |
| stage_conditional_state | One owned receiver lease, 2x2 density with four finite complex entries, session ID | Imports the **computed post-BSM conditional receiver state**, not the original alpha/beta |
| correct | Same session/lease; exactly two measured bits and known Bell-frame bits | Receiver computes correction bits and applies local X/Z gates to its staged conditional state; returns corrected rho and gate evidence |
| transfer / release | Existing leases and old/new resource IDs; no caller-controlled allocation count | Resource binding changes or leases retired exactly once; updated actual active count |
| inspect | Authenticated node/session/resource-scoped request | Identity, instance, capacity, lease/count/operation evidence; no raw private QKD bits/keys |
| QKD node operations | Session-bounded state preparation/basis measurement, parity/sample/verification/extraction messages and scoped key-use/consume | Local Alice/Bob derived material stays private; only required public classical transcript leaves worker |

Proposed transport bounds: request/response bodies <=64 KiB, no arbitrary matrices larger than one-qubit receiver state on the worker correction endpoint, session/operation replay memory bounded by capacity/outstanding operation count, route length <=16, circuit length <=8, request concurrency bounded, and no unlimited batch from a REST request. A full E91 workload streams pair consumption so finite capacity remains meaningful. Same operation ID with a different payload is rejected; a duplicate correction cannot apply X/Z a second time. No automatic network retry is proposed.

Endpoints are resolved from operator-configured node ID → exact base URL mapping; requests specify node IDs, not URLs. Do not expose callback URL, RPC URL, HTTP method, path, headers or bearer-token overrides in the quantum APIs. Disable redirects and environment proxy inheritance; reuse an AsyncClient with explicit connect/read/write/pool limits and an overall orchestration deadline. Read timeout alone is not a total deadline. HTTPX documents scoped clients, `trust_env=False`, and the separate timeout kinds. [CITED: https://www.python-httpx.org/async/] [CITED: https://www.python-httpx.org/environment_variables/] [CITED: https://www.python-httpx.org/advanced/timeouts/]

Use existing seat-passphrase authorization for the gateway's public quantum routes. The exact existing source pattern is `seat = settings.seat_for_passphrase(token)` followed by a seat allowlist `{"lead", "infra", "systems"}` on a mutating operator route; settings use `secrets.compare_digest(passphrase.encode(), expected.encode())`. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:1986-1999; services/desk-gateway/src/desk_gateway/config.py:147-155]

**Proposed least-privilege policy:** public pair mutations/routing/teleport/drill require lead or systems; operator configuration requires lead; read/proof inspection may allow any authenticated seat subject to resource scope. Distinguish absent/invalid credentials (401) from valid unauthorized role (403). Node worker credentials are independently operator-configured and scoped to coordinator/node commands, never supplied by public caller. Loopback plaintext is limited to the local process drill; non-loopback transport requires verified TLS and must not rely on network location alone. These are proposed policy choices for parent/security review, not existing authorization guarantees.

Distributed evidence must show distinct worker PIDs/instance IDs and independently observed lease counts, sender/repeater measurement acknowledgements, a delivered two-bit correction, receiver-side X/Z gate transcript, changed conditional-versus-corrected rho on a nonidentity branch, and cleanup. Public simulation snapshots may contain density matrices, but receiver correction messages must not contain original input amplitudes. A central numerical registry can of course know the simulation input; this design is a trusted-coordinator simulation, not a physically secure quantum communication implementation.

## REST Cutover and Error Semantics

Exact existing route declarations are quoted for provenance. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:6286-6329]

DATA_03b88ea1_START
```python
@mcp.custom_route("/v1/quantum/teleportation/bell-pair/create", methods=["POST"])
@mcp.custom_route("/v1/quantum/teleportation/purify", methods=["POST"])
@mcp.custom_route("/v1/quantum/repeater/route", methods=["POST"])
@mcp.custom_route("/v1/quantum/teleportation/teleport", methods=["POST"])
```
DATA_03b88ea1_END

Proposed cutover: retain these route families, add validated `bell_pair_id` selection to teleport, and use the exact pool resource returned by create/purify/route. Reject supplying both a selected pair and a request for new intermediate hops; do not create a hidden replacement pair if the selected one is invalid. Missing selected ID is a documented explicit allocation mode, not a fallback on lookup failure. Every handler uses the same injected runtime and event sink.

Use the existing problem-response convention for errors, not raw exceptions or fabricated success. Proposed mapping: malformed/invalid request 400; missing resource 404; endpoint/consumed/reservation/capacity conflict 409; worker transport not available 503; deadline 504. Purification parity rejection is a successfully executed probabilistic protocol with `ok:false`, no output resource, both inputs retired, and branch/probability evidence; return a documented domain-result response rather than treating it as malformed JSON. Below-threshold teleport returns an executed session with `success:false`, measured fidelity and consumed pair, not top-level green success. Do not require incidental exact prose in tests.

## Don't Hand-Roll

| Problem | Do not build | Use instead |
|---|---|---|
| HTTP retries/connection pooling/TLS/proxy handling | Raw sockets or homemade client | Existing HTTPX with fixed destinations and explicit bounds |
| Authenticated API responses | Parallel ad hoc auth/password scheme for gateway seats | Existing settings resolver and problem-response pattern |
| Secure entropy | Custom pseudorandom production generator | Existing stdlib secrets/SystemRandom; injectable deterministic test RNG |
| Durable phase69 receipts | Second in-memory ledger in phase68 or private drill | Inject the shared phase69 durable event sink |
| Fixed quantum operations | Full language/compiler/graph simulator or heavy dependency stack | Explicit 1–4-qubit stdlib kernels backed by branch oracles |
| Noise filtering | Scalar fidelity bump or hidden re-Wernerization | Actual BBPSSW gates/projective branches; explicit finite twirl channel if selected |

These are proposed implementation restrictions. A tiny numerical kernel is intentionally in scope; correctness comes from its explicit bounded operations and independent numerical tests, not from pretending a package name makes it faithful.

## Common Pitfalls

- **Lost phase/frame:** only testing plus superposition lets missing phase corrections look correct. Test zero/one, plus/minus, plus-i/minus-i and asymmetric complex inputs; all Bell frames and all measurement branches. IBM explicitly analyzes the differing Pauli corrections. [CITED: IBM teleportation tutorial above]
- **Bit-order mismatch:** IBM tutorial's measured `(a,b)` order differs from the proposed `(m_z,m_x)`. Freeze basis/qubit/bit order before parallel consumers implement. [CITED: IBM teleportation tutorial above]
- **Fake noisy amplitudes:** a mixed rho has no single pure amplitude pair; serialize density and purity honestly. IBM defines pure states as rank-one density matrices and explains mixed states. [CITED: IBM density-matrix basics above]
- **Scalar shortcuts propagate wrong states:** untwirled purification loses isotropy, then Werner teleport/swap formulas cease to describe every input. Retain rho or apply an explicitly modelled twirl. [VERIFIED: numerical probes 2-3]
- **Resource inflation:** two identical inputs, reused consumed pairs, unregistered nodes or new output allocations hiding transfers violate ownership. Assert lifecycle and capacity, not only fidelity. The audit already identified these missing invariants. [VERIFIED: .planning/v5.1-MILESTONE-AUDIT.md:189-193]
- **Stochastic success pinned by tests:** valid noisy purification has rejection branches. Deterministically select each branch through RNG injection; a deterministic successful acceptance drill does not erase separate rejection tests. [VERIFIED: numerical probe 2]
- **HTTP 200 mistaken for success:** check protocol outcome, fidelity, correction ack and receipt, not only transport status. Proposed acceptance rule.
- **Network evidence replaced by mock:** HTTPX ASGI/TestClient transport is useful for endpoint contract tests, but it does not exercise separate real node processes. Proposed validation distinction.
- **Model portability mistaken for proof:** installed metadata and an imported package are environment observations, not evidence the distributed simulator or Python 3.11 minimum works. Parent runs tests with the explicit service interpreter and verifies compatibility separately if required.

## Existing Tests Requiring Semantic Updates

Source was read; none of these tests was executed here.

- Lifecycle tests pin `pair.pair_id.startswith("bell-")` and exact float `pair.fidelity == 0.98`; use opaque identity/lookup/single-consumption and approximate density-derived overlap instead. Keep the repeated-consumption negative invariant. [VERIFIED: tests/test_quantum_teleportation.py:17-35]
- Purification tests construct unmanaged pair dataclasses and assert `ok is True`; noisy success must use a deterministic acceptance branch, with a distinct rejection case. The existing .90/.92 example does improve beyond .92 on an accepted branch, but that is a fixture-specific oracle, not a universal distillation property. [VERIFIED: tests/test_quantum_teleportation.py:38-49; numerical probe 2]
- Swapping tests should retain endpoint/consumption behavior but add actual rho/branch checks and every orientation; scalar `fidelity > 0.90` alone cannot prove BSM. [VERIFIED: tests/test_quantum_teleportation.py:52-63]
- Multi-hop test assumes all purification succeeds, pins `len(logs) >= 3`, and asserts `swapped.fidelity > 0.85`; replace incidental log count with lifecycle/capacity/branch evidence and use required receiver fidelity at the actual teleport boundary. Do not keep .85 as an acceptance threshold. [VERIFIED: tests/test_quantum_teleportation.py:66-81]
- Teleport tests omit node registration and cover only alpha=beta real. The literal `pauli_correction in ["I", "X", "Z", "XZ"]` and `session_id.startswith("teleport-")` are incidental representation checks; test actual correction gates, overlap, receiver density, process evidence and single-use resource. [VERIFIED: tests/test_quantum_teleportation.py:84-104]
- API fixtures use `build_app()` without authenticated headers or registered node config. Update fixtures to injected settings/runtime/auth, deterministic RNG and explicit nodes; add unauthenticated/wrong-seat tests. REST purification/routing/teleport currently assume stochastic success. [VERIFIED: tests/test_quantum_teleportation_endpoints.py:9-71]
- Existing endpoint anchor/drill test asserts a local `"confirmed"` status and `all_passed is True`; it is not a live publication proof and belongs in phase69's repair. Never let it validate invented chain data. [VERIFIED: tests/test_quantum_teleportation_endpoints.py:100-111] [VERIFIED: .planning/v5.1-MILESTONE-AUDIT.md:197-199]

## Code Examples

The following is proposed workflow pseudocode against the shared SDK above, not existing exported source or product implementation. Official operation order was read and its density evolution was independently exercised.

```python
# Proposed synchronous math; big-endian (input, sender, receiver).
rho_joint = input_state.density().tensor(oriented_pair.density)
rho_joint = rho_joint.apply_cnot(0, 1).apply_single(0, H)
measurement = rho_joint.measure_z((0, 1), rng)
rho_receiver_before = measurement.state.partial_trace((2,))
# Send derived conditional state, never original alpha/beta, to its owning worker.
await transport.stage_conditional_state(receiver_lease, session_id, rho_receiver_before)
ack = await transport.correct(receiver_lease, correction)
rho_receiver_after = ack.corrected_density
fidelity = rho_receiver_after.fidelity_pure(input_state)
# Commit lifecycle + event evidence; success also requires acknowledged correction.
```

```python
# Proposed BBPSSW branch logic, (A_keep,B_keep,A_target,B_target).
joint = canonical_pair_1.density.tensor(canonical_pair_2.density)
joint = joint.apply_cnot(0, 2).apply_cnot(1, 3)
branch = joint.measure_z((2, 3), rng)
accepted = branch.bits[0] == branch.bits[1]
# Always retire both logical input resources after measured execution.
# On acceptance transfer kept leases and retain partial_trace((0,1)).
# On rejection release all leases; return no output pair.
```

[CITED: IBM teleportation tutorial and BBPSSW paper above] [VERIFIED: numerical probes 2-3] All new method/field names in these examples are proposed, not source-verified enum/status values.

## Runtime State Inventory

This is a behavioral refactor, so all five categories are answered explicitly. Research is repo-scoped; no assertion of absence in live machines/services is made.

| Category | Observed items / evidence | Proposed action |
|---|---|---|
| Stored data | Source pool/session maps are in-memory: `self.pairs: Dict[str, EntangledBellPair] = {}`, `self.sessions: Dict[str, TeleportationResult] = {}`. [VERIFIED: quantum_teleportation.py:59-60,309-311] Live stored historical data was not inspected. | Restart invalidates old simulator allocations; phase69 durable public event history must preserve/mark historical unverified records rather than retroactively claim valid proof. Do not restore active quantum resources just by replaying receipt labels. |
| Live service config | Gateway constructs local pool/mesh objects; current operational node configuration outside git was not inspected. [VERIFIED: server.py:6272-6284] | Add operator-controlled worker/topology settings; document restart/cutover. Parent must inspect deployment target config; no "none found" claim. |
| OS-registered state | Node workers do not yet have research-observed service registrations. No systemd/pm2/OS inventory was run. | For the selected drill, start temporary separate subprocesses and stop/reap them; production service registration belongs to later approved operations, not inferred from files. |
| Secrets / env vars | Settings read the exact environment-name expression `SEAT_PASSPHRASE_{seat.upper()}`. No secret values were opened. [VERIFIED: config.py:170-173] | Keep existing seat variable names; operator adds independently scoped worker credential variables without printing values. No secret-value migration inferred. |
| Build artifacts / installed packages | Explicit service interpreter imported locked stack successfully; no product binary/package rename is proposed. [VERIFIED: research receipt command 1] | No new package required; restart actual gateway/workers after deployment. Runtime import success is not product acceptance. |

## Environment Availability

| Dependency | Observation | Version | Fallback / action |
|---|---|---|---|
| Explicit gateway interpreter | Available; metadata imports succeeded | 3.14.2 | Use this service interpreter, not root `uv run` |
| HTTPX / Starlette / Uvicorn | Available in that interpreter | .28.1 / 1.7.0 / .54.0 | Reuse; separately execute actual socket/process tests |
| pytest / pytest-asyncio | Metadata available | 9.1.1 / 1.4.0 | Parent runs actual suites; not run here |
| uv | Available | 0.11.26 | Use inside product service directory only, or explicit interpreter |
| GSD runtime | init resolved the audit worktree and phase; root cwd explicit | Parent supplied @opengsd/gsd-core 1.14.0 identity | All GSD commands at audit worktree root |
| Context7 MCP / ctx7 CLI | No mounted Context7 route observed; `command -v ctx7` exited 1 | — | Direct official-source reads used; no package auto-download |
| Actual registered simulator worker processes | Not launched or observed by this research | — | Must implement and execute separate workers; in-process labels are not fallback acceptance |

[VERIFIED: research command observations] No external QPU/quantum channel is required by the selected faithful simulator. Real worker runtime evidence remains unobserved, not "missing dependency" inferred from absent process inspection.

## Validation Architecture

### Test Framework

The service declares `asyncio_mode = "auto"` and `testpaths = ["tests"]`; root quantum tests are a different directory and must be named explicitly. [VERIFIED: services/desk-gateway/pyproject.toml:39-41]

| Property | Value |
|---|---|
| Framework | Existing pytest 9.1.1 / pytest-asyncio 1.4.0, installed metadata observed |
| Config | Existing service pyproject test configuration, quoted above |
| Quick command, proposed for parent | From product ROOT: `services/desk-gateway/.venv/bin/python -m pytest -q tests/test_quantum_teleportation.py` |
| REST command, proposed for parent | From product ROOT: `services/desk-gateway/.venv/bin/python -m pytest -q tests/test_quantum_teleportation_endpoints.py` |
| Full command, proposed for parent | From product ROOT: `services/desk-gateway/.venv/bin/python -m pytest -q tests services/desk-gateway/tests` |

These commands were not run; timings and compatibility are not promised. Any new process test file/name is a proposed Wave 0 addition, not claimed to exist.

### Phase Requirements → Test Map

| Requirement | Required behavior | Proposed automated coverage | Existing coverage observation |
|---|---|---|---|
| 001 | Four generated pure Bell vectors; norm, overlaps, marginals; actual allocated ownership | Parameterize existing numerical tests for all labels; process create/inspect evidence | Metadata lifecycle test read; no numerical/process assertions observed in it |
| 002 | 64 ideal swapping branches; reversed orientation; noisy rho; valid route/capacity/release | Existing numerical test target, plus bounded process route test | Existing scalar swap/route tests read |
| 003 | All Bell frames × all BSM branches × six axis states and general complex inputs; true receiver gates; .95 predicate | Existing numerical and API test targets; actual socket drill tests | Existing plus-only numerical test read |
| 004 | Distinct compatible inputs, four branch probabilities, accepted rho, parity reject consumption, boundaries/twirl | Existing numerical/API test targets with scripted RNG branch selection | Existing always-success tests read |
| 005 | Auth, malformed/unknown/endpoint/capacity errors, selected-resource chain, concurrent single-use, fail-closed transport | Existing API target plus real process test/drill | Existing unauthenticated fixture/test assumptions read |

### Necessary numerical checks

Proposed parent/implementation coverage:

- H/X/Z/S and CNOT correctness, norm/trace/Hermiticity preservation, unitary adjoints, finite inputs, tensor/permutation/partial-trace order and zero-probability branch handling.
- Pure Bell generation by gates, orthonormality, marginal I/2, and mixed Werner overlap at F=0, .25, .5, .9 and 1.
- Born branch probabilities sum to one; all teleport/swap ideal outcomes .25; deterministic RNG values target interior CDF intervals, not boundary-dependent hacks.
- Ideal 16 teleport branches and 64 swap branches matched to density/global-phase invariant oracles; include imaginary/asymmetric inputs that expose Z/frame errors.
- Werner teleport/swap formula oracles; no .50 fidelity floor; explicit Pauli error channel branches if selected.
- BBPSSW accepted and rejected branches, unequal/equal inputs, no universal improvement claim, no automatic successful retries; retained Bell weights and finite twirl behavior.
- Actual receiver overlap and .95 boundary, including a just-below input that cannot pass by six-decimal rounding or a .85 legacy constant.

### Necessary lifecycle/runtime checks

Proposed real gateway/worker acceptance sequence:

1. Start gateway and at least three distinct node processes (sender, repeater, receiver), all with explicit identities/capacities and operator-configured endpoints. Use authenticated HTTP calls, not ASGITransport as acceptance.
2. Create all four ideal Bell labels and observe correct owned leases/marginals. Exercise noisy two-to-one distillation success and a separate deliberate rejection, recording both retired inputs and outputs/counts.
3. Route an actual two-hop link through the repeater; observe four-qubit BSM, repeater releases, output transfer and actual density-derived fidelity.
4. Teleport a general complex qubit using the returned selected pair ID; inject an outcome requiring nonidentity correction. Receiver worker receives no original amplitudes, applies gates and returns its changed density; check F >= .95.
5. Repeat with consumed resource, wrong endpoints, same purification ID twice, unknown/repeated route nodes, reversed valid endpoints, zero/NaN/Inf amplitudes, false-string booleans and exhausted capacity. No green outcomes or count leaks.
6. Race two consumers of one pair: exactly one reserves/consumes; inspect worker counts and ledger events. Fail one transport after measurement: no fabricated correction/success or revived input; quarantine/release is visible.
7. Consume receiver output/release remaining leases and confirm counts return to baseline. Worker restart must not make stale leases valid; instance-bound commands fail closed.
8. Run phase69's drill against this same live runtime and ledger after its QKD/publisher dependencies land. Public confirmation needs actual observed publication; this research does not assert it.

### Sampling and Wave 0

- Parent owns verification once implementations land; no researcher suite execution. Proposed per-task quick target is numerical tests; per-wave target adds API and actual process tests; phase gate runs full suite and authentic multi-process drill before verify-work.
- Wave 0 needs a scripted RNG fixture, explicit registered-node/auth/runtime fixtures, authoritative pool-managed resources in tests, gate/global-phase/density comparison helpers, process harness with bounded readiness/deadlines/cleanup, and selected-pair failure coverage. Use existing files where practical; add only missing behavioral tests.
- Tests that only grep source, count log lines, pin prose or assert a mocked echoed payload are not evidence of those public invariants.

## Security Domain

The config enables security enforcement at level 1; no security gate was executed. [VERIFIED: .planning/config.json:9-12]

Use **ASVS 5.0.0 category names**, not the older template's unversioned V2-authentication/V5-validation labels. OWASP explicitly identifies stable 5.0.0 and warns requirement identifiers change across versions. [CITED: https://owasp.org/projects/asvs]

| ASVS 5.0.0 category | Applicability and proposed controls |
|---|---|
| V2 Validation and Business Logic | Finite numeric ranges, contextual endpoint/resource consistency, bounded routes/circuits/counts; single-use/locking invariants. Level-1 examples 2.2.1, 2.2.2 and 2.3.1; locking is also justified by correctness even where a specific ASVS item is higher level. |
| V4 API and Web Service | Explicit public versus worker schemas, bounded JSON, unknown-field rejection and problem responses |
| V6 Authentication | Existing seat resolver; separately scoped worker credentials; constant-time comparison; no secret DTOs/logs |
| V7 Session Management | Quantum operation/session IDs are not authentication sessions; bind commands to owned resources and process instances, with bounded duplicate handling |
| V8 Authorization | Function and object access at trusted backend; existing authenticated seat must not authorize arbitrary other-node resources. Level-1 examples 8.2.1, 8.2.2 and 8.3.1 |
| V11 Cryptography | Use standard secrets/hmac/TLS primitives, never homemade cryptography or quantum-security claims |
| V12 Secure Communication | Local loopback-only drill exception; verified TLS for non-loopback; fixed destinations and redirects/proxy restrictions |
| V13 Configuration | Operator-only nodes/capacities/endpoints, safe startup validation, no request credential/URL overrides |

Category names were read from the official v5.0.0 directory; V2 and V8 requirements were read in full relevant sections. The applicability/control mapping is proposed threat analysis, not an ASVS pass. [CITED: https://api.github.com/repos/OWASP/ASVS/contents/5.0/en?ref=v5.0.0] [CITED: https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x11-V2-Validation-and-Business-Logic.md] [CITED: https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0/5.0/en/0x17-V8-Authorization.md]

| Threat pattern | STRIDE | Proposed mitigation/test |
|---|---|---|
| Forged node or lease / selected pair IDOR | Spoofing, elevation | Authenticate and authorize function + resource + actual worker ownership |
| Concurrent reuse or duplicate correction | Tampering | Atomic pair reservation and operation-bound duplicate rejection |
| Caller URL/redirect/proxy destination escape | Tampering, disclosure | Operator allowlist, fixed paths, no caller URLs, `trust_env=False`, redirects disabled |
| Oversized route, circuits, bodies or QKD batch | Denial of service | Fixed numerical bound, capacity-bounded streaming, body/concurrency/deadline limits |
| False success after transport/event append failure | Repudiation, tampering | Gate success on acks + actual corrected state + .95 + durable sink outcome |
| Input/QKD keys in worker/public logs or anchor payload | Disclosure | Derived conditional state only for reconstruction; private keys/local key stores; public commitments only |

No statement here establishes physical quantum confidentiality, secure quantum channels or production QKD security.

## State of the Art / Scope Discipline

Do not treat newer package versions as this phase's objective. The cutover is from metadata/scalar pretending to a circuit-and-density simulator with real process ownership. The original teleportation/purification algorithms remain appropriate primary sources despite their age. The retrieved arXiv HTML identifies `quant-ph/9511027v2` and `22 Nov 1995` but also renders an unrelated 2026 date; cite the stable identifier/version, not a supposed recent algorithm change. [CITED: https://arxiv.org/html/quant-ph/9511027]

## Assumptions Log

No training-only assertion is being locked as a fact. All new SDK names, lifecycle values, message shapes, bounds, role policy, async boundary and BSM-error/twirl choices are explicitly proposed within builder discretion. They require parent interface arbitration and independent review, not an assertion that they exist already.

| Item | Unobserved / proposed point | Risk if ignored |
|---|---|---|
| P1 | Uniform async workflow cutover | QKD/server/test callers drift or nest event loops |
| P2 | Gateway role allowlists and object-scope policy | Unauthorized resource consumption / false claim existing auth covers custom routes |
| P3 | Exact worker message limits, topology and operation-instance bindings | Capacity bypass, replay/double-correction, stale leases |
| P4 | Error channel and recurrent finite twirl selection | Wrong physical-model fidelity or discarded anisotropy |
| U1 | Actual worker network/runtime behavior | Labels or mocked acknowledgements mistaken for distributed acceptance |
| U2 | Full product numerical/API/process suites and minimum-runtime compatibility | Independent snippets mistaken for product validation |
| U3 | Live stored state/service/OS deployment configuration | Repo-only inventory mistaken for completed operational cutover |

## Open Questions and Planner Disposition

1. **SDK arbitration:** freeze exact proposed numerical/result/event/transport shapes before phase69 and REST execution slices start. There is sufficient source/math evidence to plan; do not ask the user to select a library already in builder discretion.
2. **Worker choreography:** finalize how centrally correlated local gates/measurements are authorized and acknowledged versus how receiver conditional state is staged/applied. The minimal acceptance path must execute receiver gates in its actual worker process, with no original input-copy reconstruction.
3. **Ledger failure ordering:** phase69 must define durable event-sink error handling; irreversible measurements cannot be rolled back into reusable pairs. Failed ledger writes must not produce an accepted green session.
4. **Operational state:** parent owns live configuration and worker lifecycle drill. This research cannot claim no existing deployed state or authentic distributed acceptance.
5. **Independent review/receipt:** no signed approval is available; this researcher does not self-approve, commit, archive, merge or assert merge readiness.

## Sources and Evidence

### Primary sources opened this session

- Phase68 CONTEXT, original REQUIREMENTS and milestone audit relevant sections.
- Product quantum teleportation module (all operative sections), phase69 import/E91/drill sections, gateway phase68 handlers/config/auth pattern, existing numerical/API tests, pyproject/lock and gateway README.
- IBM Quantum official teleportation tutorial and density-matrix basics.
- Bennett et al., arXiv quant-ph/9511027v2, recurrence equation and protocol steps.
- HTTPX official async, environment-variable and timeout docs.
- Uvicorn official repository settings after its old documentation hostname timed out.
- OWASP ASVS official project, v5.0.0 source-directory category inventory, V2 and V8 chapters.
- PyPI HTTPX, Starlette and Uvicorn metadata (registry existence/version only; no new-install legitimacy claim).

### Numerical Proof Mapping to Original Requirements

| Original requirement | Observed independent research evidence | Still required from the actual product |
|---|---|---|
| REQ-QTELEPORT-001 | Four explicit Bell vectors used in every teleport/swap input-frame combination; density outer-product construction exercised | Gate-generated Bell vectors, orthonormal/marginal assertions, real distribution/allocations |
| REQ-QTELEPORT-002 | 64 ideal input-frame/BSM branches recover Phi+ with minimum overlap .9999999999999998; four Werner input cases match the swap formula within 1e-12 | Actual mesh orientation/topology/capacity, noisy/error-model tests, separate repeater-worker evidence |
| REQ-QTELEPORT-003 | 16 ideal Bell/measurement branches recover asymmetric complex input with overlap 1; five Werner inputs verify output fidelity, including .95 boundary and below-threshold .933333333333 | Actual sender measurement and receiver-process gates, selected pair, .95 predicate, single use/failure branches |
| REQ-QTELEPORT-004 | Six input-fidelity cases enumerate four bilateral-CNOT target branches and assert acceptance probability/retained overlap; .90/.92 has nonzero rejection; six-unitary twirl preserves overlap and equalizes error weights | Actual pool-mediated distinct inputs, success/rejection consumption, worker allocation transfer and lifecycle events |
| REQ-QTELEPORT-005 | Existing route and test source inspected only; no REST runtime acceptance claimed | Authenticated actual HTTP create/purify/route/selected teleport, typed failures, shared runtime/ledger and process evidence |

[VERIFIED: standalone mathematical probes, research receipt commands 2-3] The right-hand column is proposed required validation, not exercised evidence.

### Executed research evidence

- `node /root/.claude/gsd-core/bin/gsd-tools.cjs query init.phase-op 68` at the absolute audit worktree root: exited 0 and resolved this phase directory correctly.
- `query research-plan --input /tmp/desk-v51-68-research-plan.json`: chose Context7/websearch providers; no mounted Context7 tool/CLI was available, so direct primary-source Read fallback was used. No search tool or provider fetch is falsely claimed.
- `query classify-confidence --provider webfetch --verified`: returned LOW. `curated` also returned LOW; source code explains unknown provider authority falls through to LOW. The artifact preserves that conservative tier rather than pretending Context7 was used.
- Three fetched digests cached via `query research-store put`, with provider webfetch/confidence LOW. No config or planning state was modified by the researcher.
- Explicit product service interpreter metadata probe: Python 3.14.2, HTTPX .28.1, Starlette 1.7.0, Uvicorn .54.0, pytest 9.1.1, pytest-asyncio 1.4.0; exit 0.
- Standalone `xd://run_code` Python density-branch probe: exit 0, 57 ms reported tool duration. Sixteen all-Bell teleport branches (minimum fidelity 1), sixty-four all-Bell-pair swap branches (minimum .9999999999999998), Werner/purification boundary formulas asserted to 1e-12; no product imports or tests.
- Standalone `xd://run_code` Python finite-twirl probe: exit 0, 31 ms reported duration; all six permutations of the Bell-error states and equal retained error weights verified. No product imports or tests.
- Research receipt is a separate bot00 advisory record; no approval field is fabricated. Tool payloads/outputs are in this session history for exact replay. No worker or chain execution evidence belongs to this researcher.

## Metadata

**Confidence breakdown:** installed seam classifies direct-fetched sources LOW because the provider is not in its authority waterfall; source provenance and actually executed mathematical observations are nevertheless explicit. Existing-source behavior is grounded in Read; proposed product/runtime behavior remains unverified. Do not promote this research into a phase acceptance verdict.

**Research date:** 2026-10-09
**Refresh policy, proposed:** source/API changes require interface re-read; mathematical identities remain applicable only to the frozen conventions/noise model. Recheck environment metadata at execution rather than assume the same interpreter or packages elsewhere.
