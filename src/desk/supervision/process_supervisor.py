"""Resilient Process Supervision module with array spawning, timeout traps, and clean tree teardown."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import random
import signal
import subprocess
import time
from typing import Any, Mapping

from src.desk.security.policy_sandbox import PolicySandbox


@dataclass
class SupervisedProcessResult:
    """Outcome of a supervised process execution."""

    cmd: str
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    retries: int = 0
    pid: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class ProcessSupervisor:
    """Supervises child processes with array spawning, timeout escalation, retries, and tree teardown."""

    def __init__(
        self,
        default_timeout: float = 30.0,
        sandbox: PolicySandbox | None = None,
        workspace_root: str | Path | None = None,
    ) -> None:
        self.default_timeout = default_timeout
        self.sandbox = sandbox or PolicySandbox(workspace_root=workspace_root)
        self.workspace_root = self.sandbox.workspace_root
        self._active_processes: dict[int, subprocess.Popen[str]] = {}

    def _terminate_process_tree(self, proc: subprocess.Popen[str], grace_period: float = 1.0) -> None:
        """Kill the process and all of its spawned child processes cleanly via process group."""
        pid = proc.pid
        if pid is None or proc.poll() is not None:
            return

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except (ProcessLookupError, PermissionError):
                pass

        # Wait for grace period
        start_wait = time.monotonic()
        while time.monotonic() - start_wait < grace_period:
            if proc.poll() is not None:
                return
            time.sleep(0.05)

        # Force escalate to SIGKILL if still running
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except (ProcessLookupError, PermissionError):
                pass

    def shutdown_all(self, grace_period: float = 1.0) -> None:
        """Terminate all currently tracked active processes."""
        for pid, proc in list(self._active_processes.items()):
            self._terminate_process_tree(proc, grace_period=grace_period)
        self._active_processes.clear()

    def run(
        self,
        cmd: list[str],
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_retries: int = 0,
        backoff_base: float = 0.2,
        retry_on_exit_codes: list[int] | None = None,
    ) -> SupervisedProcessResult:
        """Execute a command array with timeout traps, retries, and process group safety."""
        # Policy & sandbox validation
        validated_cmd = self.sandbox.validate_command(cmd)

        exec_cwd = self.workspace_root
        if cwd is not None:
            exec_cwd = self.sandbox.validate_path(cwd)

        # Prepare environment
        exec_env = os.environ.copy()
        if env is not None:
            exec_env.update(env)

        timeout_sec = timeout if timeout is not None else self.default_timeout
        retry_codes = set(retry_on_exit_codes or [143, 137, 75])  # Common transient codes

        attempt = 0
        while attempt <= max_retries:
            start_time = time.monotonic()
            timed_out = False
            last_pid = None

            try:
                # Use start_new_session=True to create a new POSIX process group for clean tree termination
                proc = subprocess.Popen(
                    validated_cmd,
                    cwd=str(exec_cwd),
                    env=exec_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                last_pid = proc.pid
                self._active_processes[proc.pid] = proc

                stdout_data, stderr_data = proc.communicate(timeout=timeout_sec)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                self._terminate_process_tree(proc)
                stdout_data, stderr_data = proc.communicate()
                exit_code = -signal.SIGKILL
            finally:
                if last_pid in self._active_processes:
                    del self._active_processes[last_pid]

            duration_ms = (time.monotonic() - start_time) * 1000.0

            result = SupervisedProcessResult(
                cmd=validated_cmd[0],
                args=validated_cmd[1:],
                exit_code=exit_code,
                stdout=stdout_data or "",
                stderr=stderr_data or "",
                duration_ms=duration_ms,
                timed_out=timed_out,
                retries=attempt,
                pid=last_pid,
            )

            # Check if retry condition is met
            should_retry = attempt < max_retries and (
                timed_out or (exit_code != 0 and exit_code in retry_codes)
            )

            if not should_retry:
                return result

            attempt += 1
            # Exponential backoff with jitter
            delay = (backoff_base * (2 ** (attempt - 1))) + (random.uniform(0.01, 0.05))
            time.sleep(delay)

        return result
