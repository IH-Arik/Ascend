"""Operator assessment tracking model (DOCX section 8.1)."""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Assessment(Document):
    """A single initial or annual-follow-up operator assessment for one user."""

    user_id: PydanticObjectId
    assessment_type: str = "initial"
    status: str = "not_started"
    due_date: date | None = None
    scheduled_date: date | None = None
    completed_date: date | None = None
    result_band: str | None = None
    physical_result_summary: str | None = None
    mental_result_summary: str | None = None
    feedback_session_status: str = "pending"
    created_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "assessments"
        indexes = [
            IndexModel([("user_id", 1), ("assessment_type", 1)]),
        ]
