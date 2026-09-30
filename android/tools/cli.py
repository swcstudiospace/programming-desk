"""argparse CLI: `python -m android.tools <cmd>`."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from . import adb, gradle, metavr_bridge
from .adb import DeviceUnavailable


def _print_skip(reason: str) -> int:
    print(f"skipped: {reason}")
    return 0


def cmd_emu_boot(args: argparse.Namespace) -> int:
    argv = adb.emu_boot_argv(args.avd)
    if args.dry_run:
        print(" ".join(argv))
        return 0
    try:
        adb.which_or_raise("emulator")
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    try:
        proc = subprocess.Popen(  # noqa: S603 — argv list, no shell
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: emulator ({exc})")
    except OSError as exc:
        return _print_skip(f"emulator spawn failed: {exc}")

    # Wait out the window checking the process is still alive, instead of an
    # unconditional 1-second sleep followed by an unconditional success print.
    # This only catches an immediate bad-AVD/spawn failure, not a full boot —
    # confirming the device is actually ready needs `adb wait-for-device`,
    # which can block far longer than a CLI call should.
    window = args.timeout_sec if args.timeout_sec and args.timeout_sec > 0 else 5
    deadline = time.monotonic() + window
    while time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.2)

    exit_code = proc.poll()
    if exit_code is not None:
        err = (proc.stderr.read() if proc.stderr else "").strip()
        return _print_skip(f"emulator exited early (code {exit_code}): {err or 'no output'}")
    print(f"emulator started for avd={args.avd} (pid={proc.pid}, still running after {window}s)")
    return 0


def cmd_adb_devices(args: argparse.Namespace) -> int:
    try:
        print(adb.adb_devices_list(as_json=bool(args.json)))
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))


def cmd_install_apk(args: argparse.Namespace) -> int:
    argv = adb.install_apk_argv(args.apk, serial=args.serial)
    if args.dry_run:
        print(" ".join(argv))
        return 0
    try:
        adb.which_or_raise("adb")
        proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            if adb.is_missing_device_error(err):
                return _print_skip(f"install skipped: {err}")
            print(f"error: install failed: {err}", file=sys.stderr)
            return proc.returncode or 1
        print(proc.stdout.strip() or "install ok")
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: adb ({exc})")


def cmd_unit_test(args: argparse.Namespace) -> int:
    code, out = gradle.unit_test(
        module=args.module,
        gradle_args=list(args.gradle_args or []),
    )
    print(out)
    return code


def cmd_instrumented_run(args: argparse.Namespace) -> int:
    component = args.class_name
    argv = adb.instrument_argv(component, serial=args.serial)
    if args.dry_run:
        print(" ".join(argv))
        return 0
    try:
        adb.which_or_raise("adb")
        proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
            if adb.is_missing_device_error(err):
                return _print_skip(f"instrument skipped: {err}")
            print(f"error: instrument failed: {err}", file=sys.stderr)
            return proc.returncode or 1
        print(proc.stdout.strip() or "instrument ok")
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: adb ({exc})")


def cmd_logcat_capture(args: argparse.Namespace) -> int:
    backend = (args.backend or "adb").lower()
    out_path = Path(args.out) if args.out else None
    if backend == "metavr":
        try:
            tid = metavr_bridge.logcat(
                serial=args.serial,
                out=args.out,
                seconds=args.seconds,
            )
            msg = (
                f"metavr bridge resolved tool id {tid}; "
                "invoke device_logcat via the MetaVR MCP host (not called from this CLI)"
            )
            if out_path:
                out_path.write_text(msg + "\n", encoding="utf-8")
            print(msg)
            return 0
        except DeviceUnavailable as exc:
            return _print_skip(str(exc))
    # adb backend
    timed = bool(args.seconds and args.seconds > 0)
    if args.dry_run:
        argv = (
            adb.logcat_stream_argv(serial=args.serial)
            if timed
            else adb.logcat_argv(serial=args.serial)
        )
        print(" ".join(argv))
        return 0
    try:
        adb.which_or_raise("adb")
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    try:
        if timed:
            # Stream for the requested window instead of `logcat -d`, which
            # dumps whatever is already buffered and exits immediately.
            text, returncode, err = adb.capture_logcat_for(args.seconds, serial=args.serial)
        else:
            proc = subprocess.run(  # noqa: S603
                adb.logcat_argv(serial=args.serial), capture_output=True, text=True
            )
            text, returncode, err = proc.stdout or "", proc.returncode, (proc.stderr or "").strip()
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))

    if returncode != 0:
        message = err or f"exit {returncode}"
        # Failure: report it and leave any existing --out file untouched,
        # instead of overwriting it with empty/partial capture output.
        if adb.is_missing_device_error(message):
            return _print_skip(f"logcat failed: {message}")
        print(f"error: logcat failed: {message}", file=sys.stderr)
        return returncode or 1

    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        print(text)
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    backend = (args.backend or "adb").lower()
    out_path = Path(args.out) if args.out else None
    if backend == "metavr":
        try:
            tid = metavr_bridge.screenshot(serial=args.serial, out=args.out)
            msg = (
                f"metavr bridge resolved tool id {tid}; "
                "invoke device_screenshot via the MetaVR MCP host (not called from this CLI)"
            )
            if out_path:
                out_path.write_text(msg + "\n", encoding="utf-8")
            print(msg)
            return 0
        except DeviceUnavailable as exc:
            return _print_skip(str(exc))
    argv = adb.screenshot_argv(serial=args.serial)
    try:
        adb.which_or_raise("adb")
        proc = subprocess.run(argv, capture_output=True)  # noqa: S603
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
            message = err or f"exit {proc.returncode}"
            if adb.is_missing_device_error(message):
                return _print_skip(f"screencap skipped: {message}")
            print(f"error: screencap failed: {message}", file=sys.stderr)
            return proc.returncode or 1
        if out_path:
            out_path.write_bytes(proc.stdout or b"")
            print(f"wrote {out_path}")
        else:
            sys.stdout.buffer.write(proc.stdout or b"")
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: adb ({exc})")


def cmd_ui_dump(args: argparse.Namespace) -> int:
    try:
        tid = metavr_bridge.ui_dump(serial=args.serial, out=args.out)
        msg = (
            f"metavr bridge resolved tool id {tid}; "
            "invoke ui_dump via the MetaVR MCP host (not called from this CLI)"
        )
        if args.out:
            Path(args.out).write_text(msg + "\n", encoding="utf-8")
        print(msg)
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))


def cmd_ui_tap(args: argparse.Namespace) -> int:
    try:
        tid = metavr_bridge.ui_tap(
            serial=args.serial,
            resource_id=args.resource_id,
            text=args.text,
        )
        print(
            f"metavr bridge resolved tool id {tid}; "
            "invoke ui_tap via the MetaVR MCP host (not called from this CLI)"
        )
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m android.tools",
        description="Local adb/gradle helpers and MetaVR tool-id bridge",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("emu_boot", help="Start an AVD emulator")
    p.add_argument("--avd", required=True)
    p.add_argument("--timeout-sec", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_emu_boot)

    p = sub.add_parser("adb_devices", help="List adb devices")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_adb_devices)

    p = sub.add_parser("install_apk", help="adb install -r an APK")
    p.add_argument("--apk", required=True)
    p.add_argument("--serial", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_install_apk)

    p = sub.add_parser("unit_test", help="Run ./gradlew test or skip")
    p.add_argument("--module", default=None)
    # REMAINDER, not nargs="*": argparse's "*" stops collecting at the first
    # token that looks like an option (anything starting with "-"), so
    # `--gradle-args --offline` rejected --offline as an unknown CLI flag
    # instead of forwarding it to Gradle. REMAINDER takes everything after
    # the flag literally, so --gradle-args must be the last option passed.
    p.add_argument("--gradle-args", nargs=argparse.REMAINDER, default=[])
    p.set_defaults(func=cmd_unit_test)

    p = sub.add_parser("instrumented_run", help="adb shell am instrument")
    p.add_argument("--serial", default=None)
    p.add_argument("--class", dest="class_name", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_instrumented_run)

    p = sub.add_parser("logcat_capture", help="Capture logcat (adb or metavr)")
    p.add_argument("--serial", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--seconds", type=int, default=0)
    p.add_argument("--backend", choices=["adb", "metavr"], default="adb")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_logcat_capture)

    p = sub.add_parser("screenshot", help="Screenshot (adb or metavr)")
    p.add_argument("--serial", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--backend", choices=["adb", "metavr"], default="adb")
    p.set_defaults(func=cmd_screenshot)

    p = sub.add_parser("ui_dump", help="MetaVR-primary ui_dump wrap")
    p.add_argument("--serial", default=None)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_ui_dump)

    p = sub.add_parser("ui_tap", help="MetaVR-primary ui_tap wrap")
    p.add_argument("--serial", default=None)
    p.add_argument("--resource-id", default=None)
    p.add_argument("--text", default=None)
    p.set_defaults(func=cmd_ui_tap)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
