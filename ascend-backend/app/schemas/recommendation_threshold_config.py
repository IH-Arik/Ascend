"""Admin-configurable recommendation trigger threshold schemas."""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class RecommendationThresholdConfigCreate(BaseModel):
    """Admin creates a new versioned, effective-dated threshold configuration."""

    effective_date: date
    high_threshold: float = Field(ge=0, le=100)
    moderate_threshold: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _high_below_moderate(self) -> "RecommendationThresholdConfigCreate":
        """Matches the DOCX trigger model - high severity is a stricter (lower) cutoff than moderate."""
        if self.high_threshold >= self.moderate_threshold:
            raise ValueError("high_threshold must be lower than moderate_threshold.")
        return self


class RecommendationThresholdConfigResponse(BaseModel):
    """A single recommendation threshold configuration version."""

    id: str
    effective_date: str
    high_threshold: float
    moderate_threshold: float
    is_active: bool
    created_at: str
