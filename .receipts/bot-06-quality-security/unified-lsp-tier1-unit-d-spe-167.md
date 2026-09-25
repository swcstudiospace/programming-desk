# Unit D / SPE-167 — QUALITY sandbox recheck (PR #9)

- **Seat:** bot-06-quality-security (QUALITY)
- **Kind:** unit-d-sandbox-security-critique-recheck
- **PR:** https://github.com/swcstudiospace/programming-desk/pull/9 (draft)
- **Branch:** `bot-00-programming-lead/unified-lsp-tier1-ut-tlvsqj-b31b8fe2`
- **Graph / Linear:** `ut-tlvsqj-b31b8fe2` / SPE-167 (n6)
- **Policy head reviewed:** `73af5d6376d8ffaaf80359f2b3e0bff72ec631f1`
- **Prior blocked head:** `f5982ef3701e28e7887491ed93f5acfdacca161e`
- **Reviewed at:** 2026-09-25 ~10:35 AEST

## Disposition

**`SPIKE_SANDBOX_CLEAR`**

- **Spike-done?** YES (for F1–F5 spike-done gates; fixture LS only).
- **merge_claim.allowed:** false. This is Unit D spike-sandbox only — **not** Greptile merge-gate, **not** undraft/merge authority.
- **approved_by:** `bot-00-programming-lead` (G-2 independent slot; LEAD requested the recheck). Authoring bot remains `bot-06-quality-security`. Stamps Unit D CLEAR for SPE-167 only.

## Checklist (SPE-167)

| # | Item | Status |
|---|---|---|
| 1 | Child-process isolation | **PASS** for spike (killpg reaps grandchild; env scrubbed). F6 sandbox/rlimits deferred. |
| 2 | MCP input validation | **PASS** for spike (extension allowlist, denylist, NUL/size/utf8). |
| 3 | Diagnostics redaction | **PASS** (`API_KEY=[REDACTED]`; caps). |
| 4 | Install trust | **PASS** for spike (fixture-only; no network install). F7 pins deferred. |
| 5 | WS off-by-default | **PASS** (optional; loopback; Origin+token; frame cap). |

## F1–F5 / F8

| ID | Status | Evidence |
|---|---|---|
| F1 | **FIXED** | Evil/missing Origin → 403; bad/missing token → 401; good → 101; broker alive after huge frame |
| F2 | **FIXED** | `.env` / `*.key` / `id_rsa` / `.git/config` → `extension_not_allowed`; no secret leak |
| F3 | **FIXED** | `fine API_KEY=[REDACTED]` |
| F4 | **FIXED** | Relative `path`; no `bin`/`stderr`/`fixture` in public results |
| F5 | **FIXED** | Grandchild alive before stop, dead after; `killpg` used |
| F8 | **FIXED** | NUL → `invalid_arguments`; broker up |
| F6/F7 | **DEFERRED** | Per LEAD; not blocking spike-done |

## Commands

1. PR tip verify → `73af5d6…` (exit 0)
2. Clone + `git rev-parse` → same SHA (exit 0)
3. `python3 infra/unified-lsp-broker/spike_proof.py` → `SPIKE_OK` … `f1…f8` (exit 0)
4. `npx node@22 --experimental-strip-types web/mcp-unified-lsp/spike_proof.ts` → `MCP_SPIKE_OK` (exit 0)
5. Adversarial `probes.py` → all F1–F4/F8 summary true (exit 0)
6. `grandchild_probe.py` → `F5_pass: true` (exit 0)
7. G-3 secrets → PASS
8. G-1 ownership on these receipt paths → PASS
9. G-2 receipt → PASS with `approved_by=bot-00-programming-lead`

## Deferred / unverified

- F6/F7, real LS, G-1 multi-seat, `**/*.go` ownership, `contracts/**` promotion, Greptile (not run; do not trust stale Greptile F1 comments vs this head).

## Actions not taken

No undraft, no merge, no Greptile trigger, no `merge_claim.allowed=true`, no edits outside `.receipts/bot-06-quality-security/**`.
