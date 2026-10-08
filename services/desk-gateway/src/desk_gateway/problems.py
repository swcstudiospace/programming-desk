"""RFC-7807 Problem Details representation and helpers for HTTP and upstream errors."""

from __future__ import annotations

from typing import Any
from starlette.responses import JSONResponse


def problem_details(
    status: int,
    title: str,
    detail: str,
    error_code: str,
    *,
    instance: str | None = None,
    error_type: str = "about:blank",
    **extra: Any,
) -> dict[str, Any]:
    """Build an RFC-7807 problem details dictionary."""
    problem = {
        "type": error_type,
        "title": title,
        "status": status,
        "detail": detail,
        "error": error_code,
        **extra,
    }
    if instance:
        problem["instance"] = instance
    return problem


def problem_response(
    status: int,
    title: str,
    detail: str,
    error_code: str,
    *,
    instance: str | None = None,
    error_type: str = "about:blank",
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build a JSONResponse using application/problem+json media type."""
    data = problem_details(
        status=status,
        title=title,
        detail=detail,
        error_code=error_code,
        instance=instance,
        error_type=error_type,
        **extra,
    )
    resp_headers = {"Content-Type": "application/problem+json", "Cache-Control": "no-store"}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(data, status_code=status, headers=resp_headers)
