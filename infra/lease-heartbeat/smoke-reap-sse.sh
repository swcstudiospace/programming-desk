#!/usr/bin/env bash
# Self-contained smoke check for substrate-lease-reap.sh's SSE handling (SPE-4792).
#
#   bash infra/lease-heartbeat/smoke-reap-sse.sh                 # exit 0 = pass
#   REAP_WRAPPER=/path/to/other.sh bash .../smoke-reap-sse.sh    # check a different wrapper
#
# Starts a throwaway MCP server on an ephemeral port that answers with a SUCCESSFUL JSON-RPC
# result pretty-printed across many `data:` lines, runs the wrapper against it, and asserts
# exit 0. That framing is what Greptile P1 4142097603 was about: parsing each `data:` line as
# standalone JSON made a healthy sweep exit 4, so the timer would have reported failure on every
# tick while the substrate was fine.
#
# REAP_WRAPPER exists so the NEGATIVE case is a real command too. A check that cannot fail proves
# nothing, so the receipt records this run against the pre-fix wrapper (where it must exit 4)
# beside the run against the fixed one:
#
#   git show 99028dd:infra/lease-heartbeat/substrate-lease-reap.sh > /tmp/old.sh
#   REAP_WRAPPER=/tmp/old.sh bash infra/lease-heartbeat/smoke-reap-sse.sh   # must FAIL
#
# No external fixture, no outbound network, no secret — the bearer in the generated curl config is
# a literal placeholder the throwaway server never checks.

set -u

WRAPPER="${REAP_WRAPPER:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/substrate-lease-reap.sh}"

D=$(mktemp -d)
SRV=""

# Cleanup covers the signals too, not just EXIT. With the temp dir alone in the trap, a Ctrl-C
# between starting the server and reaching the kill below left a python process bound to a local
# port for as long as the machine stayed up — a test fixture outliving the test is a slow leak on
# anyone's dev box and on a CI runner that reuses workspaces.
cleanup() {
  [ -n "$SRV" ] && kill "$SRV" 2>/dev/null
  [ -n "$SRV" ] && wait "$SRV" 2>/dev/null
  rm -rf "$D"
}
trap cleanup EXIT INT TERM HUP

printf 'header = "Authorization: Bearer smoke-test-not-a-credential"\n' > "$D/c"
printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"coord_reap_leases","arguments":{}}}\n' > "$D/r"

python3 - "$D/port" <<'PY' &
import http.server, json, sys
OK = {"jsonrpc": "2.0", "id": 1,
      "result": {"content": [{"type": "text", "text": "reaped 2 leases"}]}}
# Pretty-printed on purpose: one JSON object split across many `data:` lines in one SSE event.
body = ("event: message\n"
        + "".join("data: %s\n" % l for l in json.dumps(OK, indent=2).splitlines())
        + "\n").encode()


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


s = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(s.server_address[1]))
s.serve_forever()
PY
SRV=$!

for _ in $(seq 60); do [ -s "$D/port" ] && break; sleep 0.05; done
if [ ! -s "$D/port" ]; then
  echo "SMOKE ERROR: throwaway server did not start" >&2
  exit 1
fi
P=$(cat "$D/port")

SUBSTRATE_MCP_URL="http://127.0.0.1:$P/mcp" \
SUBSTRATE_LEASE_REAP_CURL_CONFIG="$D/c" \
SUBSTRATE_LEASE_REAP_REQUEST="$D/r" \
  bash "$WRAPPER"
RC=$?

if [ "$RC" -eq 0 ]; then
  echo "SMOKE PASS: multiline-SSE success parsed, exit 0"
else
  echo "SMOKE FAIL: wrapper exited $RC on a successful multiline-SSE result"
fi
exit "$RC"
