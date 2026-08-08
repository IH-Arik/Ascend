"""Profile document model."""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import ConfigDict, Field


class Profile(Document):
    """Personal and work profile for a user."""

    user_id: PydanticObjectId
    name: str
    age: int
    gender: str
    company: str
    department: str
    team: str
    role: str
    height_cm: float
    weight_kg: float
    profile_image_url: str | None = None
    contact_number: str | None = None
    employee_id: str | None = None
    company_address: str | None = None
    company_logo_url: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Settings:
        """Beanie collection settings."""

        name = "profiles"
