"""Schemas for the second-reviewer confirmation queue (see `app/models/pending_confirmation.py`)."""

from pydantic import BaseModel, Field


class ConfirmationRejectRequest(BaseModel):
    """Reviewer rejects a pending confirmation."""

    reason: str | None = Field(default=None, max_length=500)
