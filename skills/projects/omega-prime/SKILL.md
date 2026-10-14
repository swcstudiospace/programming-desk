---
name: omega-prime
description: Layout, build, test, and deploy rules for Omega Prime (swcstudiospace/omes-bot). Use before editing the Python agent, v17 XML prompts, or Purple-Team pin-bump, engagement, and RoE tooling.
bots: [bot-00-programming-lead, bot-01-systems-backend]
gates: [G-3, G-5]
---

# Omega Prime

## L1 — Summary

Omega Prime is one Python process: a Hermes conversation loop, an oh-my-pi harness port, and optional Prime capabilities. The repo is `swcstudiospace/omes-bot`. The product package is `omega_prime`. This skill is pinned to commit `2322d46` (`2322d46faeb33eddbed9d24b839504f9319359a3`), "Wrap Omega Prime prompts in XML and ship v17 to main (#34)".

**Every deploy needs Ming's explicit yes in the ticket.** Rendering a manifest and `deploy check` are not a deploy. `docker build`/`docker push`, `docker compose up`, `systemctl enable`, `kubectl apply`, and `deploy.py promote` are. Stop when the yes is missing.

```
Editing Omega Prime?
├─▶ Pin is 2322d46. Init submodules. Do not clone over prime-agent/. §1
│
├─▶ Python 3.12 for the documented route. CI is 3.12–3.14. §2
│
├─▶ Prompts are v17 XML. assemble-prompts.sh --check and prompt_format --check. §3
│
├─▶ Purple-Team batches 07–18 live in findings sync, pin-bump, the engagement report, and RoE grants. §4
│
└─▶ Deploy only after Ming's yes, staging evidence, then the same digest. §5
```

Do not print tokens, webhook URLs, Opsgenie keys, or Graph client secrets. The host refuses a token on the command line or in the environment.

---

## L2 — Method

### §1 Layout

| Path | What it is |
|---|---|
| `omega_prime/` | The Python product. Tests under `omega_prime/tests` |
| `omega_prime/prompts/bot-00-omega-prime.xml` | Seat prompt. Root element `agent`, `version="1.1"` |
| `omega_prime/prompts/_shared/core-directives.xml` | Shared directives prepended at assembly |
| `omega_prime/prompts-assembled/OMEGA_PRIME.xml` | Assembled prompt. Never hand-edit; regenerate and `--check` |
| `omega_prime/skills/`, `routines/`, `grokbot/plugin/commands/` | Prompt-native skills, routines, generated slash commands |
| `omega_prime/grokbot/findings_sync.py` | Tracker adapters (Slack, Teams, Graph, PagerDuty, Opsgenie, Jira/JSM) |
| `omega_prime/grokbot/pin_bump.py` | Red Team pin bump CLI |
| `omega_prime/grokbot/roe_lifecycle.py` | RoE grants: usage ledger, renewal, watchdog, conflicts |
| `omega_prime/grokbot/deploy.py` | Image and manifest renderer (`python -m omega_prime.grokbot.deploy`) |
| `omega_prime/tooling/prompt_format.py` | v17 XML gate |
| `scripts/engagement-report.py` | Engagement report CLI |
| `sidecar/` | Provenance (`sidecar/provenance.py`), RoE schema, cases |
| `prime-agent/` | Gitlink. Pinned in `omega_prime/contracts/prime-agent.pin.json` and `VENDOR.md` |
| `redteam/` | T3MP3ST gitlink. Not copied into the image. Python pack is `omega_prime/redteam/pack/` |
| `native/omega-prime-prime/` | Optional PyO3 bridge |
| `docs/deploy.md` | Host deploy and rollback. This skill does not replace it |
| `.github/workflows/ci.yml` | verify, lint, types, docs, redteam-provenance |

An ordinary `git clone` leaves the gitlinks empty. Clone with `--recurse-submodules`, or:

```bash
git submodule update --init --recursive
# Red Team backend not needed:
git submodule update --init prime-agent
```

Never `git clone` a Prime checkout into an already populated `prime-agent/`. The gitlink is the pin. The TypeScript Red Team backend is started separately; Omega Prime does not auto-launch it.

### §2 Build and test

