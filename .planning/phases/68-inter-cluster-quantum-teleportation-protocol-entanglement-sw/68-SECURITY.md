---
phase: "68"
slug: "inter-cluster-quantum-teleportation-protocol-entanglement-sw"
status: draft
threats_open: 0
threats_closed_advisory: 22
registered_occurrences: 29
asvs_level: 2
block_on: high
independent_approval: pending
created: "2026-10-10"
---

# Phase 68 — Complete combined security register (50 IDs); signed gate blocked

Independent read-only ASVS-L2 assessment. Complete combined register: **50 unique threat IDs, 57 registered plan occurrences** — Phase 68: **22 unique / 29 occurrences, 22 advisory CLOSED, 0 open**; Phase 69: **28 unique / 28 occurrences, 28 advisory CLOSED, 0 open**; combined **50 CLOSED, 0 OPEN** per the independent latest 705-line SECURED report at agent://AuditIntegratedSecurityV51. Every ID, original category, severity, and mitigate disposition is preserved. Occurrence accounting: T-68-01 x2, T-68-02 x2, T-68-03 x3, T-68-04 x2, T-68-06 x2, T-68-07 x2; each remaining Phase 68 ID occurs once (29 total); all 28 Phase 69 IDs occur once. Zero accepted risks. 0 open advisory is not whole-gate approval.

CLOSED is an independent advisory mitigation status only: the declared mitigation was traced at its actual source boundary and parent-reported actual execution supports it. It is not signed Desk approval, not a scanner pass, not a risk waiver, and not milestone acceptance. `status: draft` and `independent_approval: pending` retain the sign-off boundary. Whole-service security gate: **BLOCKED**.

