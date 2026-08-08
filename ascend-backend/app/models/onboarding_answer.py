"""Onboarding answer persistence model."""

from datetime import datetime, timezone
from typing import Any

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class OnboardingAnswer(Document):
    """Persist a single onboarding answer or follow-up response."""

    user_id: PydanticObjectId
    question_id: int
    question_code: str
    question_text: str
    category: str
    readiness_component: str
    answer_type: str
    selected_value: str | None = None
    selected_values: list[str] | None = None
    free_text: str | None = None
    follow_up_answer: str | list[str] | dict[str, Any] | None = None
    raw_score_1_to_4: int | None = None
    numeric_score_100: float | None = None
    scoreable: bool = False
    reverse_scored: bool = False
    flag_only: bool = False
    routing_triggered: bool = False
    provider_route: str | None = None
    provider_note: str | None = None
    ai_tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "onboarding_answers"
        indexes = [
            IndexModel([("user_id", 1), ("question_id", 1)], unique=True),
        ]
