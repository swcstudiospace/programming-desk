---
phase: "68"
slug: "inter-cluster-quantum-teleportation-protocol-entanglement-sw"
status: draft
threats_open: 0
asvs_level: 1
created: "2026-10-10"
---

# Phase 68 — Security

> Draft threat register from the phase plans. This is not an independent security approval.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| seat to teleport route | Bearer seat passphrase | Pair and teleport bodies |
| coordinator to worker | Fixed command path and operator token | Lease and circuit commands |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-68-01 | Tampering | quantum_state.py | high | mitigate | 30 kernel regressions in the committed kernel receipt | closed |
| T-68-02 | Tampering | fidelity and BBPSSW density | medium | mitigate | Same kernel receipt, including the mixed-state smoke | closed |
| T-68-03 | Elevation | pool and worker lease scope | high | mitigate | Phase 68-02 suite recorded in `68-02-SUMMARY.md` | closed |
| T-68-04 | Tampering | reservation and one-shot correction | high | mitigate | Phase 68-02 suite recorded in `68-02-SUMMARY.md` | closed |
| T-68-05 | Tampering | RemoteNodeTransport | high | mitigate | Operator URL allowlist and loopback-only plaintext in `quantum_transport.py`; transport tests in the 68-02 run | closed |
| T-68-06 | Elevation | phase-68 seat auth | high | mitigate | `seat_for_passphrase` before parse; endpoint auth tests in the 87 passed run | closed |
| T-68-07 | Denial of service | REST bounds | medium | mitigate | 64 KiB body cap and count bounds in the phase-68 handlers | closed |

---

## Accepted Risks Log

No accepted risks.

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
