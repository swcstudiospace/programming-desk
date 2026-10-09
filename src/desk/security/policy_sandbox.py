"""Security, Policy & Secret Sandboxing module for Programming Desk."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from typing import Mapping


class BoundarySecurityError(Exception):
    """Raised when a path or command violates security boundary policies."""


class PolicySandbox:
    """Provides path boundary confinement, secret/token sanitization, and command policy validation."""

    # Precise secret token patterns:
    # 1. GitHub tokens: ghp_ followed by 36 alphanumeric characters
    # 2. OpenAI / API keys: sk-[a-zA-Z0-9]{20,}
    # 3. HTTP Bearer tokens: Bearer followed by base64/URL-safe token
    # 4. AWS access keys: AKIA followed by 16 uppercase alphanumeric characters
    SECRET_PATTERNS = [
        re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"),
        re.compile(r"\bgh[ousr]_[a-zA-Z0-9]{36}\b"),
        re.compile(r"\bgithub_pat_[a-zA-Z0-9_]{20,}\b"),
        re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
        re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b"),
        re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ]

    # Sensitive environment variable key prefixes/suffixes
    SENSITIVE_KEY_PATTERNS = [
        re.compile(r".*(_KEY|_SECRET|_TOKEN|_PASSWORD|_PASSWD|_CREDENTIAL|_AUTH)$", re.IGNORECASE),
        re.compile(r"^(API_KEY|AUTH_TOKEN|SECRET_KEY|ACCESS_TOKEN|PASSWORD)$", re.IGNORECASE),
    ]

    # Dangerous command substitution / injection tokens in array args
    DANGEROUS_SHELL_TOKENS = ["`", "$(", "${", "\x00"]

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        if workspace_root is None:
            self.workspace_root = Path.cwd().resolve()
        else:
            self.workspace_root = Path(workspace_root).resolve()

    def sanitize(self, text: str, placeholder: str = "[REDACTED]") -> str:
        """Redact sensitive tokens from text while preserving non-secret strings and commit hashes."""
        if not text:
            return text

        result = text
        for pattern in self.SECRET_PATTERNS:
            result = pattern.sub(placeholder, result)

        return result

    def sanitize_env(
        self,
        env: Mapping[str, str],
        redact_keys: bool = True,
        placeholder: str = "[REDACTED]",
    ) -> dict[str, str]:
        """Produce a sanitized copy of an environment variable dictionary."""
        sanitized: dict[str, str] = {}
        for k, v in env.items():
            if not isinstance(v, str):
                continue

            # Check if key name indicates sensitive credential
            is_sensitive_key = False
            if redact_keys:
                for key_pat in self.SENSITIVE_KEY_PATTERNS:
                    if key_pat.match(k):
                        is_sensitive_key = True
                        break

            if is_sensitive_key:
                sanitized[k] = placeholder
            else:
                sanitized[k] = self.sanitize(v, placeholder=placeholder)

        return sanitized

    def validate_path(self, target: str | Path) -> Path:
        """Confine a path to the workspace without following symlinks.

        Lexical `..` escapes are rejected. Any existing path component that is a
        symlink is rejected, including a link whose target would still land inside
        the workspace. Missing leaf names are allowed so callers can create files.
        """
        raw_text = os.fspath(target)
        if "\x00" in raw_text:
            raise BoundarySecurityError("Null byte detected in path")

        raw_path = Path(raw_text)
        if raw_path.is_absolute():
            candidate = Path(os.path.normpath(raw_text))
        else:
            candidate = Path(os.path.normpath(os.fspath(self.workspace_root / raw_path)))

        try:
            relative = candidate.relative_to(self.workspace_root)
        except ValueError as err:
            raise BoundarySecurityError(
                f"Path traversal violation: '{target}' resolves to '{candidate}', "
                f"which is outside workspace root '{self.workspace_root}'"
            ) from err

        current = self.workspace_root
        for part in relative.parts:
            current = current / part
            # is_symlink is false for a missing leaf and true for a dangling link.
            if current.is_symlink():
                raise BoundarySecurityError(
                    f"Symlink rejected inside workspace: '{current}'"
                )

        return candidate

    def validate_command(
        self,
        cmd: list[str],
        allowed_executables: list[str] | None = None,
    ) -> list[str]:
        """Validate an array-based command before execution.

        Ensures arguments do not contain raw shell metacharacters or unauthorized executables.
        """
        if not cmd:
            raise BoundarySecurityError("Command array cannot be empty")

        raw_exe = cmd[0]
        exe_path = Path(raw_exe)
        exe_name = exe_path.name

        if allowed_executables is not None:
            allowed_names = set(allowed_executables)
            allowed_resolved: set[str] = set()
            for item in allowed_executables:
                p = Path(item)
                if p.is_absolute() and p.exists():
                    allowed_resolved.add(str(p.resolve()))
                else:
                    found = shutil.which(item)
                    if found:
                        allowed_resolved.add(str(Path(found).resolve()))

            if exe_name not in allowed_names and str(exe_path) not in allowed_resolved:
                raise BoundarySecurityError(
                    f"Executable '{raw_exe}' is not in allowed list: {allowed_executables}"
                )

            # If an explicit path (e.g. /tmp/untrusted/git) was supplied,
            # verify it resolves to one of the trusted resolved executable paths
            if "/" in raw_exe:
                resolved_target = str(exe_path.resolve())
                if resolved_target not in allowed_resolved:
                    raise BoundarySecurityError(
                        f"Executable path '{raw_exe}' resolves to untrusted location '{resolved_target}'"
                    )

        is_shell = exe_name in ("sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh")
        is_runtime = exe_name.startswith("python") or exe_name in ("node", "bun", "deno", "ruby", "perl")

        # Inspect individual argument strings for shell injection sequences
        for i, arg in enumerate(cmd):
            if not isinstance(arg, str):
                raise BoundarySecurityError(f"Command argument must be string, got: {type(arg)}")
            if "\x00" in arg:
                raise BoundarySecurityError("Null byte detected in command argument")

            is_inline_code = i > 0 and cmd[i - 1] in ("-c", "-e", "--command")

            # Inline code for programming language runtimes allows arbitrary language code (bitwise |, semicolons, etc.)
            if is_inline_code and is_runtime:
                continue

            for token in self.DANGEROUS_SHELL_TOKENS:
                if token in arg:
                    raise BoundarySecurityError(
                        f"Potentially dangerous shell metacharacter '{token}' detected in command argument: {arg}"
                    )

            # Check for command chaining semicolon, &&, || outside language code arguments
            if not is_inline_code:
                if ";" in arg or "\n" in arg or "\r" in arg or "&&" in arg or "||" in arg:
                    raise BoundarySecurityError(
                        f"Command chaining sequence or newline detected in non-code argument: {arg}"
                    )

        return list(cmd)
