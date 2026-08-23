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

`recipient_role`/`sensitivity_level` added 2026-08-23, closing a gap found
re-checking the schedule wizard against the real `ReportExport` data
dictionary row (DOCX: "Report | export_id, report_type, date_range,
generated_by, recipient_role, export_format, sensitivity_level,
export_log_status"). `recipient_role` is real, admin-supplied at creation
(unlike on-demand `ReportExport`, which only ever defaults it to the
generating admin's own role). `sensitivity_level` is computed once at
creation from `REPORT_SENSITIVITY` (`app/services/report_export_service.py`)
- the same real aggregate/controlled/restricted gating already used
everywhere else - not the screenshot's free-text "Scope" input, which
would have duplicated that gating with a second, driftable copy of it.
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
    recipient_role: str
    sensitivity_level: str = "controlled"
    status: str = "active"  # "active" | "paused"
    next_run_at: datetime
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "scheduled_exports"
        indexes = [IndexModel([("status", 1), ("next_run_at", 1)])]
