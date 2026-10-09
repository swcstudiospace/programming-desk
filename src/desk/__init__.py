"""Programming Desk — Enterprise-Ready, Best-in-Class Developer Workbench.

Provides 7 cohesive runtime capabilities:
1. Resilient Process Supervision
2. Workspace Context & State Persistence
3. Structured Audit & Telemetry
4. Error Boundary & Transaction Recovery
5. Doctor Diagnostics Engine
6. Security, Policy & Secret Sandboxing
7. Milestone Assertion Pipeline
"""

from .assertions import MilestonePhase, MilestoneVerifier, VerificationReport
from .diagnostics import CheckStatus, DiagnosticCheckResult, DoctorEngine
from .recovery import (
    CompensationAction,
    RecoveryManager,
    TransactionContext,
    TransactionReport,
)
from .security import BoundarySecurityError, PolicySandbox
from .session import SessionFrame, SessionStore
from .supervision import ProcessSupervisor, SupervisedProcessResult
from .telemetry import AuditEvent, AuditTracer

__version__ = "1.0.0"

__all__ = [
    # 1. Supervision
    "ProcessSupervisor",
    "SupervisedProcessResult",
    # 2. Session
    "SessionStore",
    "SessionFrame",
    # 3. Telemetry
    "AuditTracer",
    "AuditEvent",
    # 4. Recovery
    "RecoveryManager",
    "TransactionContext",
    "TransactionReport",
    "CompensationAction",
    # 5. Diagnostics
    "DoctorEngine",
    "DiagnosticCheckResult",
    "CheckStatus",
    # 6. Security
    "PolicySandbox",
    "BoundarySecurityError",
    # 7. Assertions
    "MilestoneVerifier",
    "MilestonePhase",
    "VerificationReport",
]
