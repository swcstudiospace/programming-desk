# Cross-Bot Protocol

How a feature spanning multiple seats gets built without the specialists colliding.

LEAD (`bot-00-programming-lead`) is the integrating orchestrator. LEAD writes the tickets, names
the seats, and consolidates when the work returns. Specialists do not nominate themselves and do
not start from desk chat. Intake and dispatch live in `docs/desk-operating-model.md`; this
document is the contract ordering those tickets have to follow.

This document exists because the system is decomposed by platform rather than by lifecycle. That
choice buys deep platform expertise per seat and costs a clear owner for any feature that crosses
platforms. The protocol is the payment. LEAD is outside the six-member Programming Desk channel
and does not implement the feature in order to integrate it.

---

## The problem, concretely

> "Add push notifications."

Touches: Bot 1 (send API, device token storage), Bot 3 (Android FCM integration), Bot 4 (iOS APNs
integration), Bot 5 (credentials, certificate rotation).

Done naively, four bots edit one branch. Bot 1 names the field `device_token`, Bot 4 reads
`deviceToken`, Bot 3 assumes it's `fcm_token`, and nobody finds out until integration — or worse,
until a user reports that notifications stopped.

The instinct is to have one bot do everything. That defeats the decomposition: you get a bot
writing Swift it does not specialise in, badly.

---

## The protocol

```
   ┌─────────────────────────────────────────────────────────────────┐
   │ 1. LEAD TICKETS                                                 │
   │    One ticket per specialist. Paths, acceptance, non-goals.     │
   │    LEAD integrates. No specialist self-nominates.               │
   └───────────────────────────┬─────────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 2. CONTRACT PR  ── merged BEFORE any implementation             │
   │    Types, endpoints, events, errors, versioning.                │
   │    Every consumer in contract_consumers acknowledges.           │
   │    Gate G-4 enforces the acknowledgements.                      │
   └───────────────────────────┬─────────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 3. IMPLEMENT  ── in parallel, each specialist in its OWN paths  │
   │    Against the contract. Never against another seat's code.     │
   │    Each produces its own verification receipt.                  │
   └───────────────────────────┬─────────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 4. REVIEW AND CONSOLIDATE                                       │
   │    QUALITY reviews. LEAD consolidates receipts for Ove.         │
   │    LEAD does not re-implement and does not replace the review.  │
   └─────────────────────────────────────────────────────────────────┘
```

**The contract merges first.** That single ordering constraint is what lets four bots work
simultaneously without reading each other's diffs. They are all writing against a fixed interface
rather than a moving one.

---

## Step 1 — LEAD writes the tickets

LEAD is always the integrator. The table says which specialist LEAD assigns to each surface, not
which specialist gets to run the feature.

| Feature | Specialist LEAD assigns | Why that seat implements it |
|---|---|---|
| Push notifications | SYSTEMS, plus ANDROID, IOS, INFRA | SYSTEMS owns the send API; clients and credentials are separate seats |
| New onboarding screen | WEB, ANDROID, or IOS | Whichever platform ships it; one ticket per platform if all three |
| Faster search | SYSTEMS | The work is server-side; clients consume unchanged |
| Offline mode on mobile | ANDROID or IOS | Client-owned; the backend contract barely moves |
| Cutting deploy time | INFRA | Wholly within its domain |

Tie-break, when two seats could own a surface: **the seat the user would blame if that surface
broke.** LEAD still consolidates either way. LEAD does not ack a contract for a specialist.

## Step 2 — The contract PR

Lives in `contracts/`, owned by Bot 6, changed by proposal from any bot.

A contract change states:

```yaml
change_id: feat-push-notifications-v1
proposed_by: bot-01-systems-backend
surface: contracts/api/notifications.yaml
breaking: false
version: 1.4.0

summary: Adds device token registration and a send endpoint.

consumers_required:
  - bot-02-web-edge
  - bot-03-android
  - bot-04-ios

acknowledgements:
  - bot: bot-03-android
    ack: true
    note: "FCM token format fits; needs the 4096-char limit documented."
  - bot: bot-04-ios
    ack: true
    note: "APNs tokens are hex; confirmed the field is a string not bytes."
  - bot: bot-02-web-edge
    ack: true
    note: "Web push out of scope for v1; no client change needed."
```

**An acknowledgement is a commitment, not a formality.** A bot that acks a contract is saying it
can implement against it. "Looks fine" without having checked the field types is how the
`device_token` / `deviceToken` problem arrives anyway, one step later.

A bot that cannot implement the contract **must reject it** with the specific blocker. That is a
cheap, early conversation; the alternative is an expensive, late one.

## Step 3 — Implement in parallel

Each bot works only in its own paths (G-1) and produces its own receipt (G-2).

**Implementation never blocks on another bot's implementation.** If Bot 3 needs something Bot 1
has not built yet, it builds against the contract with a stub. If the stub reveals the contract is
wrong, that is a contract amendment — go back to step 2. It is not a reason to reach into Bot 1's
paths.

## Step 4 — QUALITY reviews, LEAD consolidates

QUALITY reviews the change set, including whether the implementations match the contract they
acked. QUALITY does not patch the code. LEAD then consolidates the receipts and that verdict for
Ove. LEAD's consolidation cites specialist receipt paths and the gate commands LEAD actually ran.
It is not a second implementation pass, and it is not a substitute for the review.

---

## Amending a contract mid-flight

It happens. The protocol is:

1. **Stop implementation** on the affected surface. Do not work around it locally — a local
   workaround becomes the de-facto contract and nobody else knows.
2. Amend the contract PR with the change and the reason.
3. Re-acknowledge. Only consumers affected by the delta need to re-ack.
4. Resume.

The cost of stopping is hours. The cost of two bots holding different beliefs about the same
interface is found in production.

---

## Anti-patterns

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| "I'll just edit their file, it's a one-liner" | Bypasses ownership, invisible to the owner, G-1 blocks it | Contract change or a request to the owner, ticketed by LEAD |
| Implementation before contract | Contract gets retrofitted to the first implementation; other consumers inherit its accidents | Contract PR first, always |
| Rubber-stamp acknowledgement | Reintroduces the exact bug the protocol prevents | Check the field types; ack means "I can build this" |
| One bot does everything | Loses the platform expertise the decomposition bought | LEAD tickets each seat; LEAD does not become the doer |
| Specialist starts from desk chat | Chat is status, not a ticket | Wait for a LEAD ticket, or a direct ask from Ove copied to LEAD |
| Local workaround for a wrong contract | Becomes a hidden second contract | Stop and amend |
| Verbal agreement in a thread | Not machine-checkable, not durable, invisible to G-4 | Record it in the contract PR |

---

## When the protocol is overkill

Not every change needs this. Use judgement:

- **Single-seat change, no contract touched** → LEAD still writes the ticket (or Ove asks that
  seat directly and the seat copies LEAD). Ownership and receipt gates apply; this protocol's
  contract steps do not.
- **Additive, non-breaking contract change** → contract PR still first, but acknowledgement is
  informational rather than blocking.
- **Breaking change** → full protocol, no exceptions.

The protocol's weight should scale with the blast radius. A new optional field does not need four
sign-offs; removing a field does.
