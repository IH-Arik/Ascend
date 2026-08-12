"""Real scheduled/recurring exports.

Not DOCX-sourced (a Figma "Exports" screen showed recurring exports with no
prior backend equivalent - only on-demand exports existed). Real, admin-
created, executed by `app/core/scheduler.py`'s `run_scheduled_exports` job,
which routes through the exact same real second-reviewer gate an on-demand
restricted export uses - a scheduled restricted export never bypasses it.

Deliberately does not implement the screenshot's "a scope change pauses
any non-compliant schedule" - there is no real trigger condition in this
system that defines "non-compliant" for a schedule, so nothing is invented
to auto-pause one. Pause/resume stays a real, explicit admin action.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

CADENCES = ("weekly", "monthly", "quarterly", "annual")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ScheduledExport(Document):
    """A real recurring export definition."""

    name: str
    report_type: str
    export_format: str = "csv"
    cadence: str  # "weekly" | "monthly" | "quarterly" | "annual"
    status: str = "active"  # "active" | "paused"
    next_run_at: datetime
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "scheduled_exports"
        indexes = [IndexModel([("status", 1), ("next_run_at", 1)])]
