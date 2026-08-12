"""Provider coverage-hours log schemas."""

from datetime import date

from pydantic import BaseModel, Field


class CoverageLogCreate(BaseModel):
    """Log a block of provider coverage hours."""

    provider_id: str
    role: str = Field(pattern="^(SCS|PT/IM)$")
    hours: float = Field(gt=0, le=24)
    coverage_date: date
    is_weekend_rsd: bool = False
    notes: str | None = Field(default=None, max_length=280)
    scheduled_hours: float | None = Field(default=None, gt=0, le=24)
    missed_reason: str | None = Field(default=None, max_length=120)


class CoverageLogResponse(BaseModel):
    """A single coverage-hours log entry."""

    id: str
    provider_id: str
    provider_name: str | None
    role: str
    hours: float
    coverage_date: str
    is_weekend_rsd: bool
    notes: str | None
    scheduled_hours: float | None
    missed_reason: str | None
