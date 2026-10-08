"""CLI for python -m ios.tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ios.tools.entitlements import diff as entitlements_diff
from ios.tools.entitlements import scan as entitlements_scan
from ios.tools.maestro_flow import maestro_flow
from ios.tools.metavr_bridge import wrap as metavr_wrap
from ios.tools.plist_lint import lint_path
from ios.tools.sim_drive import boot as sim_boot
from ios.tools.sim_drive import install as sim_install
from ios.tools.sim_drive import launch as sim_launch
from ios.tools.sim_drive import record as sim_record
from ios.tools.sim_drive import screenshot as sim_screenshot
from ios.tools.sim_drive import shutdown as sim_shutdown
from ios.tools.snapshot_diff import write_diff
from ios.tools.spm_linux import spm_test
from ios.tools.xcodebuild_receipt import parse_file
from ios.tools.xcodebuild_test import xcodebuild_test


def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _add_json_dry(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="print the argv as JSON and spawn nothing")
    parser.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")


def _add_sim(sub) -> None:
    sim = sub.add_parser("sim_drive")
    sim_sub = sim.add_subparsers(dest="sim_cmd", required=True)

    boot = sim_sub.add_parser("boot")
    boot.add_argument("--device-type", required=True)
    boot.add_argument("--runtime", required=True)
    boot.add_argument("--name", default=None)
    boot.add_argument("--out", type=Path)
    _add_json_dry(boot)
    boot.set_defaults(
        func=lambda args: sim_boot(
            args.device_type, args.runtime, out=args.out, name=args.name, dry_run=args.dry_run
        )
    )

    install = sim_sub.add_parser("install")
    install.add_argument("--udid", required=True)
    install.add_argument("--app", required=True)
    _add_json_dry(install)
    install.set_defaults(func=lambda args: sim_install(args.udid, args.app, dry_run=args.dry_run))

    launch = sim_sub.add_parser("launch")
    launch.add_argument("--udid", required=True)
    launch.add_argument("--bundle-id", required=True)
    _add_json_dry(launch)
    launch.set_defaults(func=lambda args: sim_launch(args.udid, args.bundle_id, dry_run=args.dry_run))

    shot = sim_sub.add_parser("screenshot")
    shot.add_argument("--udid", required=True)
    shot.add_argument("--out", type=Path, required=True)
    _add_json_dry(shot)
    shot.set_defaults(func=lambda args: sim_screenshot(args.udid, args.out, dry_run=args.dry_run))

    rec = sim_sub.add_parser("record")
    rec.add_argument("--udid", required=True)
    rec.add_argument("--out", type=Path, required=True)
    rec.add_argument("--seconds", type=int, required=True)
    _add_json_dry(rec)
    rec.set_defaults(func=lambda args: sim_record(args.udid, args.out, args.seconds, dry_run=args.dry_run))

    stop = sim_sub.add_parser("shutdown")
    stop.add_argument("--udid", required=True)
    stop.add_argument("--created-udid", required=True)
    stop.add_argument("--out", type=Path, required=True)
    stop.add_argument("--erase", action="store_true")
    _add_json_dry(stop)
    stop.set_defaults(
        func=lambda args: sim_shutdown(
            args.udid, args.created_udid, args.out, erase=args.erase, dry_run=args.dry_run
        )
    )


def _add_metavr(sub, name: str) -> None:
    parser = sub.add_parser(name)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--out", required=True)
    if name == "ui_tap":
        parser.add_argument("--target", required=True)
        parser.set_defaults(func=lambda args, cmd=name: metavr_wrap(cmd, args.serial, args.out, target=args.target))
    else:
        parser.set_defaults(func=lambda args, cmd=name: metavr_wrap(cmd, args.serial, args.out))


def _entitlements(args) -> dict:
    if args.diff:
        return entitlements_diff(args.diff[0], args.diff[1])
    if args.path:
        return entitlements_scan(args.path)
    return {"status": "error", "reason": "pass --path or --diff BASE HEAD"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ios.tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plist = sub.add_parser("plist_lint")
    plist.add_argument("--path", type=Path, required=True)
    plist.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")
    plist.set_defaults(func=lambda args: lint_path(args.path))

    ents = sub.add_parser("entitlements_scan")
    ents.add_argument("--path", type=Path)
    ents.add_argument("--diff", nargs=2, type=Path, metavar=("BASE", "HEAD"))
    ents.set_defaults(func=_entitlements)

    spm = sub.add_parser("spm_test_linux")
    spm.add_argument("--package", type=Path, required=True)
    spm.add_argument("--dry-run", action="store_true")
    spm.set_defaults(func=lambda args: spm_test(args.package, dry_run=args.dry_run))

    snap = sub.add_parser("snapshot_diff")
    snap.add_argument("--before", type=Path, required=True)
    snap.add_argument("--after", type=Path, required=True)
    snap.add_argument("--out", type=Path, required=True)
    snap.set_defaults(func=lambda args: write_diff(args.before, args.after, args.out))

    log = sub.add_parser("xcodebuild_receipt")
    log.add_argument("--log", type=Path, required=True)
    log.set_defaults(func=lambda args: parse_file(args.log))

    for name in ("device_screenshot", "ui_dump", "ui_tap"):
        _add_metavr(sub, name)

    _add_sim(sub)

    xb = sub.add_parser("xcodebuild_test")
    xb.add_argument("--scheme", required=True)
    xb.add_argument("--destination", required=True)
    xb.add_argument("--out", type=Path, required=True)
    xb.add_argument("--log", type=Path, required=True)
    xb.add_argument("--only-testing", action="append", default=None)
    _add_json_dry(xb)
    xb.set_defaults(
        func=lambda args: xcodebuild_test(
            args.scheme,
            args.destination,
            args.out,
            args.log,
            only_testing=args.only_testing,
            dry_run=args.dry_run,
        )
    )

    flow = sub.add_parser("maestro_flow")
    flow.add_argument("--flow", type=Path, required=True)
    flow.add_argument("--out", type=Path, required=True)
    _add_json_dry(flow)
    flow.set_defaults(func=lambda args: maestro_flow(args.flow, args.out, dry_run=args.dry_run))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = args.func(args)
    _emit(payload)
    code = payload.get("exit_code")
    if isinstance(code, int):
        return code
    if payload.get("status") == "error":
        return 2
    if payload.get("status") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
