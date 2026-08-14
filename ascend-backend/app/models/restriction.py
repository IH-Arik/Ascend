"""Duty/training restriction model, gated by phase-based signoff release.

Not DOCX-sourced - "restriction" only appears in the DOCX as a loose field/
tag ("restriction flags"), never a discrete gated object; "phase" as a
progression concept doesn't appear in the DOCX at all. Built as real
net-new operational tooling per explicit user go-ahead, same category as
the 2026-08-13 severity/days-out and ROM/timeline additions.

Release requires two real, checked conditions - the plan has actually
reached `required_phase` (not just the field flipping momentarily) and an
explicit provider signoff (`RestrictionService.release_restriction`) -
never an automatic release the instant a phase field changes.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Restriction(Document):
    """A single real duty/training restriction for one operator."""

    user_id: PydanticObjectId
    description: str
    required_phase: str
    status: str = "active"
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)
    released_by: PydanticObjectId | None = None
    released_at: datetime | None = None

    class Settings:
        """Beanie collection settings."""

        name = "restrictions"
        indexes = [
            IndexModel([("user_id", 1), ("status", 1)]),
        ]
