# Phase 3 Plan 01 Summary: Companion Integration Policy & Environment Boundaries

**Recorded on:** 2026-10-08
**Status:** Complete
**Plan:** `.planning/phases/03-substrate-data-planes/03-01-PLAN.md`
**Requirements:** REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-DATA-005, REQ-DATA-006

## Summary

1. **Companion Data-Planes Policy (`REQ-DATA-001`):**
   - Codified five-store data policy specifications matching `docs/upgrade-plan-desk-v2.md` §6.
   - Identified stores, schemas, writers, TTLs, and prohibited data types (no unredacted secrets or full transcripts).
2. **Companion Tailscale Networking Contract (`REQ-DATA-002`):**
   - Established forwarder, exact-port ACL, cutover, and rollback rules for substrate connectivity over Tailscale.
3. **Substrate Environment Contract (`REQ-DATA-003`, `REQ-DATA-004`):**
   - Codified environment variable contracts: `HINDSIGHT_URL`, `HINDSIGHT_API_KEY`, `HINDSIGHT_BANK_PREFIX`, `DRAGONFLY_URL`, `SUBSTRATE_TOKEN_DESK_GATEWAY`.
   - Explicitly eliminated `AGENTMEMORY_*` variables and validated all placeholders against Gate G-3.
4. **Substrate GSD Replan Boundaries (`REQ-DATA-005`, `REQ-DATA-006`):**
   - Re-planned Phase 5 (tailnet RAGFlow docs), Phase 7 (Hindsight migration), and Phase 8 (Dragonfly cache-only) to be governed in `agent-substrate` companion repository.
