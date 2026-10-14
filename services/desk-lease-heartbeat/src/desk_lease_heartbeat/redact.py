from __future__ import annotations

import re
from urllib.parse import urlparse

_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


def redact(text: str, secrets: list[str]) -> str:
    """Replace configured secrets and any Bearer token. lease_id is a secret here."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "[redacted]")
    return _BEARER.sub("Bearer [redacted]", out)


def public_url(url: str) -> str:
    """Scheme, host, port and path. Userinfo and query stay out of the journal."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    return f"{parsed.scheme}://{host}{path}"
