"""Equipment and Supply Gap Tracker (DOCX section 8.7).

"Track equipment gaps, supply needs, priority, requested by, date
identified, status, and whether included in a report."
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class EquipmentGap(Document):
    """A single tracked equipment/supply shortfall."""

    item: str
    supply_need: str
    priority: str = "medium"
    requested_by: PydanticObjectId
    date_identified: date = Field(default_factory=date.today)
    status: str = "open"
    included_in_report: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "equipment_gaps"
        indexes = [
            IndexModel([("status", 1), ("date_identified", -1)]),
        ]