Documented route is Python 3.12. Package metadata says `>=3.11`. CI verify/lint/types run 3.12, 3.13, and 3.14. Those are different claims.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest omega_prime/tests -q
.venv/bin/python -m omega_prime.setup_check --root .
.venv/bin/python -m ruff check omega_prime/
.venv/bin/python -m ruff format --check omega_prime/
.venv/bin/python -m mypy omega_prime/
.venv/bin/python -m omega_prime.evals.runner omega_prime/evals/cases
.venv/bin/python -m omega_prime.grokbot.readiness --root . --json
bash omega_prime/scripts/assemble-prompts.sh --check
.venv/bin/python -m omega_prime.tooling.prompt_format --check
.venv/bin/python -m omega_prime.tooling.catalog --check
.venv/bin/python -m omega_prime.tooling.plugin --check
python3 sidecar/provenance.py check
```

The full Python suite exercises the pinned Prime checkout even when Prime flags are off. Init `prime-agent` before `pytest`. Upstream Rust tests are a diagnostic, not the quickstart gate: the retained baseline is exit 101 (5089 passed, 2 failed). Do not skip those two failures to make the suite green.

Optional native bridge, after the pin is checked out:

```bash
cargo build --locked --manifest-path native/omega-prime-prime/Cargo.toml \
  --target-dir prime-agent/target
