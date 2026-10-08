# Requirements: Milestone v2.1 — Live Drills & Intake Hardening

This document defines the requirements for Milestone v2.1 of Programming Desk.

## 1. Gateway Resiliency & Subagent Execution Drills (Phase 8)

- **REQ-DRILL-001**: Verification script suite for 15 specialized Cursor subagents located in `.cursor/agents/` validating system prompt integrity, tools declaration matching, and prompt token bounds.
- **REQ-DRILL-002**: Automated loopback probe for `services/desk-gateway` verifying `/healthz`, `/metrics`, and `/readyz` endpoints under concurrent load simulation.
- **REQ-DRILL-003**: Token verification and expiration handling drill ensuring corrupted or expired GitHub / Substrate tokens produce structured RFC-7807 problem details.
- **REQ-DRILL-004**: Rate limiting and backpressure integration test for desk-gateway intake queues.
- **REQ-DRILL-005**: Diagnostic receipt generation validator testing offline mode receipt generation and hash verification.
- **REQ-DRILL-006**: CLI runner smoke test exercising `desk-run` commands in a mock sandbox environment.
- **REQ-DRILL-007**: Verification test for receipt schema adherence against JSON schema draft-07 specification.
- **REQ-DRILL-008**: Test harness validating agent transition handoffs between `bot-00-programming-lead` and execution agents.
- **REQ-DRILL-009**: Timeout boundary check for long-running tool executions ensuring proper signal traps and cleanup.
- **REQ-DRILL-010**: Verification of audit log immutability and checksum chaining in gateway logs.

## 2. External Intake Hardening & Telemetry Anchoring (Phase 9)

- **REQ-INTAKE-001**: Webhook payload validation drill verifying HMAC-SHA256 signatures from GitHub and companion repositories.
- **REQ-INTAKE-002**: ETag caching and conditional request verification for upstream Substrate and Swarm registry lookups.
- **REQ-INTAKE-003**: Ingress schema validation rejecting malformed PR payloads before worker dispatch.
- **REQ-INTAKE-004**: Idempotency key tracking ensuring duplicate incoming events are deduplicated within a sliding window.
- **REQ-INTAKE-005**: Graceful degradation fallback when companion `agent-substrate` or `agent-swarm` services are unreachable.
- **REQ-INTAKE-006**: Structured log formatter ensuring OTel-compatible trace and span propagation across requests.
- **REQ-INTAKE-007**: Circuit breaker implementation on gateway outbound client sessions.
- **REQ-INTAKE-008**: Dead-letter queue (DLQ) retry policies and terminal failure reporting for webhook events.
- **REQ-INTAKE-009**: Secure secrets redaction filter ensuring zero credentials appear in debug or trace output.
- **REQ-INTAKE-010**: End-to-end telemetry anchoring test validating metrics export compatibility with Prometheus / OpenTelemetry collectors.
