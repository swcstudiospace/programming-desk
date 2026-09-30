# INFRA — programming-desk Actions on VPS self-hosted runner

2026-09-30 · bot-05-infrastructure · Ove GO via LEAD

## Change
`runs-on: ubuntu-latest` → `runs-on: [self-hosted, Linux, X64]` in:
- `.github/workflows/gates.yml`
- `.github/workflows/gates-template-sync.yml`
- `ci/.github/workflows/gates.yml` (must stay body-identical to live)

## Why
Org GitHub-hosted jobs fail immediately: spending limit / payment. Org runner `srv1778002` on VPS is online.

## Rollback
Revert this commit / restore `ubuntu-latest`.

No secrets.
