"""Intervention memory document model — persists per-user recommendation state."""

from datetime import date, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field


CompletionStatus = Literal["completed", "partial", "not_completed", "no_response"]


class InterventionMemory(Document):
    """Persisted state that drives anti-repeat and escalation logic."""

    user_id: PydanticObjectId

    # Last 3 recommendation texts issued to this user (newest first)
    last_3_recommendations: list[str] = Field(default_factory=list)

    # Category of the most recent recommendation
    last_category: str | None = None

    # Completion responses for the last 3 recommendations (newest first)
    last_3_completions: list[CompletionStatus] = Field(default_factory=list)

    # Per-category current escalation level (1–3)
    current_levels: dict[str, int] = Field(default_factory=dict)

    # Date the last recommendation was issued (enforces max-1/day rule)
    last_issued_date: date | None = None

    # Cached recommendation text for today (returned directly on same-day calls)
    cached_category: str | None = None
    cached_recommendation: str | None = None
    cached_reason_line: str | None = None

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "intervention_memories"
