# Phase 8: Plan 03 Summary — Token Errors & RFC-7807 Problem Details Drill

**Executed:** 2026-10-08  
**Scope:** REQ-DRILL-003  
**PR:** [#83](https://github.com/swcstudiospace/programming-desk/pull/83) (`bot-01-systems-backend/phase-08-err-rfc7807`)

## Execution & Verification Summary

### 1. RFC-7807 Problem Details Implementation (REQ-DRILL-003)
- Created `services/desk-gateway/src/desk_gateway/problems.py` supplying `problem_details()` dict builder and `problem_response()` `JSONResponse` with `application/problem+json` media type.
- Updated `SeatRouter` in `services/desk-gateway/src/desk_gateway/server.py` to return HTTP 401 problem details on corrupted or expired bearer tokens with `WWW-Authenticate: Bearer error="invalid_token", error_description="..."`.
- Updated cross-seat token access to return HTTP 403 problem details.
- Updated `/v1/intake` handler to return HTTP 401 problem details on unauthenticated requests and HTTP 403 on invalid seat access attempts.
- Updated `services/desk-gateway/src/desk_gateway/upstreams.py` so that upstream authentication rejections (e.g. Substrate or HTTP client 401/403) emit structured RFC-7807 problem details payloads.
- Added comprehensive unit tests and drill in `services/desk-gateway/tests/test_server.py`:
  - `test_wrong_seat_token_is_403`
  - `test_corrupted_or_expired_token_is_401_problem_details`
  - `test_intake_flow_only_lead_can_drain`
  - `test_upstream_token_error_problem_details`
- Verification receipt: `.receipts/bot-01-systems-backend/phase-08-plan-03.json` validated under strict G-2 checking.
- Clean pass: all 128 desk-gateway tests pass, all 291 ci repository tests pass, and PR #83 merged cleanly to `main`.
