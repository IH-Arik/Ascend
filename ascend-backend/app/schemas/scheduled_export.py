"""Scheduled/recurring export schemas (see `app/models/scheduled_export.py`)."""

from pydantic import BaseModel, Field


class ScheduledExportCreate(BaseModel):
    """Admin creates a real recurring export schedule.

    `recipient_role` is real DOCX Data Dictionary field on the export it
    will eventually create (`ReportExport.recipient_role`) - required here
    so the recurring schedule can supply a real one instead of the
    on-demand default (the generating admin's own role).
    """

    name: str = Field(min_length=1, max_length=120)
    report_type: str
    export_format: str = "csv"
    cadence: str
    recipient_role: str = Field(min_length=1, max_length=80)


class ScheduledExportStatusUpdate(BaseModel):
    """Admin pauses or resumes a real schedule."""

    status: str  # "active" | "paused"
