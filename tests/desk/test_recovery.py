"""Tests for RecoveryManager and transaction compensation stack."""

from pathlib import Path
import tempfile
import pytest

from src.desk.recovery import RecoveryManager
from src.desk.security.policy_sandbox import BoundarySecurityError


@pytest.fixture(autouse=True)
def _isolated_audit_cwd(monkeypatch, tmp_path):
    """Transactions emit audit records; keep them out of the real .planning."""
    monkeypatch.chdir(tmp_path)

def test_successful_transaction() -> None:
    mgr = RecoveryManager()
    with mgr.transaction("step-1") as tx:
        tx.register_compensation(lambda: None, name="dummy")

    assert len(mgr.history) == 1
    report = mgr.history[0]
    assert report.name == "step-1"
    assert report.succeeded is True
    assert report.error_message is None
    assert tx.is_committed is True
    assert tx.is_rolled_back is False


def test_failed_transaction_lifo_order() -> None:
    mgr = RecoveryManager()
    call_log: list[str] = []

    def make_action(msg: str):
        return lambda: call_log.append(msg)

    with pytest.raises(RuntimeError):
        with mgr.transaction("step-fail", reraise=True) as tx:
            tx.register_compensation(make_action("first"))
            tx.register_compensation(make_action("second"))
            tx.register_compensation(make_action("third"))
            raise RuntimeError("something exploded")

    # Compensations must execute in LIFO order: third, second, first
    assert call_log == ["third", "second", "first"]

    assert len(mgr.history) == 1
    report = mgr.history[0]
    assert report.succeeded is False
    assert "something exploded" in (report.error_message or "")
    assert report.rollbacks_executed == 3
    assert report.rollbacks_failed == 0


def test_file_backup_and_restoration_on_failure() -> None:
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "config.json"
        test_file.write_text('{"version": 1}', encoding="utf-8")

        with pytest.raises(ValueError):
            with mgr.transaction("mutate-config", reraise=True) as tx:
                tx.backup_file(test_file)
                # Overwrite file with corrupt content
                test_file.write_text('{"version": 999, "corrupted": true}', encoding="utf-8")
                raise ValueError("Bad config mutation")

        # After rollback, original file content should be restored
        assert test_file.read_text(encoding="utf-8") == '{"version": 1}'


def test_file_creation_rollback() -> None:
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        new_file = Path(tmp_dir) / "scratchpad.txt"

        with pytest.raises(RuntimeError):
            with mgr.transaction("create-scratchpad", reraise=True) as tx:
                tx.backup_file(new_file)
                new_file.write_text("temporary data", encoding="utf-8")
                assert new_file.exists()
                raise RuntimeError("Failed midway")

        # Rollback should delete newly created file
        assert not new_file.exists()


def test_suppressed_exception() -> None:
    mgr = RecoveryManager()

    with mgr.transaction("step-suppressed", reraise=False) as tx:
        raise KeyError("missing key")

    assert len(mgr.history) == 1
    assert mgr.history[0].succeeded is False
    assert "missing key" in (mgr.history[0].error_message or "")


def test_explicit_rollback_partial_failure() -> None:
    mgr = RecoveryManager()

    def failing_action():
        raise RuntimeError("failed to clean up resource")

    executed_log: list[str] = []

    with mgr.transaction("step-explicit-rollback") as tx:
        tx.register_compensation(lambda: executed_log.append("first_succeeded"), name="success_comp")
        tx.register_compensation(failing_action, name="failing_comp")
        executed, failed = tx.rollback()
        assert executed == 1
        assert failed == 1

    assert len(mgr.history) == 1
    report = mgr.history[0]
    assert report.succeeded is False
    assert report.rollbacks_executed == 1
    assert report.rollbacks_failed == 1
    assert len(tx.failed_restorations) == 1
    assert "failing_comp: failed to clean up resource" in tx.failed_restorations[0]


def test_backup_file_rejects_symlink_target() -> None:
    """A symlink leaf must raise and must not copy the outside target."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        outside = root / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("outside-secret", encoding="utf-8")

        workspace = root / "workspace"
        workspace.mkdir()
        link = workspace / "config.json"
        link.symlink_to(secret)

        with pytest.raises(BoundarySecurityError):
            with mgr.transaction("reject-symlink") as tx:
                tx.backup_file(link)

        assert tx._backup_dir is None
        assert secret.read_text(encoding="utf-8") == "outside-secret"
        assert link.is_symlink()
        assert list(outside.iterdir()) == [secret]
        assert list(workspace.iterdir()) == [link]


def test_backup_file_rejects_relative_symlink(monkeypatch: pytest.MonkeyPatch) -> None:
    """Relative targets are confined to cwd, so a nested link is still rejected."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        outside = root / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("outside-secret", encoding="utf-8")

        workspace = root / "workspace"
        nested = workspace / "nested"
        nested.mkdir(parents=True)
        link = nested / "link.txt"
        link.symlink_to(secret)

        monkeypatch.chdir(workspace)
        with pytest.raises(BoundarySecurityError):
            with mgr.transaction("reject-relative-symlink") as tx:
                tx.backup_file(Path("nested") / "link.txt")

        assert tx._backup_dir is None
        assert secret.read_text(encoding="utf-8") == "outside-secret"
        assert link.is_symlink()


