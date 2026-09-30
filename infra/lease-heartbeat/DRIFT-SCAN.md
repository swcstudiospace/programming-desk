# `coord.drift_scan(repo)` — the INFRA support half (SPE-4792)

**Owner of this document:** INFRA (`bot-05-infrastructure`). **Owner of `coord.drift_scan`:**
SYSTEMS (`bot-01-systems-backend`). Companion: [LEASE-HEARTBEAT.md](./LEASE-HEARTBEAT.md) §1 for the ownership split.

Drift is the gap between what a seat believes and what is true: a seat holding a claim against a
tip that moved, or renewing a lease into a plane nobody can reach. The scan exists so a seat finds
that out at turn start rather than at merge.

---

## 1. Interface preference

**`coord.drift_scan(repo)`, called by seats.** One call, one repo argument, one answer.

INFRA's preference is for the seat to call SYSTEMS' coordination surface, *not* for each seat to
assemble a drift picture out of separate probe calls. Three reasons, in order of how much they
cost when ignored:

1. **One reading, one timestamp.** A seat that calls a tip probe, then a reachability probe, then a
   claims query has three answers from three moments and no way to say whether they describe the
   same instant. `drift_scan` returns one snapshot with one `checked_at`, so "tip moved while the
   claim was open" is answerable.
2. **The comparison lives with the state.** Whether a tip difference *is* drift depends on the
   claim: same sha, no drift; seat behind with an open claim, drift; seat behind with no claim,
   routine. Only the claim holder's state answers that, and that state is SYSTEMS'.
3. **Seven seats, one implementation.** Seven seats each assembling their own drift verdict is
   seven subtly different definitions of drift, and the disagreements surface as merge conflicts.

INFRA is a **data source** behind that call, not a second entry point. Nothing in this directory is
intended to be called by a seat directly.

## 2. The three inputs, and who asserts what

| Input | INFRA provides | INFRA does **not** provide |
|---|---|---|
| **Git tip** | Local tip sha, current branch, dirty flag, remote tip via `ls-remote`, and the ahead/behind/diverged relation when both commits are local objects | Whether a tip difference matters for a claim |
| **Last-events reachability** | That the events plane's port answers a TCP connect, with latency | The newest `agent_events` row, its age, or any query result |
| **Open-claims connectivity** | That the index plane's port answers a TCP connect, with latency | Which claims are open, their holders, or any CAS on them |

The right-hand column is the load-bearing one. INFRA probes **reachability**, not content:

- A reachability probe needs no credential, so its failure has exactly one meaning: the hop is
  shut. A probe that authenticates fails for two reasons — network or credential — and cannot tell
  you which, which is precisely the ambiguity a drift scan must not add.
- `GREPTIME_*` and `SUBSTRATE_PG_URL` live in `/etc/substrate/substrate.env` and are read by
  `substrate-mcp` ([`../substrate/SUBSTRATE-ENV.md`](../substrate/SUBSTRATE-ENV.md) §1). A probe that read the
  newest event row would need that credential in a second place, which is a second thing to rotate
  and a second thing to leak.
- **Claim CAS is SYSTEMS'.** INFRA asserting anything about claim *contents* would be a second
  reader of the claim table, and a second reader becomes a second writer the first time someone
  needs the scan to "just clean up the stale one".

So the honest shape of INFRA's contribution is: *"the planes are reachable and the tip is X"*.
SYSTEMS decides what that means.

## 3. The helper: `drift-probe.sh`

Read-only and credential-free by construction. It fetches nothing, checks out nothing, resets
nothing, opens no authenticated connection, and writes no file.

```sh
./drift-probe.sh tip   [repo_dir]              # git tip facts for one checkout
./drift-probe.sh reach <host:port>[,host:port] # bounded TCP connect per target
./drift-probe.sh all                           # both, one JSON object
```

Env inputs (`lease-heartbeat.env.example`): `DRIFT_REPO_DIR`, `DRIFT_GIT_REMOTE`,
`DRIFT_GIT_BRANCH`, `DRIFT_REACH_TARGETS`, `DRIFT_PROBE_TIMEOUT_S`.

