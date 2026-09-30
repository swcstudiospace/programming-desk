# INFRA — desk-gateway install layout for future DESK_GATE_USER

- **Task ID:** `infra-desk-gate-install-layout-2026-09-30`
- **Bot:** bot-05-infrastructure
- **Greptile P1:** 4141126594
- **Approved by:** *null until QUALITY stamps*

## Fixed
Install the desk checkout under `/opt/programming-desk` (world-traversable), create `desk-gate` system user, and verify that account can read `ci/gates` and execute the venv python. **`DESK_GATE_USER` stays unset.**

## Deferred / follow-ups
- SYSTEMS: optional `config.py` default `repo_dir` alignment (`services/desk-gateway/**`).
- Separate ticket to *enable* `DESK_GATE_USER=desk-gate` after a live install verify.
