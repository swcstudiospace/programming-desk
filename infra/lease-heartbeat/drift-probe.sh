#!/usr/bin/env bash
# INFRA reachability + git-tip probe helpers for coord.drift_scan (SPE-4792).
#
# Read-only and credential-free by construction. It fetches nothing, checks out nothing, resets
# nothing, and opens no authenticated connection: a reachability probe that needs a password is a
# probe that fails for two different reasons and cannot tell you which. Interface and division of
# labour: DRIFT-SCAN.md in this directory.
#
#   ./drift-probe.sh tip   [repo_dir]              git tip facts for one checkout
#   ./drift-probe.sh reach <host:port>[,host:port] TCP connect to each target
#   ./drift-probe.sh all                           both, as one JSON object
#
# Exit status is about the PROBE, not about the result: 0 means every probe ran and the JSON below
# is complete. An unreachable target is `"reachable": false` with exit 0, because "the desk cannot
# see Greptime" is an answer drift_scan needs, not a script failure.
#
#   0  every probe ran; trust the JSON
#   2  usage error
#   3  a probe could not be ATTEMPTED — no such checkout, an empty target list, or a malformed
#      target. Distinct from 0 on purpose: an empty DRIFT_REACH_TARGETS would otherwise exit 0
#      with `"targets": []`, and a misconfiguration that checked no plane at all would read as a
#      clean reachability result. `ok` in the JSON carries the same answer for a caller that
#      parses rather than shells out.
#
# Env (all optional; see lease-heartbeat.env.example):
#   DRIFT_REPO_DIR DRIFT_GIT_REMOTE DRIFT_GIT_BRANCH DRIFT_REACH_TARGETS DRIFT_PROBE_TIMEOUT_S
#   DRIFT_GIT_TIMEOUT_S

set -euo pipefail

REPO_DIR="${DRIFT_REPO_DIR:-$(pwd)}"
GIT_REMOTE="${DRIFT_GIT_REMOTE:-}"
GIT_BRANCH="${DRIFT_GIT_BRANCH:-main}"
REACH_TARGETS="${DRIFT_REACH_TARGETS:-}"
PROBE_TIMEOUT_S="${DRIFT_PROBE_TIMEOUT_S:-5}"
# ls-remote talks to the network and has no timeout of its own, so it gets one here.
GIT_TIMEOUT_S="${DRIFT_GIT_TIMEOUT_S:-$PROBE_TIMEOUT_S}"

# Probe could not be attempted — see the exit-status table above.
EX_NOT_ATTEMPTED=3
# Internal only, never the script's own exit status: it lets probe_reach tell a target it could
# not PARSE from one it could not RUN. Both are configuration faults and both end in exit 3, but
# they need different fixes, so they are counted separately in the JSON.
EX_MALFORMED=4

# `timeout` exit codes that mean the command NEVER RAN, as opposed to ran-and-failed. 124 is
# absent on purpose: that one means the command ran and was killed at the deadline, which is a
# probe result. These three mean `timeout` itself could not start it — a bad interval, or no
# `timeout` on PATH — so whatever they precede was never attempted.
timeout_never_ran() { [[ $1 -eq 125 || $1 -eq 126 || $1 -eq 127 ]]; }

# The numeric env inputs are interpolated into JSON unquoted and passed to `timeout` as a
# duration, so an unvalidated one is two bugs at once: `timeout_s: abc` is not parseable JSON,
# and `timeout abc` exits 125 before the probe runs while every target still reports
# "reachable": false — a typo in the env file reading as "every plane is down". Validate once,
# here, rather than patching each call site. `timeout`'s own suffixes are accepted.
die_config() {
  printf '{"probe":%s,"checked_at":%s,"ok":false,"error":%s}\n' \
    "$(jstr "config")" "$(jstr "$(now_utc)")" "$(jstr "$1")" >&2
  exit "$EX_NOT_ATTEMPTED"
}

