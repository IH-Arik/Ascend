"""Macro target schemas (see `app/models/macro_target.py`)."""

from pydantic import BaseModel, Field, model_validator


class MacroTargetSet(BaseModel):
    """A Nutritionist sets an operator's real carbs/protein/fat percentage split target."""

    title: str = Field(min_length=1, max_length=120)
    carbs_pct: float = Field(ge=0, le=100)
    protein_pct: float = Field(ge=0, le=100)
    fat_pct: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _percentages_sum_to_100(self) -> "MacroTargetSet":
        total = self.carbs_pct + self.protein_pct + self.fat_pct
        if abs(total - 100) > 0.5:
            raise ValueError(f"Macro percentages must sum to 100 (got {total}).")
        return self
