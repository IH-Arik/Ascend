"""Utilization Event tracking (DOCX Data Dictionary: "Utilization Event |
event_id, event_type, opportunity_offered, actual_use, date, staff_lead,
attendance_count, notes | Training, education, feedback utilization").

Feeds the quarterly Utilization Report.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class UtilizationEvent(Document):
    """A single training/education/feedback utilization event."""

    event_type: str
    opportunity_offered: str
    actual_use: bool = False
    event_date: date = Field(default_factory=date.today)
    staff_lead_id: PydanticObjectId
    attendance_count: int = 0
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "utilization_events"
        indexes = [
            IndexModel([("event_date", -1)]),
        ]
