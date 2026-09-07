"""Meal log schemas (see `app/models/meal_log.py`)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.meal_log import MEAL_TYPES


class MealLogCreate(BaseModel):
    """An operator (or a Nutritionist logging on their behalf) records a real meal entry."""

    meal_date: datetime
    meal_type: str = Field(pattern="^(" + "|".join(MEAL_TYPES) + ")$")
    description: str = Field(min_length=1, max_length=500)
    calories: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)


class MealLogFlagUpdate(BaseModel):
    """A Nutritionist flags a real meal entry for review (skipped meal, low protein, etc.)."""

    flagged: bool
    flag_reason: str | None = Field(default=None, max_length=300)
