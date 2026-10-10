---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: "10"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [6c7d8ef, d452fb1]
publication_status: local_unpublished
requirements-completed: []
---

# 69-10 — Canonical receipts, committed prefix, bounded work and atomic failure recovery

## Parent-owned implementation

QuantumQKDReceipt is the unchanged five-field immutable receipt; obsolete aliases are removed and all callers migrated. Committed verification binds exact trusted checkpoint size/root; algebraic external-root verification retains its original meaning. Still-open peer readers refresh committed deltas without local append/reopen. Indexed receipt and prepared/signature lookups remain bounded.

Actual last-hit/miss SQLite VM work is measured at small/4096 same-type history with progress handlers always removed. An actual five-numerical-stage drill supplies the eligible150byte leaf; genuine history grows to131073 leaves/18 siblings and valid crypto, then exporter413 before signing/send (0/0), never fabricated sibling/leaf padding.

Checkpoint trigger failure and childSIGKILL preserve exact committed prefixes. Independent security found failed COMMIT plus failed ROLLBACK exposed uncommitted writer rows/proofs; parent reproduced and repaired it. The common failure helper closes the public handle before raw close, covers allfour append error branches and preserves interruption identity. Every public receipt/proof/lookup refuses until clean reopen; exporter translates a close between proof and verification to existing503 ledger_unavailable.

## Observed verification

Historical checks at the 6c7d8ef checkpoint: actual pending-transaction probe before 0.35 s served tree 3 with proof true while the independent reader saw 2; after 0.48 s all 10 public paths closed with peer and reopen at exact 2 and root. Focus 5 passed in 1.99 s / tool 2.64 s, covering IO and KeyboardInterrupt, 11 closed guards, no new append, clean reopen then append 3, and trigger, SIGKILL, and VM cases. Closed-export probe: before 0.53 s raised; after 0.76 s typed 503 with no signature slot; focus 3 passed in 0.32 s / tool 0.94 s. Final full 752 passed in 414.33 s / tool 415.77 s.

Final current complete command, run by the parent only:

```bash
TMPDIR=/dev/shm uv run --project services/desk-gateway --no-sync python -m pytest -q --tb=short --show-capture=no --junitxml=/tmp/desk-v51-gateway.xml tests
```

Result: **752 passed in 414.33 s**, exit 0, tool wall 415.77 s. This is a historical checkpoint on product code 6c7d8ef, BEFORE the fresh-review repairs below — not a new-tree final pass and not a new final head. Exact before/failure/after history is in `.receipts/bot-01-systems-backend/v5.1-faithful-simulator.json` on source draft PR 214. Source executors/reviewers ran no checks or commits. Parent integrated source and wrote artifacts.

## Fresh boundary continuation (parent-observed; repair commit pending)

Relevant to this plan: genuine odd-width all-level equality plus native cursor typing plus snapshot, receipt, and proof 503. Verification now checks at every level that the even-last sibling equals the current hash, so genuine 4-to-3 and 11-to-10 higher-level forgeries verify false on both the algebraic and committed paths while authentic odd-width proofs still pass. Cursor creation moved inside the sqlite.Error guard and a native closed-connection cursor error is now a typed LedgerError; the common failure helper closes the public handle before the raw close, covers all four append error branches, and preserves interruption identity. Both HTTP snapshot/receipt handlers and the proof path translate that typed error to the existing 503 ledger_unavailable, with every public receipt, proof, and lookup refusing until clean reopen and the exporter mapping a close between proof and verification to 503.

Parent-run `/tmp/desk-v51-final-boundaries-smoke.py` (exit 0): BEFORE, tool 2.23 s, GET proof with the native connection closed raised LedgerError while control read 200, auth-first 401, and invalid 400 held; AFTER, 2.39 s and post-scoped-format 2.32 s, GET proof returns 503 ledger_unavailable with 401, 400, and control 200 preserved.

