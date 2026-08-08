"""Leader action log document model."""

from datetime import datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field


class LeaderActionLog(Document):
    """Stored action taken by a leader for a team risk signal."""

    leader_user_id: PydanticObjectId
    organization_name: str
    department: str | None = None
    team: str | None = None
    risk_key: Literal[
        "recovery_deficit",
        "high_stress",
        "fatigue",
        "workload_strain",
        "morale_decline",
        "other",
    ] = "other"
    action: str
    note: str | None = None
    selected_from_recommended: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "leader_action_logs"