Claim P2 history preserved and closed: parent actual BEFORE (bg231 exit 0 tool 0.42 s, artifact://1171) proved claim_anchor rollback left the handle OPEN with the uncommitted claim visible on 10 public-served paths and the cursor transaction stranded (commit-IO and duplicate-committed rollback failures directly observed; Keyboard actual-pending marker observed, initial no-rollback detail [source inference] per sqlite-only path and post-retry rollback attribute). Source fix landed (shared `_rollback_failed_transaction` across 4 append + 3 claim callers, old name gone with no shims; duplicate failed rollback now LedgerClosedError not False, Keyboard Base cleanup barrier raise, poison before close; 204-line consumer audit static-wired). Parent actual AFTER (bg233 exit 0 tool 0.62 s, artifact://1179) grounded poison-before-close across the same 3 cases (10 public closed, same-handle LedgerClosedError, typed SQL errors with identical Keyboard marker, peer/reopen exact root with old committed authority and pending new claim absent; fresh new claim wins after reopen only if uncommitted, duplicate False). The independent auditor's latest 705-line SECURED report confirms T-69-G04-B advisory CLOSED on that 3-target plus probe after-actual; BEFORE 0.42 s and 765 pre-claim counts are preserved as qualified history, not erased. No new threat ID is invented; categories, severities, and the 57-occurrence accounting are unchanged. No source-counterexample waiver.

## Trust boundaries

Seat authorization precedes bounded public admission. Operator worker destinations and credentials bind original instances and fixed authenticated command paths. Pair, survivor, and uncertain release custody never transfers to a replacement by absence. Private QKD draws, candidates, blinding, and capabilities stay worker-owner local; the gateway never proxies them. Ledger proofs require exact trusted committed checkpoints; failed rollback poisons the public handle before close. Publisher pins Devnet and signs/sends once with exact readback checks. Classical coordination and numerical state/channel models are trusted simulator components, not physical or device-independent secret channels.

## P1 history preserved: T-68-04 and T-68-G06-02 reopened, then repaired

T-68-04 (high) and T-68-G06-02 (high) were reopened by the fresh P1 finding and are now advisory CLOSED after the actual repair. The failure is retained, not erased. Parent-reported actual before repair (job bg224, tool 2.23 s): all 4 typed/generic x Cancel/Keyboard pre-effect cleanup interruption cases left the pair RESERVED, original halves held 1/1 and untouched, new-input original uncertainty retained, no transport after interruption, subsequent teleport pair_unavailable. Parent-reported actual after repair (job bg225, exit 0, tool 2.39 s, artifact://1160, independently read in full): all 4 cases pair ACTIVE, identical interruption, no later transport, original pair custody unchanged with worker leases 1/1, original new-input obligation retained, next genuinely NEW teleport success true with reason teleported. Post-scoped-format actual guard retained the same outcomes at 2.32 s. Source match independently read after formatting: typed branch quantum_teleportation.py:2081-2106 restores the matching reservation synchronously then bare-reraises; generic branch quantum_teleportation.py:2110-2130 carries the same guard; sync invariant quantum_teleportation.py:615-622 restores only RESERVED records held by this operation and never resurrects quarantined or other-operation records. No retry: the original input release uncertainty remains indexed and a new teleport is a new operation, not a retry of the ambiguous release. Consumer regressions (parent job bg226, exit 0, tool 2.97 s, 6 passed in 1.94 s with 106 deselected): 4 actual cleanup-interruption and recovery cases plus 2 real public/native proof-storage fault cases; test bodies independently read at tests/test_quantum_teleportation.py:1807-1904 and tests/test_quantum_teleportation_endpoints.py:1357-1440.

## Phase 68 register — 22 rows (this phase owns these rows)

| Threat ID | Original category | Severity | Disposition | Advisory mitigation status | Source boundary evidence | Assessment |
|---|---|---|---|---|---|---|
| T-68-01 | Tampering (ASVS 5.0 V2 Validation) | high | mitigate | CLOSED | quantum_state.py:117-129,305-324,412-475,651-708; server.py:6496-6504,6542-6560 | Finite amplitudes, scale-first normalization, density/Born constraints and typed numeric admission. |
| T-68-02 | Tampering (ASVS 5.0 V2 Business Logic) | medium | mitigate | CLOSED | quantum_state.py:622-635; quantum_teleportation.py:1036-1105,1880-1940 | Actual stored density/untwirled survivor and actual-state BBPSSW odds, not Werner-only substitution. |
| T-68-03 | Elevation (ASVS 5.0 V8 Authorization) | high | mitigate | CLOSED | quantum_teleportation.py:634-658,830-860,905-989; quantum_node.py:1077-1078,1554-1558 | Authoritative pair records/original instances/survivor custody; E91 lease.resource_id before RNG/mutation. |
| T-68-04 | Tampering (ASVS 5.0 V2 Business Logic) | high | mitigate | CLOSED | quantum_node.py:656-694; quantum_teleportation.py:431-500,871-960,1197-1245,1419-1466,2041-2130; tests/test_quantum_teleportation.py:1807-1904; artifact://1160 | Retirement/tombstones/whole-operation interruption retained. Both typed/generic pre-effect cleanup interruption branches now synchronously restore matching pool reservation before bare-reraise. Actual 4-combination after-proof retains input uncertainty and untouched original halves; next new teleport succeeds. P1 failure history retained above. |
| T-68-05 | Disclosure/Tampering (ASVS 5.0 V12 Secure Communication, V4 API) | high | mitigate | CLOSED | quantum_transport.py:90-110,383-395,405-540; config.py:73-129 | Operator URLs/fixed paths, no redirects/environment proxy, loopback-only plaintext and bounded replies. |
| T-68-06 | Spoofing/Elevation (ASVS 5.0 V6 Authentication, V8 Authorization) | high | mitigate | CLOSED | config.py:329-337; server.py:6416-6436,6615-6633,6641-6653,6680-6706,6715-6727,6745-6750,6819-6832 | Constant-time seat resolver/auth-first 401/403 across six mutations and authenticated reads. |
| T-68-07 | Denial of Service (ASVS 5.0 V4 API, V2 Validation) | medium | mitigate | CLOSED | server.py:6327,6451-6490,6597-6615,6631,6650,6701,6725,6787,6831; quantum_node.py:100-104; tests/test_quantum_teleportation_endpoints.py:1144-1285 | Original max4 immediate 429/no queue, 60 s overall deadline/typed 504/finally slot recovery; body/route/circuit bounds. Original medium severity preserved. |
| T-68-G04-01 | Tampering | high | mitigate | CLOSED | quantum_state.py:249-266,412-468; tests/test_quantum_state_kernel.py:1-18 | Hermitian-part PSD predicate without stored-row rewrite/tolerance weakening. |
| T-68-G04-02 | Tampering | medium | mitigate | CLOSED | quantum_state.py:88-94; tests/test_quantum_state_kernel.py:1-18,41-53 | Single Gate2 alias and deterministic numerical oracles. |
| T-68-G05-01 | Denial of Service | high | mitigate | CLOSED | quantum_node.py:1840-1876 | Worker authentication before 64 KiB streamed body. |
| T-68-G05-02 | Tampering | high | mitigate | CLOSED | quantum_node.py:195-197,656-694,936-1018 | Matrix-inclusive replay digest and permanent tombstones. |
| T-68-G05-03 | Spoofing / Tampering | medium | mitigate | CLOSED | quantum_transport.py:493-540,554-572; quantum_teleportation.py:399-429,506-563,634-658 | Ambiguous mutations retained original-scoped; read-only inspection never treats absence as clearance. |
| T-68-G05-04 | Tampering | medium | mitigate | CLOSED | quantum_node.py:200-213,229-232,732-735 | Minted lease identifiers independently bounded for subsequent release. |
| T-68-G06-01 | Tampering | high | mitigate | CLOSED | quantum_teleportation.py:871-960 | Whole-batch retirement prevalidation/atomic input-to-survivor custody transfer. |
| T-68-G06-02 | Denial of Service | high | mitigate | CLOSED | quantum_teleportation.py:288-315,431-500,576-622,667-700,2081-2130; tests/test_quantum_teleportation.py:1712-1904; artifact://1160 | Normal release uses original node/instance/lease index rather than adopted history; sticky release obligations survive physical absence. New P1 synchronous restoration prevents stranded RESERVED pair while retaining new-input uncertainty. Actual next-use recovery observed. P1 failure history retained above. |
| T-68-G06-03 | Tampering | medium | mitigate | CLOSED | quantum_teleportation.py:905-960,1130-1170,1380-1418,1940-2040,2130-2231 | Receipt-gated provisional outputs, failure quarantine and successful receiver owner-release lifecycle. |
| T-68-G06-04 | Information Integrity | medium | mitigate | CLOSED | quantum_teleportation.py:1036-1105,1880-1940 | Actual-state purification odds and corrected receiver density. |
| T-68-G07-01 | Denial of Service | high | mitigate | CLOSED | server.py:6330-6342; quantum_ledger.py:753-818 | Storage initialization failure isolated from unrelated gateway routes. |
| T-68-G07-02 | Denial of Service | medium | mitigate | CLOSED | quantum_ledger.py:722,1586-1617; tests/test_quantum_ledger_anchor.py:2076-2134 | Bounded indexed receipt SQL without pre-limit full refresh. |
| T-68-G07-03 | Spoofing | high | mitigate | CLOSED | server.py:6808-6839; quantum_teleportation.py:2130-2231; tests/test_quantum_teleportation.py:1674-1710 | Auth-first receiver ownership, serialized replay/terminal guards; unknown IDs refuse 404 before lock allocation. Actual: 128 unknown IDs retain 0 locks. |
| T-68-G07-04 | Denial of Service | medium | mitigate | CLOSED | server.py:6451-6490 | Streamed request byte cap and normalized decoder failures. |
| T-68-G08-A | Tampering | high | mitigate | CLOSED | quantum_teleportation.py:2130-2231; tests/test_quantum_teleportation.py:1370-1484 | Owner release interruption synchronously quarantines and cannot repeat worker mutation. |

## Phase 69 register — 28 rows (combined completeness; owned by 69-SECURITY)

| Threat ID | Original category | Severity | Disposition | Advisory mitigation status | Source boundary evidence | Assessment |
|---|---|---|---|---|---|---|
| T-69-01 | Tampering | high | mitigate | CLOSED | quantum_ledger.py:781-818,849-890,1134-1253,1281-1363,1439-1457; tests/test_quantum_ledger_anchor.py:2319-2395,2422-2466 | Durable rows/checkpoints/replay validation; rollback-failure handle poisoning; exact proof structural binding. |
| T-69-02 | Spoofing | high | mitigate | CLOSED | quantum_anchor.py:449-525,774-831,841-847,890-986,1152-1260 | Private signer/pinned Devnet/claim-before-sign/one-send/exact readback; closed-proof verification typed 503 before sign/RPC. |
| T-69-SC | Tampering | high | mitigate | CLOSED | quantum_anchor.py:23-49; quantum_ledger.py:16-32; services/desk-gateway/pyproject.toml:1-36; /tmp/desk-v51-dependency-audit.json safe projection | Existing-dependency narrow publisher, no new SDK/installer path; exact 47 versions 0 known advisory findings, not artifact attestation. |
| T-69-03 | Information disclosure | high | mitigate | CLOSED | quantum_qkd_mesh.py:157-221,887-1052; quantum_key.py:65-80,136-179; quantum_node.py:1677-1718 | Aggregate-only public DTO; private keys/capabilities/blinds; leakage budget/minimum 128-bit extraction. |
| T-69-04 | Spoofing | high | mitigate | CLOSED | quantum_node.py:642-654,1173-1194,1530-1563,1677-1728,1790-1828; quantum_qkd_mesh.py:340-457 | Action/role/stage/owner/original-instance/resource guards and one-shot capability lifecycle. |
| T-69-05 | Elevation | high | mitigate | CLOSED | server.py:6356-6375,6416-6436,6522-6540,6895-7300; quantum_transport.py:642-659 | Auth-first/shared operator transport/no caller URL or test-hook bypass. |
| T-69-06 | Denial of service | medium | mitigate | CLOSED | quantum_node.py:100-104,157-190; quantum_transport.py:405-540; quantum_qkd_mesh.py:1140-1288 | Bounded counts/sessions/replies; safe zero-count cleanup; single drill/truthful conjunction. |
| T-69-G04-A | Tampering | high | mitigate | CLOSED | quantum_ledger.py:1134-1253,1315-1363,1365-1508; tests/test_quantum_ledger_anchor.py:2422-2466 | Typed metadata/index/seq/preimage binding; odd-width duplicate-last sibling equals current hash at every level. Genuine 4-to-3 and 11-to-10 reject, authentic prefixes pass. |
| T-69-G04-B | Repudiation | high | mitigate | CLOSED | quantum_ledger.py:1619-1682,1725-1751; quantum_anchor.py:589-592,890-986; artifact://1171; artifact://1179 | BEFORE counterexample (commit-IO and duplicate-committed rollback failures observed; Keyboard marker observed, initial no-rollback [source inference]) then AFTER poison-before-close grounded across the same 3 cases (10 public closed, same-handle LedgerClosedError, typed errors, peer/reopen exact). Independent auditor confirms advisory closure. Original category/severity/disposition unchanged. |
| T-69-G04-C | Information disclosure | medium | mitigate | CLOSED | quantum_anchor.py:626-658,1034-1071,1152-1260 | Historical observation only for stored public signatures; sanitized errors. |
| T-69-G05-A | Elevation | high | mitigate | CLOSED | quantum_node.py:1173-1194,1790-1828; quantum_transport.py:642-659 | Coordinator allowlist/separate owner action/capability-hash replay/constant-time one-shot admission. |
| T-69-G05-B | Denial of service | medium | mitigate | CLOSED | quantum_node.py:157-190,386-569,1163-1172,1720-1728 | Codec/session/effect bounds and terminal private-buffer reclamation with replay. |
| T-69-G06-A | Information disclosure | high | mitigate | CLOSED | quantum_node.py:1530-1589; quantum_qkd_mesh.py:740-825,157-221 | Endpoint-private E91 clicks and disjoint public witness/phase samples. |
| T-69-G06-B | Tampering | high | mitigate | CLOSED | quantum_qkd_mesh.py:378-457,498-596,1028-1052; tests/test_quantum_qkd_mesh.py:1223-1300 | Emission failure confirms keylessness or retains sticky original scope; no mutating abort retry. |
| T-69-G06-C | Denial of service | medium | mitigate | CLOSED | quantum_qkd_mesh.py:1154-1288 | Owned partial allocation/every-exit cleanup; cleanup failure cannot report pass. |
| T-69-G07-A | Elevation | high | mitigate | CLOSED | server.py:6356-6375,6416-6436,6522-6540,6895-7300 | Auth before readiness/parsing; configured transport-bound discovery. |
| T-69-G07-B | Denial of service | medium | mitigate | CLOSED | server.py:6330-6342,6973-7005,7036-7060,7070-7095; quantum_ledger.py:849-890,1586-1617; tests/test_quantum_teleportation_endpoints.py:1289-1440; artifact://1160 | Storage isolation/bounded listing; snapshot/receipt/proof read errors typed 503. Latest actual: native proof outage 503 ledger_unavailable with control 200, auth 401, invalid 400; no fabricated proof. Cursor creation is inside the sqlite error guard and native closed-connection cursor error is typed. |
| T-69-G08-A | Tampering | high | mitigate | CLOSED | quantum_qkd_mesh.py:269-306,740-825; quantum_node.py:1530-1563 | Registered shortest route/actual density/frame/resource-owned graph leases. |
| T-69-G08-B | Tampering | high | mitigate | CLOSED | quantum_qkd_mesh.py:740-825,1054-1084,378-457; tests/test_quantum_qkd_mesh.py:930-1115 | Confirmed retirement before extraction; keyless resource/key quarantine on failure. |
| T-69-G08-C | Denial of service | medium | mitigate | CLOSED | server.py:6451-6490,6496-6504,6542-6560; quantum_transport.py:526-540; quantum_node.py:1840-1876 | Declared decoder/conversion errors normalized within existing bounds; storage proof failure mapped separately to G07-B. |
| T-69-G09-A | Tampering | high | mitigate | CLOSED | quantum_qkd_mesh.py:340-457; tests/test_quantum_qkd_mesh.py:1151-1222 | Late begin retained original pending/quarantine; unknown-session absence not terminal proof; read-only reconciliation. |
| T-69-G09-B | Information disclosure | high | mitigate | CLOSED | quantum_qkd_mesh.py:498-596,887-1052,378-457; tests/test_quantum_qkd_mesh.py:1223-1300 | Distinguished keyless cleanup failures/sticky quarantine/original interruption. |
| T-69-G09-C | Tampering | high | mitigate | CLOSED | quantum_qkd_mesh.py:100-155,940-988; tests/test_quantum_qkd_mesh.py:1355-1400 | Original exact integer 11 percent threshold/Born intercept-resend/tag disagreement prevents extraction. |
| T-69-G09-D | Denial of service | medium | mitigate | CLOSED | quantum_qkd_mesh.py:1239-1288,1290-1333; tests/test_quantum_qkd_mesh.py:1603-1650 | Survivor cleanup Boolean propagated; existing quarantine skips sweep mutation. |
| T-69-G10-A | Tampering | high | mitigate | CLOSED | quantum_ledger.py:1365-1508,1134-1253; server.py:7090-7130; tests/test_quantum_ledger_anchor.py:2422-2466 | Trusted committed checkpoint plus index/seq/preimage/odd-width binding; caller-selected root not trusted. |
| T-69-G10-B | Tampering | high | mitigate | CLOSED | quantum_ledger.py:849-890,1134-1253,1281-1363; tests/test_quantum_ledger_anchor.py:2319-2395,2468-2487 | Immutable locked peer delta/atomic writer refresh/poisoned-handle isolation; native cursor error typed. No claim of newly added explicit reader-BEGIN. |
| T-69-G10-C | Information disclosure | high | mitigate | CLOSED | quantum_anchor.py:774-831,890-986; tests/test_quantum_ledger_anchor.py:2252-2315,2397-2416 | Genuine proof oversize 413/closed verifier 503 before signer/send; no private/live signer read by auditor. |
| T-69-G10-D | Denial of service | medium | mitigate | CLOSED | quantum_ledger.py:722-724,1586-1617,1725-1772; tests/test_quantum_ledger_anchor.py:2076-2134 | Matching expression indexes/bounded SQL/real VM-work assertions/finally-cleared callback. |

## Reproduced storage, lifecycle, and fresh-boundary disposition

SEC-LEDGER-ROLLBACK-FAILURE affected original T-69-01, T-69-G04-A, T-69-G10-A, and T-69-G10-B. Actual before 0.35 s: native pending event with checkpoint 3, failed commit and rollback, writer proof true while peer 2. Actual after 0.48 s: all 10 public paths and pending verifier closed, peer and reopen exact 2 and root. Five corrected focused tests cover real IO, KeyboardInterrupt identity, 11 public guard with no append, clean reopen with next append 3, and trigger with SIGKILL and VM. The common helper closes the handle before raw close and all four error branches use it. The exporter close-between-proof/verify path now returns typed 503 before signer/RPC (before 0.53 s, after 0.76 s; 3 focused tests passed). No retry, no fake transaction state, no accepted risk.

Original custody, first-effect cancellation, fresh grant cleanup, second cleanup interruption, common release no-retry, unknown-lease false ACK, late begin, and ambiguous QKD abort roots are fixed with actual effectful before/after evidence. All five negative drill exits retain exact caller leases, original output, and dual key usability; independent Nyquist coverage finding AC011f was closed, not moved to manual.

Fresh bounds retained: genuine 4-to-3 proof pairs both reject with authentic prefixes passing (odd-width fix mapped to T-69-01, T-69-G04-A, T-69-G10-A); 257 actual adopted records with normal release visiting 0 history entries (original node/instance/lease index mapped to T-68-G06-02); 128 unknown output IDs retaining 0 locks with 404 before lock allocation (mapped to T-68-G07-03); snapshot, receipt, and proof HTTP reads all typed 503 ledger_unavailable with auth-first 401 and invalid 400 preserved and cursor creation under guard (mapped to T-69-G07-B). Earlier focused union: 283 passed in 82.94 s (tool 84.41 s) after correcting the ACK-loss fixture expectation with no source weakening.

## Scanner evidence: exact 10 core LOW dispositions (2 claim LOWs removed by fix, history preserved)

Final whole-service Bandit: **FAILED** with exit 1, tool 7.91 s, 57419 lines, 2 HIGH, 6 MEDIUM, 105 LOW, with the post-claim scan observed. Exact v5.1 core, gateway, and config projection: 10 LOW with 0 MEDIUM and 0 HIGH. The two source-claim unsafe B110 LOWs (quantum_ledger.py:1672 claim-conflict rollback False, quantum_ledger.py:1680 claim-failure LedgerError) are REMOVED by the shared-helper fix, recorded here as historical dispositions, not benign waivers: the unsafe pattern no longer exists at those coordinates because rollback now poisons before close and duplicate failure raises LedgerClosedError. Core-only absence of HIGH/MEDIUM is not whole-service approval. No suppression, no waiver, no pass.

| File at scan snapshot | Scanner | Severity | Disposition grounded in source |
|---|---|---|---|
| quantum_anchor.py:1443 | B110 | LOW | Best-effort terminal audit write cannot change result or undo prepared single-send authority. |
| quantum_ledger.py:806 | B110 | LOW | Initialization cleanup failure still marks handle closed and rethrows; no usable half-open ledger. |
| quantum_ledger.py:815 | B110 | LOW | Unreadable/corrupt initialization remains closed/typed despite failed cleanup. |
| quantum_ledger.py:1522 | B101 | LOW | Assertion is not security guard: actual eligibility/Mapping/field validation rejects malformed content independently. |
| quantum_ledger.py:1672 (historical, REMOVED by fix) | B110 | LOW (was) | Historical: claim-conflict rollback failure returned False. Pattern removed by shared `_rollback_failed_transaction` with poison-before-close; duplicate failure now LedgerClosedError. Not a benign waiver. |
| quantum_ledger.py:1680 (historical, REMOVED by fix) | B110 | LOW (was) | Historical: claim failure raised LedgerError via old branch. Pattern removed by shared helper; retained here for history, not counted in current 10 LOW. |
| quantum_qkd_mesh.py:431 | B110 | LOW | Abort failure retains original unconfirmed/quarantined keyless scope. |
| quantum_qkd_mesh.py:446 | B110 | LOW | Terminal read failure is non-proof and cannot clear scope/key destruction obligation. |
| quantum_qkd_mesh.py:1069 | B110 | LOW | Retirement interruption already quarantines; original interruption reraised, no extraction/finish. |
| quantum_qkd_mesh.py:1109 | B110 | LOW | Owner-use failure followed by verified abort or quarantine, not fabricated cleanup success. |
| quantum_qkd_mesh.py:1253 | B110 | LOW | Terminal reserve failure reaches resource cleanup; failure false/quarantine/sticky skip. |
| quantum_teleportation.py:2069 | B110 | LOW | Best-effort quarantine audit failure occurs after custody handling and before transport_ambiguous raise. Scan coordinate predates later guard formatting/line shifts. |

## Outstanding whole-service scanner findings: 8 legacy HIGH/MEDIUM

| File at scan snapshot | Scanner | Severity | Scope and disposition |
|---|---|---|---|
| sharding.py:57 | B324 | HIGH | Inherited MD5 ring fallback; remains outstanding whole-service HIGH, not a quantum hash finding and not waived. |
| sharding.py:189 | B324 | HIGH | Inherited MD5 ORSet tag; remains outstanding HIGH requiring owner/QUALITY disposition. |
| formal_verification.py:309 | B307 | MEDIUM | Precondition eval; restricted builtins are not approved sandbox assurance. |
| formal_verification.py:345 | B307 | MEDIUM | Postcondition/invariant eval; unresolved independent inherited finding. |
| formal_verification.py:491 | B102 | MEDIUM | Dynamic verification exec; unresolved independent inherited finding. |
| skill_synthesis.py:177 | B102 | MEDIUM | Synthesized tool exec; restricted namespace does not authorize suppression. |
| upstreams.py:524 | B608 | MEDIUM | Composed read-only SQL wrapper; read-only guard is not scanner waiver. |
| upstreams.py:572 | B608 | MEDIUM | Read-only PostgreSQL transaction/parameterized limit still require independent composed-query disposition. |

These 8 legacy HIGH/MEDIUM results require owning-seat and QUALITY disposition and still block whole-service security approval. Pre-existing and out-of-scope is not a waiver; none was authorized. No unregistered threat flags were invented; source changes map to the preserved register. Odd-width proof maps to T-69-01/G04-A/G10-A; release history and locks map to T-68-G06-02/07 and T-68-G07-03; pre-effect cleanup interruption maps to T-68-04/G06-02; proof storage 503 maps to T-69-G07-B.

## Parent execution and provenance

- Current source commit: `6c7d8ef`; source receipt and gate publication head `dac2fdf` on draft PR 214. User checkout untouched. The repaired working tree is not yet published under a new commit; parent supplies the new commit when observed.
- Qualified historical checkpoint: 752 passed in 414.33 s (exit 0, tool wall 415.77 s) on code `6c7d8ef`, before the fresh review repairs. Command: `TMPDIR=/dev/shm uv run --project services/desk-gateway --no-sync python -m pytest -q --tb=short --show-capture=no --junitxml=/tmp/desk-v51-gateway.xml tests` from `/tmp/desk-v51-implementation`. This is a historical checkpoint, not a final corrected-tree pass.
- Qualified historical checkpoint: 759 passed was likewise before the subsequently repaired P1 and proof boundary. Neither 752 nor 759 is relabeled as a final corrected-tree pass.
- Final source complete consumer suite: **768 passed in 425.51 s** (tool 427.04 s, Python 3.14), current product `d452` local and unpublished — no new head is guessed; parent publishes the new commit when observed. Earlier 765 (412.69 s, tool 414.06 s) is preserved as the qualified pre-claim checkpoint, not erased; 752 and 759 likewise remain qualified pre-repair history.
- Strict SOURCE G2 now has 2 blockers: missing independent stamp plus cmd94 forced-ignored receipt generic false positive. Isolated QUALITY owner fix is active with push held and not merged; no merge, auto-merge, or force-push is claimed.
- Actual four distinct CLI workers with gateway, no direct endpoint link, 20000 repeater-only E91 rounds, 256-bit endpoint keys, QBER 0, CHSH 2.828630008762767 with lower bound 2.3775443874507514; original one-shot owner use; final active leases 0 on all nodes. Tool wall 1125.58 s. The process started before the final error-only release, storage, and exporter guards; this is normal-flow proof with explicit provenance, not an unqualified final-head execution claim.
- All five numerical drill stages passed, then the genuine publisher refused `insufficient_balance` with signature and slot null and all_passed false. Unrelated user capacities 3/3/0/0 stayed unchanged.
- Current two-worker/gateway HTTP smoke exit 0 (tool 2.68 s): all six busy mutations 429 after four actual applied reserves, auth 401/403 with no extra effects, applied-reserve 504 with original custody, next 200 slot recovery, explicit operator cleanup 0/0. The smoke shortened only its private timeout; product 60 s and E91/drill sample counts are unchanged.
- Original failed and intermediate runs and before/after probes remain in the SYSTEMS receipt; 752 never erases 11/728, 4/744, 5/32, or fixture and API failures. The full Python 3.12 suite was not run; the complete suite used Python 3.14.
- Pinned-version audit: exact 47 noneditable installed versions, 0 known vulnerabilities and fixes, exit 0 with tool 1.52 s, after a failed editable collection. Version-only advisory evidence, not artifact or hash integrity attestation.
- Review provenance: fresh review 30954537 at `dac2fdf` with confidence 3/5 is not ready; unaddressed remote comments and unpublished repairs are not claimed as final-head approval. The independent latest 705-line SECURED report at agent://AuditIntegratedSecurityV51 confirms the complete 50/57 CLOSED advisory with G04-B after-actual closure grounded on the 3-target plus probe evidence; this file mirrors that verdict without self-stamping beyond it. All 70 stored-comment cohort reviews remain dispositioned in source; remote addressed flags are not claimed and final-head Greptile remains pending.

## Security Audit

2026-10-10 (final auditor-mirrored): 50 declared mitigations assessed, 50 advisory CLOSED, 0 OPEN, 57 registered occurrences; Phase 68 counts in frontmatter above. 0 open advisory is not whole-gate approval. Independent auditor executed 0 commands, tests, scans, builds, lints, formats, edits, or commits. Parent owns every receipt and artifact.

## Limits and approval

No accepted risk. No new threat IDs. No physical/hardware, device-independent/composable secrecy, or independent-consensus guarantee. Worker nonterminal QKD keys remain bounded at 64, never silently evicted; original fixed effect-history admission remains unchanged. Latest Devnet read-only balance 0 at confirmed slot 509600313. No new funding request and no eligible provider access were issued; dedicated payer with 0 lamports and official airdrop 429 leaves original REQ-QTELEPORT-009 and positive REQ-QTELEPORT-010 live-blocked. All 11 original requirement boxes remain open with signed acceptance 0 of 11 and phases 0 of 2. Strict G2 independent stamp, QUALITY whole-service disposition, final-head Greptile, and final corrected-tree suite/scan/gates remain blocking. No completion, archive, release, merge, auto-merge, force-push, or branch deletion.
