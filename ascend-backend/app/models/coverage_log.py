"""Provider coverage-hours log (DOCX: "Track SCS coverage hours and missed
coverage flags against 2,080 annual hours and 95% coverage evidence. Track
PT/IM coverage hours and missed coverage flags against 512 annual hours and
95% coverage evidence. Track RSD weekend support coverage separately.").

Feeds the quarterly PRS/QCP Support Report.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CoverageLog(Document):
    """A single logged block of provider coverage hours."""

    provider_id: PydanticObjectId
    role: str
    hours: float
    coverage_date: date = Field(default_factory=date.today)
    is_weekend_rsd: bool = False
    notes: str | None = None
    # Real, additive (2026-08-10, Leadership Aggregate pass) - "scheduled
    # hours" is a genuinely new concept, not tracked anywhere before this.
    # `None` on every entry logged before this pass, unchanged - not
    # retroactively fabricated. Only meaningful when set and `hours <
    # scheduled_hours`.
    scheduled_hours: float | None = None
    missed_reason: str | None = None
    logged_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "coverage_logs"
        indexes = [
            IndexModel([("provider_id", 1), ("coverage_date", -1)]),
        ]
