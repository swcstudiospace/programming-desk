# G-6 fixtures for the `loop_acks` rule

Three receipts that exist to be run through `ci/gates/check_rollback.py`. They are the evidence for
§3.1 of the skill — why a degraded-mode turn ack goes in `loop_acks` and never in `approvals[]` —
and they are committed here so that reasoning is reproducible from the repository alone rather than
from a `/tmp` path in someone's session.

None is a real receipt. Each names a fake `task_id`, carries one synthetic destructive command that
is never executed, and is never cited as evidence for anything about this branch's own work.

| Fixture | `approvals[]` | `loop_acks` | G-6 | Shows |
|---|---|---|---|---|
| `g6-turn-ack-in-approvals.json` | a **valid** four-field approval for the `rm -rf`, **plus** a turn ack with `{operation, approved_by, id}` | — | **exit 1** | The destructive op is properly approved, so this receipt should pass. It fails only because G-6 validates **every** `approvals` entry once any destructive command is present, and the turn ack has no `at`/`blast_radius` |
| `g6-turn-ack-four-fields.json` | the turn ack **alone**, completed with `at` + `blast_radius` | — | **exit 0** | G-6 pairs approvals to destructive ops **by count**, so a turn ack silently satisfies the gate for an `rm -rf` that nobody approved |
| `g6-turn-ack-in-loop-acks.json` | the valid approval for the `rm -rf`, and nothing else | the turn ack, with `human_granted_by` | **exit 0** | The control: the same receipt with the ack where §3.1 says it belongs. Passes for the **right** reason — the destructive op has its own approval and the ack is counted against nothing |

The first two are the failure directions; the third is what correct looks like. Read together they
say why the remedy is to move the ack out of `approvals[]` rather than to complete its fields:
fixture 2 and fixture 3 both exit 0, but only one of them has an approved `rm -rf`.

Run them:


```sh
F=skills/desk-bootstrap/desk-production-loop/fixtures
python3 ci/gates/check_rollback.py --receipt $F/g6-turn-ack-in-approvals.json   # exit 1
python3 ci/gates/check_rollback.py --receipt $F/g6-turn-ack-four-fields.json    # exit 0
python3 ci/gates/check_rollback.py --receipt $F/g6-turn-ack-in-loop-acks.json   # exit 0, correctly
```

`verify.sh` runs all three and asserts those exit codes, so the second row cannot quietly stop being true.
The second row is the load-bearing one: it is why the remedy is to keep turn acks out of
`approvals[]` rather than to fill in their missing fields. Filling them in turns a loud failure into
a silent pass inside the gate that exists to stop unapproved destruction.

**If G-6 changes** — if `check_rollback.py` starts pairing approvals to destructive operations
instead of counting them — `verify.sh` fails on the second fixture. That failure is the correct
signal: the hazard would be gone, and §3.1's second row would need rewriting rather than the
fixture being edited to keep the old result.
