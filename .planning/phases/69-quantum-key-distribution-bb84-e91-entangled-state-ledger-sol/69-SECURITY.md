---
phase: "69"
slug: "quantum-key-distribution-bb84-e91-entangled-state-ledger-sol"
status: draft
threats_open: 0
asvs_level: 1
created: "2026-10-10"
---

# Phase 69 — Security

> Draft threat register from the phase plans. This is not an independent security approval.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| seat to quantum route | Bearer seat passphrase | Request bodies and public receipts |
| drill to publisher | Frozen prefix and inclusion proof | Non-secret Memo payload |
| coordinator to worker | In-process QKD calls | Private bits stay on the worker object |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-69-01 | Tampering | quantum_ledger.py | high | mitigate | Ledger suite included in the 87 passed run on `5e22296` | closed |
| T-69-02 | Spoofing | quantum_anchor.py | high | mitigate | Genesis pin, one send, exact readback. Unfunded export stays unconfirmed | closed |
| T-69-03 | Information disclosure | quantum_qkd_mesh.py | high | mitigate | Public session has commitments only. Drill and export tests reject key markers | closed |
| T-69-04 | Spoofing | quantum_node.py | high | mitigate | QKD suite included in the 87 passed run. `use_key` returns an outcome, not bytes | closed |
| T-69-05 | Elevation | server.py | high | mitigate | `seat_for_passphrase` only. 401 before parse, 403 for other seats, scoped 404s (`fa210d5`) | closed |
| T-69-06 | Denial of service | server.py drill | medium | mitigate | Zero aborts, negative/bool/string/excessive counts rejected, one drill admission. Deadline and 413 paths were not re-run in `fa210d5` | closed |
| T-69-SC | Tampering | dependencies | high | mitigate | No new package installed for the publisher | closed |

*Status: open · closed. `threats_open` counts open threats at or above high.*

---

## Accepted Risks Log

No accepted risks.

The unfunded payer and the missing remote QKD command surface are acceptance gaps, not accepted security risks. The publisher refuses to report confirmation without a matching readback.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-10 | 7 | 7 | 0 | parent implementation session, draft only |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [ ] `status: verified` set in frontmatter

**Approval:** pending
