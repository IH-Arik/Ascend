"""Duty/training restriction schema (net-new, not DOCX-sourced - see model docstring)."""

from pydantic import BaseModel, Field

from app.schemas.reconditioning import PHASES


class RestrictionCreate(BaseModel):
    """PT/IM, SCS, or Admin adds a real duty/training restriction for an operator."""

    description: str = Field(min_length=1, max_length=300)
    required_phase: str = Field(pattern="^(" + "|".join(PHASES) + ")$")
