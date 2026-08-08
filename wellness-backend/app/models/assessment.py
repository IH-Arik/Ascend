"""Assessment document models."""

from datetime import datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field


class Answer(BaseModel):
    """Single normalized answer submitted within an assessment."""

    question_id: PydanticObjectId | str
    question_text: str | None = None
    answer_text: str
    numeric_value: float
    driver: Literal["PC", "MR", "MC", "PA", "RC"]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class CheckIn(Document):
    """Stored assessment submission."""

    user_id: PydanticObjectId
    answers: list[Answer]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "checkins"


class DailyCheckIn(Document):
    """Stored daily check-in submission."""

    user_id: PydanticObjectId
    answers: list[Answer]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "daily_checkins"


class WeeklyCheckIn(Document):
    """Stored weekly check-in submission."""

    user_id: PydanticObjectId
    answers: list[Answer]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "weekly_checkins"


class MonthlyCheckIn(Document):
    """Stored monthly check-in submission."""

    user_id: PydanticObjectId
    answers: list[Answer]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "monthly_checkins"
