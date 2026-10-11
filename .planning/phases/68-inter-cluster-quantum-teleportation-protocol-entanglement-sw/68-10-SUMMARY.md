---
phase: 68-inter-cluster-quantum-teleportation-protocol-entanglement-sw
plan: "10"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [6c7d8ef, d452fb1]
publication_status: local_unpublished
requirements-completed: []
---

# 68-10 — Worker scope, bounded gateway admission and exact-prefix REST verification

## Parent-owned implementation

Duplicate release IDs refuse typed400 before deletion; a later distinct release succeeds. E91 compares actual owned lease.resource_id with pair_id before RNG/session effects. Huge fidelity/amplitude integers fail typed400 instead of OverflowError. The obsolete collector and unused plumbing are removed; durable ledger is the runtime sink.

Six phase68 mutations share4 active slots, immediate429/no queue and an overall60s timeout returning504 with slot recovery. Auth and bounded body admission precede the gate. No E91/drill round truncation. REST proof verification uses the committed exact-size/root checkpoint, rejecting genuine3-to4 and5-to6 same-depth changes while authentic frozen proofs pass.

## Observed verification

Historical admission smoke at the 6c7d8ef checkpoint: actual two CLI workers and gateway smoke exit 0 / tool wall 2.68 s with four applied Alpha reserves and Beta 0; all six fifth-family requests 429 within approximately 0.002 s; 401/403 paths with no additional effects. An applied first-reserve timeout 504 retained original custody at Alpha 1 / Beta 0; the next 200 recovered capacity at Alpha 2 / Beta 1; explicit operator cleanup ended 0/0. Earlier harness failures remain recorded; no false pass.

Final current complete command, run by the parent only:

```bash
TMPDIR=/dev/shm uv run --project services/desk-gateway --no-sync python -m pytest -q --tb=short --show-capture=no --junitxml=/tmp/desk-v51-gateway.xml tests
```

Result: **752 passed in 414.33 s**, exit 0, tool wall 415.77 s. This is a historical checkpoint on product code 6c7d8ef, BEFORE the fresh-review repairs below — not a new-tree final pass and not a new final head. Exact before/failure/after history is in `.receipts/bot-01-systems-backend/v5.1-faithful-simulator.json` on source draft PR 214. Source executors/reviewers ran no checks or commits. Parent integrated source and wrote artifacts.

## Fresh boundary continuation (parent-observed; repair commit pending)

Relevant to this plan: unknown-owner locks plus bounded release index plus odd-width public proof and typed outage. Unknown owner output release now prechecks the existing output before taking the per-session lock and retains the authoritative checks under lock, so 128 actual unknown IDs retain 0 locks (before: locks retained). The bounded original node/instance/lease index covers all uncertainty writes, so the 257 actual adopted lost-reply reserves visit 0 history entries on normal release (before: 514 visits) while original ACK-loss obligations survive.

Odd-width proof boundary: the repair checks that the even-last sibling equals the current hash at every level, preserving authentic odd widths with exact committed verification; the unused root helper was removed and genuine four-to-three and eleven-to-ten higher-level regressions were added. Parent-run `/tmp/desk-v51-final-boundaries-smoke.py` (exit 0): BEFORE, tool 2.23 s, genuine 4-to-3 forgery verified true against the algebraic path but false against committed verification; AFTER, 2.39 s and post-scoped-format 2.32 s, both false with the authentic proof still true. GET proof outage boundary: native closed-connection cursor error now raises a typed LedgerError, both HTTP handlers translate it to 503 ledger_unavailable, and control 200 with auth-first 401 and invalid 400 are preserved (before: both HTTP reads raised native ProgrammingError).

Current union evidence (parent-observed): new 6 consumer regressions pass 1.94 s / tool 2.97 s (4 custody plus 2 actual public/native proof outages) with no incidental file-size assertion; 759-pass checkpoint at 416.36 s / tool 417.86 s is BEFORE these repairs, not a final complete pass; current CI 299 pass 15.53 s / tool 16.07 s; final formatted full suite (bg 228) still RUNNING with no count inferred; historical pre-claim Bandit FAILED exit 1 / tool 6.81 s over 57408 lines (HIGH 2, MED 6, LOW 107, errors empty, skips 0, nosec 0) with the then-exact milestone core/gateway/config 12 LOW and 8 legacy HIGH/MED unchanged and no waiver (historical checkpoint, superseded by Final stable current below). Latest Devnet read-only balance 0 at confirmed slot 509600313; no new funding request and no eligible provider access mounted. Source published head remains dac2fdf with old product 6c7d8ef as the initial source checkpoint until the parent observes and supplies the new repair commit — none invented here.

**Final stable current (parent-observed bg 235):** final actual stable complete consumer suite: 768 passed in 425.51 s, exit 0, tool 427.04 s, Python 3.14, bg 235, after ALL source corrections including the claim fix. Earlier 752 (6c7d8ef product checkpoint), 759 (pre-repair checkpoint), and 765 (pre-claim checkpoint) remain qualified history, not current. Product commit is new d452fb1, locally committed and unpublished — listed here as local-only with no remote URL claimed. For this plan it confirms the unknown-lock, bounded-index, and odd-width proof/outage surface above. Gates: G1/G3/G4/G5/G6/G7 current PASS; strict G2 shows 2 actual blockers (missing independent stamp; old command-94 git add -f false positive); QUALITY isolated owner repair/push held, not a bypass or waiver. Final SAST: 57419 lines, H2/M6/L105, core 10 LOW, legacy 8 unchanged, exit 1, tool 7.91 s. Source 70 cohort: 49 phase-68 plus 21 phase-69 repaired, 0 new; advisory 50 closed / 57 occurrences, not signed. requirements-completed [] unchanged; signed acceptance 0; live 009/010 remain blocked.

## Deviation and acceptance boundary

The smoke shortened only its internal test timeout to 0.05 s; production overall 60 s and phase 69 sample counts remain unchanged.

All original eleven descriptions/checks remain unchanged and open; signed acceptance 0/11. Current source and numerical/API evidence do not approve the milestone. Dedicated payer remains unfunded; no genuine Memo signature/slot/readback and no positive live all_passed, so REQ-QTELEPORT-009 and REQ-QTELEPORT-010 stay live-blocked with no waiver. Whole-service final SAST still FAILED 2 HIGH / 6 MEDIUM / 105 LOW over 57419 lines, exit 1, tool 7.91 s, with no waiver; exact milestone core/gateway/config 10 LOW. Dependency 47-version audit is not artifact integrity. Independent Desk receipt stamp and final-head Greptile disposition remain required. All 70 stored comment-cohort independent reviews stay active; phase 68 shows 49 source-repaired with 0 new findings as an actual report, not a remote addressed flag or signoff. No archive, release, merge, auto-merge, force-push or branch deletion.
