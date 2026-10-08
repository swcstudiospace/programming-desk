"""Run ``xcodebuild test`` and parse the log with the existing receipt parser.

The argv carries ``-scheme``, ``-destination``, ``-resultBundlePath`` and any
``-only-testing`` selectors the caller passed. Simulator destinations also get
``CODE_SIGNING_ALLOWED=NO``. No signing identity, team, or profile is added.

The log is written only at ``--log``, which must sit inside ``--out``. On Linux,
or when ``xcodebuild`` is missing, the command skips with exit 3. ``--dry-run``
prints the argv and spawns nothing. A skip is not a pass.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from ios.tools.xcodebuild_receipt import parse_file

SKIP = 3
SIGNING_OFF = "CODE_SIGNING_ALLOWED=NO"
FORBIDDEN_SETTINGS = (
    "CODE_SIGN_IDENTITY",
    "DEVELOPMENT_TEAM",
    "PROVISIONING_PROFILE",
    "CODE_SIGN_STYLE",
    "CODE_SIGN_ENTITLEMENTS",
)


def _system(system_name: str | None) -> str:
    return system_name if system_name is not None else platform.system()


def is_simulator_destination(destination: str) -> bool:
    return "simulator" in destination.casefold()


def _contained(parent: Path, child: Path) -> bool:
    root = parent.resolve()
    target = child.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def build_argv(scheme: str, destination: str, result_bundle: Path, only_testing: list[str] | None) -> list[str]:
    argv = [
        "xcodebuild",
        "test",
        "-scheme",
        scheme,
        "-destination",
        destination,
        "-resultBundlePath",
        str(result_bundle),
    ]
    for item in only_testing or []:
        if item:
            argv.extend(["-only-testing", item])
    if is_simulator_destination(destination):
        argv.append(SIGNING_OFF)
    return argv


def xcodebuild_test(
    scheme: str,
    destination: str,
    out: Path,
    log: Path,
    only_testing: list[str] | None = None,
    dry_run: bool = False,
    system_name: str | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    if not scheme or not destination:
        return {"status": "error", "reason": "--scheme and --destination are required", "exit_code": 2, "invoked": False}
    out = Path(out)
    log = Path(log)
    if out.exists() and not out.is_dir():
        return {"status": "error", "reason": f"--out is not a directory: {out}", "exit_code": 2, "invoked": False}
    bundle = out / "TestResults.xcresult"
    if not _contained(out, log):
        return {
            "status": "error",
            "reason": "--log must be inside --out; evidence is not written outside the directory the caller passed",
            "exit_code": 2,
            "invoked": False,
        }
    if not _contained(out, bundle):
        return {"status": "error", "reason": "result bundle path escaped --out", "exit_code": 2, "invoked": False}
    argv = build_argv(scheme, destination, bundle, only_testing)
    for token in argv:
        if any(token.startswith(prefix + "=") or token == prefix for prefix in FORBIDDEN_SETTINGS):
            return {
                "status": "error",
                "reason": f"refusing signing setting {token}",
                "exit_code": 2,
                "invoked": False,
            }
    if dry_run:
        return {
            "status": "dry-run",
            "argv": argv,
            "exit_code": 0,
            "invoked": False,
            "xcodebuild_invoked": False,
            "result_bundle": str(bundle),
            "log": str(log),
        }
    if _system(system_name) != "Darwin":
        return {
            "status": "skipped",
            "reason": "skipped: not on macOS",
            "argv": argv,
            "exit_code": SKIP,
            "invoked": False,
            "xcodebuild_invoked": False,
        }
    binary = which("xcodebuild")
    if not binary:
        return {
            "status": "skipped",
            "reason": "skipped: xcodebuild is not on PATH",
            "argv": argv,
            "exit_code": SKIP,
            "invoked": False,
            "xcodebuild_invoked": False,
        }
    resolved = [binary, *argv[1:]]
    out.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if is_simulator_destination(destination):
        env["CODE_SIGNING_ALLOWED"] = "NO"
    proc = runner(resolved, capture_output=True, text=True, check=False, env=env)
    log.write_text(_tail_full(proc), encoding="utf-8")
    parsed = parse_file(log)
    return {
        "status": parsed.get("status"),
        "exit_code": parsed.get("exit_code", 1),
        "argv": resolved,
        "log": str(log),
        "result_bundle": str(bundle),
        "invoked": True,
        "xcodebuild_invoked": True,
        "tool_exit_code": proc.returncode,
        "receipt": parsed,
    }


def _tail_full(proc) -> str:
    stdout = getattr(proc, "stdout", None) or ""
    stderr = getattr(proc, "stderr", None) or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    return stdout + stderr
