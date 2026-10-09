"""Tests for ProcessSupervisor and SupervisedProcessResult."""

import os
import signal
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


def test_supervisor_deadline_stops_retries() -> None:
    supervisor = ProcessSupervisor()
    result = supervisor.run(
        [sys.executable, "-c", "import sys; sys.exit(75)"],
        max_retries=5,
        backoff_base=0.4,
        deadline_s=0.35,
        retry_on_exit_codes=[75],
    )

    assert result.exit_code == 75
    assert result.retries < 5
    assert result.duration_ms < 2000


def test_supervisor_rejection_of_unsafe_command() -> None:
    supervisor = ProcessSupervisor()
    with pytest.raises(BoundarySecurityError):
        supervisor.run(["cat", "test.py && rm -rf /"])


def test_supervisor_partial_output_preserved_on_timeout() -> None:
    supervisor = ProcessSupervisor()
    # Flushes output before sleeping past the timeout
    script = "import sys, time; sys.stdout.write('progress_before_timeout\\n'); sys.stdout.flush(); time.sleep(10)"
    result = supervisor.run([sys.executable, "-c", script], timeout=0.3)
    assert result.timed_out is True
    assert result.stdout == "progress_before_timeout\n"
    assert result.stdout_truncated is False


def test_supervisor_truncates_stdout_over_max_output_bytes() -> None:
    supervisor = ProcessSupervisor()
    result = supervisor.run(
        [sys.executable, "-c", "import sys; sys.stdout.write('a' * 250)"],
        max_output_bytes=100,
    )

    assert result.succeeded
    assert result.stdout_truncated is True
    assert result.stdout == "a" * 100
    assert len(result.stdout.encode("utf-8")) == 100
    assert result.stderr_truncated is False


def test_supervisor_child_sees_empty_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "dummy")
    supervisor = ProcessSupervisor()
    script = (
        "import os; "
        "print(os.environ.get('GITHUB_TOKEN', '')); "
        "print(os.environ.get('DESK_PLAIN', '')); "
        "print('path' if os.environ.get('PATH') else 'nopath')"
    )
    result = supervisor.run(
        [sys.executable, "-c", script],
        env={"GITHUB_TOKEN": "dummy", "DESK_PLAIN": "kept"},
    )

    assert result.succeeded
    token_line, marker_line, path_line = result.stdout.splitlines()
    assert token_line == ""
    assert "dummy" not in result.stdout
    assert marker_line == "kept"
    assert path_line == "path"


def test_signal_group_skips_killpg_when_pgid_is_own_group(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = ProcessSupervisor()
    calls: list[tuple[int, int]] = []

    def record_killpg(pgid: int, sig: int) -> None:
        calls.append((pgid, int(sig)))

    monkeypatch.setattr(os, "getpgrp", lambda: 4242)
    monkeypatch.setattr(os, "killpg", record_killpg)

    supervisor._signal_group(4242, signal.SIGTERM)
    assert calls == []

    supervisor._signal_group(4243, signal.SIGTERM)
    assert calls == [(4243, int(signal.SIGTERM))]
