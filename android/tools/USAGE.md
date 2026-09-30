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

Missing binary or no connected device: the library raises `DeviceUnavailable`; the CLI prints `skipped: <reason>` and exits 0 so CI without an emulator is fine. `--dry-run` never spawns and never needs a device.

A command that *does* reach a connected device and fails there (a rejected APK, a failed instrumentation run, a screencap/logcat error) is reported as `error: ...` on a nonzero exit, not silently swallowed as a skip — only the documented no-binary/no-device cases skip with exit 0.

## MetaVR bridge

`metavr_bridge.py` maps local names to documented MetaVR tool ids only:

- `device_logcat`
- `device_screenshot`
- `ui_dump`
- `ui_tap`
- `metavr_device`

It does **not** call MCP, the network, or a metavr binary. Connection state defaults to auto-detecting a device via `adb devices -l` (a Quest/MetaVR headset in USB debugging mode enumerates like any other adb device); `set_device_connected(True|False)` forces the state for tests or callers that know better. When no device is connected, `require_device()` raises `DeviceUnavailable` naming the tool id.

## Tests

`./android/tools/run_tests.sh` runs this package's suite (`python3 -m unittest android.tools.tests.test_tools`). It is not wired into `.github/workflows/gates.yml` — that file is INFRA-owned (`ownership.yaml`) — so the repo's CI gate does not run it yet; this script is the ANDROID-owned entrypoint for INFRA to call.

## Ownership note

`android/tools/README.md` is not shipped: the basename `README.md` is owned by QUALITY (`ownership.yaml`). This `USAGE.md` lives under `android/**` (ANDROID seat).
