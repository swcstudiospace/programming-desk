"""Error boundary and transaction recovery primitives for Programming Desk."""

from .recovery_manager import (
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
