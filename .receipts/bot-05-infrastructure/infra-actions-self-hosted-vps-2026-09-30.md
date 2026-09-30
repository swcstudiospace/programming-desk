# INFRA — programming-desk Actions on VPS self-hosted runner

2026-09-30 · bot-05-infrastructure · Ove GO via LEAD

## Change
`runs-on: ubuntu-latest` → `runs-on: [self-hosted, Linux, X64]` in:
- `.github/workflows/gates.yml`
- `.github/workflows/gates-template-sync.yml`
- `ci/.github/workflows/gates.yml` (body identical to live)

## Why
Org GitHub-hosted jobs fail immediately (Actions spending limit). Org runner `srv1778002` on VPS is online (`ActiveState=active`).

## Evidence
See companion JSON receipt (G-2 schema). Runner labels used by workflows: `self-hosted`, `Linux`, `X64`.

## Rollback
Revert this PR / restore `ubuntu-latest`.

No secrets.
