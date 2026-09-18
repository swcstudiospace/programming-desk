# Cross-Bot Protocol

How a feature spanning multiple bots gets built without the bots colliding.

This document exists because the system is decomposed by platform rather than by lifecycle. That
choice buys deep platform expertise per bot and costs a clear owner for any feature that crosses
platforms. The protocol is the payment.

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
   │ 1. NOMINATE                                                     │
   │    The bot owning the user-facing surface integrates.           │
   │    Ambiguous? The bot the user would blame if it broke.         │
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
   │ 3. IMPLEMENT  ── in parallel, each bot in its OWN paths         │
   │    Against the contract. Never against another bot's code.      │
   │    Each produces its own verification receipt.                  │
   └───────────────────────────┬─────────────────────────────────────┘
                               ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ 4. INTEGRATE                                                    │
   │    Integrating bot verifies end to end.                         │
   │    Bot 6 reviews. Receipts are consolidated.                    │
   └─────────────────────────────────────────────────────────────────┘
```

**The contract merges first.** That single ordering constraint is what lets four bots work
simultaneously without reading each other's diffs. They are all writing against a fixed interface
rather than a moving one.

---

## Step 1 — Nominate the integrating bot

The bot that owns the surface the user actually touches.

| Feature | Integrating bot | Why |
|---|---|---|
| Push notifications | Bot 1 (Backend) | It owns the send API that everything else consumes |
| New onboarding screen | Bot 2 / 3 / 4 | Whichever platform ships it; one per platform if all three |
| Faster search | Bot 1 (Backend) | The work is server-side; clients consume unchanged |
| Offline mode on mobile | Bot 3 or Bot 4 | Client-owned; the backend contract barely moves |
| Cutting deploy time | Bot 5 (Infrastructure) | Wholly within its domain |

Tie-break: **the bot the user would blame if the feature broke.**

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

## Step 4 — Integrate

The integrating bot verifies end to end and consolidates receipts. Bot 6 reviews the whole change
set, including whether the implementations actually match the contract they acked.

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
| "I'll just edit their file, it's a one-liner" | Bypasses ownership, invisible to the owner, G-1 blocks it | Contract change or a request to the owner |
| Implementation before contract | Contract gets retrofitted to the first implementation; other consumers inherit its accidents | Contract PR first, always |
| Rubber-stamp acknowledgement | Reintroduces the exact bug the protocol prevents | Check the field types; ack means "I can build this" |
| One bot does everything | Loses the platform expertise the decomposition bought | Nominate an integrator, not a doer |
| Local workaround for a wrong contract | Becomes a hidden second contract | Stop and amend |
| Verbal agreement in a thread | Not machine-checkable, not durable, invisible to G-4 | Record it in the contract PR |

---

## When the protocol is overkill

Not every change needs this. Use judgement:

- **Single-bot change, no contract touched** → just build it. Ownership and receipt gates apply,
  nothing else.
- **Additive, non-breaking contract change** → contract PR still first, but acknowledgement is
  informational rather than blocking.
- **Breaking change** → full protocol, no exceptions.

The protocol's weight should scale with the blast radius. A new optional field does not need four
sign-offs; removing a field does.
