#!/usr/bin/env bash
# One lease-reap sweep against the local substrate-mcp, with the result actually checked.
# SPE-4792 INFRA half; called by substrate-lease-reap.service. Design notes: LEASE-HEARTBEAT.md §6.
#
# WHY THIS EXISTS RATHER THAN A BARE curl IN ExecStart
# `curl --fail-with-body` fails on a non-2xx status and nothing else. MCP does not report tool
# failures that way: a `tools/call` whose tool failed answers **HTTP 200** with `isError: true`
# inside `result`, and a protocol-level failure answers 200 with a JSON-RPC `error` member. Both
# would have left systemd marking the sweep successful while every expired lease stayed unreaped
# until something happened to call the tool on demand — a green timer over a job that is not
# running, which is the failure this whole directory is written to avoid.
#
# So the contract here is: exit non-zero unless the tool actually ran and actually succeeded.
#
#   0  swept: HTTP 2xx, no JSON-RPC error, result.isError not set
#   2  HTTP status was not 2xx
#   3  curl could not complete the request (connect, timeout, bad config)
#   4  the response could not be parsed as an MCP result
#   5  the tool reported failure (JSON-RPC error, or result.isError)
#
# NO SECRET ON THE COMMAND LINE. The bearer stays in the curl config file named by
# SUBSTRATE_LEASE_REAP_CURL_CONFIG, exactly as before; this script never reads or echoes it.
# Response bodies ARE logged (bounded) because a failing sweep is undiagnosable without them —
# the request is a fixed no-argument tool call, so the body carries no credential of its own.
#
# Requires: curl, python3 (both already present on a host running substrate-mcp).

set -euo pipefail

: "${SUBSTRATE_MCP_URL:?SUBSTRATE_MCP_URL is not set — the installer has not run}"
: "${SUBSTRATE_LEASE_REAP_CURL_CONFIG:?SUBSTRATE_LEASE_REAP_CURL_CONFIG is not set}"
: "${SUBSTRATE_LEASE_REAP_REQUEST:?SUBSTRATE_LEASE_REAP_REQUEST is not set}"
TIMEOUT_SEC="${SUBSTRATE_LEASE_REAP_TIMEOUT_SEC:-30}"
# How much of a failing body reaches the journal. Bounded so a large error payload cannot fill the
# disk one sweep at a time.
#
# Validated as a non-negative integer, because the cap is applied by `head -c "$LOG_BYTES"` and by
# a Python slice, and BOTH invert on a negative number: `head -c -50` means "all but the last 50
# bytes" and `raw[:-50]` the same, so a single stray minus sign turns the cap into "log almost
# everything" — on every failing tick, which is exactly when the payload is largest.
LOG_BYTES="${SUBSTRATE_LEASE_REAP_LOG_BYTES:-2000}"
if [[ ! "$LOG_BYTES" =~ ^[0-9]+$ ]]; then
  printf 'substrate-lease-reap: SUBSTRATE_LEASE_REAP_LOG_BYTES must be a non-negative integer, got: %s\n' \
    "$LOG_BYTES" >&2
  exit 1
fi

body=$(mktemp)
trap 'rm -f "$body"' EXIT

http_code=0
curl_rc=0
http_code=$(curl --silent --show-error \
  --output "$body" --write-out '%{http_code}' \
  --max-time "$TIMEOUT_SEC" \
  --config "$SUBSTRATE_LEASE_REAP_CURL_CONFIG" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json, text/event-stream" \
  --data @"$SUBSTRATE_LEASE_REAP_REQUEST" \
  "$SUBSTRATE_MCP_URL") || curl_rc=$?

if [[ $curl_rc -ne 0 ]]; then
  printf 'substrate-lease-reap: request failed (curl exit %s)\n' "$curl_rc" >&2
  head -c "$LOG_BYTES" "$body" >&2 || true
  exit 3
fi

if [[ ! "$http_code" =~ ^2[0-9][0-9]$ ]]; then
  printf 'substrate-lease-reap: HTTP %s from %s\n' "$http_code" "$SUBSTRATE_MCP_URL" >&2
  head -c "$LOG_BYTES" "$body" >&2
  exit 2
fi

# HTTP said fine. Now ask the payload, which is the part that actually knows.
python3 - "$body" "$LOG_BYTES" <<'PY'
import json, sys

path, log_bytes = sys.argv[1], int(sys.argv[2])
raw = open(path, "r", errors="replace").read()


def messages(text):
    """Yield JSON-RPC messages from a plain JSON body or an SSE stream.

    Streamable-HTTP MCP may answer either way for the same call, and a sweeper that understood
    only one of them would silently stop checking results the day the server switched framing.

    The SSE half follows the spec rather than the common case: an event's data is *all* of its
    `data:` lines joined with newlines, dispatched at the blank line that ends the event. Parsing
    each line on its own works only while the server happens to emit compact one-line JSON — the
    moment it pretty-prints or wraps a long result, every line is a JSON fragment, the parse
    fails, and the sweep is reported failed on every tick while the substrate is perfectly fine.
    """
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        yield json.loads(stripped)
        return

    found = False
    buf = []

    def flush(buf):
        payload = "\n".join(buf)
        if payload and payload != "[DONE]":
            return json.loads(payload)
        return None

    for line in text.splitlines():
        if line.startswith("data:"):
            # One optional space after the colon belongs to the framing, not the data.
            chunk = line[5:]
            if chunk.startswith(" "):
                chunk = chunk[1:]
            buf.append(chunk)
        elif line.strip() == "":
            if buf:
                msg = flush(buf)
                buf = []
                if msg is not None:
                    found = True
                    yield msg
        # Any other field (event:, id:, retry:, a comment line) is framing we do not need.

    if buf:  # last event with no trailing blank line
        msg = flush(buf)
        if msg is not None:
            found = True
            yield msg

    if not found:
        raise ValueError("no JSON object and no SSE data: frame in response")


try:
    msgs = [m for m in messages(raw) if isinstance(m, dict)]
except (ValueError, json.JSONDecodeError) as exc:
    print(f"substrate-lease-reap: unparseable response: {exc}", file=sys.stderr)
    print(raw[:log_bytes], file=sys.stderr)
    sys.exit(4)

if not msgs:
    print("substrate-lease-reap: response carried no JSON-RPC message", file=sys.stderr)
    print(raw[:log_bytes], file=sys.stderr)
    sys.exit(4)

for m in msgs:
    # Protocol-level failure: HTTP 200 with an `error` member.
    if m.get("error") is not None:
        err = m["error"]
        print(f"substrate-lease-reap: JSON-RPC error: {json.dumps(err)[:log_bytes]}", file=sys.stderr)
        sys.exit(5)
    # Tool-level failure: HTTP 200, no `error`, but the result says it failed.
    result = m.get("result")
    if isinstance(result, dict) and result.get("isError"):
        print("substrate-lease-reap: tool reported isError", file=sys.stderr)
        print(json.dumps(result)[:log_bytes], file=sys.stderr)
        sys.exit(5)

if not any("result" in m for m in msgs):
    print("substrate-lease-reap: no result in response", file=sys.stderr)
    print(raw[:log_bytes], file=sys.stderr)
    sys.exit(4)

print("substrate-lease-reap: swept")
PY
