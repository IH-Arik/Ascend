"""Shared API response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    """Standard API response envelope."""

    message: str
    data: Any = None
    meta: dict[str, Any] = Field(default_factory=dict)
