"""Admin-configurable OPS scoring schemas."""

from datetime import date

from pydantic import BaseModel, Field, model_validator


class ScoringConfigCreate(BaseModel):
    """Admin creates a new versioned, effective-dated scoring configuration."""

    effective_date: date
    physical_weight: float = Field(ge=0, le=1)
    sleep_weight: float = Field(ge=0, le=1)
    mental_weight: float = Field(ge=0, le=1)
    nutritional_weight: float = Field(ge=0, le=1)
    spiritual_weight: float = Field(ge=0, le=1)
    band_thresholds: dict[str, float] | None = None

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "ScoringConfigCreate":
        """Enforce the DOCX's weighted-average model - weights must sum to 1.0."""
        total = (
            self.physical_weight
            + self.sleep_weight
            + self.mental_weight
            + self.nutritional_weight
            + self.spiritual_weight
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Component weights must sum to 1.0 (got {total:.3f}).")
        return self


class ScoringConfigResponse(BaseModel):
    """A single scoring configuration version."""

    id: str
    effective_date: str
    physical_weight: float
    sleep_weight: float
    mental_weight: float
    nutritional_weight: float
    spiritual_weight: float
    band_thresholds: dict[str, float]
    is_active: bool
    created_at: str
