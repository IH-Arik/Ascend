"""Specialist note schema (DOCX Section 17 - see model docstring)."""

from pydantic import BaseModel, Field

from app.models.specialist_note import NOTE_TYPES, STATUSES

# Real, matches the MP dashboard mock's own "Reason category" picker
# (Records tab) verbatim.
REVEAL_REASON_CATEGORIES = ("Routine", "Escalation", "Follow-up", "Audit", "Other")


class SpecialistNoteCreate(BaseModel):
    """A specialist records a real, lightweight note about an operator."""

    user_concern: str = Field(min_length=1, max_length=1000)
    action_assigned: str | None = Field(default=None, max_length=500)
    follow_up_needed: bool = False
    note_type: str = Field(default="follow_up", pattern="^(" + "|".join(NOTE_TYPES) + ")$")
    escalated: bool = False


class SpecialistNoteStatusUpdate(BaseModel):
    """The authoring specialist (or Admin) updates a note's status."""

    status: str = Field(pattern="^(" + "|".join(STATUSES) + ")$")


class SpecialistNoteRevealRequest(BaseModel):
    """A viewer who isn't the authoring specialist requests a one-time reveal."""

    field_name: str
    reason: str = Field(min_length=10, max_length=280)
    reason_category: str = Field(pattern="^(" + "|".join(REVEAL_REASON_CATEGORIES) + ")$")
