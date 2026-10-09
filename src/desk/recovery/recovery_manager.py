"""Error Boundary & Transaction Recovery module with LIFO compensating-action stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile
import traceback
from typing import Any, Callable


@dataclass
class CompensationAction:
    """Represents a registered compensating action in the rollback stack."""

    name: str
    action: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionReport:
    """Diagnostic outcome of a transaction execution."""

    name: str
    succeeded: bool
    started_at: str
    finished_at: str
    error_message: str | None = None
    traceback_dump: str | None = None
    rollbacks_executed: int = 0
    rollbacks_failed: int = 0


class TransactionContext:
    """Context object passed into a recovery transaction."""

    def __init__(self, name: str, manager: RecoveryManager) -> None:
        self.name = name
        self.manager = manager
        self._compensations: list[CompensationAction] = []
        self._file_backups: dict[Path, Path] = {}
        self._backup_dir: Path | None = None
        self.is_committed: bool = False
        self.is_rolled_back: bool = False
        self.rollbacks_executed: int = 0
        self.rollbacks_failed: int = 0
        self.failed_restorations: list[str] = []

    def register_compensation(
        self,
        action: Callable[..., Any],
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Register a compensating action to run on transaction failure (LIFO)."""
        action_name = name or getattr(action, "__name__", "anonymous_compensation")
        self._compensations.append(CompensationAction(name=action_name, action=action, args=args, kwargs=kwargs))

    def backup_file(self, file_path: str | Path) -> Path:
        """Create a backup of a file to be automatically restored if transaction fails."""
        target = Path(file_path).resolve()
        if not target.exists():
            # If file doesn't exist yet, compensation is to delete it if created
            def _remove_created() -> None:
                if target.exists():
                    target.unlink()

            self.register_compensation(_remove_created, name=f"delete_created_{target.name}")
            return target

        if self._backup_dir is None:
            self._backup_dir = Path(tempfile.mkdtemp(prefix="desk_tx_backup_"))

        backup_copy = self._backup_dir / f"{target.name}.bak.{len(self._file_backups)}"
        shutil.copy2(target, backup_copy)
        self._file_backups[target] = backup_copy

        def _restore() -> None:
            if backup_copy.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_copy, target)

        self.register_compensation(_restore, name=f"restore_{target.name}")
        return target

    def rollback(self) -> tuple[int, int]:
        """Execute all compensations in reverse order (LIFO). Returns (executed, failed)."""
        if self.is_rolled_back:
            return self.rollbacks_executed, self.rollbacks_failed

        self.is_rolled_back = True
        executed = 0
        failed = 0

        # Run in reverse order
        for comp in reversed(self._compensations):
            try:
                comp.action(*comp.args, **comp.kwargs)
                executed += 1
            except Exception as err:
                failed += 1
                self.failed_restorations.append(f"{comp.name}: {err}")

        self.rollbacks_executed = executed
        self.rollbacks_failed = failed

        # Retain backups if any restoration failed so original copies are preserved for recovery
        if failed == 0:
            self.cleanup()
        return executed, failed

    def commit(self) -> None:
        """Mark transaction as successfully completed."""
        self.is_committed = True
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up temporary backup directory."""
        if self._backup_dir and self._backup_dir.exists():
            try:
                shutil.rmtree(self._backup_dir, ignore_errors=True)
            except OSError:
                pass


class RecoveryManager:
    """Manages transactional execution boundaries, rollback stacks, and failure diagnostics."""

    def __init__(self) -> None:
        self.history: list[TransactionReport] = []

    def transaction(self, name: str, reraise: bool = True):
        """Context manager creating a transactional recovery boundary."""
        mgr = self

        class _TxContextManager:
            def __enter__(self) -> TransactionContext:
                self.tx = TransactionContext(name=name, manager=mgr)
                self.started_at = datetime.now(timezone.utc).isoformat()
                return self.tx

            def __exit__(self, exc_type, exc_val, exc_tb):
                finished_at = datetime.now(timezone.utc).isoformat()
                if exc_type is not None:
                    # An error occurred; trigger LIFO rollback
                    executed, failed = self.tx.rollback()
                    tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
                    report = TransactionReport(
                        name=name,
                        succeeded=False,
                        started_at=self.started_at,
                        finished_at=finished_at,
                        error_message=str(exc_val),
                        traceback_dump=tb_str,
                        rollbacks_executed=executed,
                        rollbacks_failed=failed,
                    )
                    mgr.history.append(report)
                    return not reraise  # Suppress exception if reraise is False
                elif self.tx.is_rolled_back:
                    # Transaction was explicitly rolled back inside the block
                    report = TransactionReport(
                        name=name,
                        succeeded=False,
                        started_at=self.started_at,
                        finished_at=finished_at,
                        error_message="Transaction explicitly rolled back",
                        rollbacks_executed=self.tx.rollbacks_executed,
                        rollbacks_failed=self.tx.rollbacks_failed,
                    )
                    mgr.history.append(report)
                    return False
                else:
                    self.tx.commit()
                    report = TransactionReport(
                        name=name,
                        succeeded=True,
                        started_at=self.started_at,
                        finished_at=finished_at,
                    )
                    mgr.history.append(report)
                    return False

        return _TxContextManager()
