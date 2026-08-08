"""FAQ model for Help Center content."""

from datetime import datetime, timezone

from beanie import Document
from pydantic import ConfigDict, Field


class FAQ(Document):
    """Persist frequently asked questions for the help center."""

    question: str
    answer: str
    order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "faqs"
