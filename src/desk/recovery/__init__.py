"""Error boundary and transaction recovery primitives for Programming Desk."""

from src.desk.recovery.recovery_manager import (
    CompensationAction,
    RecoveryManager,
    TransactionContext,
    TransactionReport,
)

__all__ = [
    "CompensationAction",
    "RecoveryManager",
    "TransactionContext",
    "TransactionReport",
]
