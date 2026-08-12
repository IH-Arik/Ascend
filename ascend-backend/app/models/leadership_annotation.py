"""Leadership "Annotated events" editorial timeline (2026-08-10).

Not DOCX-sourced (a Figma Leadership "Trends" screen triggered this - no
"annotation"/"editorial"/"event log" concept exists in the DOCX). This is
genuinely different from every other Leadership-surface piece built so
far: real, human-authored narrative content (a title + free-text summary
tied to a real date), not a computed aggregate - nothing here is derived
from tracked data, it is manually written by an Admin/Leadership user to
give real material context to a trend period (e.g. "a training-load change
happened this month, here's why").
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class LeadershipAnnotation(Document):
    """A single admin/leadership-authored editorial note tied to a real date."""

    title: str
    narrative: str
    event_date: date
    unit_id: str | None = None
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "leadership_annotations"
        indexes = [
            IndexModel([("event_date", -1)]),
        ]
