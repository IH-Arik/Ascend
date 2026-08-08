"""Check-in answer persistence model (daily, weekly, monthly cadence)."""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CheckinAnswer(Document):
    """Persist a single cadence-tagged check-in answer."""

    user_id: PydanticObjectId
    cadence: str = "daily"
    checkin_date: date
    question_id: int
    question_code: str
    question_text: str
    readiness_component: str
    h2f_component_tag: str
    selected_value: str
    follow_up_answer: str | None = None
    raw_score_1_to_4: int | None = None
    numeric_score_100: float | None = None
    scoreable: bool = False
    flag_only: bool = False
    routing_triggered: bool = False
    provider_route: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "checkin_answers"
        indexes = [
            IndexModel(
                [
                    ("user_id", 1),
                    ("cadence", 1),
                    ("checkin_date", 1),
                    ("question_id", 1),
                ],
                unique=True,
            ),
        ]
