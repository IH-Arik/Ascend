"""PT/IM quarterly recommendation model.

Net-new (2026-09-07, explicit user go-ahead - not DOCX-sourced). A PT/IM-
authored recommendation tied to one real fiscal quarter's injury data
(e.g. "3 of 5 lumbar injuries share a load-bearing onset pattern") and
routed to SCS for joint action - distinct from `CoordinationItem` (a
single-operator training-decision handoff) and `Recommendation` (the
per-operator readiness-driven recommendation engine's own output). This is
a quarterly, cohort-level recommendation, always human-authored.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

RECOMMENDATION_STATUSES = ("open", "done")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class PtimRecommendation(Document):
    """A single PT/IM-authored, quarter-scoped recommendation routed to SCS."""

    fiscal_year: int
    quarter: int
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=1000)
    # Free-text tag of who/what this recommendation targets, shown as the
    # card's subtitle (e.g. "Reyes, Cho, Hayes" or "Flight A - rate 5.4") -
    # deliberately not a structured operator-id list, since the underlying
    # data (which real injuries motivated this) already lives on the real
    # quarterly report the author is looking at while drafting.
    subject: str = Field(min_length=1, max_length=160)
    owners: list[str] = Field(default_factory=list)
    due_date: date | None = None
    status: str = "open"
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "ptim_recommendations"
        indexes = [
            IndexModel([("fiscal_year", 1), ("quarter", 1)]),
        ]
