"""CLI for python -m ios.tools."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ios.tools.entitlements import diff as entitlements_diff
from ios.tools.entitlements import scan as entitlements_scan
from ios.tools.metavr_bridge import wrap as metavr_wrap
from ios.tools.plist_lint import lint_path
from ios.tools.snapshot_diff import write_diff
from ios.tools.spm_linux import spm_test
from ios.tools.xcodebuild_receipt import parse_file


def _emit(payload: dict, as_json: bool) -> None:
    if as_json or True:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")


def _add_metavr(sub, name: str) -> None:
    parser = sub.add_parser(name)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--out", required=True)
    parser.set_defaults(func=lambda args, cmd=name: metavr_wrap(cmd, args.serial, args.out))


def _add_ui_tap(sub) -> None:
    parser = sub.add_parser("ui_tap")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--x", type=float)
    parser.add_argument("--y", type=float)
    parser.add_argument("--selector")
    parser.set_defaults(
        func=lambda args: metavr_wrap(
            "ui_tap", args.serial, args.out, x=args.x, y=args.y, selector=args.selector
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ios.tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plist = sub.add_parser("plist_lint")
    plist.add_argument("--path", type=Path, required=True)
    plist.add_argument("--json", action="store_true")
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

    for name in ("device_screenshot", "ui_dump"):
        _add_metavr(sub, name)
    _add_ui_tap(sub)
    return parser


def _entitlements(args) -> dict:
    if args.diff:
        return entitlements_diff(args.diff[0], args.diff[1])
    if args.path:
        return entitlements_scan(args.path)
    return {"status": "error", "reason": "pass --path or --diff BASE HEAD"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = args.func(args)
    _emit(payload, getattr(args, "json", False))
    code = payload.get("exit_code")
    if isinstance(code, int):
        return code
    if payload.get("status") in {"error"}:
        return 2
    if payload.get("status") in {"failed", "unverified"}:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
