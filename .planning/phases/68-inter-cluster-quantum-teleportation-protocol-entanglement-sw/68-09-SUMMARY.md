---
phase: 68-inter-cluster-quantum-teleportation-protocol-entanglement-sw
plan: "09"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [6c7d8ef, d452fb1]
publication_status: local_unpublished
requirements-completed: []
---

# 68-09 — Original custody, whole-operation cancellation and terminal release

## Parent-owned implementation

Reservation-time instances survive every pair/survivor transfer. Mixed or missing original scope refuses before reservation/effects. Definite pre-effect failure releases only genuinely new grants; existing input leases remain intact.

First potentially applied measurement and reservation interruptions retain original obligations synchronously and bare-reraise the identical exception with zero follow-up awaits. Interrupted failure cleanup retains every remaining lease, not just the first interrupted release. Common primitive and terminal release refuse any automatic new-operation retry of an unresolved original release; duplicate obligations are avoided. Owner release serializes per session, keeps definite pre-send/refusal available, preserves confirmed replay, and treats unknown_lease as non-proof. Bell/survivor outputs activate only after receipt commit.

## Observed verification

Historical custody probe: before 0.46 s / after 0.52 s. Applied/lost release probe: before 0.43 s reissued the original twice with uncertainty 0; after 0.57 s issued once with uncertainty 1 and quarantined. The whole-operation CancelledError/KeyboardInterrupt matrix and the provisional-sink, original-instance, and owner-race regressions passed in the 752 consumer suite at the 6c7d8ef checkpoint.

Final current complete command, run by the parent only:

```bash
TMPDIR=/dev/shm uv run --project services/desk-gateway --no-sync python -m pytest -q --tb=short --show-capture=no --junitxml=/tmp/desk-v51-gateway.xml tests
```

Result: **752 passed in 414.33 s**, exit 0, tool wall 415.77 s. This is a historical checkpoint on product code 6c7d8ef, BEFORE the fresh-review repairs below — not a new-tree final pass and not a new final head. Exact before/failure/after history is in `.receipts/bot-01-systems-backend/v5.1-faithful-simulator.json` on source draft PR 214. Source executors/reviewers ran no checks or commits. Parent integrated source and wrote artifacts.

## Fresh boundary continuation (parent-observed; repair commit pending)

Relevant to this plan: sticky original-instance index plus composed first-measure cleanup interrupt and restoration. Normal release now resolves through the original node/instance/lease index that every uncertainty write maintains, so the 257 actual adopted lost-reply reserves visit 0 history entries on normal release (before: 514 visits). Original ACK-loss obligations survive physical worker absence; the faulty held-lease fixture expectation was corrected with no retry added, and original ambiguity still blocks retries.

First-measure cleanup boundary from the parent-run `/tmp/desk-v51-final-boundaries-smoke.py` (exit 0): BEFORE, tool 2.23 s, showed 4 typed/generic Cancel/KeyboardInterrupt untouched pairs RESERVED with next pair unavailable, sticky NEW input identity, no after-transport, and old halves held 1/1. AFTER, same command 2.39 s and post-scoped-format 2.32 s, showed all 4 ACTIVE with the actual next NEW teleport teleported, and all sticky uncertainty, custody, marker, and no-follow-up invariants preserved.

Current union evidence (parent-observed): new 6 consumer regressions pass 1.94 s / tool 2.97 s (4 custody plus 2 actual public/native proof outages) with no incidental file-size assertion; 759-pass checkpoint at 416.36 s / tool 417.86 s is BEFORE these repairs, not a final complete pass; current CI 299 pass 15.53 s / tool 16.07 s; final formatted full suite (bg 228) still RUNNING with no count inferred; historical pre-claim Bandit FAILED exit 1 / tool 6.81 s over 57408 lines (HIGH 2, MED 6, LOW 107, errors empty, skips 0, nosec 0) with the then-exact milestone core/gateway/config 12 LOW and 8 legacy HIGH/MED unchanged and no waiver (historical checkpoint, superseded by Final stable current below). Latest Devnet read-only balance 0 at confirmed slot 509600313; no new funding request and no eligible provider access mounted. Source published head remains dac2fdf with old product 6c7d8ef as the initial source checkpoint until the parent observes and supplies the new repair commit — none invented here.

**Final stable current (parent-observed bg 235):** final actual stable complete consumer suite: 768 passed in 425.51 s, exit 0, tool 427.04 s, Python 3.14, bg 235, after ALL source corrections including the claim fix. Earlier 752 (6c7d8ef product checkpoint), 759 (pre-repair checkpoint), and 765 (pre-claim checkpoint) remain qualified history, not current. Product commit is new d452fb1, locally committed and unpublished — listed here as local-only with no remote URL claimed. For this plan it confirms the sticky custody and first-measure cleanup surface above. Gates: G1/G3/G4/G5/G6/G7 current PASS; strict G2 shows 2 actual blockers (missing independent stamp; old command-94 git add -f false positive); QUALITY isolated owner repair/push held, not a bypass or waiver. Final SAST: 57419 lines, H2/M6/L105, core 10 LOW, legacy 8 unchanged, exit 1, tool 7.91 s. Source 70 cohort: 49 phase-68 plus 21 phase-69 repaired, 0 new; advisory 50 closed / 57 occurrences, not signed. requirements-completed [] unchanged; signed acceptance 0; live 009/010 remain blocked.

## Deviation and acceptance boundary

Original-instance and cancellation fixes did not change public DTOs, joint-state math, route counts or introduce retry/fallback aliases.

All original eleven descriptions/checks remain unchanged and open; signed acceptance 0/11. Current source and numerical/API evidence do not approve the milestone. Dedicated payer remains unfunded; no genuine Memo signature/slot/readback and no positive live all_passed, so REQ-QTELEPORT-009 and REQ-QTELEPORT-010 stay live-blocked with no waiver. Whole-service final SAST still FAILED 2 HIGH / 6 MEDIUM / 105 LOW over 57419 lines, exit 1, tool 7.91 s, with no waiver; exact milestone core/gateway/config 10 LOW. Dependency 47-version audit is not artifact integrity. Independent Desk receipt stamp and final-head Greptile disposition remain required. All 70 stored comment-cohort independent reviews stay active; phase 68 shows 49 source-repaired with 0 new findings as an actual report, not a remote addressed flag or signoff. No archive, release, merge, auto-merge, force-push or branch deletion.
