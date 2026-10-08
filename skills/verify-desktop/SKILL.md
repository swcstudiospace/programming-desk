---
name: verify-desktop
description: Prove a desktop shell by driving its window. Use for WEB seat work under a Tauri, Electron, or other desktop tree.
bots: [bot-02-web-edge]
gates: [G-2]
---

# Verify desktop

## L1 — Summary

**The webview's unit tests are not the window.** WEB owns desktop shells and
proves the window a person opens.

**Decision tree:**

```
Does the change live in a desktop shell a person launches?
├─ NO ──▶ Use verify-web for a browser page.
└─ YES
    ├─ Can this OS build and open that shell?
    │   ├─ NO ──▶ unverified names the OS. Do not claim the window.
    │   └─ YES ──▶ Drive the real window. Record action and resulting state.
    └─ About to sign or ship a store build? Stop. That is G-6, not Drive.
```

Apply the proof standard in `skills/verify/SKILL.md`. WEB loads this skill
beside `skills/verify-web/SKILL.md`.

---

## Launch

`ownership.yaml` assigns desktop shells to WEB (the desktop tree, the apps
desktop tree, electron, and tauri). None of those trees are in
programming-desk at the base this skill was written against. Launch starts in the product
checkout that contains the shell. clippyos is the first product (public,
Tauri plus web). Fill `skills/verify/references/feature-map-template.md` for
each window a person can open. There is no desktop harness in this desk
checkout; do not cite one.

## Doctor

Confirm the shell builds on the OS you are sitting on. Tauri v2's documented
driver is WebdriverIO `@wdio/tauri-service`; its embedded provider runs on
Windows, Linux and macOS. Use the version the product repo already pins. Do
not add an unpinned driver (`SECURITY.md` §6).

Playwright 1.64.0 can reach Electron through `_electron`. That support is
experimental. An experimental driver pass is reported as experimental in
`unverified` or in the claim text, because a reviewer who reads "the app
works" will think the driver is production-stable.

If the product checkout has no driver and no scripted window path, Doctor
stops. The check is inconclusive.

## Drive

1. Open the shell the way a person opens it. A test that renders a component
   without the shell process did not drive the window.
2. Perform the action from the feature map and record the resulting window
   state, plus the side effect outside the window (the file written, the
   setting stored).
3. Mock only at a boundary the production shell already has. Mocking the
   window itself proves nothing about the shell.
4. A dry run that prints a driver argv and never opens a window is not Drive.
   Do not put `--dry-run` in a receipt command (G-2).

## Evidence

Save the driver log and a capture of the resulting state under
`.verify-evidence/<task-id>/`. `output_tail` names those files. Do not commit
the directory.

## Cleanup

Close the shell process you started. Do not sign a binary and do not submit
a store build. Signing and store submission stay approval-gated (G-6). This
skill has no path that does either.

## Where it runs

| Runner | What it can host | Unverified line when it cannot |
|---|---|---|
| Linux cloud agent | A Linux build of the shell, if the product builds on Linux and the driver launches | `no desktop shell: Linux cloud agent` |
| Self-hosted VPS runner | A Linux build only when the product builds there. No macOS shell | `no desktop shell for macOS: self-hosted VPS runner` |
| GitHub-hosted `macos-26` | Public-repo macOS shell runs | `macOS shell not run: private repo` |
| GitHub-hosted `ubuntu-latest` | Public-repo Linux shell runs | `Linux shell not run: workflow not in this checkout` |
| Ming's Mac | Private-repo macOS shell | `no desktop shell: Ming's Mac` |

A Linux pass does not cover the Windows or macOS shell. Name the OS you did
not open.

## Receipt mapping

| Observation | Field |
|---|---|
| Driver command and exit code | `commands[]`. The claim cites that index |
| Window state you observed | `output_tail` names the capture. The claim says what state followed which action |
| OS you could not launch | `unverified` using the row above |
| Experimental Electron driver | the claim says experimental, or `unverified` says the driver is not a production boundary |
| Reproduce-first failure | `expects_failure: true` |
