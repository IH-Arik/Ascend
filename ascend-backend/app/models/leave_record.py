"""Provider leave/TDY tracking.

Not DOCX-sourced (a Figma SCS dashboard showed a "Leave overlap - next 30
days" widget with no backend concept anywhere). Real new scope, explicit
user go-ahead (2026-08-25): a real logged date-range a provider is
unavailable, used to compute genuine overlaps - never a fabricated
severity label, just the real overlapping date ranges.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class LeaveRecord(Document):
    """A single logged block of provider leave/TDY/training/medical absence."""

    user_id: PydanticObjectId
    leave_type: str
    start_date: date
    end_date: date
    note: str | None = None
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "leave_records"
        indexes = [
            IndexModel([("user_id", 1), ("start_date", 1)]),
        ]
