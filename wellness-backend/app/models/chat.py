"""Chat-related document models."""

from datetime import datetime, timezone
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field


class ChatMessage(Document):
    """Persisted assistant chat message for a user."""

    user_id: PydanticObjectId
    role: Literal["assistant", "user"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "chat_messages"
