"""Specialist note schema (DOCX Section 17 - see model docstring)."""

from pydantic import BaseModel, Field

from app.models.specialist_note import STATUSES


class SpecialistNoteCreate(BaseModel):
    """A specialist records a real, lightweight note about an operator."""

    user_concern: str = Field(min_length=1, max_length=1000)
    action_assigned: str | None = Field(default=None, max_length=500)
    follow_up_needed: bool = False


class SpecialistNoteStatusUpdate(BaseModel):
    """The authoring specialist (or Admin) updates a note's status."""

    status: str = Field(pattern="^(" + "|".join(STATUSES) + ")$")
