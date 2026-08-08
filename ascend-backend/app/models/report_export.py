"""Report export log (DOCX Data Dictionary: "Report | export_id, report_type,
date_range, generated_by, recipient_role, export_format, sensitivity_level,
export_log_status | Report control and OPSEC/CUI audit").

Written once per export, never modified - "Each report export must create
an export log entry" per DOCX section 12.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


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
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "report_exports"
        indexes = [
            IndexModel([("report_type", 1), ("created_at", -1)]),
        ]
