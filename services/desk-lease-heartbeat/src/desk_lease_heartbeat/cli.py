"""CLI for the systemd oneshot. ``renew`` is what the unit execs."""

from __future__ import annotations

import argparse
from pathlib import Path

from desk_lease_heartbeat.renew import run_renew


def console() -> int:
    """Entry point. The installed script exits with this status."""
    return main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="desk-lease-heartbeat",
        description=(
            "Renew graph-node leases this desk already holds, then exit. "
            "The systemd timer owns the 60s cadence. See INTERFACE.md for the env contract and exit codes."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    renew = sub.add_parser("renew", help="renew every lease in the held file, once")
    renew.add_argument(
        "--env-file",
        type=Path,
        help="systemd EnvironmentFile to load. Assignments are literal; $ is not expanded. File values win over the process environment.",
    )
    args = parser.parse_args(argv)
    if args.command == "renew":
        return run_renew(env_file=args.env_file)
    return 2
