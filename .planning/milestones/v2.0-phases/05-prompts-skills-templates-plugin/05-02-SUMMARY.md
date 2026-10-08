# Plan 05-02 Summary: Seat Prompt Invariants & Policy

## Execution Results
1. **Seat Invariants Checked:**
   - Every seat prompt (`bot-00` through `bot-06`) specifies `<tools>` pointing to `contracts/tool-rosters/<seat>.yaml`.
   - Tool lists include the exact base counts (LEAD 15, SYSTEMS 14, others 15).
   - Gate tags `g5`/`g6` require `rollback_plan` and `approval_id`.
   - `<memory>` sections define `pd-<seat>` write ownership and shared read banks (`pd-desk`).
   - `<connectors>` state: prefer connector over computer use, never both for one action.
2. **PD-8 External Intake Enforcement:**
   - `prompts/_shared/core-directives.xml` enforces that external requests must enter only through LEAD.
   - Non-LEAD seats hold outside requests and emit held handoffs (priority false) to LEAD without acting.
3. **LEAD Polling Invariants:**
   - LEAD prompt codifies Phase 0 poll: poll held handoffs before intake.
   - `desk-held-poll` runs every 10m.
   - `desk-intake-poll` runs every 10m or on `desk:intake` label events.
