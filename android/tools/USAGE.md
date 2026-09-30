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
| `unit_test` | `--module PATH --gradle-args ...` | `./gradlew :module:test` (module path is converted to a Gradle task ref); prints a skip line and exits 0 if no wrapper. `--gradle-args` consumes all remaining args verbatim (so `--offline` etc. work) and must be the last flag. |
| `instrumented_run` | `--serial --class --dry-run` | `adb shell am instrument -w CLASS`. |
| `logcat_capture` | `--serial --out PATH --seconds N --backend adb\|metavr` | adb logcat, or documents `device_logcat` via the bridge. |
| `screenshot` | `--serial --out PATH --backend adb\|metavr` | adb screencap, or documents `device_screenshot`. |
| `ui_dump` | `--serial --out PATH` | MetaVR-primary wrap of `ui_dump`. |
| `ui_tap` | `--serial --resource-id / --text` | MetaVR-primary wrap of `ui_tap`; requires one target. |

Missing binary or no connected device: the library raises `DeviceUnavailable`; the CLI prints `skipped: <reason>` and exits 0 so CI without an emulator is fine. `--dry-run` never spawns and never needs a device.

## MetaVR bridge

`metavr_bridge.py` maps local names to documented MetaVR tool ids only:

- `device_logcat`
- `device_screenshot`
- `ui_dump`
- `ui_tap`
- `metavr_device`

It does **not** call MCP, the network, or a metavr binary. When no device is connected, `require_device()` raises `DeviceUnavailable` naming the tool id.

## CI test entrypoint

`android/tools/run_tests.sh` runs the android.tools unit suite
(`python3 -m unittest android.tools.tests.test_tools -v`). It requires no
adb/emulator/gradlew and exits nonzero on failure. Any INFRA-owned workflow
under `.github/workflows/**` can shell out to it; that wiring is left to
INFRA since workflow files are outside the ANDROID seat.

## Ownership note

`android/tools/README.md` is not shipped: the basename `README.md` is owned by QUALITY (`ownership.yaml`). This `USAGE.md` lives under `android/**` (ANDROID seat).
