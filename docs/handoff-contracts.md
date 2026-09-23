# Handoff Contracts

Bots coordinate through typed events rather than direct calls, so that every handoff is logged,
replayable and attributable.

LEAD (`bot-00-programming-lead`) is the integrating orchestrator. A specialist may start work on
`ticket.assigned` from LEAD, or on a direct ask from Ove with LEAD copied. Desk chat is status.
It is not an event that authorises scope. LEAD is outside the six-member Programming Desk channel;
these events are how the desk reaches LEAD without putting LEAD in that channel.

## Envelope

```json
{
  "envelope_version": "1.0",
  "message_id": "<uuid>",
  "correlation_id": "<uuid>",
  "causation_id": "<uuid|null>",
  "emitted_by": "bot-01-systems-backend",
  "emitted_at": "<iso8601>",
  "event_type": "contract.proposed",
  "subject": { "type": "contract", "id": "contracts/api/notifications.yaml" },
  "payload": { },
  "receipt_path": ".receipts/<bot-id>/<task-id>.json",
  "requires_human_gate": false,
  "idempotency_key": "<deterministic from business facts>"
}
```

- `correlation_id` threads a whole feature across bots end to end.
- `causation_id` gives a causal tree — which message produced which.
- `receipt_path` links the event to its evidence (G-2).
- `idempotency_key` is derived from the facts, so a replay is a no-op rather than a duplicate.

## Event catalogue

| Event | Emitter | Consumer | Effect |
|---|---|---|---|
| `ticket.assigned` | bot-00 | named specialist | **Authorises that specialist's scope** |
| `ticket.escalated` | specialist | bot-00 | Blocker, scope change, or cross-seat need |
| `contract.proposed` | any | consumers, bot-00 | Acknowledgement requested |
| `contract.acknowledged` | consumer | proposer, bot-00 | One ack recorded |
| `contract.rejected` | consumer | proposer, bot-00 | **Blocks merge.** Blocker stated |
| `contract.merged` | bot-06 | all | **Unlocks implementation** |
| `implementation.started` | specialist | bot-00 | Status only. Does not widen the ticket |
| `implementation.completed` | specialist | bot-00, bot-06 | Receipt attached |
| `review.requested` | any | bot-06, bot-00 | Review queued |
| `review.completed` | bot-06 | author, bot-00 | approve / request_changes / block |
| `lead.consolidated` | bot-00 | Ove, bot-06 | Receipts and the QUALITY verdict in one status |
| `gate.failed` | CI | author, bot-00 | Which gate, and why |
| `deploy.requested` | any | human gate | Needs rollback plan (G-5) |
| `destructive.requested` | any | human gate | Needs approval (G-6) |
| `incident.declared` | any | all | **Broadcast. Non-incident deploys pause** |

`incident.declared` is the only broadcast. Every bot honours it within its current work unit
rather than at the next poll — continuing to ship into an active incident is how a small outage
becomes a confusing one.

## Key payloads

### `contract.proposed`

```json
{
  "change_id": "feat-push-notifications-v1",
  "surface": "contracts/api/notifications.yaml",
  "breaking": false,
  "version": "1.4.0",
  "previous_version": "1.3.2",
  "summary": "Adds device token registration and a send endpoint.",
  "semantic_changes": [],
  "migration_note": "<required when breaking>",
  "consumers_required": ["bot-02-web-edge", "bot-03-android", "bot-04-ios"]
}
```

`semantic_changes` is mandatory even when empty. A field whose *meaning* changed while its name and
type did not is undetectable by any tool — the only defence is a declaration, and the only way to
get one is to require it.

### `review.completed`

```json
{
  "review_id": "<uuid>",
  "subject": { "bot": "bot-02-web-edge", "task_id": "fix-pagination" },
  "verdict": "request_changes",
  "receipt_assessment": {
    "receipt_present": true,
    "claims_substantiated": false,
    "unverified_honest": true,
    "issues": ["claim 'no regressions' cites only the new test file"]
  },
  "findings": [
    { "severity": "high", "category": "correctness",
      "file": "web/lib/pagination.ts", "line": 42,
      "summary": "Offset drops the last page when total is an exact multiple of page size",
      "failure_scenario": "40 items, pageSize 20: page 2 requests offset 40, returns empty.",
      "suggested_owner": "bot-02-web-edge" }
  ]
}
```

Every finding carries a concrete failure scenario and names the owning bot — Bot 6 reports, it
does not fix.

## Idempotency

| Event | Key |
|---|---|
| `ticket.assigned` | `task_id + ':' + bot_id` |
| `contract.proposed` | `change_id` |
| `implementation.completed` | `task_id + ':' + commit_sha` |
| `review.completed` | `review_id` |
| `lead.consolidated` | `correlation_id + ':' + head_sha` |
| `deploy.requested` | `commit_sha + ':' + environment` |

LEAD keeps a processed-key set with a 30-day TTL; duplicates are acknowledged and dropped.
