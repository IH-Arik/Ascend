"""AI insight persistence model."""

from datetime import datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class AIInsight(Document):
    """Persist AI-ready summaries and generated insight logs."""

    user_id: PydanticObjectId
    trace_id: str
    insight_type: str
    source_flow: str
    model_name: str
    status: str = "stub_ready"
    title: str
    summary: str
    payload: dict[str, Any]
    signals: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "ai_insights"
        indexes = [
            IndexModel([("user_id", 1), ("insight_type", 1), ("created_at", -1)]),
            IndexModel([("trace_id", 1)]),
        ]
