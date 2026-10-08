"""Host acceleration probe. Never starts an emulator and never needs root."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# Read-only open of this node is the whole KVM check. Do not create a guest.
KVM_PATH = Path("/dev/kvm")

RECOMMENDATIONS = ("accelerated", "tcg-only", "no-emulator")


def kvm_status(path: Path | None = None) -> tuple[bool, bool]:
    """Return (node_exists, opened_read_only).

    A missing node is not usable. A node that refuses a read-only open is
    present and still not usable. This never retries as root and never uses
    O_RDWR.
    """
    node = KVM_PATH if path is None else path
    if not node.exists():
        return False, False
    try:
        fd = os.open(node, os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        return True, False
    else:
        os.close(fd)
        return True, True


def emulator_accel_check(emulator: str) -> tuple[str, bool]:
    """Run `emulator -accel-check` and return (output, exited_zero).

    The argv is only the binary plus `-accel-check`. No `-avd`, no guest.
    """
    argv = [emulator, "-accel-check"]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "emulator -accel-check timed out", False
    except OSError as exc:
        return f"emulator -accel-check failed: {exc}", False
    text = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if not text:
        text = f"emulator -accel-check exited {proc.returncode}"
    return text, proc.returncode == 0


def recommend(
    *,
    kvm_node: bool,
    kvm_usable: bool,
    emulator_present: bool,
    emulator_ok: bool,
) -> str:
    """accelerated, tcg-only, or no-emulator.

    No emulator binary means the host cannot run a guest at all, accelerated
    or TCG. A binary with KVM missing, unusable, or rejected by -accel-check
    can still run in software.
    """
    if not emulator_present:
        return "no-emulator"
    if kvm_node and kvm_usable and emulator_ok:
        return "accelerated"
    return "tcg-only"


def build_report() -> dict[str, object]:
    """JSON-ready probe: kvm_node, kvm_usable, emulator_accel, recommendation."""
    kvm_node, kvm_usable = kvm_status()
    emulator = shutil.which("emulator")
    emulator_accel: str | None = None
    emulator_ok = False
    if emulator:
        emulator_accel, emulator_ok = emulator_accel_check(emulator)
    recommendation = recommend(
        kvm_node=kvm_node,
        kvm_usable=kvm_usable,
        emulator_present=emulator is not None,
        emulator_ok=emulator_ok,
    )
    return {
        "kvm_node": kvm_node,
        "kvm_usable": kvm_usable,
        "emulator_accel": emulator_accel,
        "recommendation": recommendation,
    }
