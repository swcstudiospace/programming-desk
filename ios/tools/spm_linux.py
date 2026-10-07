#!/usr/bin/env python3
"""Linux-safe Swift Package Manager check.

Runs `swift test` only when a Package.swift is present and a swift binary is on PATH.
A missing toolchain is unverified, not a pass. This tool never invokes xcodebuild and
never claims an iOS Simulator run.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def check_package(package_root: Path, swift_bin: str | None = None, timeout_s: int = 600) -> dict:
    package_root = package_root.resolve()
    manifest = package_root / "Package.swift"
    if not manifest.is_file():
        return {
            "status": "error",
            "reason": f"Package.swift not found under {package_root}",
            "tests_ran": False,
            "simulator_claimed": False,
            "xcodebuild_invoked": False,
        }

    swift = swift_bin if swift_bin is not None else shutil.which("swift")
    if not swift or not Path(swift).exists():
        return {
            "status": "unverified",
            "reason": "swift toolchain not available; SPM tests were not executed",
            "package": str(manifest),
            "tests_ran": False,
            "simulator_claimed": False,
            "xcodebuild_invoked": False,
        }

    proc = subprocess.run(
        [swift, "test", "--package-path", str(package_root)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    tail = (proc.stdout + proc.stderr)[-2000:]
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "package": str(manifest),
        "swift": swift,
        "tests_ran": True,
        "simulator_claimed": False,
        "xcodebuild_invoked": False,
        "output_tail": tail,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run swift test when a Linux toolchain exists")
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--swift", dest="swift_bin", default=None, help="Explicit swift binary")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)
    result = check_package(args.package_root, swift_bin=args.swift_bin, timeout_s=args.timeout)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if result["status"] == "error":
        return 2
    if result["status"] == "failed":
        return int(result.get("exit_code") or 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
