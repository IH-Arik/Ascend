"""Real, append-only reconditioning-plan event log.

Not DOCX-sourced - the DOCX's "timeline" mentions are always compliance
due-dates, never a chronological injury/recovery event view. Built as real
net-new operational tooling per explicit user decision.

A "treatment-plan timeline" only means something if it's a genuine record
of things that actually happened, so this is never manually authored -
`ReconditioningService.upsert_for_user` writes one entry per real field
that actually changed value, and `RomMeasurementService.add_measurement`
writes one when a measurement is actually added. Same append-only,
never-edited shape as the existing `MedicalRecordAccessEvent`.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

EVENT_TYPES = (
    "plan_created",
    "phase_changed",
    "clearance_changed",
    "severity_changed",
    "rom_measurement_added",
    "restriction_added",
    "restriction_released",
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ReconditioningEvent(Document):
    """A single real, immutable event in one operator's reconditioning history."""

    user_id: PydanticObjectId
    event_type: str
    detail: str
    recorded_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "reconditioning_events"
        indexes = [
            IndexModel([("user_id", 1), ("created_at", 1)]),
        ]
