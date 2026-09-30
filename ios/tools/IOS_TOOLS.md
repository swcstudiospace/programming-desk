# ios.tools

`python -m ios.tools <cmd>` from the repo root.

SPE-5161 asked for `ios/tools/README.md`. That file is not here. `ownership.yaml` has a bare `README.md` rule owned by QUALITY that matches at any depth and wins over `ios/**`, so G-1 would reject it. This note is the substitute until QUALITY moves that rule.

| Command | Where it runs | Exit |
| --- | --- | --- |
| `plist_lint --path FILE --json` | Linux, file on disk | 0 ok, 1 blank usage or bad plist, 2 missing file |
| `entitlements_scan --path DIR` or `--diff BASE HEAD` | Linux | 0 ok, 1 unreadable plist, 2 missing args |
| `spm_test_linux --package PATH` | `swift test` only if `swift` is on PATH | 3 skip when the toolchain is missing. `--dry-run` prints the argv and does not run it |
| `snapshot_diff --before --after --out` | sha256, plus PNG width/height | 0 written. Not a pixel diff |
| `xcodebuild_receipt --log PATH` | saved CI log only | does not invoke xcodebuild and does not boot a Simulator |
| `device_screenshot` / `ui_dump` / `ui_tap` | executable of that exact name, `--serial` `--out` | 3 skip when the name is not on PATH. No stand-in image |

No App Store submission. No entitlement change in an app target.
