# Requirements: Milestone v3.1 — Model Context Protocol (MCP) Dynamic Mesh & Cross-Desk Remote Tool Invocation

This document defines the requirements for Milestone v3.1 of Programming Desk.

## 1. Dynamic MCP Tool Mesh Registry & Capability Scopes (Phase 28)

- [x] **REQ-MCP-001**: Dynamic MCP server capability discovery and registration across federated desks.
- [x] **REQ-MCP-002**: Fine-grained per-seat tool permission schemas and capability scoping.
- [x] **REQ-MCP-003**: Dynamic schema translation and validation for foreign tool descriptors.
- [x] **REQ-MCP-004**: Rate-limiting and concurrent tool execution quotas per MCP server connection.
- [x] **REQ-MCP-005**: Health monitoring and automatic circuit breaker for degraded remote MCP endpoints.

## 2. Cross-Desk Distributed Remote Tool Invocation & Attested Execution Receipts (Phase 29)

- [x] **REQ-MCP-006**: Asynchronous RPC transport for cross-desk tool invocations over private WAN mesh.
- [x] **REQ-MCP-007**: Cryptographic request-response signing with seat identity attestation.
- [x] **REQ-MCP-008**: Streaming execution proxy supporting real-time progress and telemetry relay.
- [x] **REQ-MCP-009**: Distributed tool execution timeout supervision and zombie process reclamation.
- [x] **REQ-MCP-010**: Non-repudiable tool execution receipts with input/output content hashing and audit logging.
