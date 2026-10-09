"""Tests for ProcessSupervisor and SupervisedProcessResult."""

import sys
import time
import pytest

from src.desk.security.policy_sandbox import BoundarySecurityError
from src.desk.supervision import ProcessSupervisor, SupervisedProcessResult


def test_supervisor_successful_execution() -> None:
    supervisor = ProcessSupervisor()
    result = supervisor.run([sys.executable, "-c", "print('hello from python')"])

    assert result.succeeded
    assert result.exit_code == 0
    assert "hello from python" in result.stdout.strip()
    assert result.timed_out is False
    assert result.duration_ms > 0
    assert result.retries == 0


def test_supervisor_nonzero_exit() -> None:
    supervisor = ProcessSupervisor()
    result = supervisor.run([sys.executable, "-c", "import sys; sys.exit(42)"])

    assert not result.succeeded
    assert result.exit_code == 42
    assert result.timed_out is False


def test_supervisor_timeout_and_tree_kill() -> None:
    supervisor = ProcessSupervisor(default_timeout=0.4)
    # Child spawns a grandchild and both sleep
    script = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)']); time.sleep(10)"

    start = time.monotonic()
    result = supervisor.run([sys.executable, "-c", script], timeout=0.3)
    elapsed = time.monotonic() - start

    assert result.timed_out is True
    assert not result.succeeded
    assert elapsed < 3.0  # Finished promptly after timeout and grace period


def test_supervisor_retries_on_transient_exit() -> None:
    supervisor = ProcessSupervisor()
    # Code 75 is in the default retry_on_exit_codes
    result = supervisor.run(
        [sys.executable, "-c", "import sys; sys.exit(75)"],
        max_retries=2,
        backoff_base=0.05,
    )

    assert result.exit_code == 75
    assert result.retries == 2


def test_supervisor_rejection_of_unsafe_command() -> None:
    supervisor = ProcessSupervisor()
    with pytest.raises(BoundarySecurityError):
        supervisor.run(["cat", "test.py && rm -rf /"])
