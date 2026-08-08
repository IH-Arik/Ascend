"""Score request and response schemas."""

from datetime import datetime

from pydantic import BaseModel


class DimensionScoreRead(BaseModel):
    """Serialized dimension score payload."""

    PC: float
    MR: float
    MC: float
    PA: float
    RC: float


class ScoreRead(BaseModel):
    """Serialized score response."""

    id: str
    user_id: str
    checkin_id: str
    dimension_scores: DimensionScoreRead
    overall_score: float
    condition: str
    created_at: datetime


class ScoreHistoryResponse(BaseModel):
    """Response schema for score history queries."""

    items: list[ScoreRead]
