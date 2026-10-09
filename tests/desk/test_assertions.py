"""Tests for MilestoneVerifier and VerificationReport."""

from pathlib import Path
import tempfile

from src.desk.assertions import MilestonePhase, MilestoneVerifier
from src.desk.supervision.process_supervisor import ProcessSupervisor


SAMPLE_ROADMAP = """# Roadmap: Milestone v8.0 — Enterprise Workbench Runtime

## Phase 1: Security & Sandboxing
- [x] Implement PolicySandbox and secret sanitization
- [x] Implement path traversal confinement
- [x] Unit test suite for security boundaries

## Phase 2: Process Supervision
- [x] Safe array spawning
- [ ] Implement timeout escalation
"""


def test_parse_roadmap() -> None:
    verifier = MilestoneVerifier()
    title, phases = verifier.parse_roadmap(SAMPLE_ROADMAP)

    assert "Milestone v8.0" in title
    assert len(phases) == 2

    p1 = phases[0]
    assert p1.phase_name == "Phase 1: Security & Sandboxing"
    assert p1.total_tasks == 3
    assert p1.completed_tasks == 3
    assert p1.pending_tasks == 0
    assert p1.is_complete is True
    assert p1.completion_pct == 100.0

    p2 = phases[1]
    assert p2.phase_name == "Phase 2: Process Supervision"
    assert p2.total_tasks == 2
    assert p2.completed_tasks == 1
    assert p2.pending_tasks == 1
    assert p2.is_complete is False
    assert p2.completion_pct == 50.0


def test_verify_milestone_incomplete() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        roadmap_file = Path(tmp_dir) / "ROADMAP.md"
        roadmap_file.write_text(SAMPLE_ROADMAP, encoding="utf-8")

        verifier = MilestoneVerifier(roadmap_path=roadmap_file)
        report = verifier.verify_milestone()

        assert report.total_tasks == 5
        assert report.completed_tasks == 4
        assert report.completion_pct == 80.0
        assert report.all_phases_complete is False

        summary = verifier.format_summary(report)
        assert "INCOMPLETE" in summary


def test_verify_milestone_all_complete() -> None:
    roadmap_done = """# Roadmap: Milestone v8.0
## Phase 1: All Good
- [x] Task 1
- [x] Task 2
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        roadmap_file = Path(tmp_dir) / "ROADMAP.md"
        roadmap_file.write_text(roadmap_done, encoding="utf-8")

        verifier = MilestoneVerifier(roadmap_path=roadmap_file)
        report = verifier.verify_milestone()

        assert report.all_phases_complete is True
        assert report.completion_pct == 100.0
        summary = verifier.format_summary(report)
        assert "PASSED" in summary


def test_check_layout_and_gaps_block_completion() -> None:
    roadmap_done = """# Roadmap: Milestone v8.0
## Phase 1: All Good
- [x] Task 1
- [x] Task 2
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        empty = Path(tmp_dir)
        probe = MilestoneVerifier()
        assert probe.check_layout(empty) == list(MilestoneVerifier.REQUIRED_FILES)

        roadmap_file = empty / "ROADMAP.md"
        roadmap_file.write_text(roadmap_done, encoding="utf-8")

        supervised = MilestoneVerifier(
            roadmap_path=roadmap_file,
            supervisor=ProcessSupervisor(),
        )
        counted = supervised.verify_milestone()
        assert counted.total_tasks == 2
        assert counted.completed_tasks == 2
        assert counted.completion_pct == 100.0
        assert counted.phases[0].total_tasks == 2
        assert counted.phases[0].completed_tasks == 2
        assert counted.phases[0].pending_tasks == 0

        gapped = MilestoneVerifier(roadmap_path=roadmap_file)
        report = gapped.verify_milestone(layout_root=empty)
        assert report.layout_gaps
        assert report.total_tasks == counted.total_tasks
        assert report.completed_tasks == counted.completed_tasks
        assert report.all_phases_complete is False
        assert "Layout gaps" in gapped.format_summary(report)
