# iOS Linux-safe checks

Python tools under `ios/tools/`. They run on Linux. They do not invoke `xcodebuild`, boot the Xcode Simulator, sign a binary, or talk to App Store Connect.

| Tool | What it does | What it refuses |
| --- | --- | --- |
| `spm_linux.py` | `swift test` when `Package.swift` and a `swift` binary exist | A missing toolchain is `unverified`, not a pass |
| `plist_lint.py` | Blank usage strings, always-location without when-in-use, entitlements that embed a key | Does not submit the plist |
| `snapshot_diff.py` | sha256 diff of two directories | Not a pixel or UI snapshot |
| `metavr_evidence.py` | Evidence JSON for `remote` or `metavr` runs | Any simulator kind. No MetaVR SDK is bundled |
| `xcodebuild_receipt.py` | Parses a CI log or JSON artifact | Does not launch `xcodebuild` |

`README.md` is not used here. A bare `README.md` rule in `ownership.yaml` belongs to QUALITY at any depth.
