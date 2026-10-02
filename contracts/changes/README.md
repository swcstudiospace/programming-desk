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

`surfaces` is optional and holds any further contract paths the change touches. Together with
`surface` it must cover **every** contract-surface file in the diff, except the change document
itself and anything else under `contracts/changes/` — G-4 fails and names the undeclared paths
otherwise. This directory is the protocol's own bookkeeping, not a surface anyone builds
against, so archiving the previous document does not have to be declared as a change to it. List them individually;
`contracts/**` satisfies the check while describing nothing, which is the failure the check
exists to catch.

`semantic_changes` has no default on purpose. Set it to `[]` to state there are none. A field
whose meaning changed while its name and type did not is the one break no schema diff, compiler
or test catches — the only defence is being asked, deliberately, every time.

A breaking change additionally needs `migration_note` and an `ack: true` from every consumer
resolved for the surface.

Start from `TEMPLATE.yaml.example`. It is `.example` rather than `.yaml` so the CI step that
picks up a change document does not select the template.

## One active document at a time

The gate's callers select a change document by globbing this directory — the CI template uses
`ls -1 contracts/changes/*.yaml | head -n1`. Keep exactly one active `*.yaml` here: the change
this pull request is proposing.

**Once a change has merged, move its document to `archive/`.** The glob is not recursive, so an
archived document stays readable as history without being picked up as the active one.

Two things enforce this rather than trusting it:

- `ci/hooks/g4-preflight.sh` refuses to run with more than one document here, and says which
  ones to archive.
- G-4 itself requires the document's declared surfaces to cover the diff. A document left
  behind after its change merged describes different paths, so it cannot validate a later
  change — which is what a filename-ordered `head -n1` would otherwise let it do, including
  for a breaking change with no acknowledgements.
