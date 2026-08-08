"""Shared response helpers."""

from typing import Any

from app.common.schemas.response import ApiResponse


def success_response(
    message: str,
    data: Any = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a consistent successful API response as a plain, JSON-safe dict.

    Every route declares `-> dict[str, Any]`, so this must return a dict, not
    an ApiResponse instance - returning the model itself fails FastAPI's
    response validation on every single route that uses this helper.
    """
    return ApiResponse(message=message, data=data, meta=meta or {}).model_dump(mode="json")
