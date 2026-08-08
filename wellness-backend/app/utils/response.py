"""Response formatting helpers."""

from typing import Any


def success_response(message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a standardized success response payload."""
    return {
        "success": True,
        "message": message,
        "data": data or {},
    }


def error_response(message: str, errors: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a standardized error response payload."""
    payload: dict[str, Any] = {
        "success": False,
        "message": message,
    }
    if errors:
        payload["errors"] = errors
    return payload
