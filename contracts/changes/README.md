# contracts/changes/

One YAML document per proposed contract change. This is the input to G-4
(`ci/gates/check_contracts.py`).

```bash
python3 ci/gates/check_contracts.py --base origin/main \
    --change contracts/changes/<change-id>.yaml
```

## Why a separate document rather than a commit message

The gate has to read it. A commit message stating "non-breaking, everyone is fine with it" is
not machine-checkable, is invisible to G-4, and is exactly the verbal agreement that
`docs/cross-bot-protocol.md` lists as an anti-pattern. The change document turns consumer
sign-off into a merge condition instead of a thread nobody can find later.

## Required fields

`change_id`, `proposed_by`, `surface`, `breaking`, `version`, `summary`, and `semantic_changes`.

`semantic_changes` has no default on purpose. Set it to `[]` to state there are none. A field
whose meaning changed while its name and type did not is the one break no schema diff, compiler
or test catches — the only defence is being asked, deliberately, every time.

A breaking change additionally needs `migration_note` and an `ack: true` from every consumer
resolved for the surface.

Start from `TEMPLATE.yaml.example`. It is `.example` rather than `.yaml` so the CI step that
picks up a change document does not select the template.

## One active document at a time

CI selects the change document with `ls -1 contracts/changes/*.yaml | head -n1`, so keep exactly
one active `*.yaml` here: the change this pull request is proposing.

**Once a change has merged, move its document to `archive/`.** The glob is not recursive, so an
archived document stays readable as history without being picked up as the active one.
