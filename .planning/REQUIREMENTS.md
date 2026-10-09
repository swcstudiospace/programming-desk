# Requirements: Milestone v4.9 — Autonomous Space-Air-Ground Integrated Network (SAGIN) & Delay-Tolerant Satellite Swarm Mesh

This document defines the requirements for Milestone v4.9 of Programming Desk.

## 1. Delay-Tolerant Bundle Protocol & Orbital Ephemeris Routing (Phase 64)

- [x] **REQ-SAGIN-001**: Orbital Ephemeris & Kinematics Modeling (`OrbitalEphemeris`) defining satellite altitude, inclination, true anomaly, orbital velocity, slant range, and elevation contact windows.
- [x] **REQ-SAGIN-002**: Delay-Tolerant Bundle Protocol Architecture (`DelayTolerantBundle`, `BundlePriority`, `CustodyStatus`) implementing RFC 5050/9171 compliant bundle representations with TTL, hop counts, and SHA-256 payload digests.
- [x] **REQ-SAGIN-003**: Dynamic Contact Graph Routing (`ContactGraphRouter`, `ContactPlanEntry`) calculating earliest arrival paths over scheduled, time-varying contact graphs.
- [x] **REQ-SAGIN-004**: Resilient Custodial Storage Management (`CustodialStorageManager`) supporting store-and-forward retention queues, custody acceptance/release, and HMAC-SHA256 custody receipts.
- [x] **REQ-SAGIN-005**: Doppler Shift & Orbital Telemetry Tracker (`DopplerTelemetryTracker`) evaluating carrier frequency shifts, relative velocities, and SNR link degradation margins.
- [x] **REQ-SAGIN-006**: SAGIN Phase 64 REST API endpoints under `/v1/sagin/ephemeris/*`, `/v1/sagin/doppler/*`, `/v1/sagin/bundle/*`, and `/v1/sagin/custody/*` in `services/desk-gateway/src/desk_gateway/server.py`.

## 2. Ground Station Downlink Consensus & Multi-Constellation State Anchoring (Phase 65)

- [x] **REQ-SAGIN-007**: Earth Ground Station Terminal Representation (`GroundStationNode`) tracking ground station coordinates, antenna gain, slew rates, and concurrent satellite tracking passes.
- [x] **REQ-SAGIN-008**: Multi-Constellation Downlink Session Manager (`MultiConstellationDownlinkManager`) orchestrating cross-constellation passes with Doppler compensation and contact telemetry.
- [x] **REQ-SAGIN-009**: Intermittent Contact BFT Consensus Engine (`IntermittentGroundConsensusEngine`) coordinating ground station verification quorums across intermittent passes.
- [x] **REQ-SAGIN-010**: Satellite Append-Only Merkle Receipt Ledger (`SatelliteMerkleReceiptLedger`, `SatelliteLedgerReceipt`) recording verifiable orbital state transitions and calculating Merkle tree roots.
- [x] **REQ-SAGIN-011**: Solana Devnet SAGIN Commitment Exporter (`SAGINAnchorExporter`) exporting batch Merkle roots and orbital downlink proofs to Solana devnet targets.
- [x] **REQ-SAGIN-012**: SAGIN Verification Drill Simulator (`SAGINOrbitalVerificationDrillSimulator`) verifying ephemeris windows, CGR routing, bundle custody, downlink sessions, BFT ground consensus, and Solana anchoring.
- [x] **REQ-SAGIN-013**: SAGIN Phase 65 REST API endpoints under `/v1/sagin/downlink/*`, `/v1/sagin/consensus/*`, `/v1/sagin/anchor/*`, and `/v1/sagin/drill/simulate` in `services/desk-gateway/src/desk_gateway/server.py`.
