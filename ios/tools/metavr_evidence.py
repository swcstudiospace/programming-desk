#!/usr/bin/env python3
"""Record remote or MetaVR device-run evidence.

This does not boot the Xcode Simulator and does not invent a MetaVR SDK.
A run is either an evidence record you already observed, or a command list
executed locally with subprocess (no shell) whose exit code is stored.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_KINDS = {"remote", "metavr"}
SIMULATOR_MARKERS = ("simulator", "xcode-simulator", "ios-simulator")


class EvidenceError(ValueError):
    pass


def _reject_simulator(kind: str) -> None:
    lowered = kind.strip().lower()
    if any(marker in lowered for marker in SIMULATOR_MARKERS):
        raise EvidenceError(
            "simulator claims are rejected; this tool does not boot the Xcode Simulator"
        )
    if lowered not in ALLOWED_KINDS:
        raise EvidenceError(f"kind must be one of {sorted(ALLOWED_KINDS)}, got {kind!r}")


def validate_record(record: dict) -> list[str]:
    problems: list[str] = []
    kind = str(record.get("kind", ""))
    try:
        _reject_simulator(kind)
    except EvidenceError as exc:
        problems.append(str(exc))
    for field in ("device_id", "host", "command", "observed_at"):
        if field not in record or record[field] in ("", None, []):
            problems.append(f"missing {field}")
    if record.get("exit_code") is not None and not isinstance(record.get("exit_code"), int):
        problems.append("exit_code must be an int when present")
    if record.get("simulator_claimed") is True:
        problems.append("simulator_claimed must not be true")
    return problems


def build_record(
    kind: str,
    device_id: str,
    host: str,
    command: list[str],
    artifact_path: str | None = None,
    exit_code: int | None = None,
    observed_at: str | None = None,
) -> dict:
    _reject_simulator(kind)
    if not device_id or not host or not command:
        raise EvidenceError("device_id, host, and command are required")
    record = {
        "kind": kind.strip().lower(),
        "device_id": device_id,
        "host": host,
        "command": list(command),
        "artifact_path": artifact_path,
        "exit_code": exit_code,
        "observed_at": observed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "simulator_claimed": False,
        "xcodebuild_invoked": False,
    }
    if exit_code is None:
        record["status"] = "unverified"
        record["reason"] = "command was not executed; no device was contacted"
    else:
        record["status"] = "recorded"
    return record


def execute(command: list[str], timeout_s: int = 120) -> int:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write remote/MetaVR evidence JSON")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--artifact", default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Execute the command list and store its exit code")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    try:
        if args.run and not command:
            raise EvidenceError("refusing to run an empty command")
        exit_code = execute(command, timeout_s=args.timeout) if args.run else None
        record = build_record(
            args.kind,
            args.device_id,
            args.host,
            command,
            artifact_path=args.artifact,
            exit_code=exit_code,
        )
    except EvidenceError as exc:
        json.dump({"status": "error", "reason": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    json.dump(record, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
