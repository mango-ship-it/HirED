"""Shared error response shape (API_CONTRACT.md).

Every endpoint returns the same error envelope on failure:
    { "error": "<human-readable message>", "code": "<machine code>" }
so the frontend can branch on `code` and show `error` to the user.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


class ErrorCode:
    """Machine-readable error codes shared with the frontend (API_CONTRACT.md)."""

    INVALID_INPUT = "INVALID_INPUT"
    PARSE_FAILED = "PARSE_FAILED"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    SERVER_ERROR = "SERVER_ERROR"
    NOT_FOUND = "NOT_FOUND"


def error_response(message: str, code: str, status_code: int) -> JSONResponse:
    """Build the standard `{error, code}` JSON response at the given HTTP status."""
    return JSONResponse(status_code=status_code, content={"error": message, "code": code})
