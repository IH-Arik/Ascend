"""Org unit hierarchy (Wing / Detachment / Flight).

Not DOCX-sourced (a Figma "Scope matrix" screen showed a real-looking
Wing/Detachment/Flight structure with no prior backend equivalent - DOCX
line 191 only says an Admin can "assign roles, coaches, specialists, teams,
units, reporting groups", with no hierarchy). This is additive, real,
admin-created structure - no fake seed unit names.

`User.unit_id` stays a free-text string, unchanged by this model - when it
happens to match a real `OrgUnit.id` the hierarchy resolves; existing
free-text values from before this pass simply don't resolve to one, same
as today.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


UNIT_TYPES = ("wing", "detachment", "flight")


class OrgUnit(Document):
    """A single node in the org unit hierarchy."""

    name: str
    unit_type: str  # "wing" | "detachment" | "flight"
    parent_id: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "org_units"
        indexes = [IndexModel([("parent_id", 1)])]