Current union evidence (parent-observed): new 6 consumer regressions pass 1.94 s / tool 2.97 s (4 custody plus 2 actual public/native proof outages) with no incidental file-size assertion; 759-pass checkpoint at 416.36 s / tool 417.86 s is BEFORE these repairs, not a final complete pass; current CI 299 pass 15.53 s / tool 16.07 s; final formatted full suite (bg 228) still RUNNING with no count inferred; final Bandit FAILED exit 1 / tool 6.81 s over 57408 lines (HIGH 2, MED 6, LOW 107, errors empty, skips 0, nosec 0) with the exact milestone core/gateway/config 12 LOW — ledger files 806/815/1522/1672/1680, anchor 1443, qkd 431/446/1069/1109/1253, teleport 2075 — and 8 legacy HIGH/MED unchanged and no waiver. Latest Devnet read-only balance 0 at confirmed slot 509600313; no new funding request and no eligible provider access mounted. Source published head remains dac2fdf with old product 6c7d8ef as the initial source checkpoint until the parent observes and supplies the new repair commit — none invented here.

**Latest parent update (bg 228 complete, supersedes the RUNNING line above without rewriting it):** parent bg 228 full suite is now COMPLETE with 765 passed in 412.69 s, exit 0, tool 414.06 s, Python 3.14. This is a VALID checkpoint AFTER the teleport plus HTTP corrections recorded above — but BEFORE the newly found claim-anchor correction, so it is not a final current all-source pass and especially not a 69-10 final signoff. The independent phase 69 cohort just found a new P2: claim_anchor failed rollback leaves the handle open with the uncommitted claim visible (ledger lines 1669–1682). Parent is reading the code and running the actual before proof next; a narrow fix is still needed. Comment cohort: most of all 70 are source-side already repaired (49 phase 68 correct, 21 phase 69 flagged as the new increment) while remote 70 remain addressed false with no approval. All prior before/after timings, requirements-completed [], and the 6c7d8ef checkpoint qualification stand unchanged; no repair hash guessed here.

**Source claim fix — parent AFTER probe observed (artifact 1179):** parent bg 233 actual run exit 0 / tool 0.62 s over the same 3 claim fault cases: all 10 paths and the next claim closed; typed SQL LedgerError with the identical KeyboardInterrupt marker; failed duplicate raises LedgerClosedError rather than returning False; peer/reopen at exact root and authority with the pending new claim absent and the proper new winner plus duplicates False. Native 3 new tests, full suite, and SAST after the claim fix are still pending; the helper is already shared across 4 append plus 3 claim paths with no old alias. The 765 checkpoint above remains pre-claim history; no new hash guessed here.

**Final stable current (parent-observed bg 235):** final actual stable complete consumer suite: 768 passed in 425.51 s, exit 0, tool 427.04 s, Python 3.14, bg 235, after ALL source corrections including the claim fix — this supersedes the pending full/SAST lines above without rewriting them. Earlier 752 (6c7d8ef product checkpoint), 759 (pre-repair checkpoint), and 765 (pre-claim checkpoint) remain qualified history, not current. Product commit is new d452fb1, locally committed and unpublished — listed here as local-only with no remote URL claimed. For this plan it covers the odd-width, native-cursor, 503, and claim-anchor rollback-closure surface above. Gates: G1/G3/G4/G5/G6/G7 current PASS; strict G2 shows 2 actual blockers (missing independent stamp; old command-94 git add -f false positive); QUALITY isolated owner repair/push held, not a bypass or waiver. Final SAST: 57419 lines, H2/M6/L105, core 10 LOW, legacy 8 unchanged, exit 1, tool 7.91 s. Source 70 cohort: 49 phase-68 plus 21 phase-69 repaired, 0 new; advisory 50 closed / 57 occurrences, not signed. requirements-completed [] unchanged; signed acceptance 0; live 009/010 remain blocked.

## Deviation and acceptance boundary

SEC-LEDGER-ROLLBACK-FAILURE was a reachable declared-boundary defect affecting four registered high threats, not accepted risk. Independent ASVS-L2 reassessment closes all 50 declared entries advisory; signed security and Desk gates remain blocked. Genuine oversized boundary is not live Devnet acceptance.

All original eleven descriptions/checks remain unchanged and open; signed acceptance 0/11. Current source and numerical/API evidence do not approve the milestone. Dedicated payer remains unfunded; no genuine Memo signature/slot/readback and no positive live all_passed, so REQ-QTELEPORT-009 and REQ-QTELEPORT-010 stay live-blocked with no waiver. Whole-service final SAST still FAILED 2 HIGH / 6 MEDIUM / 107 LOW with no waiver; exact milestone core/gateway/config 12 LOW. Dependency 47-version audit is not artifact integrity. Independent Desk receipt stamp and final-head Greptile disposition remain required. All 70 stored comment-cohort independent reviews stay active. No archive, release, merge, auto-merge, force-push or branch deletion.