### Exit status is about the probe, not the result

**0** means every probe ran and the JSON is complete. An unreachable target is `"reachable": false`
with exit **0** — "the desk cannot see Greptime" is an answer `drift_scan` needs, not a script
failure, and collapsing the two would make an outage indistinguishable from a broken probe.
Non-zero means a probe could not be attempted (bad arguments, no such checkout) and the JSON must
not be trusted.

### `relation` and the deliberate `unknown_no_fetch`

`ls-remote` reads refs, not objects, so when the remote tip is not already in the local object
store the ahead/behind relation is genuinely unanswerable. The probe reports
`"relation": "unknown_no_fetch"` rather than fetching: a probe that mutates the checkout it is
measuring is not a probe, and a background fetch inside a heartbeat is a surprise write to a
working tree a seat may be mid-edit in. `behind` and `diverged` both collapse into that value; if
`drift_scan` needs them separated, the fetch is the caller's decision to make, not the probe's.

`dirty: true` is reported but is not drift on its own — uncommitted work is the normal state of a
seat mid-task. It is in the snapshot because "tip moved **and** the tree is dirty" is the case
where a seat is about to have a bad time.

### Targets

`DRIFT_REACH_TARGETS` is normally the forwarder host:port pairs from
[`../railway/forwarders.yaml`](../railway/forwarders.yaml) — `4000` for the events plane, `5432`
for the index plane. While `GREPTIME_URL` is still on the public HTTPS fallback
([`../substrate/SUBSTRATE-ENV.md`](../substrate/SUBSTRATE-ENV.md) §3), a TCP probe of the tailnet port reports
the route the substrate is *not* currently using. That is worth knowing and is not the same
question as "is the configured route up", so a scan that cares about the configured route probes
the host the substrate is actually pointed at.

## 4. Suggested snapshot shape (a proposal, not a contract)

`drift-probe.sh all` emits, with error text and the malformed-target case elided:

```json
{
  "drift_probe": 1,
  "checked_at": "2026-09-30T00:00:00Z",
  "git_tip": {
    "probe": "git_tip", "ok": true, "repo_dir": "/opt/programming-desk",
    "branch": "main", "local_tip": "<sha>", "dirty": false,
    "remote": "origin", "remote_branch": "main", "remote_tip": "<sha>",
    "relation": "same|ahead|behind|diverged|unknown_no_fetch|unknown"
  },
  "reachability": {
    "probe": "reachability", "timeout_s": 5,
    "targets": [
      { "target": "host:port", "host": "host", "port": 4000,
        "reachable": true, "latency_ms": 9 }
    ]
  }
}
```

This is INFRA's suggestion for what `coord.drift_scan(repo)` consumes, offered so SYSTEMS has
something concrete to accept or reject. It is **not** a contract change: the tool rosters under
`contracts/tool-rosters/` are QUALITY-owned and `coord.*` is SYSTEMS', so if `drift_scan` becomes a
desk tool the schema lands there through the contract-first protocol
([`../../docs/cross-bot-protocol.md`](../../docs/cross-bot-protocol.md)), not here. Every field
above is either already emitted by the helper or absent; nothing is described that the script does
not produce.

## 5. Open questions for SYSTEMS

1. Does `drift_scan` want the raw snapshot (§4) or a reduced verdict per input? INFRA's preference
   is raw: a verdict computed twice, in two places, drifts.
2. Should the probe be invoked by the heartbeat tick and cached in `LEASE_STATE_DIR` under
   `DRIFT_CACHE_TTL_S`, or called on demand by `coord.drift_scan`? The first bounds the cost per
   scan; the second is always current. INFRA can do either and has no preference.
3. Which hosts belong in `DRIFT_REACH_TARGETS` while the events plane is on the public HTTPS
   fallback — the tailnet forwarder port, the configured public host, or both (see §3)?
