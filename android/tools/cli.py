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


def _print_fail(reason: str, code: int = 1) -> int:
    """A binary actually ran and failed — never report this as skip/exit 0."""
    print(f"error: {reason}", file=sys.stderr)
    return code if code else 1


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
        proc = subprocess.Popen(argv)  # noqa: S603 — argv list, no shell
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: emulator ({exc})")
    except OSError as exc:
        return _print_skip(f"emulator spawn failed: {exc}")

    # Poll the spawned process so an immediate crash (bad AVD, missing SDK
    # image) isn't reported as success; bounded so this never hangs the CLI.
    check_window = min(args.timeout_sec, 5) if args.timeout_sec and args.timeout_sec > 0 else 1.0
    poll_interval = 0.1
    waited = 0.0
    while waited < check_window:
        time.sleep(poll_interval)
        waited += poll_interval
        if proc.poll() is not None:
            return _print_fail(
                f"emulator exited early (code {proc.returncode}) for avd={args.avd}",
                code=proc.returncode or 1,
            )
    print(f"emulator started for avd={args.avd}, pid={proc.pid} (alive after {check_window:g}s)")
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
            return _print_fail(f"install failed: {err}", code=proc.returncode)
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
            return _print_fail(f"instrument failed: {err}", code=proc.returncode)
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
    seconds = int(args.seconds) if args.seconds else 0
    try:
        adb.which_or_raise("adb")
        if seconds > 0:
            # Live capture window: stream `adb logcat` for `seconds`, then
            # stop and collect whatever was captured in that window.
            argv = adb.logcat_argv(serial=args.serial, dump=False)
            proc = subprocess.Popen(  # noqa: S603
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            try:
                text, err_text = proc.communicate(timeout=seconds)
                returncode = proc.returncode
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    text, err_text = proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    text, err_text = proc.communicate()
                returncode = 0  # capture window elapsed as requested, not a failure
        else:
            # One-shot dump: `adb logcat -d` (dump current buffer and exit).
            argv = adb.logcat_argv(serial=args.serial, dump=True)
            proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603
            text, err_text, returncode = proc.stdout or "", proc.stderr or "", proc.returncode
        if returncode != 0:
            err = (err_text or "").strip() or f"exit {returncode}"
            return _print_fail(f"logcat failed: {err}", code=returncode)
        # Only write --out once we know the capture actually succeeded, so a
        # failed capture never clobbers a previously written good log.
        if out_path:
            out_path.write_text(text or "", encoding="utf-8")
            print(f"wrote {out_path}")
        else:
            print(text or "")
        return 0
    except DeviceUnavailable as exc:
        return _print_skip(str(exc))
    except FileNotFoundError as exc:
        return _print_skip(f"missing binary: adb ({exc})")


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
            return _print_fail(f"screencap failed: {err or proc.returncode}", code=proc.returncode)
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
    # REMAINDER (not "*"): with nargs="*", argparse treats a flag-looking
    # token like "--offline" as a new option and errors out instead of
    # collecting it. REMAINDER grabs everything after --gradle-args
    # verbatim, so it must be the last flag on the command line.
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
