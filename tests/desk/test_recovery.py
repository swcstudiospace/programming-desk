"""Tests for RecoveryManager and transaction compensation stack."""

from pathlib import Path
import tempfile
import pytest

from src.desk.recovery import RecoveryManager


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
