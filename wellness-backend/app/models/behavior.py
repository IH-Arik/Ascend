"""Behavior log document model."""

from datetime import date, datetime
from enum import Enum
from typing import Literal

from beanie import Document, Indexed, PydanticObjectId
from pydantic import ConfigDict, Field


class BehaviorType(str, Enum):
    """Supported behavior log values."""

    PHYSICAL_ACTIVITY = "physical_activity"
    RECOVERY_PRACTICE = "recovery_practice"
    GRATITUDE_REFLECTION = "gratitude_reflection"
    MEANINGFUL_CONNECTION = "meaningful_connection"
    INTENTIONAL_SLEEP_ROUTINE = "intentional_sleep_routine"


class BehaviorLog(Document):
    """Stored behavior completion log for a user and source period."""

    user_id: PydanticObjectId
    logged_at: datetime = Field(default_factory=datetime.utcnow)
    behavior_date: date
    behaviors: list[BehaviorType] = Field(default_factory=list)
    source: Literal["daily", "weekly", "monthly"]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "behavior_logs"
        indexes = [
            [
                ("user_id", 1),
                ("behavior_date", 1),
                ("source", 1),
            ],
        ]
