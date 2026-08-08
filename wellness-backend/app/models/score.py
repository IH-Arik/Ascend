"""Score document models."""

from datetime import datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class DimensionScore(BaseModel):
    """Dimension scores normalized to a 0-100 range."""

    PC: float = Field(ge=0, le=100)
    MR: float = Field(ge=0, le=100)
    MC: float = Field(ge=0, le=100)
    PA: float = Field(ge=0, le=100)
    RC: float = Field(ge=0, le=100)


class Score(Document):
    """Calculated score for a submitted assessment."""

    user_id: PydanticObjectId
    checkin_id: PydanticObjectId
    dimension_scores: DimensionScore
    overall_score: float
    condition: Literal["Optimal", "Stable", "Strained", "High Risk", "Critical"]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "scores"
