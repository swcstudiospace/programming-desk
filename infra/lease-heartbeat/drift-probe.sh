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
# see Greptime" is an answer drift_scan needs, not a script failure. Non-zero means a probe could
# not be attempted (bad arguments, no such checkout) and the JSON must not be trusted.
#
# Env (all optional; see lease-heartbeat.env.example):
#   DRIFT_REPO_DIR DRIFT_GIT_REMOTE DRIFT_GIT_BRANCH DRIFT_REACH_TARGETS DRIFT_PROBE_TIMEOUT_S

set -euo pipefail

REPO_DIR="${DRIFT_REPO_DIR:-$(pwd)}"
GIT_REMOTE="${DRIFT_GIT_REMOTE:-}"
GIT_BRANCH="${DRIFT_GIT_BRANCH:-main}"
REACH_TARGETS="${DRIFT_REACH_TARGETS:-}"
PROBE_TIMEOUT_S="${DRIFT_PROBE_TIMEOUT_S:-5}"

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
    return 1
  fi

  local_tip=$(git -C "$dir" rev-parse HEAD)
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD)
  if [[ -z "$(git -C "$dir" status --porcelain)" ]]; then dirty="false"; else dirty="true"; fi

  if [[ -n "$GIT_REMOTE" ]]; then
    local ls_out=""
    if ls_out=$(git -C "$dir" ls-remote "$GIT_REMOTE" "refs/heads/$GIT_BRANCH" 2>&1); then
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
      err="ls-remote failed: ${ls_out//$'\n'/ }"
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
    printf '{"target":%s,"reachable":false,"error":%s}' \
      "$(jstr "$target")" "$(jstr "expected host:port")"
    return 1
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

  printf '{"target":%s,"host":%s,"port":%s,"reachable":%s,"latency_ms":%s,"error":%s}' \
    "$(jstr "$target")" "$(jstr "$host")" "$port" "$reachable" "$elapsed_ms" \
    "$(jstr "${err//$'\n'/ }")"
}

probe_reach() {
  local targets="$1" first=1 t
  printf '{"probe":"reachability","checked_at":%s,"timeout_s":%s,"targets":[' \
    "$(jstr "$(now_utc)")" "$PROBE_TIMEOUT_S"
  if [[ -n "$targets" ]]; then
    local IFS=','
    for t in $targets; do
      t="${t#"${t%%[![:space:]]*}"}"
      t="${t%"${t##*[![:space:]]}"}"
      [[ -z "$t" ]] && continue
      [[ $first -eq 1 ]] || printf ','
      first=0
      # A malformed target is reported in its own object; it must not abort the remaining probes.
      probe_one_target "$t" || true
    done
  fi
  printf ']}\n'
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
      printf '{"drift_probe":1,"checked_at":%s,"git_tip":' "$(jstr "$(now_utc)")"
      probe_tip "$REPO_DIR" | tr -d '\n'
      printf ',"reachability":'
      probe_reach "$REACH_TARGETS" | tr -d '\n'
      printf '}\n'
      ;;
    -h|--help|help) usage ;;
    *) usage; return 2 ;;
  esac
}

main "$@"
