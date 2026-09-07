"""PT/IM quarterly recommendation schemas."""

from datetime import date

from pydantic import BaseModel, Field


class PtimRecommendationCreateRequest(BaseModel):
    """PT/IM drafts a new quarter-scoped recommendation routed to SCS."""

    fiscal_year: int = Field(ge=2020, le=2100)
    quarter: int = Field(ge=1, le=4)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=1000)
    subject: str = Field(min_length=1, max_length=160)
    owners: list[str] = Field(default_factory=list, max_length=4)
    due_date: date | None = None
