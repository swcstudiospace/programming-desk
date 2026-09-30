"""Run swift test when a toolchain exists. Otherwise skip with exit 3.

Never invokes xcodebuild and never treats a missing toolchain as a pass.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SKIP_NO_TOOLCHAIN = 3


def spm_test(package: Path, dry_run: bool = False, swift_bin: str | None = None, runner=subprocess.run) -> dict:
    package = package.resolve()
    manifest = package / "Package.swift"
    if not manifest.is_file():
        return {"status": "error", "reason": f"Package.swift not found under {package}", "tests_ran": False, "exit_code": 2}

    swift = swift_bin if swift_bin is not None else shutil.which("swift")
    planned = [swift or "swift", "test", "--package-path", str(package)]
    toolchain = bool(swift and Path(swift).exists())

    if dry_run:
        return {
            "status": "dry-run",
            "argv": planned,
            "toolchain_present": toolchain,
            "tests_ran": False,
            "simulator_claimed": False,
            "xcodebuild_invoked": False,
            "exit_code": 0,
        }

    if not toolchain:
        return {
            "status": "skipped",
            "reason": "swift toolchain not on PATH; SPM tests were not executed",
            "package": str(manifest),
            "tests_ran": False,
            "simulator_claimed": False,
            "xcodebuild_invoked": False,
            "exit_code": SKIP_NO_TOOLCHAIN,
        }

    proc = runner(planned, capture_output=True, text=True, check=False)
    return {
        "status": "passed" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "package": str(manifest),
        "swift": swift,
        "tests_ran": True,
        "simulator_claimed": False,
        "xcodebuild_invoked": False,
        "output_tail": ((proc.stdout or "") + (proc.stderr or ""))[-2000:],
    }
