"""Workout/activity log model (DOCX section 9, Workout and Activity Logging).

Fields match the DOCX exactly: date, activity type, duration, intensity,
completion status, notes/limitations, optional session rating. The DOCX
explicitly warns not to overbuild a full fitness programming platform here -
this is logging only, no plan/program builder.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class WorkoutLog(Document):
    """A single logged workout/activity session."""

    user_id: PydanticObjectId
    activity_date: date
    activity_type: str
    custom_title: str | None = None
    duration_minutes: int
    intensity: int
    completion_status: str = "completed"
    notes: str | None = None
    reported_limitation: bool = False
    session_rating: int | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "workout_logs"
        indexes = [
            IndexModel([("user_id", 1), ("activity_date", -1)]),
        ]