def test_backup_file_rejects_symlink_directory_component() -> None:
    """A real file reached through a symlink directory must not be copied."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        outside = root / "outside"
        outside.mkdir()
        secret = outside / "secret.txt"
        secret.write_text("outside-secret", encoding="utf-8")

        workspace = root / "workspace"
        workspace.mkdir()
        linkdir = workspace / "linkdir"
        linkdir.symlink_to(outside)
        reached = linkdir / "secret.txt"
        assert reached.is_file()
        assert not reached.is_symlink()

        with pytest.raises(BoundarySecurityError):
            with mgr.transaction("reject-symlink-dir") as tx:
                tx.backup_file(reached)

        assert tx._backup_dir is None
        assert secret.read_text(encoding="utf-8") == "outside-secret"
        assert list(outside.iterdir()) == [secret]


def test_failed_restore_keeps_backup_when_destination_is_symlink() -> None:
    """A refused restore leaves the backup directory on disk and does not follow the link."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        target = root / "config.json"
        target.write_text('{"version": 1}', encoding="utf-8")
        outside = root / "outside.txt"
        outside.write_text("do-not-touch", encoding="utf-8")

        backup_dir: Path | None = None
        with pytest.raises(ValueError):
            with mgr.transaction("restore-through-symlink") as tx:
                tx.backup_file(target)
                backup_dir = tx._backup_dir
                assert backup_dir is not None and backup_dir.is_dir()
                target.unlink()
                target.symlink_to(outside)
                raise ValueError("mutation failed")

        assert outside.read_text(encoding="utf-8") == "do-not-touch"
        assert target.is_symlink()
        assert target.read_text(encoding="utf-8") == "do-not-touch"
        assert backup_dir is not None and backup_dir.exists()
        preserved = [path for path in backup_dir.iterdir() if path.is_file() and not path.is_symlink()]
        assert len(preserved) == 1
        assert preserved[0].read_text(encoding="utf-8") == '{"version": 1}'
        assert tx.rollbacks_failed == 1
        assert mgr.history[0].rollbacks_failed == 1
        assert any("symlink" in item.lower() for item in tx.failed_restorations)


def test_backup_file_private_modes_before_commit() -> None:
    """Backup copies are 0o600 and the backup directory is 0o700 before commit."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "notes.txt"
        source.write_text("keep-me", encoding="utf-8")
        source.chmod(0o644)

        with mgr.transaction("private-backup") as tx:
            returned = tx.backup_file(source)
            backup = tx._file_backups[returned]
            assert tx._backup_dir is not None
            assert (backup.stat().st_mode & 0o777) == 0o600
            assert (tx._backup_dir.stat().st_mode & 0o777) == 0o700
            assert (source.stat().st_mode & 0o777) == 0o644


def test_backup_restore_preserves_source_mode() -> None:
    """Rollback puts the original mode back. The private backup mode must not stick."""
    mgr = RecoveryManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "notes.txt"
        source.write_text("keep-me", encoding="utf-8")
        source.chmod(0o640)

        with pytest.raises(RuntimeError):
            with mgr.transaction("restore-mode") as tx:
                tx.backup_file(source)
                source.write_text("mutated", encoding="utf-8")
                source.chmod(0o606)
                raise RuntimeError("mutation failed")

        assert source.read_text(encoding="utf-8") == "keep-me"
        assert (source.stat().st_mode & 0o777) == 0o640


def _tx_audit_rows(root, action):
    import json

    log = root / ".planning" / "audit.jsonl"
    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("action") == action]


def test_transaction_commit_emits_audit(tmp_path) -> None:
    mgr = RecoveryManager()
    target = tmp_path / "data.txt"
    target.write_text("v1", encoding="utf-8")
    with mgr.transaction("audit-commit", correlation_id="corr-tx-01") as tx:
        tx.backup_file(target)
        target.write_text("v2", encoding="utf-8")

    commits = _tx_audit_rows(tmp_path, "transaction_commit")
    assert len(commits) == 1
    assert commits[0]["correlation_id"] == "corr-tx-01"
    assert commits[0]["details"]["transaction"] == "audit-commit"
    assert commits[0]["details"]["files"] == 1


def test_transaction_rollback_emits_audit(tmp_path) -> None:
    mgr = RecoveryManager()
    target = tmp_path / "data.txt"
    target.write_text("v1", encoding="utf-8")
    with pytest.raises(RuntimeError, match="boom"):
        with mgr.transaction("audit-rollback") as tx:
            tx.backup_file(target)
            target.write_text("v2", encoding="utf-8")
            raise RuntimeError("boom")

    rollbacks = _tx_audit_rows(tmp_path, "transaction_rollback")
    assert len(rollbacks) == 1
    assert rollbacks[0]["details"]["transaction"] == "audit-rollback"
    assert rollbacks[0]["details"]["rollbacks_executed"] == 1
    assert rollbacks[0]["details"]["rollbacks_failed"] == 0
    assert "boom" in (rollbacks[0]["details"]["error"] or "")
