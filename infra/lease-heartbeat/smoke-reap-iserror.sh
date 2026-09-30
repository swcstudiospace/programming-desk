#!/usr/bin/env bash
# Why substrate-lease-reap.sh is a wrapper and not a bare `curl` (SPE-4792, Greptile P1 4142018423).
#
#   bash infra/lease-heartbeat/smoke-reap-iserror.sh      # exit 0 = the distinction still holds
#
# Starts a throwaway MCP that answers HTTP 200 with `result.isError: true` — a tool that FAILED,
# reported the way MCP reports it — and runs two things against it:
#
#   curl --fail-with-body      -> exit 0   systemd would record a SUCCESSFUL sweep
#   substrate-lease-reap.sh    -> exit 5   the unit fails, as it must
#
# That gap is the whole reason ExecStart is not a curl line: `--fail-with-body` only fails on a
# non-2xx status, so every expired lease would have stayed unreaped behind a green timer. This
# check fails if the wrapper ever stops distinguishing the two.
#
# No external fixture, no outbound network, no secret.

set -u
D=$(mktemp -d); SRV=""
cleanup(){ [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; [ -n "$SRV" ] && wait "$SRV" 2>/dev/null; rm -rf "$D"; }
trap cleanup EXIT INT TERM HUP
printf 'header = "Authorization: Bearer smoke-test-not-a-credential"\n' > "$D/c"
printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"coord_reap_leases","arguments":{}}}\n' > "$D/r"
python3 - "$D/port" <<'PY' &
import http.server, json, sys
ERR={"jsonrpc":"2.0","id":1,"result":{"isError":True,"content":[{"type":"text","text":"index plane unreachable"}]}}
body=json.dumps(ERR).encode()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length",0)))
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
s=http.server.HTTPServer(("127.0.0.1",0),H); open(sys.argv[1],"w").write(str(s.server_address[1])); s.serve_forever()
PY
SRV=$!
for _ in $(seq 60); do [ -s "$D/port" ] && break; sleep 0.05; done
P=$(cat "$D/port")
curl --fail-with-body --silent --show-error --max-time 5 --config "$D/c" \
  --header "Content-Type: application/json" --data @"$D/r" "http://127.0.0.1:$P/mcp" >/dev/null 2>&1
echo "bare curl --fail-with-body exit=$?   (0 = systemd would record a SUCCESSFUL sweep)"
SUBSTRATE_MCP_URL="http://127.0.0.1:$P/mcp" SUBSTRATE_LEASE_REAP_CURL_CONFIG="$D/c" \
SUBSTRATE_LEASE_REAP_REQUEST="$D/r" bash infra/lease-heartbeat/substrate-lease-reap.sh >/dev/null 2>&1
W=$?
echo "substrate-lease-reap.sh    exit=$W   (5 = tool failure, unit fails)"
[ "$W" -eq 5 ] || exit 1
