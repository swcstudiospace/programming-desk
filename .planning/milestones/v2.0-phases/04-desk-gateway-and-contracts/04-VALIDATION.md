# Phase 4: Desk Gateway and Contracts — Validation Strategy

## Quality Gate Compliance

- **G-1 (Ownership):** Planning artifacts remain under `.planning/phases/04-desk-gateway-and-contracts/` owned by `bot-00-programming-lead`. Gateway code lives under `services/desk-gateway/` owned by `bot-01-systems-backend`. Contract files live under `contracts/` owned by `bot-06-quality-security`.
- **G-2 (Receipt Integrity):** Phase receipt `.receipts/bot-00-programming-lead/n4-gateway.json` strictly complies with schema validation, command index references, and external review approval.
- **G-3 (Secret Scanning):** Zero committed secrets. Gateway environment variables read from configuration templates with no exposed tokens.
- **G-4 (Contract Changes):** All contract surface changes are accompanied by valid `contracts/changes/` records with declared consumers and semantic change status.
- **G-5/G-6 (Rollbacks & Destructive Ops):** Rollback procedures documented for deployment and infrastructure changes.
- **G-7 (Desk Integrity):** Tool rosters strictly adhere to tool counts (core 8 + seat-specific tools: 10–15 tools per seat) and ceiling caps (<= 20 total active tools).

## Automated Checks
1. Gate G-1 ownership validation: `python3 ci/gates/check_ownership.py --bot bot-00-programming-lead`.
2. Gate G-3 secret scan: `python3 ci/gates/check_secrets.py`.
3. Gate G-4 contract check: `python3 ci/gates/check_contracts.py`.
4. Gate G-7 integrity check: `python3 ci/gates/check_desk_integrity.py`.
