# G-6 fixtures for the `loop_acks` rule

Two receipts that exist to be run through `ci/gates/check_rollback.py`. They are the evidence for
§3.1 of the skill — why a degraded-mode turn ack goes in `loop_acks` and never in `approvals[]` —
and they are committed here so that reasoning is reproducible from the repository alone rather than
from a `/tmp` path in someone's session.

Neither is a real receipt. Both name a fake `task_id`, carry one synthetic destructive command, and
are never cited as evidence for anything about this branch's own work.

| Fixture | `approvals[0]` | G-6 | Shows |
|---|---|---|---|
| `g6-turn-ack-in-approvals.json` | turn ack, `{operation, approved_by, id}` | **exit 1** | G-6 validates **every** `approvals` entry once any destructive command is present, so a turn ack fails a receipt whose destructive op was properly approved |
| `g6-turn-ack-four-fields.json` | same turn ack **plus** `at` + `blast_radius` | **exit 0** | G-6 pairs approvals to destructive ops **by count**, so a completed turn ack silently satisfies the gate for an unrelated `rm -rf` |

Run both:

```sh
python3 ci/gates/check_rollback.py --receipt skills/desk-bootstrap/desk-production-loop/fixtures/g6-turn-ack-in-approvals.json   # exit 1
python3 ci/gates/check_rollback.py --receipt skills/desk-bootstrap/desk-production-loop/fixtures/g6-turn-ack-four-fields.json    # exit 0
```

`verify.sh` runs both and asserts those exit codes, so the second row cannot quietly stop being true.
That second row is the load-bearing one: it is why the remedy is to keep turn acks out of
`approvals[]` rather than to fill in their missing fields. Filling them in turns a loud failure into
a silent pass inside the gate that exists to stop unapproved destruction.

**If G-6 changes** — if `check_rollback.py` starts pairing approvals to destructive operations
instead of counting them — `verify.sh` fails on the second fixture. That failure is the correct
signal: the hazard would be gone, and §3.1's second row would need rewriting rather than the
fixture being edited to keep the old result.
