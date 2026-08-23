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


class ScheduledExportUpdate(BaseModel):
    """Admin edits a real recurring export schedule - only the fields given are changed.

    Added 2026-08-23 to close a real gap: the Exports "Schedules" table's
    Edit action had no backing beyond pause/resume - `report_type` is
    deliberately not editable here (matches the design's own Edit wizard,
    which never re-asks for it either). Changing `cadence` recomputes
    `next_run_at` from now, same as at creation.
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    cadence: str | None = None
    export_format: str | None = None
    recipient_role: str | None = Field(default=None, min_length=1, max_length=80)
    status: str | None = None  # "active" | "paused"
