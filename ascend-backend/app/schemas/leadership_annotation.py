"""Leadership "Annotated events" editorial timeline schemas."""

from datetime import date

from pydantic import BaseModel, Field


class LeadershipAnnotationCreate(BaseModel):
    """Admin/Leadership authors a real editorial note tied to a date."""

    title: str = Field(min_length=1, max_length=120)
    narrative: str = Field(min_length=1, max_length=1000)
    event_date: date
    unit_id: str | None = None


class LeadershipAnnotationResponse(BaseModel):
    """A single editorial annotation."""

    id: str
    title: str
    narrative: str
    event_date: str
    unit_id: str | None
    created_by_name: str | None
    created_at: str
