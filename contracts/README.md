# Contracts

The interface surface between seats. Owned by QUALITY (`ownership.yaml`, `contract_surface: true`);
changed by proposal from any seat (`desk_contract_propose`), acknowledged by consumers
(`desk_contract_ack`), enforced by G-4 (`ci/gates/check_contracts.py`) and G-7
(`ci/gates/check_desk_integrity.py`). Protocol: `docs/cross-bot-protocol.md`.

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

## Versioning

`version` is semver. Removing or renaming a tool, narrowing an input, or making an optional field
required is breaking: bump the major, add a `migration_note`, and collect acknowledgements from
every consumer listed in `ownership.yaml` `contract_consumers` before merging (G-4).
