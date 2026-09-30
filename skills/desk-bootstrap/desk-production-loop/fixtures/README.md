# Fixtures for the `loop_acks` rule

Eight receipts and a checker. Three go through `ci/gates/check_rollback.py`, five through
`check-loop-acks.py` beside them. They are the evidence for
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


---

## `loop_acks` shape fixtures, and the checker

`check-loop-acks.py` applies §3.1's rules for a degraded-mode turn acknowledgement: the six required
fields, the two-value `condition` vocabulary, `human_granted_by` rejected when it names a seat, and
the entry shape guarded **before** any field is read. It is a LEAD-owned stand-in — the rule belongs
in G-2, which is `bot-06-quality-security`'s, and the patch is
[`../companion-patches/C-3-quality-loop-acks-g2.md`](../companion-patches/C-3-quality-loop-acks-g2.md).
Until that lands, CI does not check `loop_acks` at all and this is what makes the rule executable.

| Fixture | `loop_acks[0]` | Checker | Shows |
|---|---|---|---|
| `loop-acks-valid.json` | six fields, `human_granted_by: "Ove"`, `relayed_by` the LEAD seat | **exit 0** | The shape §3.1 asks for, including the relay named separately from the grantor |
| `loop-acks-seat-grantor.json` | same, but `human_granted_by: "bot-00-programming-lead"` | **exit 1** | The round-9 defect: a complete-looking entry with no human in it, which reads as compliance |
| `loop-acks-missing-grantor.json` | `human_granted_by` omitted | **exit 1** | An ack obtained and its grantor dropped |
| `loop-acks-bad-condition.json` | `condition: "brief_slow"` | **exit 1** | An entry that cannot be matched to the turn it claims to authorise |
| `loop-acks-malformed.json` | `loop_acks: ["ack-…"]` — strings, not objects | **exit 1**, and **no traceback** | A checker that crashes on malformed input gives no verdict, which is worse than one that says no. This is the guard C-3 must carry into G-2 |

```sh
F=skills/desk-bootstrap/desk-production-loop/fixtures
python3 $F/check-loop-acks.py $F/loop-acks-valid.json            # 0
python3 $F/check-loop-acks.py $F/loop-acks-seat-grantor.json     # 1
python3 $F/check-loop-acks.py $F/loop-acks-missing-grantor.json  # 1
python3 $F/check-loop-acks.py $F/loop-acks-bad-condition.json    # 1
python3 $F/check-loop-acks.py $F/loop-acks-malformed.json        # 1, and not a traceback
```

`verify.sh` runs all five and asserts both the exit code and the absence of a traceback, so the
acknowledgement rules cannot decay into prose again. `loop_acks` is optional: a receipt for a turn
that never went degraded records nothing and passes.

---

## `lease-cas-drift-smoke.py` — SPE-5715

Not run by `verify.sh` — it needs a live substrate-mcp and a real bearer token, neither of which
belongs in a check that runs with no credentials and no network. Proves exclusivity (two concurrent
`graph_claim` calls on one node, exactly one holder) against a real substrate when
`DESK_LEASE_SMOKE_LIVE=1`, `SUBSTRATE_URL` and `SUBSTRATE_TOKEN` are all set. Only
`DESK_LEASE_SMOKE_LIVE` unset skips cleanly (exit 0, printed reason) — once it is set to opt in,
a missing `SUBSTRATE_URL`/`SUBSTRATE_TOKEN` or any other broken precondition is a FAIL (exit 1),
not a skip, so an operator or CI running a partially configured live smoke gets a failure, not a
false clean exit. It does not attempt the expired-lease or tip/event-disagreement cases — see the
script's own docstring and the "SPE-5715" section of `../SKILL.md` for why neither tool exists yet
to exercise.

```sh
python3 skills/desk-bootstrap/desk-production-loop/fixtures/lease-cas-drift-smoke.py   # 0, SKIP printed, no env set
DESK_LEASE_SMOKE_LIVE=1 python3 skills/desk-bootstrap/desk-production-loop/fixtures/lease-cas-drift-smoke.py   # 1, FAIL printed, opted in but no SUBSTRATE_TOKEN
```
