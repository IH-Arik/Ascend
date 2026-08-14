"""Specialist note model (DOCX Section 17, "Specialist Notes and Boundaries").

DOCX: "If specialist notes are added, keep them simple and role-specific:
date, specialist type, user concern, action assigned, follow-up needed, and
status... Specialist notes should support coaching continuity, not formal
clinical or privileged documentation."

Real and DOCX-sourced, but deliberately narrower than the SOAP/pastoral
clinical-documentation concepts explicitly rejected elsewhere this session
(the same DOCX says the app "should not become a medical record, behavioral
health record, chaplain record... or official clinical documentation") -
this is a single, generic model shared across every specialist pathway
(Mental Performance/Chaplain/Nutritionist), not a role-specific clinical
note.

Visibility is pathway-siloed (a note is visible only to the specialist who
wrote it, plus Admin) - not DOCX-specified, but matches the same
minimum-necessary access pattern already enforced everywhere else in this
codebase (e.g. `VIEW_ALLOWED_ROLES` on medical records).
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

STATUSES = ("open", "closed")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SpecialistNote(Document):
    """A single real, lightweight specialist note about one operator."""

    user_id: PydanticObjectId
    specialist_id: PydanticObjectId
    specialist_type: str
    note_date: date = Field(default_factory=date.today)
    user_concern: str
    action_assigned: str | None = None
    follow_up_needed: bool = False
    status: str = "open"
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "specialist_notes"
        indexes = [
            IndexModel([("user_id", 1), ("specialist_type", 1)]),
        ]
