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
        └─▶ desk_preview_check and desk_bundle_secret_scan. Do not promote.
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
   off-host redirects (`contracts/tool-rosters/web.yaml`). Then call
   `desk_bundle_secret_scan` on the build output paths inside the checkout.
   `desk_vercel_deployments` is the read that lists what was built. None of
   these three promote.
4. Mock only where production already isolates the call. A stub in place of
   the preview URL proves the stub.
5. A dry run that never opened the URL did not drive the page. Do not record
   a `--dry-run` command in the receipt; G-2 rejects that flag.

## Evidence

Write the preview result and any suite log under
`.verify-evidence/<task-id>/`. `output_tail` names the file. Do not commit
the directory (`.gitignore`). A body hash you did not receive from
`desk_preview_check` is not a hash.

## Cleanup

Do not call `desk_vercel_promote` or `desk_vercel_rollback` from this skill.
Promotion and rollback need `rollback_plan` and `approval_id` (G-5, G-6).
Verification ends when the evidence is on the receipt.

## Where it runs

| Runner | Web proof it can host | When it cannot, write |
|---|---|---|
| Linux cloud agent | `desk_preview_check`, bundle scan, pytest. A browser suite only if the browser actually launched | `no browser: Linux cloud agent` |
| Self-hosted VPS runner | Same read tools, if the gateway is reachable. No assumption of a desktop browser | `no browser: self-hosted VPS runner` |
| GitHub-hosted `ubuntu-latest` | Public-repo browser suites when the workflow installs the pinned browser | `browser suite not run: workflow not in this checkout` |
| Ming's Mac | Private-repo browser runs when a browser is installed | `no browser: Ming's Mac` |

This repo's CI runs on the self-hosted VPS runner because hosted minutes are
blocked. Public product repos are the exception and may use GitHub-hosted
runners. Do not add a workflow in this unit.

## Receipt mapping

| Observation | Field |
|---|---|
| Preview status from `desk_preview_check` | a `commands` entry whose `output_tail` names the saved result, cited by the claim |
| Playwright (or other) suite exit code | a separate command. Exit 0 supports "the suite passed" only. It does not support "promoted" |
| Bundle scan | its own command. A lint pass is not this scan |
| Suite or preview you could not run | `unverified`, with the runner phrase from the table above |
| Reproduce-first failure | `expects_failure: true` on that claim |
