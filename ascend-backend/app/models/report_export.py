"""Report export log (DOCX Data Dictionary: "Report | export_id, report_type,
date_range, generated_by, recipient_role, export_format, sensitivity_level,
export_log_status | Report control and OPSEC/CUI audit").

Written once per export - "Each report export must create an export log
entry" per DOCX section 12. `export_log_status` (completed/pending_approval/
approved/rejected) already isn't strictly immutable in practice - the
second-reviewer workflow (`admin_confirmation_service.py`) updates it after
creation - so `lifecycle_status` below follows the same real, already-
established pattern rather than introducing a new violation.

`lifecycle_status`/`title`/`flight_id` are real, additive (2026-08-10,
Leadership "Reports" pass) - not DOCX-sourced. Existing rows default to
`lifecycle_status="ready"`/`title=None`/`flight_id=None`, unaffected.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

LIFECYCLE_STATUSES = ("draft", "ready", "sent", "archived", "in_review")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ReportExport(Document):
    """A single report export event."""

    report_type: str
    date_range: str
    generated_by: PydanticObjectId
    recipient_role: str
    export_format: str
    sensitivity_level: str = "controlled"
    export_log_status: str = "completed"
    # Real Leadership-facing lifecycle, distinct from `export_log_status`
    # (the second-reviewer approval gate) - reachable via
    # `PATCH /admin/reports/export-log/{id}/lifecycle` for "sent"/
    # "archived"/"draft"; "in_review"/"ready" are also set automatically
    # alongside `export_log_status`'s "pending_approval"/"approved".
    lifecycle_status: str = "ready"
    title: str | None = None
    flight_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "report_exports"
        indexes = [
            IndexModel([("report_type", 1), ("created_at", -1)]),
        ]
