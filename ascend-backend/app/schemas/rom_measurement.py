"""Range-of-motion measurement schema (net-new, not DOCX-sourced - see model docstring)."""

from datetime import date

from pydantic import BaseModel, Field

from app.models.rom_measurement import MOVEMENTS


class RomMeasurementCreate(BaseModel):
    """PT/IM, SCS, or Admin records a real ROM measurement for an operator."""

    movement: str = Field(pattern="^(" + "|".join(MOVEMENTS) + ")$")
    value_degrees: float = Field(ge=0, le=180)
    measured_date: date
    note: str | None = Field(default=None, max_length=500)
