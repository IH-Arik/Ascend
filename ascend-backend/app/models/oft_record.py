"""OFT (Operational Fitness Test) tracking model (DOCX section 8.2)."""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class OFTRecord(Document):
    """A single scheduled or completed OFT test event for one user."""

    user_id: PydanticObjectId
    test_date: date
    status: str = "scheduled"
    pass_fail: str | None = None
    items_passed: int | None = None
    items_total: int | None = None
    entered_into_government_system: bool = False
    notes: str | None = None
    recorded_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "oft_records"
        indexes = [
            IndexModel([("user_id", 1), ("test_date", -1)]),
        ]