# Seconds as a bare number, no unit suffix, and no leading zero. The variables are named
# *_TIMEOUT_S and the field is emitted as `"timeout_s": <n>`, so a suffix would both make that
# name a lie and produce `"timeout_s":2s`. A leading zero is the same class of fault and easier to
# miss: `05` is a perfectly ordinary thing to type, `timeout` accepts it, and it emits
# `"timeout_s":05` — which JSON forbids, so the snapshot the caller gets is unparseable even
# though every probe succeeded. Both are rejected here rather than normalised, because silently
# turning 05 into 5 hides a config file that says something the operator did not mean.
# `timeout` reads a bare number as seconds, so nothing is lost.
check_duration() {
  local name="$1" value="$2"
  if [[ ! "$value" =~ ^(0|[1-9][0-9]*)([.][0-9]+)?$ ]]; then
    die_config "$name must be a number of seconds — no unit suffix, no leading zero (e.g. 5 or 2.5), got: $value"
  fi
  if [[ "$value" =~ ^0([.]0+)?$ ]]; then
    die_config "$name must be greater than zero, got: $value"
  fi
}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Minimal JSON string escaping: quote, backslash, control characters. Git ref names and error text
# reach this, and an unescaped quote in a branch name produces JSON the caller silently misparses.
jstr() {
  local s=${1-}
  s=${s//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\t'/\\t}
  s=${s//$'\r'/\\r}
  s=${s//$'\n'/\\n}
  printf '"%s"' "$s"
}

# --- git tip -----------------------------------------------------------------
# Local tip, local dirtiness, and (only when a remote is named) the remote tip plus the
# ahead/behind relation. Never a fetch: a probe that mutates the checkout it is measuring is not a
# probe. Without a fetch the remote tip comes from ls-remote, which reads refs and no objects.
probe_tip() {
  local dir="$1" local_tip="" branch="" dirty="unknown" remote_tip="" relation="unknown" err=""
  # `ok` answers "is this output trustworthy", not "did the remote answer". A remote that timed
  # out or refused is a RESULT (ok stays true, relation stays unknown, note says why); a lookup
  # that could not be started at all is not (ok goes false and the caller must not trust it).
  local ok="true" attempted=0

  if ! git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
    printf '{"probe":"git_tip","checked_at":%s,"repo_dir":%s,"ok":false,"error":%s}\n' \
      "$(jstr "$(now_utc)")" "$(jstr "$dir")" "$(jstr "not a git checkout")"
    return "$EX_NOT_ATTEMPTED"
  fi

  local_tip=$(git -C "$dir" rev-parse HEAD)
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  if [[ -z "$(git -C "$dir" status --porcelain)" ]]; then dirty="false"; else dirty="true"; fi

  if [[ -n "$GIT_REMOTE" ]]; then
    local ls_out="" ls_rc=0
    # Bounded, and never interactive. Without the timeout an unresponsive remote hangs the whole
    # scan — in `all` the reachability half never even starts, so a stalled git server looks like
    # a stalled desk. GIT_TERMINAL_PROMPT and ssh BatchMode stop it blocking on a credential
    # prompt, which no timeout would make a useful answer anyway.
    if ls_out=$(GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -oBatchMode=yes' \
                  timeout "$GIT_TIMEOUT_S" \
                  git -C "$dir" ls-remote "$GIT_REMOTE" "refs/heads/$GIT_BRANCH" 2>&1); then
      remote_tip=${ls_out%%$'\t'*}
      [[ "$remote_tip" == "$ls_out" ]] && remote_tip=""
      if [[ -z "$remote_tip" ]]; then
        err="remote has no refs/heads/$GIT_BRANCH"
      elif [[ "$remote_tip" == "$local_tip" ]]; then
        relation="same"
      elif git -C "$dir" cat-file -e "$remote_tip^{commit}" 2>/dev/null; then
        # Both commits are local objects, so the relation is answerable without a fetch.
        if git -C "$dir" merge-base --is-ancestor "$remote_tip" "$local_tip" 2>/dev/null; then
          relation="ahead"
        elif git -C "$dir" merge-base --is-ancestor "$local_tip" "$remote_tip" 2>/dev/null; then
          relation="behind"
        else
          relation="diverged"
        fi
      else
        # The remote tip is not in this object store. Behind or diverged — a fetch would say
        # which, and this probe does not fetch, so it reports the honest "unknown_no_fetch".
        relation="unknown_no_fetch"
      fi
    else
      ls_rc=$?
      # A timed-out remote is still a probe RESULT, not a probe that could not be attempted: the
      # honest answer is "the git remote did not answer in time", so the relation stays unknown
      # and the exit status stays 0.
      if [[ $ls_rc -eq 124 ]]; then
        err="ls-remote timed out after ${GIT_TIMEOUT_S}s"
      elif timeout_never_ran "$ls_rc"; then
        # The lookup NEVER RAN. Reporting ok:true here would let a caller that trusts `ok` treat
        # an unchecked remote tip as a completed check — the same confusion the empty-target case
        # creates for reachability, and just as wrong.
        ok="false"
        attempted="$EX_NOT_ATTEMPTED"
        err="ls-remote could not be started (exit $ls_rc): ${ls_out//$'\n'/ }"
      else
        err="ls-remote failed (exit $ls_rc): ${ls_out//$'\n'/ }"
      fi
    fi
  else
    err="no DRIFT_GIT_REMOTE set — local tip only"
  fi

  # remote_checked is the unambiguous signal a caller actually wants: did this run obtain the
  # remote tip? False covers "no remote configured", "timed out", "git failed" and "never ran" —
  # `relation` alone cannot distinguish those from an answered lookup.
  local remote_checked="false"
  if [[ -n "$remote_tip" ]]; then remote_checked="true"; fi

  printf '{"probe":"git_tip","checked_at":%s,"repo_dir":%s,"ok":%s,"branch":%s,' \
    "$(jstr "$(now_utc)")" "$(jstr "$dir")" "$ok" "$(jstr "$branch")"
  printf '"local_tip":%s,"dirty":%s,"remote":%s,"remote_branch":%s,"remote_tip":%s,' \
    "$(jstr "$local_tip")" "$dirty" "$(jstr "$GIT_REMOTE")" "$(jstr "$GIT_BRANCH")" \
    "$(jstr "$remote_tip")"
  printf '"remote_checked":%s,"relation":%s,"note":%s}\n' \
    "$remote_checked" "$(jstr "$relation")" "$(jstr "$err")"
  return "$attempted"
}

# --- TCP reachability --------------------------------------------------------
# One bounded TCP connect per target. No protocol handshake and no auth, so the answer is strictly
# "the hop is open", which is exactly the input drift_scan needs and exactly as much as INFRA can
# honestly assert without the store credential.
probe_one_target() {
  local target="$1" host="" port="" started="" elapsed_ms="" reachable="false" err=""

  # An EMPTY entry is malformed, not skippable. `events-host:4000,` has a trailing comma, and
  # quietly dropping the empty field would have the probe check one plane, count one target and
  # report ok:true for a list the operator wrote two entries into — a whole plane disappearing
  # from the scan because of a stray comma is exactly the silent gap this probe exists to close.
  if [[ -z "$target" ]]; then
    printf '{"target":%s,"reachable":false,"probed":false,"error":%s}' \
      "$(jstr "")" "$(jstr "empty target entry — check for a stray or trailing comma")"
    return "$EX_MALFORMED"
  fi

  host=${target%%:*}
  port=${target##*:}

  # The port is emitted as an unquoted JSON number, so it is validated like a duration: no leading
  # zero (`080` would emit `"port":080`, which JSON forbids), and inside the real port range. A
  # probe whose snapshot cannot be parsed is worth no more than a probe that did not run.
  if [[ -z "$host" || -z "$port" || "$host" == "$target" || ! "$port" =~ ^[1-9][0-9]*$ ]]; then
    printf '{"target":%s,"reachable":false,"probed":false,"error":%s}' \
      "$(jstr "$target")" "$(jstr "expected host:port, with a port of 1-65535 and no leading zero")"
    return "$EX_MALFORMED"
  fi
  if (( port > 65535 )); then
    printf '{"target":%s,"reachable":false,"probed":false,"error":%s}' \
      "$(jstr "$target")" "$(jstr "port out of range (1-65535): $port")"
    return "$EX_MALFORMED"
  fi

  local rc=0 probed="true" attempted=0
  started=$(date +%s%3N)
  err=$(timeout "$PROBE_TIMEOUT_S" \
          bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$host" "$port" 2>&1) && rc=0 || rc=$?
  elapsed_ms=$(( $(date +%s%3N) - started ))

  if [[ $rc -eq 0 ]]; then
    reachable="true"
    err=""
  elif timeout_never_ran "$rc"; then
    # The connect NEVER RAN, so this target's state is unknown — not down. Reporting
    # "reachable": false here would turn one bad env value into "every plane is down", which is
    # the most misleading thing a reachability probe can say.
    probed="false"
    attempted="$EX_NOT_ATTEMPTED"
    err="probe could not be started (exit $rc): ${err//$'\n'/ }"
  elif [[ $rc -eq 124 ]]; then
    err="connect timed out after ${PROBE_TIMEOUT_S}"
  elif [[ -z "$err" ]]; then
    err="connect failed (exit $rc)"
  fi

  printf '{"target":%s,"host":%s,"port":%s,"reachable":%s,"probed":%s,"latency_ms":%s,"error":%s}' \
    "$(jstr "$target")" "$(jstr "$host")" "$port" "$reachable" "$probed" "$elapsed_ms" \
    "$(jstr "${err//$'\n'/ }")"
  return "$attempted"
}

# An empty or malformed target list is a CONFIGURATION failure, not a reachability result. Exiting
# 0 on it would let "no plane was checked at all" read exactly like "every plane answered", which
# is the one confusion a drift scan cannot afford — so both cases return EX_NOT_ATTEMPTED and say
# so in `ok`, while every well-formed target is still probed and reported.
probe_reach() {
  local targets="$1" first=1 t rc=0 requested=0 malformed=0 unattempted=0 status=0 ok="true"
  printf '{"probe":"reachability","checked_at":%s,"timeout_s":%s,"targets":[' \
    "$(jstr "$(now_utc)")" "$PROBE_TIMEOUT_S"
  if [[ -n "$targets" ]]; then
    # Split by hand rather than with IFS word-splitting or `read -ra`: both DISCARD a trailing
    # empty field, so `events-host:4000,` would arrive as one target and the stray comma — along
    # with whatever plane the operator meant to put after it — would vanish silently. This loop
    # keeps every field, empty ones included, so probe_one_target can count them as malformed.
    local rest="$targets"
    local -a parts=()
    while [[ "$rest" == *,* ]]; do
      parts+=("${rest%%,*}")
      rest="${rest#*,}"
    done
    parts+=("$rest")

    for t in "${parts[@]}"; do
      t="${t#"${t%%[![:space:]]*}"}"
      t="${t%"${t##*[![:space:]]}"}"
      requested=$((requested + 1))
      [[ $first -eq 1 ]] || printf ','
      first=0
      # A target that could not be parsed or could not be run is reported in its own object and
      # counted; it must not abort the remaining probes, but it must not be silently forgiven
      # either. The two are counted apart because they need different fixes: a malformed target
      # is a typo in DRIFT_REACH_TARGETS, an unattempted one is a broken probe environment.
      rc=0
      probe_one_target "$t" || rc=$?
      case $rc in
        0) ;;
        "$EX_MALFORMED")     malformed=$((malformed + 1)) ;;
        *)                   unattempted=$((unattempted + 1)) ;;
      esac
    done
  fi
  if [[ $requested -eq 0 || $malformed -gt 0 || $unattempted -gt 0 ]]; then
    status=$EX_NOT_ATTEMPTED
    ok="false"
  fi
  printf '],"targets_requested":%s,"targets_malformed":%s,"targets_unattempted":%s,"ok":%s}\n' \
    "$requested" "$malformed" "$unattempted" "$ok"
  return "$status"
}

usage() {
  printf 'usage: %s {tip [repo_dir] | reach <host:port>[,host:port] | all}\n' "${0##*/}" >&2
}

main() {
  local cmd="${1:-}"
  # Before any probe: these two are interpolated into JSON unquoted and handed to `timeout`, so
  # an invalid one must stop the run rather than produce unparseable output and a false "down".
  case "$cmd" in
    -h|--help|help) : ;;
    *) check_duration DRIFT_PROBE_TIMEOUT_S "$PROBE_TIMEOUT_S"
       check_duration DRIFT_GIT_TIMEOUT_S "$GIT_TIMEOUT_S" ;;
  esac
  case "$cmd" in
    tip)   probe_tip "${2:-$REPO_DIR}" ;;
    reach) probe_reach "${2:-$REACH_TARGETS}" ;;
    all)
      # Captured rather than piped: a pipeline's status is the LAST command's, so piping through
      # `tr` would discard exactly the sub-probe status this command has to propagate.
      local tip_json="" reach_json="" tip_rc=0 reach_rc=0 ok="true"
      tip_json=$(probe_tip "$REPO_DIR") || tip_rc=$?
      reach_json=$(probe_reach "$REACH_TARGETS") || reach_rc=$?
      if [[ $tip_rc -ne 0 || $reach_rc -ne 0 ]]; then ok="false"; fi
      printf '{"drift_probe":1,"checked_at":%s,"ok":%s,"git_tip":%s,"reachability":%s}\n' \
        "$(jstr "$(now_utc)")" "$ok" "${tip_json//$'\n'/}" "${reach_json//$'\n'/}"
      if [[ "$ok" == "false" ]]; then return "$EX_NOT_ATTEMPTED"; fi
      ;;
    -h|--help|help) usage ;;
    *) usage; return 2 ;;
  esac
}

main "$@"
