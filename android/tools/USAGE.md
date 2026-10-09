# android.tools

Local adb/gradle helpers and a MetaVR tool-id bridge for the Android seat.

Entry (from repo root):

```
python -m android.tools <cmd>
```

## Commands

| cmd | flags | notes |
|---|---|---|
| `emu_boot` | `--avd NAME --timeout-sec N --dry-run` | Prints `emulator -avd NAME` under `--dry-run`; never needs a device. |
| `adb_devices` | `--json` | Runs `adb devices -l`; structured text or JSON. |
| `install_apk` | `--apk PATH --serial S --dry-run` | `adb [-s S] install -r APK`. |
| `unit_test` | `--module PATH --gradle-args ...` | `./gradlew test`; prints a skip line and exits 0 if no wrapper. |
| `instrumented_run` | `--serial --class --dry-run` | `adb shell am instrument -w CLASS`. |
| `logcat_capture` | `--serial --out PATH --seconds N --backend adb\|metavr` | adb logcat, or documents `device_logcat` via the bridge. |
| `screenshot` | `--serial --out PATH --backend adb\|metavr` | adb screencap, or documents `device_screenshot`. |
| `ui_dump` | `--serial --out PATH` | MetaVR-primary wrap of `ui_dump`. |
| `ui_tap` | `--serial --resource-id / --text` | MetaVR-primary wrap of `ui_tap`; requires one target. |
| `accel_check` | `--json --require` | Host probe only. Prints JSON with `kvm_node`, `kvm_usable`, `emulator_accel`, and `recommendation` (`accelerated`, `tcg-only`, or `no-emulator`). Opens `/dev/kvm` read-only when the node exists, and runs `emulator -accel-check` when that binary is on `PATH`. Does not pass `-avd` and does not start a guest. Exit 0 with the report. `--require` exits 3 unless the recommendation is `accelerated`. |
| `maestro_flow` | `--serial S --flow PATH --out DIR` | `maestro --device S test --format junit --output DIR/maestro-junit.xml --debug-output DIR/debug`. The wrapper does not pin Maestro; 2.11.0 is the version the workflow is expected to install. Exit 1 when the JUnit report has a failure/error, is unreadable or unrelated XML, or contains no executed (non-skipped) test cases. |
| `screenrecord` | `--serial S --out DIR --seconds N` | `adb shell screenrecord --time-limit N` then `adb pull` to a fresh temporary file under `DIR`. A successful pull producing a nonempty regular file atomically replaces `DIR/screenrecord.mp4`; a failed, empty, or interrupted pull preserves the previous recording. `N` is an integer from 1 to 180 (default 30). Values outside that range are a usage error (exit 2) and are not clamped. |

## Exit codes

`maestro_flow` and `screenrecord` exit 3 when they skip: `maestro` or `adb` is missing, or the serial is not a connected device in state `device`. `accel_check` exits 0 and prints the JSON report either way. `accel_check --require` exits 3 when the recommendation is `tcg-only` or `no-emulator`. Usage mistakes (bad serial, missing flow, `--seconds` outside 1..180, a symlink that would leave `--out`) and local output preparation/replacement/cleanup failures exit 2. A JUnit failure, a report with no executed cases, a failed recording, or a failed pull exits 1. An interrupted `screenrecord` exits 130, including interruption during cleanup; local cleanup errors do not override that interruption status.

Commands `emu_boot` through `ui_tap` still print `skipped: <reason>` and exit 0 when a binary or device is missing. `contracts/tool-packs/androidlocal.yaml` records that exit code for `emu_boot`, `adb_devices`, `install_apk`, `unit_test`, and `instrumented_run`, so this harness leaves those commands alone. QUALITY can decide later whether a contract change should use one skip code for both generations.

`--dry-run` on the original commands never spawns a process and never needs a device. `accel_check` has no dry-run because the probe itself does not start a VM.

`maestro_flow` resolves the flow and the Maestro executable found on `PATH` relative to the caller's working directory before running Maestro from `--out`. Both a relative flow path and a relative `PATH` entry are supported.

`maestro_flow` and `screenrecord` create files only as children of the directory passed to `--out` (`maestro-junit.xml`, `debug/`, `screenrecord.mp4`, and temporary `.screenrecord-*.mp4` pull files). A symlink at one of the final output names is refused. Temporary pull files are removed after unsuccessful pulls; an inability to remove one is reported as a local usage error rather than a traceback.

After recording starts, `screenrecord` always attempts best-effort removal of its unique `/sdcard/desk-screenrecord-*.mp4` device file, including after a timeout, failed pull, or interruption. A remote cleanup failure adds a warning that the device file may remain, without turning a failed/interrupted capture into success. A successfully pulled local recording remains available even if remote cleanup fails.

## MetaVR bridge

`metavr_bridge.py` maps local names to documented MetaVR tool ids only:

- `device_logcat`
- `device_screenshot`
- `ui_dump`
- `ui_tap`
- `metavr_device`

It does **not** call MCP, the network, or a metavr binary. When no device is connected, `require_device()` raises `DeviceUnavailable` naming the tool id.

## Ownership note

`android/tools/README.md` is not shipped: the basename `README.md` is owned by QUALITY (`ownership.yaml`). This `USAGE.md` lives under `android/**` (ANDROID seat).
