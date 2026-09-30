#!/usr/bin/env bash
# Response-shape matrix for substrate-lease-reap.sh (SPE-4792).
#
#   bash infra/lease-heartbeat/smoke-reap-matrix.sh      # exit 0 = every shape mapped as expected
#
# The wrapper's whole job is to map an MCP answer onto a unit exit code. This runs it against a
# throwaway server in each shape MCP can answer with and asserts the expected code, so the
# mapping is checked rather than asserted in prose:
#
#   ok              plain JSON success                      -> 0
#   iserror         HTTP 200, result.isError                -> 5
#   rpcerror        HTTP 200, JSON-RPC error member          -> 5
#   sse_ok          SSE, one-line data:                      -> 0
#   sse_multiline   SSE, result split over many data: lines  -> 0
#   sse_iserror     SSE, result.isError                      -> 5
#   http500         non-2xx                                  -> 2
#   garbage         body that is not an MCP result           -> 4
#
# The two exit-5 cases are the point of the wrapper: HTTP says 200 and the tool still failed.
# The sse_multiline case is the inverse trap — HTTP 200, tool fine, framing split — where a
# per-line parser reports a healthy sweep as broken.
#
# Not covered here: the transport case (nothing listening -> 3) and missing env (-> 1), which need
# no server and are exercised directly in the receipt.
#
# No external fixture, no outbound network, no secret.

set -u

WRAPPER="${REAP_WRAPPER:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/substrate-lease-reap.sh}"

D=$(mktemp -d)
SRV=""
cleanup() {
  [ -n "$SRV" ] && kill "$SRV" 2>/dev/null
  [ -n "$SRV" ] && wait "$SRV" 2>/dev/null
  rm -rf "$D"
}
trap cleanup EXIT INT TERM HUP

printf 'header = "Authorization: Bearer smoke-test-not-a-credential"\n' > "$D/c"
printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"coord_reap_leases","arguments":{}}}\n' > "$D/r"

fail=0
for case in ok:0 iserror:5 rpcerror:5 sse_ok:0 sse_multiline:0 sse_iserror:5 http500:2 garbage:4; do
  mode=${case%%:*}
  want=${case##*:}
  rm -f "$D/port"

  python3 - "$mode" "$D/port" <<'PY' &
import http.server, json, sys
mode, portfile = sys.argv[1], sys.argv[2]
OK = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "reaped 2"}]}}
ERR = {"jsonrpc": "2.0", "id": 1,
       "result": {"isError": True, "content": [{"type": "text", "text": "index plane unreachable"}]}}
RPC = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}}


def sse(obj, multiline=False):
    text = json.dumps(obj, indent=2) if multiline else json.dumps(obj)
    return ("event: message\n"
            + "".join("data: %s\n" % l for l in text.splitlines()) + "\n")


TABLE = {
    "ok":            (200, "application/json",  json.dumps(OK)),
    "iserror":       (200, "application/json",  json.dumps(ERR)),
    "rpcerror":      (200, "application/json",  json.dumps(RPC)),
    "sse_ok":        (200, "text/event-stream", sse(OK)),
    "sse_multiline": (200, "text/event-stream", sse(OK, multiline=True)),
    "sse_iserror":   (200, "text/event-stream", sse(ERR, multiline=True)),
    "http500":       (500, "application/json",  '{"detail":"internal"}'),
    "garbage":       (200, "text/plain",        "not an mcp result at all"),
}
code, ctype, payload = TABLE[mode]
body = payload.encode()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(portfile, "w").write(str(s.server_address[1]))
s.serve_forever()
PY
  SRV=$!

  for _ in $(seq 60); do [ -s "$D/port" ] && break; sleep 0.05; done
  if [ ! -s "$D/port" ]; then
    printf '  %-14s ERROR server did not start\n' "$mode"
    fail=1
    kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""
    continue
  fi
  P=$(cat "$D/port")

  SUBSTRATE_MCP_URL="http://127.0.0.1:$P/mcp" \
  SUBSTRATE_LEASE_REAP_CURL_CONFIG="$D/c" \
  SUBSTRATE_LEASE_REAP_REQUEST="$D/r" \
    bash "$WRAPPER" >/dev/null 2>&1
  got=$?

  kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""

  if [ "$got" -eq "$want" ]; then
    printf '  %-14s exit=%s  ok\n' "$mode" "$got"
  else
    printf '  %-14s exit=%s  EXPECTED %s\n' "$mode" "$got" "$want"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "MATRIX PASS: 8/8 response shapes mapped to the expected exit code"
else
  echo "MATRIX FAIL"
fi
exit "$fail"
