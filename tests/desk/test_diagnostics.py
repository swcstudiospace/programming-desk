"""Tests for DoctorEngine and diagnostic checks."""

from pathlib import Path
import tempfile

from src.desk.diagnostics import (
    CheckStatus,
    DiagnosticCheckResult,
    DoctorEngine,
    check_git_installed,
    check_ownership_manifest,
    check_planning_directory,
    check_python_version,
    check_workspace_permissions,
)


def test_python_version_check() -> None:
    res = check_python_version(Path.cwd())
    assert res.name == "python_version"
    assert res.status == CheckStatus.PASS
    assert "version" in res.details


def test_ownership_manifest_check() -> None:
    # Existing repo root has ownership.yaml
    res = check_ownership_manifest(Path.cwd())
    assert res.status == CheckStatus.PASS

    # Isolated directory without ownership.yaml
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_tmp = check_ownership_manifest(Path(tmp_dir))
        assert res_tmp.status == CheckStatus.WARN

        # Empty ownership.yaml
        empty_manifest = Path(tmp_dir) / "ownership.yaml"
        empty_manifest.touch()
        res_empty = check_ownership_manifest(Path(tmp_dir))
        assert res_empty.status == CheckStatus.FAIL


def test_planning_directory_check() -> None:
    # Existing repo root has .planning
    res = check_planning_directory(Path.cwd())
    assert res.status == CheckStatus.PASS

    with tempfile.TemporaryDirectory() as tmp_dir:
        res_missing = check_planning_directory(Path(tmp_dir))
        assert res_missing.status == CheckStatus.WARN


def test_workspace_permissions_check() -> None:
    res = check_workspace_permissions(Path.cwd())
    assert res.status == CheckStatus.PASS


def test_doctor_engine_run() -> None:
    engine = DoctorEngine(workspace_root=Path.cwd())
    results = engine.run_checks()
    assert len(results) >= 5
    overall = engine.overall_status(results)
    assert overall in (CheckStatus.PASS, CheckStatus.WARN)
    assert engine.exit_code(results) == 0

    report = engine.format_report(results, verbose=True)
    assert "Programming Desk Health Inspection" in report
    assert "Summary:" in report


def test_doctor_engine_custom_probe_and_failure() -> None:
    engine = DoctorEngine(workspace_root=Path.cwd())

    def failing_probe(root: Path) -> DiagnosticCheckResult:
        return DiagnosticCheckResult(
            name="broken_dependency",
            status=CheckStatus.FAIL,
            message="Required library missing",
            fix_hint="Install library",
        )

    engine.register_probe(failing_probe)
    results = engine.run_checks()
    assert any(r.name == "broken_dependency" for r in results)
    assert engine.overall_status(results) == CheckStatus.FAIL
    assert engine.exit_code(results) == 1
