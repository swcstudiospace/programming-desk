# INFRA — desk-gateway install layout for future DESK_GATE_USER

- **Task ID:** `infra-desk-gate-install-layout-2026-09-30`
- **Bot:** bot-05-infrastructure
- **PR:** #34 (hold draft)
- **Approved by:** *null until QUALITY Path B*

## Tip fixes (QUALITY re-stamp @ 798f162 → this tip)
- **4141252895** — probe uses in-memory `compile(read_text)` (no `py_compile` / `__pycache__` write).
- **4141252905** — sync requires `rsync -a --delete`; tar fallback removed.
- **4141252913** — receipt evidence commands are real and re-runnable (no placeholders).

## Still true
- `/opt/programming-desk` canonical layout; `DESK_GATE_USER` **unset**.
- Prior P1/P2s from first tip fix remain addressed.
