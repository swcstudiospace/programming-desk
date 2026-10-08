# Phase 3: Substrate Data Planes — Validation Strategy

## Quality Gate Compliance

- **G-1 (Ownership):** All Phase 3 planning artifacts remain under `.planning/phases/03-substrate-data-planes/` owned by `bot-00-programming-lead`.
- **G-3 (Secrets):** Zero plaintext secrets or credentials in connection string examples (`postgresql://[AUTH]@...`, `redis://[AUTH]@...`).
- **G-4 (Contracts):** Does not touch breaking contract surfaces.
- **G-5/G-6 (Rollbacks):** Data-plane migrations must include forward migration and clean rollback scripts.
- **G-7 (Desk Integrity):** All prompt rosters and tool definitions maintain exact tool counts and validation criteria.

## Automated Checks
1. Schema validation against SQL DDL definitions.
2. Unit tests covering cache TTL fallthrough logic.
3. Memory bank isolation rules tests.
