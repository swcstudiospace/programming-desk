"""Wrap MetaVR/remote tool names. Does not invent a vendor SDK.

device_screenshot, ui_dump, and ui_tap are invoked only if an executable
with that exact name is on PATH. A missing tool is a skip (exit 3), and
this module does not write a stand-in screenshot.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

COMMANDS = ("device_screenshot", "ui_dump", "ui_tap")
SKIP_MISSING = 3


def wrap(
    command: str,
    serial: str,
    out: str,
    which=shutil.which,
    runner=subprocess.run,
    *,
    x: float | None = None,
    y: float | None = None,
    selector: str | None = None,
) -> dict:
    if command not in COMMANDS:
        return {"status": "error", "reason": f"unknown MetaVR command {command}", "exit_code": 2, "invoked": False}
    if not serial or not out:
        return {"status": "error", "reason": "--serial and --out are required", "exit_code": 2, "invoked": False}
    if command == "ui_tap" and not selector and (x is None or y is None):
        return {
            "status": "error",
            "reason": "ui_tap requires --selector or both --x and --y",
            "exit_code": 2,
            "invoked": False,
        }
    binary = which(command)
    argv = [binary or command, "--serial", serial, "--out", out]
    if command == "ui_tap":
        argv += ["--selector", selector] if selector else ["--x", str(x), "--y", str(y)]
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
    output_written = Path(out).is_file()
    status = "recorded" if proc.returncode == 0 and output_written else "failed"
    result = {
        "status": status,
        "argv": argv,
        "exit_code": proc.returncode if proc.returncode != 0 else (0 if output_written else 1),
        "invoked": True,
        "simulator_claimed": False,
        "output_written": output_written,
        "output_tail": ((proc.stdout or "") + (proc.stderr or ""))[-2000:],
    }
    if proc.returncode == 0 and not output_written:
        result["reason"] = f"{command} exited 0 but did not write --out {out}"
    return result
