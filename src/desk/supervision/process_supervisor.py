"""Resilient Process Supervision module with array spawning, timeout traps, and clean tree teardown."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import random
import signal
import subprocess
import threading
import time
from typing import Any, Mapping

from ..security.policy_sandbox import PolicySandbox


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
    stdout_truncated: bool = False
    stderr_truncated: bool = False

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
        max_output_bytes: int = 1_048_576,
    ) -> None:
        self.default_timeout = default_timeout
        self.sandbox = sandbox or PolicySandbox(workspace_root=workspace_root)
        self.workspace_root = self.sandbox.workspace_root
        self.max_output_bytes = max_output_bytes
        self._active_processes: dict[int, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def _signal_group(self, pgid: int, sig: int) -> bool:
        """Signal a process group, never this supervisor's own group.

        Returns False without calling ``os.killpg`` when ``pgid`` equals
        ``os.getpgrp()``. Returns True after ``os.killpg`` delivers ``sig``.
        """
        if pgid == os.getpgrp():
            return False
        os.killpg(pgid, sig)
        return True

    @staticmethod
    def _is_sensitive_env_key(key: str) -> bool:
        return any(pattern.match(key) for pattern in PolicySandbox.SENSITIVE_KEY_PATTERNS)

    def _child_environment(self, overlay: Mapping[str, str] | None) -> dict[str, str]:
        """Copy the parent environment, then drop credential-like keys.

        Caller overlay is applied after the scrub. Sensitive names in the
        overlay are ignored so they cannot reintroduce a removed secret.
        """
        child = {
            key: value
            for key, value in os.environ.items()
            if not self._is_sensitive_env_key(key)
        }
        if overlay is not None:
            for key, value in overlay.items():
                if self._is_sensitive_env_key(key):
                    continue
                child[key] = value
        return child

    @staticmethod
    def _limit_output(text: str, limit: int) -> tuple[str, bool]:
        """Keep the first ``limit`` UTF-8 bytes. Short text is returned unchanged."""
        encoded = text.encode("utf-8")
        if len(encoded) <= limit:
            return text, False
        if limit <= 0:
            return "", True
        return encoded[:limit].decode("utf-8", errors="ignore"), True

    def _terminate_process_tree(self, proc: subprocess.Popen[str], grace_period: float = 1.0) -> None:
        """Kill the process and all of its spawned child processes cleanly via process group."""
        pid = proc.pid
        if pid is None:
            return

        pgid: int | None = None
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError, OSError):
            pgid = None

        # 1. Send SIGTERM to the process group, or to the direct child when the
        # group cannot be signaled (no pgid, or the group is our own).
        deliver_direct_sigterm = pgid is None
        if pgid is not None:
            try:
                deliver_direct_sigterm = not self._signal_group(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                deliver_direct_sigterm = False
        if deliver_direct_sigterm:
            try:
                proc.terminate()
            except (ProcessLookupError, PermissionError, OSError):
                pass

        # 2. Wait for grace period, checking if any processes remain in the group
        start_wait = time.monotonic()
        while time.monotonic() - start_wait < grace_period:
            parent_alive = proc.poll() is None
            group_alive = False
            if pgid is not None:
                try:
                    group_alive = self._signal_group(pgid, 0)
                except (ProcessLookupError, PermissionError, OSError):
                    group_alive = False
            if not parent_alive and not group_alive:
                return
            time.sleep(0.05)

        # 3. Force escalate to SIGKILL against entire process group and parent
        if pgid is not None:
            try:
                self._signal_group(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def shutdown_all(self, grace_period: float = 1.0) -> None:
        """Terminate all currently tracked active processes."""
        with self._lock:
            procs = list(self._active_processes.items())
        for pid, proc in procs:
            self._terminate_process_tree(proc, grace_period=grace_period)
            with self._lock:
                self._active_processes.pop(pid, None)

    def run(
        self,
        cmd: list[str],
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        max_retries: int = 0,
        backoff_base: float = 0.2,
        retry_on_exit_codes: list[int] | None = None,
        max_output_bytes: int | None = None,
    ) -> SupervisedProcessResult:
        """Execute a command array with timeout traps, retries, and process group safety.

        Collected stdout and stderr longer than the byte cap are cut to the
        first ``max_output_bytes`` (instance default when omitted). The child
        environment starts from ``os.environ`` with credential-like keys removed;
        ``env`` is applied after that, and sensitive overlay keys are dropped.
        """
        # Policy & sandbox validation
        validated_cmd = self.sandbox.validate_command(cmd)

        exec_cwd = self.workspace_root
        if cwd is not None:
            exec_cwd = self.sandbox.validate_path(cwd)

        # Scrub credential-like keys before the child starts. Do not interpolate
        # secret values into the command array.
        exec_env = self._child_environment(env)

        timeout_sec = timeout if timeout is not None else self.default_timeout
        output_limit = self.max_output_bytes if max_output_bytes is None else max_output_bytes
        retry_codes = set(retry_on_exit_codes or [143, 137, 75])  # Common transient codes

        attempt = 0
        while attempt <= max_retries:
            start_time = time.monotonic()
            timed_out = False
            last_pid: int | None = None
            proc: subprocess.Popen[str] | None = None
            stdout_data = ""
            stderr_data = ""

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
                with self._lock:
                    self._active_processes[proc.pid] = proc

                stdout_data, stderr_data = proc.communicate(timeout=timeout_sec)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                out_accum = exc.output or ""
                err_accum = exc.stderr or ""
                if isinstance(out_accum, bytes):
                    out_accum = out_accum.decode("utf-8", errors="replace")
                if isinstance(err_accum, bytes):
                    err_accum = err_accum.decode("utf-8", errors="replace")

                stdout_data = out_accum
                stderr_data = err_accum

                if proc is not None:
                    self._terminate_process_tree(proc)
                    try:
                        # Bounded read to prevent hanging on surviving children keeping pipes open
                        more_out, more_err = proc.communicate(timeout=1.0)
                        if more_out is not None:
                            if isinstance(more_out, bytes):
                                more_out = more_out.decode("utf-8", errors="replace")
                            stdout_data = more_out
                        if more_err is not None:
                            if isinstance(more_err, bytes):
                                more_err = more_err.decode("utf-8", errors="replace")
                            stderr_data = more_err
                    except subprocess.TimeoutExpired as exc2:
                        extra_out = exc2.output
                        extra_err = exc2.stderr
                        if extra_out is not None:
                            if isinstance(extra_out, bytes):
                                extra_out = extra_out.decode("utf-8", errors="replace")
                            stdout_data = extra_out
                        if extra_err is not None:
                            if isinstance(extra_err, bytes):
                                extra_err = extra_err.decode("utf-8", errors="replace")
                            stderr_data = extra_err
                    except Exception:
                        pass
                exit_code = -signal.SIGKILL
            finally:
                if proc is not None and proc.poll() is None:
                    self._terminate_process_tree(proc)
                    try:
                        proc.communicate(timeout=0.5)
                    except Exception:
                        pass
                if last_pid is not None:
                    with self._lock:
                        self._active_processes.pop(last_pid, None)

            duration_ms = (time.monotonic() - start_time) * 1000.0

            stdout_text, stdout_truncated = self._limit_output(stdout_data or "", output_limit)
            stderr_text, stderr_truncated = self._limit_output(stderr_data or "", output_limit)

            result = SupervisedProcessResult(
                cmd=validated_cmd[0],
                args=validated_cmd[1:],
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_ms=duration_ms,
                timed_out=timed_out,
                retries=attempt,
                pid=last_pid,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
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
