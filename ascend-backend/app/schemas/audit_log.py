"""Audit log open/close event schemas (real duration tracking, see service docstring)."""

from pydantic import BaseModel, Field


class AuditLogOpenEventRequest(BaseModel):
    """Log the start of a real record-view session."""

    target_entity_type: str = Field(min_length=1, max_length=60)
    target_entity_id: str = Field(min_length=1, max_length=60)
    summary_message: str = Field(min_length=1, max_length=280)
