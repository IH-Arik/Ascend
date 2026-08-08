"""Utilization Event schemas."""

from datetime import date

from pydantic import BaseModel, Field


class UtilizationEventCreate(BaseModel):
    """Log a training/education/feedback utilization event."""

    event_type: str = Field(min_length=1, max_length=80)
    opportunity_offered: str = Field(min_length=1, max_length=200)
    actual_use: bool = False
    event_date: date
    attendance_count: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class UtilizationEventResponse(BaseModel):
    """A single utilization event."""

    id: str
    event_type: str
    opportunity_offered: str
    actual_use: bool
    event_date: str
    staff_lead_name: str | None
    attendance_count: int
    notes: str | None
