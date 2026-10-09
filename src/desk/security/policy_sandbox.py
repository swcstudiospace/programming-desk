"""Security, Policy & Secret Sandboxing module for Programming Desk."""

from __future__ import annotations

import os
from pathlib import Path
import re
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
        re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
        re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ]

    # Sensitive environment variable key prefixes/suffixes
    SENSITIVE_KEY_PATTERNS = [
        re.compile(r".*(_KEY|_SECRET|_TOKEN|_PASSWORD|_PASSWD|_CREDENTIAL|_AUTH)$", re.IGNORECASE),
        re.compile(r"^(API_KEY|AUTH_TOKEN|SECRET_KEY|ACCESS_TOKEN|PASSWORD)$", re.IGNORECASE),
    ]

    DANGEROUS_SHELL_TOKENS = {"&&", "||", "|", "`", "$(", "${"}

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
        """Validate that a target path resolves strictly within the configured workspace root.

        Raises BoundarySecurityError if traversal outside workspace is detected.
        """
        raw_path = Path(target)
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.workspace_root / raw_path).resolve()

        try:
            # Check if resolved path is relative to workspace_root
            resolved.relative_to(self.workspace_root)
        except ValueError as err:
            raise BoundarySecurityError(
                f"Path traversal violation: '{target}' resolves to '{resolved}', "
                f"which is outside workspace root '{self.workspace_root}'"
            ) from err

        return resolved

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

        executable = Path(cmd[0]).name
        if allowed_executables is not None and executable not in allowed_executables:
            raise BoundarySecurityError(
                f"Executable '{executable}' is not in allowed list: {allowed_executables}"
            )

        # Inspect individual argument strings for shell injection sequences
        for i, arg in enumerate(cmd):
            if not isinstance(arg, str):
                raise BoundarySecurityError(f"Command argument must be string, got: {type(arg)}")
            for token in self.DANGEROUS_SHELL_TOKENS:
                if token in arg:
                    raise BoundarySecurityError(
                        f"Potentially dangerous shell metacharacter '{token}' detected in command argument: {arg}"
                    )
            # Check for command chaining semicolon outside language code arguments (-c, -e)
            is_inline_code = i > 0 and cmd[i - 1] in ("-c", "-e", "--command")
            if not is_inline_code and (";" in arg or "\n" in arg or "\r" in arg):
                raise BoundarySecurityError(
                    f"Command chaining sequence or newline detected in non-code argument: {arg}"
                )

        return list(cmd)
