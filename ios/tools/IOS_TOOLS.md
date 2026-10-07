# iOS Linux-safe checks

Python tools under `ios/tools/`. They run on Linux. They do not invoke `xcodebuild`, boot the Xcode Simulator, sign a binary, or talk to App Store Connect.

SPE-5161 asked for `ios/tools/README.md`. That file is not here. `ownership.yaml` has a bare `README.md` rule owned by QUALITY that matches at any depth and wins over `ios/**`, so G-1 would reject it. This note is the substitute until QUALITY moves that rule.

## Modules

| Tool | What it does | What it refuses |
| --- | --- | --- |
| `spm_linux.py` | `swift test` when `Package.swift` and a `swift` binary exist | A missing toolchain is `unverified`/`skipped`, not a pass |
| `plist_lint.py` | Blank usage strings, always-location without when-in-use, entitlements that embed a key | Does not submit the plist |
| `entitlements.py` | Entitlement and usage-string scan, or a diff of two trees; tracks values and the owning target, not just key names | Does not change an app target's entitlements |
| `snapshot_diff.py` | sha256 diff of two directories, two files, or a file against a directory, plus PNG width/height | Not a pixel or UI snapshot |
| `metavr_evidence.py` | Evidence JSON for `remote` or `metavr` runs | Any simulator kind. No MetaVR SDK is bundled |
| `metavr_bridge.py` | Wraps an on-PATH executable of the exact tool name | Invents no vendor SDK; a missing name is a skip |
| `xcodebuild_receipt.py` | Parses a CI log or JSON artifact | Does not launch `xcodebuild` |

## CLI

`python -m ios.tools <cmd>` from the repo root.

| Command | Where it runs | Exit |
| --- | --- | --- |
| `plist_lint --path FILE --json` | Linux, file or directory on disk | 0 ok, 1 blank usage or bad plist, 2 missing file |
| `entitlements_scan --path DIR` or `--diff BASE HEAD` | Linux | 0 ok, 1 unreadable plist or blank usage description, 2 missing args. Entitlement/usage values and their owning file (target) are tracked, not just key names |
| `spm_test_linux --package PATH` | `swift test` only if `swift` is on PATH | 3 skip when the toolchain is missing. `--dry-run` prints the argv and does not run it |
| `snapshot_diff --before --after --out` | sha256, plus PNG width/height | 0 written. Not a pixel diff. A renamed single file still pairs, so a rename is reported as changed-or-not rather than one add plus one remove |
| `xcodebuild_receipt --log PATH` | saved CI log only | does not invoke xcodebuild and does not boot a Simulator. `status` is `failed` if any `** ... FAILED **` banner appears anywhere in the log, not only the last one, and `scheme`/`destination` name the invocation that produced that banner |
| `device_screenshot` / `ui_dump` | executable of that exact name, `--serial` `--out` | 3 skip when the name is not on PATH. No stand-in image |
| `ui_tap` | executable named `ui_tap`, `--serial` `--out` `--target` | `--target` selects what to tap and is required; 3 skip when the name is not on PATH |

No App Store submission. No entitlement change in an app target.

`README.md` is not used here. A bare `README.md` rule in `ownership.yaml` belongs to QUALITY at any depth.
