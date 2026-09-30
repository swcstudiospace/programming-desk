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
      else
        err="ls-remote failed (exit $ls_rc): ${ls_out//$'\n'/ }"
      fi
    fi
  else
    err="no DRIFT_GIT_REMOTE set — local tip only"
  fi

  printf '{"probe":"git_tip","checked_at":%s,"repo_dir":%s,"ok":true,"branch":%s,' \
    "$(jstr "$(now_utc)")" "$(jstr "$dir")" "$(jstr "$branch")"
  printf '"local_tip":%s,"dirty":%s,"remote":%s,"remote_branch":%s,"remote_tip":%s,' \
    "$(jstr "$local_tip")" "$dirty" "$(jstr "$GIT_REMOTE")" "$(jstr "$GIT_BRANCH")" \
    "$(jstr "$remote_tip")"
  printf '"relation":%s,"note":%s}\n' "$(jstr "$relation")" "$(jstr "$err")"
}

# --- TCP reachability --------------------------------------------------------
# One bounded TCP connect per target. No protocol handshake and no auth, so the answer is strictly
# "the hop is open", which is exactly the input drift_scan needs and exactly as much as INFRA can
# honestly assert without the store credential.
probe_one_target() {
  local target="$1" host="" port="" started="" elapsed_ms="" reachable="false" err=""
  host=${target%%:*}
  port=${target##*:}

  if [[ -z "$host" || -z "$port" || "$host" == "$target" || ! "$port" =~ ^[0-9]+$ ]]; then
    printf '{"target":%s,"reachable":false,"probed":false,"error":%s}' \
      "$(jstr "$target")" "$(jstr "expected host:port")"
    return "$EX_NOT_ATTEMPTED"
  fi

  started=$(date +%s%3N)
  if err=$(timeout "$PROBE_TIMEOUT_S" \
             bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$host" "$port" 2>&1); then
    reachable="true"
    err=""
  elif [[ -z "$err" ]]; then
    err="connect failed or timed out after ${PROBE_TIMEOUT_S}s"
  fi
  elapsed_ms=$(( $(date +%s%3N) - started ))

  printf '{"target":%s,"host":%s,"port":%s,"reachable":%s,"probed":true,"latency_ms":%s,"error":%s}' \
    "$(jstr "$target")" "$(jstr "$host")" "$port" "$reachable" "$elapsed_ms" \
    "$(jstr "${err//$'\n'/ }")"
}

# An empty or malformed target list is a CONFIGURATION failure, not a reachability result. Exiting
# 0 on it would let "no plane was checked at all" read exactly like "every plane answered", which
# is the one confusion a drift scan cannot afford — so both cases return EX_NOT_ATTEMPTED and say
# so in `ok`, while every well-formed target is still probed and reported.
probe_reach() {
  local targets="$1" first=1 t requested=0 malformed=0 status=0 ok="true"
  printf '{"probe":"reachability","checked_at":%s,"timeout_s":%s,"targets":[' \
    "$(jstr "$(now_utc)")" "$PROBE_TIMEOUT_S"
  if [[ -n "$targets" ]]; then
    local IFS=','
    for t in $targets; do
      t="${t#"${t%%[![:space:]]*}"}"
      t="${t%"${t##*[![:space:]]}"}"
      [[ -z "$t" ]] && continue
      requested=$((requested + 1))
      [[ $first -eq 1 ]] || printf ','
      first=0
      # A malformed target is reported in its own object and counted; it must not abort the
      # remaining probes, but it must not be silently forgiven either.
      if ! probe_one_target "$t"; then
        malformed=$((malformed + 1))
      fi
    done
  fi
  if [[ $requested -eq 0 || $malformed -gt 0 ]]; then
    status=$EX_NOT_ATTEMPTED
    ok="false"
  fi
  printf '],"targets_requested":%s,"targets_malformed":%s,"ok":%s}\n' \
    "$requested" "$malformed" "$ok"
  return "$status"
}

usage() {
  printf 'usage: %s {tip [repo_dir] | reach <host:port>[,host:port] | all}\n' "${0##*/}" >&2
}

main() {
  local cmd="${1:-}"
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
