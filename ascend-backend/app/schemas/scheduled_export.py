"""Scheduled/recurring export schemas (see `app/models/scheduled_export.py`)."""

from pydantic import BaseModel, Field


class ScheduledExportCreate(BaseModel):
    """Admin creates a real recurring export schedule."""

    name: str = Field(min_length=1, max_length=120)
    report_type: str
    export_format: str = "csv"
    cadence: str


class ScheduledExportStatusUpdate(BaseModel):
    """Admin pauses or resumes a real schedule."""

    status: str  # "active" | "paused"
