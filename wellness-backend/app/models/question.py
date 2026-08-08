"""Question bank document model."""

from typing import Literal

from beanie import Document
from pydantic import Field


class Question(Document):
    """Assessment question definition."""

    code: str | None = None
    text: str
    driver: Literal["PC", "MR", "MC", "PA", "RC"]
    response_type: Literal["scale", "multiple_choice"]
    options: list[str]
    weight: float = Field(default=1.0)
    order: int

    class Settings:
        """Beanie collection settings."""

        name = "questions"
