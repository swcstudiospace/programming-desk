"""Wrap MetaVR/remote tool names. Does not invent a vendor SDK.

device_screenshot, ui_dump, and ui_tap are invoked only if an executable
with that exact name is on PATH. A missing tool is a skip (exit 3), and
this module does not write a stand-in screenshot.
"""

from __future__ import annotations

import shutil
import subprocess

COMMANDS = ("device_screenshot", "ui_dump", "ui_tap")
SKIP_MISSING = 3


def wrap(command: str, serial: str, out: str, which=shutil.which, runner=subprocess.run) -> dict:
    if command not in COMMANDS:
        return {"status": "error", "reason": f"unknown MetaVR command {command}", "exit_code": 2, "invoked": False}
    if not serial or not out:
        return {"status": "error", "reason": "--serial and --out are required", "exit_code": 2, "invoked": False}
    binary = which(command)
    argv = [binary or command, "--serial", serial, "--out", out]
    if not binary:
        return {
            "status": "skipped",
            "reason": f"{command} is not on PATH; no device was contacted",
            "argv": argv,
            "exit_code": SKIP_MISSING,
            "invoked": False,
            "simulator_claimed": False,
            "artifact_written_by_wrapper": False,
        }
    proc = runner(argv, capture_output=True, text=True, check=False)
    return {
        "status": "recorded" if proc.returncode == 0 else "failed",
        "argv": argv,
        "exit_code": proc.returncode,
        "invoked": True,
        "simulator_claimed": False,
        "output_tail": ((proc.stdout or "") + (proc.stderr or ""))[-2000:],
    }