```

Unset `GH_TOKEN`, `GITHUB_TOKEN`, and `OPENROUTER_API_KEY` before Prime daemon tests. With them set, model tests resolve `github-copilot` instead of the hermetic catalog. `which prime-agent` is the wrong oracle for the TypeScript differential tests; CI does not install that binary.

### §3 v17 XML prompts

Commit `2322d46` wraps first-party prompts in XML (`version="1"` on the envelope). `python -m omega_prime.tooling.prompt_format --check` exits 0 only when all of these parse as strict XML:

- `omega_prime/prompts/bot-00-omega-prime.xml` (root `agent`)
- `omega_prime/prompts/_shared/core-directives.xml` (root `core_directives`)
- `omega_prime/prompts-assembled/OMEGA_PRIME.xml`
- skill bodies (`<skill>`), routines (`<routine>`), generated slash commands (`<command>`)
- runtime builders (system prompt, steer rows, context summaries, memory blocks, advisor notes)

Not checked, on purpose (`EXCLUDED_FROM_STANDARD`):

- `omega_prime/redteam/pack/` — vendored upstream bytes, provenance-pinned
- `omega_prime/grokbot/templates/OMEGA_PRIME.md` — Grok import format, no prompt body
- `omega_prime/evals/cases/` — eval data
- tool description strings

Assembly reads no ambient user flags. `bash omega_prime/scripts/assemble-prompts.sh --check` compares the assembled file. A hand edit of `prompts-assembled/OMEGA_PRIME.xml` fails that check. Phase 85 records both commands green on this tree (`85-VERIFICATION.md`, `verified_at: 2026-10-14`).

### §4 Purple-Team batches 07–18

History on this pin, oldest first. Each `feat(batch-NN)` commit is the code; the following `docs(v17)` commit is the report. Adapters live in `omega_prime/grokbot/findings_sync.py`. They share one idempotency rule: a row that already has `issue_url` is skipped, a failed row stays unsynced, and `dry_run` does not call the network.

| Batch | Commit | What landed |
|---|---|---|
| 07 | `1422a4a` | Moderate advisory sweep, Teams rich cards, drill-down diff, side-by-side comparison, semver-aware pin-bump |
| 08 | `d9baf48` | Microsoft Graph adapter, `pin-bump --bump-commit`, engagement `--export html`, RoE renewal reminders, risk-weighted coverage |
| 09 | `1dbb63c` | Slack Block Kit, `pin-bump --audit-only`, engagement `--compare`, Graph-delivered RoE renewal reminders, HTML coverage drill-down |
| 10 | `8b4bb5c` | PagerDuty Events v2, `pin-bump --json`, engagement `--annotate`, RoE `--revoke`, HTML risk-score badge |
| 11 | `7761406` | Opsgenie adapter, `pin-bump --pin`, engagement exec-summary and CSV, RoE expiry watchdog |
| 12 | `b733ace` | Jira Service Management adapter, `pin-bump --schedule`, engagement `--threshold`, RoE multi-grant, HTML evidence links |
| 13 | `93e95ea` | Webhook HMAC with rotation, `pin-bump --rollback`, engagement three-way `--delta`, per-grant tracker allowlists, `--export-md` |
| 14 | `448a18e` | Webhook payload templates, `pin-bump --explain`, engagement `--recipient-file` and scorecard export, RoE grant usage ledger |
| 15 | `59c6f84` | Retry-After handling, `pin-bump --verify`, engagement `--compare-multi` and trend glyphs, RoE expiry notices via adapters |
| 16 | `4be3a56` | Per-tracker quiet hours, `pin-bump --from-audit`, engagement `--sidebar`, renewal links in notices, per-class `--baseline` gates |
| 17 | `5c0670a` | Dispatch dry-run ledger, `pin-bump --pin-note`, engagement `--spark-history` / `--grant-matrix` / `--worst` |
| 18 | `0c38974` | Sync budget, `pin-bump --report-to`, digest plus JSONL export, RoE conflicts, chat reporting, purple cycle |

Functions: `sync_findings_slack`, `sync_findings_teams`, `sync_findings_graph` (OAuth client-credentials, then a Teams `chatMessage`), `sync_findings_pagerduty`, `sync_findings_opsgenie` (GenieKey header, alias is the dedupe hash), `sync_findings_jira`. A blank credential raises `ValueError`. It is not guessed.

`pin-bump` exit codes: 0 bump complete, 1 audit regressed or provenance still red, 2 usage error, 3 degraded (node/npm missing or submodule unreachable), 4 `--verify` smoke failed and the bump was rolled back locally with no PR. `--rollback` re-pins from the last bump record. When the tick carries a RoE artifact, that grant has to be active; without an artifact, rollback is fail-open for a local run. `--report-to PATH` replaces `report.md` and then `--rollback` can no longer read the report-based record.

Engagement report: `python3 scripts/engagement-report.py`. `--threshold` exits 3 on a failed gate. `--digest` cannot combine with `--json` or `--summary`. `--grant-matrix` reads a RoE artifact JSON and is fail-soft on an unreadable file.

RoE grants: `omega_prime/grokbot/roe_lifecycle.py` (`record_grant_usage`, `renewal_reminders`, `watchdog_check`, conflict detection) and `sidecar/roe.py`. Multi-grant and per-grant tracker allowlists are data on the artifact, not a second CLI personality. Do not invent a grant to make a pin-bump or a sync succeed.

### §5 Deploy rules

Ming's explicit yes comes first. Then staging, then the same digest.

```bash
python -m omega_prime.grokbot.deploy render --target k8s --out deploy/k8s
python -m omega_prime.grokbot.deploy check deploy/k8s
```

Targets: `docker`, `compose`, `systemd`, `k8s`. `check` exits 0 for clean or warnings, 1 on an error, 2 on bad usage. Promotion-marker findings (`promote-without-staging-evidence`, `missing-promotion-approval-record`) are warnings. A filename is not an approval and does not replace Ming's yes.

The token is a mode-0600 file owned by uid 10001. The host refuses a non-loopback bind without it, and refuses a token that group or others can read. Never put it in argv, an env var, a compose file, a unit, or a manifest. Clients send `Authorization: Bearer`.

The image root is read-only. State goes to `/var/lib/omega-prime` (`OMEGA_PRIME_STATE_DIR`, `OMEGA_PRIME_AUDIT_LOG`). One replica: SSE sessions live in the process. `redteam/` is excluded from the image; `omega_prime/redteam/` Python adapters stay.

Rollback is the prior validated digest or the retained image archive, not a rebuild of the old tag. `docs/deploy.md` is the procedure. This skill does not authorise running it.

### §6 Gotchas

- Submodule not inited: pytest and provenance fail in ways that look like missing product code.
- Cloning into `prime-agent/` destroys the gitlink.
- CI is 3.12–3.14. A local 3.11 venv can pass metadata and still miss a 3.12-only failure.
- `prompt_format --check` will try to XML-parse a skill you wrap in Markdown only. v17 wants the envelope.
- Red Team pack bytes are upstream. Edit them in the upstream pin, not by reformatting the vendored tree.
- `pin-bump --open-pr` pushes a branch and opens a GitHub PR. That is not Ming's deploy yes, and it is not something to run unasked.
- `--verify` failure rolls back locally and exits 4. Do not "fix" that by skipping the audit.
- Graph, Opsgenie, PagerDuty, Slack, and Teams adapters post real messages. `dry_run=True` is the safe call.
- Provider credentials and the token file stay out of receipts, skills, and chat.
