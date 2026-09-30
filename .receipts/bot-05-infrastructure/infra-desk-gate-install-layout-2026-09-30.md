# INFRA — desk-gateway install layout for future DESK_GATE_USER

- **Task ID:** `infra-desk-gate-install-layout-2026-09-30`
- **Bot:** bot-05-infrastructure
- **PR:** #34 (hold draft)
- **Greptile P1 (layout):** 4141126594
- **Tip-fix P1s:** 4141208698, 4141208705, 4141208711
- **Tip-fix P2s:** 4141208714, 4141208717, 4141208723
- **Approved by:** *null until QUALITY Path B*

## Fixed
- Install under `/opt/programming-desk`; re-sync `/opt` when install is invoked from a non-canonical tree.
- Broad `DESK_REPO_DIR` rewrite (bare / quoted / missing).
- Receipt claims are `{claim, evidence_command_index}` objects.
- Tighter perms (no world `a+rX`), `desk-gate` home at `/var/lib/desk-gate`, `py_compile` probe as `desk-gate`.
- **`DESK_GATE_USER` stays unset.**

## Deferred
- SYSTEMS: optional `config.py` default `repo_dir` alignment.
- Separate ticket to *enable* `DESK_GATE_USER=desk-gate` after live install verify.
