# Desk Operating Model — Seven-Seat Programming Desk

Programming Lead sits **outside** the Programming Desk channel and orchestrates. Six specialists
sit in the channel (platform max 6 members). Lead + six = seven-seat desk.

```
Ove ──▶ LEAD (outside channel) ──SendToAgent──▶ specialists (1:1)
              │                                      │
              │         optional status ping         │
              └──────────▶ Desk channel ◀────────────┘
              │
              └──▶ QUALITY review ◀── receipts
              │
              └──▶ report to Ove
```

## Flow

For a real build, fix, research, or change, intake is the dense GoTxCoT path in
`docs/gotxcot-cloud-pipeline.md` and `skills/gotxcot-uplift` — not a short paraphrase.

1. **Drop prompt in** — Ove messages LEAD with the plain ask.
2. **First uplift** — LEAD rewrites it into long nested XML (`BUILD_PROMPT` / `FIX_PROMPT` / `RESEARCH_PROMPT` / `CHANGE_PROMPT` / `UPLIFTED_PROMPT`).
3. **GoT + CoT** — **5–8 nodes**, then **4–8 CoT steps per node**, one node at a time unless parallel fill is safe.
4. **Trackers** — Notion Agent Task Graph (Task → Issue → Sub-Issue) and Linear (one issue per node, one sub-issue per step). `Agent` = `cursor-cloud` when Cloud Agents execute.
5. **Second uplift** — the same XML, extended with `<ISSUES>` and live Notion/Linear URLs.
6. **Dispatch** — `skills/trackplan-dispatch` to Cursor Cloud Agent (default) or Hermes. Lane C specialist tickets (below) still carry the relevant issue/sub-issue URLs.
7. **Implement** — Specialist executes only assigned work in owned paths; writes a receipt. Specialists do not re-run uplift.
8. **Receipt** — Specialist reports to LEAD with receipt path + summary.
9. **QUALITY** — LEAD requests review when a completion claim needs an independent check, including the Greptile merge gate on the PR.
10. **Consolidate / report** — LEAD reports to Ove. Specialists do not invent work from desk-channel vibes.

A small, already-scoped ask may skip straight to a Lane C ticket when LEAD records why a full graph is not warranted (trivial ack, single-file question already answered). Real build tasks do not skip the 5-node minimum.

## Lane C ticket flow

1. **Intake** — goal, constraints, and success criteria are already in the second uplift when the graph ran.
2. **Ticket** — LEAD writes one concrete ticket per owning seat (see format below).
3. **Dispatch** — LEAD `SendToAgent` to each seat 1:1 (never vague "please help").
4. **Implement** — Specialist executes only assigned work in owned paths; writes a receipt.
5. **Receipt** — Specialist reports to LEAD with receipt path + summary.
6. **QUALITY** — LEAD requests review when a completion claim needs an independent check.
7. **Consolidate** — LEAD consolidates specialist receipts + QUALITY verdict.
8. **Report** — LEAD reports to Ove. Specialists do not invent work from desk-channel vibes.

Cross-seat features: **contract-first via QUALITY**, then parallel tickets
(`docs/cross-bot-protocol.md`). LEAD is the integrating orchestrator who opens the work and
consolidates — not the implementer.

## Ticket format

```markdown
## Ticket

- **task_id:** feat-push-notifications-android
- **owner:** bot-03-android (ANDROID)
- **goal:** Register FCM device tokens and display data-message notifications per contract v1.4.0
- **paths_in_scope:**
  - android/app/src/main/**/notifications/**
  - android/app/src/test/**/notifications/**
- **out_of_scope:**
  - Backend send API (SYSTEMS)
  - iOS APNs (IOS)
  - Infra credentials (INFRA) unless this ticket says otherwise
- **trackers:** (when a graph exists) Graph ID, Notion Issue/Sub-Issue URLs, Linear issue/sub-issue URLs from the second uplift. Do not paste the entire XML into chat if the packet already lives on the branch; cite it.
- **success_criteria:**
  - Unit tests for token registration pass (`./gradlew :app:testDebugUnitTest`)
  - Receipt at `.receipts/bot-03-android/<task_id>.json` with cited commands
  - No owned-path violations (G-1)
- **report_back:**
  - Receipt path
  - Summary of files changed
  - `unverified` list (devices / OS versions not exercised)
  - Blockers for LEAD (if any)
```

## Channel rules

| Actor | Channel | Assignment |
|---|---|---|
| LEAD | Outside (not a member) | Writes tickets; optional status after assign |
| Specialists | Members | Status only; tickets come via SendToAgent |
| Ove | Messages LEAD | Primary operator interface |

If a specialist is woken by a desk-channel ping with **no LEAD ticket**: acknowledge to LEAD; do
not invent work.

## Verification

LEAD never fabricates specialist receipts. "Done" to Ove requires consolidated specialist
receipts and QUALITY approval when review was requested. Honest `unverified` lists are success;
silent incompleteness is not (PD-1, PD-6).
