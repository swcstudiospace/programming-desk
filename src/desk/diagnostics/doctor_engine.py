"""Zero-dependency Doctor Diagnostics Engine for Programming Desk."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class DiagnosticCheckResult:
    """Outcome of an individual diagnostic check."""

    name: str
    status: CheckStatus
    message: str
    fix_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


DiagnosticProbe = Callable[[Path], DiagnosticCheckResult]


def check_python_version(root: Path) -> DiagnosticCheckResult:
    """Verify python runtime is >= 3.10."""
    major, minor, micro = sys.version_info[:3]
    version_str = f"{major}.{minor}.{micro}"
    if major > 3 or (major == 3 and minor >= 10):
        return DiagnosticCheckResult(
            name="python_version",
            status=CheckStatus.PASS,
            message=f"Python version {version_str} meets requirements (>= 3.10)",
            details={"version": version_str},
        )
    return DiagnosticCheckResult(
        name="python_version",
        status=CheckStatus.FAIL,
        message=f"Python version {version_str} is below required minimum 3.10",
        fix_hint="Upgrade system Python to 3.10 or higher",
        details={"version": version_str},
    )


def check_git_installed(root: Path) -> DiagnosticCheckResult:
    """Verify git executable is available and current directory is in a git worktree."""
    git_path = shutil.which("git")
    if not git_path:
        return DiagnosticCheckResult(
            name="git_toolchain",
            status=CheckStatus.FAIL,
            message="Git executable was not found on PATH",
            fix_hint="Install git package via system package manager",
        )

    try:
        res = subprocess.run(
            [git_path, "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip() == "true":
            return DiagnosticCheckResult(
                name="git_toolchain",
                status=CheckStatus.PASS,
                message="Git is installed and repository root is a valid worktree",
                details={"git_binary": git_path},
            )
        return DiagnosticCheckResult(
            name="git_toolchain",
            status=CheckStatus.WARN,
            message="Git is installed, but root does not appear to be inside a git worktree",
            fix_hint="Run 'git init' or execute within a git repository clone",
            details={"git_binary": git_path, "stderr": res.stderr.strip()},
        )
    except Exception as exc:
        return DiagnosticCheckResult(
            name="git_toolchain",
            status=CheckStatus.WARN,
            message=f"Failed to query git worktree: {exc}",
            fix_hint="Ensure git has sufficient filesystem execution permissions",
        )


def check_ownership_manifest(root: Path) -> DiagnosticCheckResult:
    """Verify ownership.yaml manifest exists and is non-empty."""
    manifest_path = root / "ownership.yaml"
    if not manifest_path.exists():
        return DiagnosticCheckResult(
            name="ownership_manifest",
            status=CheckStatus.WARN,
            message="No ownership.yaml found at workspace root",
            fix_hint="Create ownership.yaml to enforce bot-scoped path governance",
        )

    size = manifest_path.stat().st_size
    if size == 0:
        return DiagnosticCheckResult(
            name="ownership_manifest",
            status=CheckStatus.FAIL,
            message="ownership.yaml exists but is empty",
            fix_hint="Populate ownership.yaml with valid bot definitions and rules",
        )

    return DiagnosticCheckResult(
        name="ownership_manifest",
        status=CheckStatus.PASS,
        message=f"ownership.yaml exists and is accessible ({size} bytes)",
        details={"size_bytes": size},
    )


def check_planning_directory(root: Path) -> DiagnosticCheckResult:
    """Verify .planning directory exists and is writable."""
    planning_dir = root / ".planning"
    if not planning_dir.exists():
        return DiagnosticCheckResult(
            name="planning_directory",
            status=CheckStatus.WARN,
            message=".planning/ directory does not exist",
            fix_hint="Initialize .planning/ with ROADMAP.md and STATE.md",
        )

    if not os.access(str(planning_dir), os.W_OK):
        return DiagnosticCheckResult(
            name="planning_directory",
            status=CheckStatus.FAIL,
            message=".planning/ directory exists but is not writable",
            fix_hint="Check file system permissions on .planning/ directory",
        )

    return DiagnosticCheckResult(
        name="planning_directory",
        status=CheckStatus.PASS,
        message=".planning/ directory exists and is writable",
        details={"path": str(planning_dir)},
    )


def check_workspace_permissions(root: Path) -> DiagnosticCheckResult:
    """Verify that temporary files and locks can be created in workspace."""
    test_file = root / f".desk_doctor_probe_{os.getpid()}.tmp"
    try:
        test_file.write_text("probe", encoding="utf-8")
        test_file.unlink()
        return DiagnosticCheckResult(
            name="workspace_permissions",
            status=CheckStatus.PASS,
            message="Workspace root permits file creation and deletion",
        )
    except Exception as exc:
        return DiagnosticCheckResult(
            name="workspace_permissions",
            status=CheckStatus.FAIL,
            message=f"Workspace root write test failed: {exc}",
            fix_hint="Grant write permissions to workspace directory",
        )


class DoctorEngine:
    """Extensible workspace diagnostic supervisor."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.probes: list[DiagnosticProbe] = [
            check_python_version,
            check_git_installed,
            check_ownership_manifest,
            check_planning_directory,
            check_workspace_permissions,
        ]

    def register_probe(self, probe: DiagnosticProbe) -> None:
        """Register an additional diagnostic probe."""
        self.probes.append(probe)

    def run_checks(self) -> list[DiagnosticCheckResult]:
        """Execute all registered diagnostic probes against the workspace root."""
        results: list[DiagnosticCheckResult] = []
        for probe in self.probes:
            try:
                res = probe(self.workspace_root)
            except Exception as exc:
                res = DiagnosticCheckResult(
                    name=getattr(probe, "__name__", "custom_probe"),
                    status=CheckStatus.FAIL,
                    message=f"Unhandled exception during check: {exc}",
                    fix_hint="Review probe implementation and workspace access",
                )
            results.append(res)
        return results

    def overall_status(self, results: list[DiagnosticCheckResult]) -> CheckStatus:
        """Calculate overall health status across all results."""
        if any(r.status == CheckStatus.FAIL for r in results):
            return CheckStatus.FAIL
        if any(r.status == CheckStatus.WARN for r in results):
            return CheckStatus.WARN
        return CheckStatus.PASS

    def exit_code(self, results: list[DiagnosticCheckResult]) -> int:
        """Return typed exit code: 0 for PASS/WARN, 1 for FAIL."""
        return 1 if self.overall_status(results) == CheckStatus.FAIL else 0

    def format_report(self, results: list[DiagnosticCheckResult], verbose: bool = False) -> str:
        """Format human-readable CLI report."""
        status = self.overall_status(results)
        lines = [
            f"=== Programming Desk Health Inspection ({status.value}) ===",
            f"Workspace: {self.workspace_root}",
            "",
        ]

        for r in results:
            tag = f"[{r.status.value}]"
            lines.append(f"{tag:<8} {r.name}: {r.message}")
            if r.fix_hint and r.status != CheckStatus.PASS:
                lines.append(f"         Hint: {r.fix_hint}")
            if verbose and r.details:
                for k, v in r.details.items():
                    lines.append(f"         - {k}: {v}")

        lines.append("")
        passed_count = sum(1 for r in results if r.status == CheckStatus.PASS)
        warn_count = sum(1 for r in results if r.status == CheckStatus.WARN)
        fail_count = sum(1 for r in results if r.status == CheckStatus.FAIL)
        lines.append(f"Summary: {passed_count} passed, {warn_count} warnings, {fail_count} failures")
        return "\n".join(lines)
