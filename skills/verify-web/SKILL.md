---
name: verify-web
description: Prove a browser or Vercel change on the preview and the real click path. Use for WEB seat work that a person opens in a browser.
bots: [bot-02-web-edge]
gates: [G-2]
---

# Verify web

## L1 — Summary

**A green type-check is not a page that loaded.** WEB proves the preview and
the click path, then maps that run onto the receipt.

**Decision tree:**

```
Is the change something a person does in a browser?
├─ NO ──▶ verify-systems or verify-desktop may own it. Do not borrow this skill.
└─ YES
    ├─ Public product with a Playwright suite (clippyos pins Playwright 1.64.0)?
    │   └─▶ Drive that suite. A missing browser is unverified, not a pass.
    └─ Desk checkout (no Playwright suite in this repo)?
        └─▶ desk_preview_check. Generated-bundle secret coverage stays unverified.
```

Apply the proof standard in `skills/verify/SKILL.md` before the first claim.

---

## Launch

Read `skills/platforms/vercel/SKILL.md` (preview before promote) and the read
tools in `contracts/tool-rosters/web.yaml`. For a user-visible page, copy
`skills/verify/references/feature-map-template.md` and fill the four headings
before Drive. This checkout has no `Playwright` suite and no web harness
directory; do not cite a helper that is not in the tree.

## Doctor

| Check | If it fails |
|---|---|
| You can name the preview URL you will open | Stop. Local-only is the failure mode in `skills/platforms/vercel/SKILL.md` |
| `desk_preview_check` is on the WEB roster you were served | A tool the gateway did not list does not exist |
| The product suite's browser can launch | Inconclusive: `no browser: Linux cloud agent` |

`desk_vercel_promote` and `desk_vercel_rollback` are g5. Doctor does not call
them. A promotion is not a verification step.

## Drive

1. Reproduce first when the report is a bug. Record the failing command with
   `expects_failure`.
2. On a product repo that already pins Playwright, run that repo's suite.
   clippyos is the first such repo (public, Playwright `qa-*.ts` suites,
   Playwright 1.64.0). Run the suite the repo documents. Capture the action
   and the resulting page state, including the side effect (the write, the
   navigation, the error that should appear).
3. On this desk checkout, call `desk_preview_check` with the preview `url`.
   The tool records status, latency and a body hash and does not follow
   off-host redirects (`contracts/tool-rosters/web.yaml`).
   `desk_vercel_deployments` is the read that lists what was built. Neither
   promotes. `desk_bundle_secret_scan` runs G-3, which skips files under
   `dist`, `build`, and `.next` and does not recurse into directory arguments
   (`ci/gates/check_secrets.py`). Even `ok: true` or exit 0 does not prove
   generated bundles were scanned. Record `generated-bundle secret scan
   unverified: G-3 excludes generated output` until a real scan of the
   generated files exists. Do not claim bundle verification from this tool.
4. Mock only where production already isolates the call. A stub in place of
   the preview URL proves the stub.
5. A dry run that never opened the URL did not drive the page. Do not record
   a `--dry-run` command in the receipt; G-2 rejects that flag.

## Evidence

Save the preview result and any suite log under
`.verify-evidence/<task-id>/`. Put the observed status, action and resulting
state in the receipt's durable evidence, following `skills/verify/SKILL.md`;
an artifact filename alone is insufficient. Do not commit the directory
(`.gitignore`). A body hash you did not receive from `desk_preview_check`
is not a hash.

## Cleanup

Do not call `desk_vercel_promote` or `desk_vercel_rollback` from this skill.
Promotion and rollback need `rollback_plan` and `approval_id` (G-5, G-6).
Verification ends when the evidence is on the receipt.

## Where it runs

| Runner | Web proof it can host | When it cannot, write |
|---|---|---|
| Linux cloud agent | `desk_preview_check` observations and pytest; generated-bundle scan stays unverified. A browser suite only if the browser actually launched | `no browser: Linux cloud agent` |
| Self-hosted VPS runner | Same read tools, if the gateway is reachable. No assumption of a desktop browser | `no browser: self-hosted VPS runner` |
| GitHub-hosted `ubuntu-latest` | Public-repo browser suites when the workflow installs the pinned browser | `browser suite not run: workflow not in this checkout` |
| Ming's Mac | Private-repo browser runs when a browser is installed | `no browser: Ming's Mac` |

This repo's CI runs on the self-hosted VPS runner because hosted minutes are
blocked. Public product repos are the exception and may use GitHub-hosted
runners. Do not add a workflow in this unit.

## Receipt mapping

| Observation | Field |
|---|---|
| Preview status from `desk_preview_check` | `commands[]` only for an actually executed replayable shell/CLI invocation with its observed process exit code and result excerpt. A tool-only observation stays separate; the G-2 proof claim stays `unverified` |
| Playwright (or other) suite exit code | a separate command. Exit 0 supports "the suite passed" only. It does not support "promoted" |
| `desk_bundle_secret_scan` result | `unverified` for generated-bundle secret coverage, even if G-3 returned exit 0 |
| Suite or preview you could not run | `unverified`, with the runner phrase from the table above |
| Reproduce-first failure | `expects_failure: true` on that claim |

Tool names are not shell commands. For a command-backed gateway read, reuse
the authenticated `curl` route documented in
`services/desk-gateway/README.md`: POST JSON-RPC `tools/call` to `/mcp/web`
with `params.name` and `params.arguments` from the roster. Record the actual
invocation, working directory and named environment prerequisites without
secrets. Inspect the JSON-RPC error, MCP `isError`, and returned preview
`matches`/status; a successful HTTP request is not a successful preview.
Never assign a synthetic exit 0 to an MCP call.
