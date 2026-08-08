"""Reconditioning plan model (DOCX: "Joint PT/IM-SCS Coordination" - reconditioning
assignment/monitoring; referenced on the Fly Away Kit "Rehab status" card).

One active plan per user at a time. PT/IM and SCS both author/update it per
the DOCX's joint-coordination model for reconditioning; Admin can as well.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ReconditioningPlan(Document):
    """A single operator's active reconditioning/rehab status."""

    user_id: PydanticObjectId
    phase: str = "active"
    phase_started_on: date = Field(default_factory=date.today)
    sessions_completed: int = 0
    sessions_total: int = 0
    cadence_note: str | None = None
    injury_flags: list[str] = Field(default_factory=list)
    ptim_clearance_status: str = "pending_review"
    next_review_date: date | None = None
    updated_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "reconditioning_plans"
        indexes = [
            IndexModel([("user_id", 1)], unique=True),
        ]
