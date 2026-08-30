"""SCS/PT-IM group training-session schedule.

Not DOCX-sourced (a Figma SCS dashboard showed "Today's PT line-up" and
"Upcoming PT sessions" widgets - time/group/focus/lead - with no backend
concept anywhere). Real new scope, explicit user go-ahead (2026-08-25):
a real, scheduled group session a provider leads, distinct from an
individual operator's own workout log (`app/models/workout_log.py`) or
their reconditioning plan - this is the provider's own class schedule.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class PTSession(Document):
    """A single scheduled group training session."""

    lead_provider_id: PydanticObjectId
    lead_provider_role: str
    session_date: date
    start_time: str
    group_label: str
    focus: str
    capacity: int
    # Real, added 2026-08-25 - the frontend's "Upcoming PT sessions" widget
    # implied an enrollment/fill percentage against capacity with no real
    # attendee data anywhere; this is the real list backing it.
    attendee_user_ids: list[PydanticObjectId] = Field(default_factory=list)
    unit_id: str | None = None
    status: str = "scheduled"
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "pt_sessions"
        indexes = [
            IndexModel([("lead_provider_id", 1), ("session_date", 1)]),
        ]
