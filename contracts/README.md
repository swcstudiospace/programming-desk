# contracts/

**The only shared surface between seats.** Owned by QUALITY (`bot-06-quality-security`),
changed by proposal from any bot.

Every other path in this repository resolves to exactly one owner, and a bot may only write
inside its own paths (G-1). That decomposition buys platform depth and costs a shared editing
space — so the one interface every seat reads is held by the seat that writes no product code.
A reviewer that can quietly reshape the interface it is reviewing is not a reviewer.

This directory is a **skeleton**. It is committed empty-of-product on purpose: G-4
(`ci/gates/check_contracts.py`) needs a surface to watch, and a gate with nothing to guard is a
gate nobody notices has stopped working.

---

## Layout

```
contracts/
├── api/          Request/response surfaces. Consumers: WEB, ANDROID, IOS.
├── events/       Async messages and their envelopes. Consumers: SYSTEMS, WEB, INFRA.
└── changes/      One change document per proposed contract change. The G-4 input.

openapi.yaml      Repo root. The HTTP surface, when there is one.
**/*.proto        Anywhere in the tree. Stays QUALITY-owned even under web3/ or chains/.
```

The consumer list for each surface lives in `ownership.yaml` under `contract_consumers`, not
here. One list, machine-read by the gate, rather than a prose copy that drifts.

---

## Changing a contract

The order is the whole point: **the contract merges before any implementation.** That single
constraint is what lets four seats build simultaneously against a fixed interface instead of a
moving one.

```
1. DRAFT        A change document in contracts/changes/. Version, breaking flag,
                migration note if breaking.
2. IDENTIFY     Consumers, from ownership.yaml → contract_consumers.
3. ACKNOWLEDGE  Every consumer confirms it can build against this.
4. MERGE        The contract lands first, alone.
5. IMPLEMENT    Each seat, in its own paths, in parallel.
```

Full protocol: `docs/cross-bot-protocol.md`. Breaking-change analysis and the expand-contract
technique that avoids most of them: `skills/contract-first-changes/SKILL.md`.

### What G-4 enforces

A **breaking** change needs a major version bump, a migration note, and a positive
acknowledgement from *every* listed consumer. A **non-breaking** change still needs a change
document; acknowledgements are informational, but a rejection blocks.

Both need the declared surfaces (`surface`, plus `surfaces` for anything further) to cover
every contract-surface file in the diff. That is what ties a document to a change: without it, a
document left in `contracts/changes/` after its own change merged will validate a later,
unrelated one, because the caller selects a document by globbing the directory.

Both also need `semantic_changes` declared explicitly — `[]` if there are none. A field whose
*meaning* changed while its name and type stayed the same is the one change no tool detects, and
every consumer's behaviour shifts under it silently. Declaring it requires noticing it, which
requires being asked. The gate asks.

```bash
python3 ci/gates/check_contracts.py --base origin/main \
    --change contracts/changes/<change-id>.yaml
```

### Acknowledgement means "I can build this"

Not "looks fine". A consumer that acks without checking the field types reintroduces exactly the
bug the protocol prevents — one step later, and with a paper trail suggesting it was agreed. A
consumer that cannot implement the change must reject it with the specific blocker: a cheap,
early conversation instead of an expensive, late one.

---

## Adding the first real contract

1. Put the schema under `api/` or `events/` — OpenAPI, JSON Schema or `.proto`, whichever fits
   the surface. Add the path pattern to `contract_consumers` in `ownership.yaml` if no existing
   pattern covers it, or G-4 fails with *"no consumers resolved"*, which is the gate correctly
   refusing to guess who is affected.
2. Write the change document (`contracts/changes/TEMPLATE.yaml.example`).
3. Collect the acknowledgements on the pull request.
4. Merge the contract on its own, then implement.
