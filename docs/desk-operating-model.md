# Desk operating model

How work enters the Programming Desk, who may start it, and how it comes back to Ove.

Seven seats. One of them does not sit in the channel.

| Seat | Bot id | Where they sit | Job |
|---|---|---|---|
| **LEAD** | `bot-00-programming-lead` | Outside the desk channel | Orchestrate. Tickets, dispatch, consolidate. |
| **SYSTEMS** | `bot-01-systems-backend` | Programming Desk channel | Services, APIs, data. |
| **WEB** | `bot-02-web-edge` | Programming Desk channel | Browser, edge, Vercel. |
| **ANDROID** | `bot-03-android` | Programming Desk channel | Android app and Play release. |
| **IOS** | `bot-04-ios` | Programming Desk channel | iOS app and App Store release. |
| **INFRA** | `bot-05-infrastructure` | Programming Desk channel | IaC, Kubernetes, CI, dev machine. |
| **QUALITY** | `bot-06-quality-security` | Programming Desk channel | Review, gates, contracts. Read everywhere, write almost nowhere. |

In-repo identity is the callsign and the bot id. Live agent UUIDs live in the Grok Bot agent map.
This repository does not store them and does not require them as configuration.

## Channel constraint

The live Programming Desk chat channel holds **at most six members**. LEAD is not one of them.
The six specialists fill those seats. LEAD stays outside and orchestrates by ticket and by direct
message.

Joining the channel to "keep an eye on things" is not a workaround. A seventh member does not fit.
Dropping a specialist to make room would leave a platform without a seat. Status that the whole
desk needs is posted by the specialists; LEAD reads it because they copy LEAD, not because LEAD
is in the room.

## Who may create work

Ove messages LEAD. LEAD writes a concrete ticket and dispatches the specialist who owns the paths.

Two other inputs are valid, and they still land on LEAD's record:

- **Ove asks a specialist directly.** The specialist does the work and copies LEAD. LEAD records
  the ticket so the log matches. LEAD does not restart the task.
- **A specialist is blocked or sees scope that belongs to another seat.** They escalate to LEAD.
  They do not recruit each other, and they do not edit each other's paths.

The desk channel is **status and coordination**. It is not a backlog. A message in chat does not
authorise a branch. If chat starts to sound like a feature, the specialist asks LEAD for a ticket
or LEAD says the idea is not assigned.

## Flow

```
Ove
  │  intake
  ▼
LEAD writes a ticket (one specialist, paths, acceptance, non-goals)
  │  dispatch          LEAD is outside the six-member channel
  ▼
Specialist implements only that ticket, only in owned paths
  │  receipt           commands and exit codes (G-2)
  ▼
QUALITY reviews        read everywhere, write almost nowhere
  │  verdict
  ▼
LEAD consolidates      cites specialist receipts; does not re-claim their runs
  │
  ▼
Ove                    what is verified, what is not, what decision is needed
```

Cross-seat features add a contract step in front of implementation. The contract merges first,
every consumer acknowledges, then LEAD's implementation tickets run in parallel. Protocol:
`docs/cross-bot-protocol.md`. Events: `docs/handoff-contracts.md`.

### What a ticket contains

- `task_id` in kebab-case
- one specialist, by bot id
- paths in scope and paths out of scope
- acceptance: the observation that would show the work is done
- contract surface, if any, and the rule that implementation waits on `contract.merged`
- verification expected, and anything that may honestly remain unverified

If LEAD cannot name the owner and the acceptance check, there is no ticket yet.

## QUALITY stays asymmetric

QUALITY reads every path and writes almost none: gates, hooks, `ownership.yaml`, `SECURITY.md`,
`contracts/`, and most of `docs/`. A defect in SYSTEMS is a finding sent to SYSTEMS, with LEAD
copied so the consolidation is honest. QUALITY does not patch the code it is reviewing, does not
dispatch other specialists, and does not approve its own gate changes. Those still go to a human.

`docs/desk-operating-model.md` is the exception inside `docs/`: LEAD owns it. Last matching
pattern in `ownership.yaml` wins.

## Receipts and gates

G-1 through G-6 are unchanged. LEAD does not get a quieter set of rules.

- A specialist's completion claim needs a receipt in `.receipts/<bot-id>/`.
- LEAD's consolidation receipt lives in `.receipts/bot-00-programming-lead/`. Claims in it cite
  commands LEAD ran (gate checks against the specialist receipts, manifest validation). Specialist
  test results are referenced by receipt path. LEAD does not write "tests passed" as if LEAD had
  run them.
- `approved_by` is never the authoring bot. QUALITY or Ove approves specialist work. A human
  approves LEAD's own edits to this model and to LEAD's prompt.
- Destructive operations and production deploys still need the recorded human approval. A ticket
  is not that approval.

## What nobody does

| Who | Does not |
|---|---|
| LEAD | Implement specialist paths; join the six-member channel; treat chat as a ticket; approve LEAD's own prompt or operating-model edit |
| Specialists | Invent work from desk chat; edit another seat's paths; recruit each other; skip the copy to LEAD when Ove asked them directly |
| QUALITY | Fix the code under review; weaken a gate to unblock a seat; dispatch implementation |

Ownership, contract acknowledgements, and verification receipts stay the controls. This document
is who is allowed to *start* the work those controls then check.
