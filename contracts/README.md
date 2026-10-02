# contracts/

**The only shared surface between seats.** Owned by QUALITY (`bot-06-quality-security`),
changed by proposal from any bot.

Every other path in this repository resolves to exactly one owner, and a bot may only write
inside its own paths (G-1). That decomposition buys platform depth and costs a shared editing
space — so the one interface every seat reads is held by the seat that writes no product code.
A reviewer that can quietly reshape the interface it is reviewing is not a reviewer.

Proposals arrive through `desk_contract_propose` and are acknowledged by consumers through
`desk_contract_ack`; enforcement is G-4 (`ci/gates/check_contracts.py`) for the change protocol
and G-7 (`ci/gates/check_desk_integrity.py`) for the tool rosters below.

---

## Layout

```
contracts/
├── api/            Request/response surfaces. Consumers: WEB, ANDROID, IOS.
├── events/         Async messages and their envelopes. Consumers: SYSTEMS, WEB, INFRA.
├── tool-rosters/   The MCP tool surface each seat sees on the Desk Gateway.
├── tool-packs/     Application-specific tool bundles, loaded per ticket.
└── changes/        One change document per proposed contract change. The G-4 input.

openapi.yaml      Repo root. The HTTP surface, when there is one.
**/*.proto        Anywhere in the tree. Stays QUALITY-owned even under web3/ or chains/.
```

`api/` and `events/` are still **skeletons**. They are committed empty-of-product on purpose: G-4
needs a surface to watch, and a gate with nothing to guard is a gate nobody notices has stopped
working.

The consumer list for each surface lives in `ownership.yaml` under `contract_consumers`, not
here. One list, machine-read by the gate, rather than a prose copy that drifts.

---

## Tool rosters — `tool-rosters/`

One file per seat plus `_core.yaml`. The effective roster a seat sees on `/mcp/<seat>` is the core
eight tools plus the seat file's `tools`. The Desk Gateway (`services/desk-gateway/`) loads these
files at startup and serves exactly these names and schemas; a tool that is not in the roster does
not exist on that endpoint.

| File | Seat | Tools |
|---|---|---|
| `_core.yaml` | every seat | 8 |
| `lead.yaml` | bot-00-programming-lead | 15 |
| `systems.yaml` | bot-01-systems-backend | 14 |
| `web.yaml` | bot-02-web-edge | 15 |
| `android.yaml` | bot-03-android | 15 |
| `ios.yaml` | bot-04-ios | 15 |
| `infra.yaml` | bot-05-infrastructure | 15 |
| `quality.yaml` | bot-06-quality-security | 15 |

Fields per tool: `name`, `kind` (`read` fails open, `write` fails closed), `gates` (`g5` requires
`rollback_plan` and `approval_id`; `g6` requires `approval_id`), `description`, `input` (JSON
Schema, `additionalProperties: false`), `backend` (`<module>.<function>` in the gateway).

G-7 fails the build when a roster has fewer than 10 or more than 15 effective tools, a tool has no
input schema, or a g5/g6 tool's schema does not require the fields its gate demands.

## Tool packs — `tool-packs/`

Application-specific bundles of at most five tools that ANDROID, IOS or WEB load for one ticket
with `desk_app_tools_load`. The gateway adds a loaded pack's tools to that seat's `tools/list`
until the ticket closes; live tools never exceed 20. `seats` lists which seats may load the pack.

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
every contract-surface file in the diff, other than the change document itself and the rest of
`contracts/changes/`, which is bookkeeping rather than a consumer surface. That is what ties a document to a change: without it, a
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

### Versioning

`version` is semver. Removing or renaming a tool, narrowing an input, or making an optional field
required is breaking: bump the major, add a `migration_note`, and collect acknowledgements from
every consumer listed in `ownership.yaml` `contract_consumers` before merging (G-4).

---

## Adding the first real contract

1. Put the schema under `api/` or `events/` — OpenAPI, JSON Schema or `.proto`, whichever fits
   the surface. Add the path pattern to `contract_consumers` in `ownership.yaml` if no existing
   pattern covers it, or G-4 fails with *"no consumers resolved"*, which is the gate correctly
   refusing to guess who is affected.
2. Write the change document (`contracts/changes/TEMPLATE.yaml.example`).
3. Collect the acknowledgements on the pull request.
4. Merge the contract on its own, then implement.
