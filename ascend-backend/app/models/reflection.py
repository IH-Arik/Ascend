"""Spiritual reflection entry model (Chaplain / Purpose pathway).

Not DOCX-sourced as a named data model, but not groundless either: DOCX's
recommendation-engine examples explicitly name "reflection... action" as a
real suggested action for low purpose/support scores (section 4), and the
Chaplain dashboard mock showed a real, opt-in, theme-tagged journal
concept distinct from `SpecialistNote` in one important way - this is
authored by the operator themselves, about themselves, not a specialist's
note about them. Real new scope, explicit user go-ahead.

Deliberately NOT the "chaplain record" DOCX explicitly says this app must
never become (section 15: "should not become a medical record, behavioral
health record, chaplain record..."). A chaplain record would be the
chaplain's own clinical/pastoral documentation about a person - this is
the opposite: the person's own private words, visible to the chaplain
only because they opted in, and gone from view the moment they opt out.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

REFLECTION_THEMES = ("Purpose", "Values", "Transition", "Gratitude", "Grief", "Other")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Reflection(Document):
    """A single, private, operator-authored spiritual reflection entry."""

    user_id: PydanticObjectId
    theme: str
    body: str
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "reflections"
        indexes = [
            IndexModel([("user_id", 1), ("created_at", -1)]),
        ]
