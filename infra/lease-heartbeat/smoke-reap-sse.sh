#!/usr/bin/env bash
# Self-contained smoke check for substrate-lease-reap.sh's SSE handling (SPE-4792).
#
#   bash infra/lease-heartbeat/smoke-reap-sse.sh      # exit 0 = pass
#
# Starts a throwaway MCP server on an ephemeral port that answers with a SUCCESSFUL JSON-RPC
# result pretty-printed across many `data:` lines, runs the real wrapper against it, and asserts
# exit 0. That framing is what Greptile P1 4142097603 was about: parsing each `data:` line as
# standalone JSON made a healthy sweep exit 4, so the timer would have reported failure on every
# tick while the substrate was fine.
#
# No external fixture, no network, no secret — the bearer in the generated curl config is a
# literal placeholder the throwaway server never checks.

set -u
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
printf 'header = "Authorization: Bearer smoke-test-not-a-credential"\n' > "$D/c"
printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"coord_reap_leases","arguments":{}}}\n' > "$D/r"
python3 - "$D/port" <<'PY' &
import http.server, json, sys, threading
OK = {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"reaped 2 leases"}]}}
body = ("event: message\n" + "".join("data: %s\n" % l for l in json.dumps(OK, indent=2).splitlines()) + "\n").encode()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length',0)))
        self.send_response(200); self.send_header("Content-Type","text/event-stream")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
s = http.server.HTTPServer(("127.0.0.1",0),H)
open(sys.argv[1],"w").write(str(s.server_address[1]))
s.serve_forever()
PY
SRV=$!
for _ in $(seq 60); do [ -s "$D/port" ] && break; sleep 0.05; done
P=$(cat "$D/port")
SUBSTRATE_MCP_URL="http://127.0.0.1:$P/mcp" \
SUBSTRATE_LEASE_REAP_CURL_CONFIG="$D/c" \
SUBSTRATE_LEASE_REAP_REQUEST="$D/r" \
  ./infra/lease-heartbeat/substrate-lease-reap.sh
RC=$?
kill $SRV 2>/dev/null; wait $SRV 2>/dev/null
[ "$RC" -eq 0 ] && echo "SMOKE PASS: multiline-SSE success parsed, exit 0" || echo "SMOKE FAIL: exit $RC"
exit "$RC"
