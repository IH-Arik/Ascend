"""Range-of-motion measurement model.

Not DOCX-sourced - "ROM"/"range of motion" never appears in the DOCX (all
raw hits are substrings inside words like "from"/"program"). Built as real
net-new operational tracking per explicit user decision, same category as
the 2026-08-13 severity/days-out addition to `ReconditioningPlan`.

`straight_leg_raise`/flexion movement values mirror the ascend-admin
frontend mock's own filter vocabulary (SLR/Flex) - a reasonable real
vocabulary choice, not a fabricated data claim.
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

MOVEMENTS = (
    "shoulder_flexion",
    "shoulder_abduction",
    "knee_flexion",
    "hip_flexion",
    "straight_leg_raise",
    "other",
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RomMeasurement(Document):
    """A single real range-of-motion measurement for one operator."""

    user_id: PydanticObjectId
    movement: str
    value_degrees: float
    measured_date: date
    measured_by: PydanticObjectId
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "rom_measurements"
        indexes = [
            IndexModel([("user_id", 1), ("measured_date", 1)]),
        ]
