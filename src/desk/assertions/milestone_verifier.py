"""Automated Verification & Milestone Assertion Pipeline for Programming Desk."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from ..supervision.process_supervisor import ProcessSupervisor, SupervisedProcessResult


@dataclass
class MilestonePhase:
    """Represents a phase and its checklist state from a roadmap."""

    phase_name: str
    total_tasks: int = 0
    completed_tasks: int = 0
    pending_tasks: int = 0
    task_items: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.total_tasks > 0 and self.completed_tasks == self.total_tasks

    @property
    def completion_pct(self) -> float:
        if self.total_tasks == 0:
            return 100.0
        return (self.completed_tasks / self.total_tasks) * 100.0


@dataclass
class VerificationReport:
    """Consolidated milestone verification outcome."""

    milestone_name: str
    phases: list[MilestonePhase]
    total_tasks: int
    completed_tasks: int
    completion_pct: float
    all_phases_complete: bool
    test_result: SupervisedProcessResult | None = None
    layout_gaps: list[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.test_result:
            data["test_result"] = {
                "exit_code": self.test_result.exit_code,
                "succeeded": self.test_result.succeeded,
                "duration_ms": self.test_result.duration_ms,
                "timed_out": self.test_result.timed_out,
            }
        return data


class MilestoneVerifier:
    """Cross-validates .planning/ROADMAP.md checklist items and runs automated verification harnesses."""

    REQUIRED_FILES: tuple[str, ...] = (
        "src/desk/security/policy_sandbox.py",
        "src/desk/telemetry/audit_tracer.py",
        "src/desk/supervision/process_supervisor.py",
        "src/desk/session/session_store.py",
        "src/desk/recovery/recovery_manager.py",
        "src/desk/diagnostics/doctor_engine.py",
        "src/desk/assertions/milestone_verifier.py",
        "src/desk/cli.py",
    )

    def __init__(
        self,
        roadmap_path: str | Path = ".planning/ROADMAP.md",
        supervisor: ProcessSupervisor | None = None,
    ) -> None:
        self.roadmap_path = Path(roadmap_path).resolve()
        self.supervisor = supervisor or ProcessSupervisor()

    def parse_roadmap(self, text: str | None = None) -> tuple[str, list[MilestonePhase]]:
        """Parse roadmap markdown text into milestone name and list of MilestonePhase objects."""
        if text is None:
            if not self.roadmap_path.exists():
                return "Unknown Milestone", []
            text = self.roadmap_path.read_text(encoding="utf-8")

        milestone_name = "Milestone"
        phases: list[MilestonePhase] = []
        current_phase: MilestonePhase | None = None

        # Check if the roadmap uses ### Phase ... headings under a container like ## Phase Details
        has_subphase_headings = any(
            re.match(r"^###\s+Phase\s+\d+", line.strip(), re.IGNORECASE)
            for line in text.splitlines()
        )

        for line in text.splitlines():
            line_str = line.strip()

            # Heading 1 indicates milestone title
            if line_str.startswith("# "):
                milestone_name = line_str[2:].strip()
                continue

            if has_subphase_headings:
                if line_str.startswith("### "):
                    phase_title = line_str[4:].strip()
                    current_phase = MilestonePhase(phase_name=phase_title)
                    phases.append(current_phase)
                    continue
                elif line_str.startswith("## "):
                    # Overview sections like ## Phases or ## Phase Details should not collect tasks
                    current_phase = None
                    continue
            else:
                if line_str.startswith("## "):
                    phase_title = line_str[3:].strip()
                    if phase_title.lower() in ("phases", "phase details", "overview", "progress"):
                        current_phase = None
                        continue
                    current_phase = MilestonePhase(phase_name=phase_title)
                    phases.append(current_phase)
                    continue

            # Checkbox item
            if current_phase is not None:
                if re.match(r"^-\s*\[x\]", line_str, re.IGNORECASE):
                    current_phase.total_tasks += 1
                    current_phase.completed_tasks += 1
                    current_phase.task_items.append(line_str)
                elif re.match(r"^-\s*\[\s*\]", line_str):
                    current_phase.total_tasks += 1
                    current_phase.pending_tasks += 1
                    current_phase.task_items.append(line_str)

        return milestone_name, phases

    def check_layout(self, root: Path | None = None) -> list[str]:
        """Return required repo-relative paths that are missing under root."""
        base = Path.cwd() if root is None else Path(root)
        return [rel for rel in self.REQUIRED_FILES if not (base / rel).is_file()]

    def verify_milestone(
        self,
        test_command: list[str] | None = None,
        timeout: float = 60.0,
        layout_root: Path | None = None,
    ) -> VerificationReport:
        """Evaluate roadmap task completion, required file layout, and optional tests."""
        milestone_name, phases = self.parse_roadmap()

        total_tasks = sum(p.total_tasks for p in phases)
        completed_tasks = sum(p.completed_tasks for p in phases)
        completion_pct = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 100.0
        phases_complete = len(phases) > 0 and all(p.is_complete for p in phases)
        layout_gaps = self.check_layout(layout_root)

        test_res: SupervisedProcessResult | None = None
        if test_command:
            test_res = self.supervisor.run(test_command, timeout=timeout)

        tests_ok = test_res is None or test_res.succeeded
        all_ok = phases_complete and not layout_gaps and tests_ok

        return VerificationReport(
            milestone_name=milestone_name,
            phases=phases,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            completion_pct=completion_pct,
            all_phases_complete=all_ok,
            test_result=test_res,
            layout_gaps=layout_gaps,
        )

    def format_summary(self, report: VerificationReport) -> str:
        """Format human-readable CLI verification summary."""
        lines = [
            f"=== Milestone Assertion: {report.milestone_name} ===",
            f"Timestamp: {report.timestamp}",
            f"Overall Status: {'PASSED' if report.all_phases_complete else 'INCOMPLETE'}",
            f"Tasks Completed: {report.completed_tasks}/{report.total_tasks} ({report.completion_pct:.1f}%)",
            "",
            "Phase Breakdown:",
        ]

        for p in report.phases:
            mark = "[✓]" if p.is_complete else "[ ]"
            pct = f"{p.completion_pct:.0f}%"
            lines.append(f"  {mark} {p.phase_name}: {p.completed_tasks}/{p.total_tasks} ({pct})")

        if report.layout_gaps:
            lines.append("")
            lines.append("Layout gaps:")
            for gap in report.layout_gaps:
                lines.append(f"  MISSING {gap}")

        if report.test_result:
            lines.append("")
            t_status = "PASSED" if report.test_result.succeeded else "FAILED"
            lines.append(
                f"Automated Test Run: {t_status} (exit code {report.test_result.exit_code}, {report.test_result.duration_ms:.0f}ms)"
            )

        return "\n".join(lines)
