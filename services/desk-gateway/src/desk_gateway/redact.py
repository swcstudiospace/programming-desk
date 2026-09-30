"""Redaction applied to everything that leaves the gateway for a log, an event or a memory bank.

The shapes mirror agent-substrate's redact() D-04 list so the two planes agree on what a secret
looks like. Placeholders and `$VAR` references are kept; real values are replaced.
"""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[abpr]-[0-9A-Za-z-]{10,}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{20,}\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("do-token", re.compile(r"\bdop_v1_[a-f0-9]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")),
    ("stripe-key", re.compile(r"\b[prs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("url-credentials", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")),
    ("private-block", re.compile(r"<private>[\s\S]*?</private>")),
    (
        "assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|passphrase|password|passwd|authkey|auth_key)"
            r"(\s*[:=]\s*)(['\"]?)(?![$<{])([^\s'\"]{8,})(['\"]?)"
        ),
    ),
]

REDACTED = "<redacted>"


def redact_text(text: str) -> str:
    out = text
    for name, pattern in _PATTERNS:
        if name == "url-credentials":
            out = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}@", out)
        elif name == "assignment":
            out = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}{m.group(5)}", out)
        else:
            out = pattern.sub(REDACTED, out)
    return out


def contains_secret(text: str) -> bool:
    return redact_text(text) != text


def redact_value(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(k): redact_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, depth + 1) for v in value]
    return value
