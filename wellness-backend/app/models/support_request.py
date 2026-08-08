"""Support request document model."""

from datetime import datetime
from beanie import Document, PydanticObjectId
from pydantic import EmailStr, Field


class SupportRequest(Document):
    """User support and help request record."""

    user_id: PydanticObjectId
    email: EmailStr
    issue: str
    status: str = "pending"
    estimated_response: str = "Within 2 hours"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        """Beanie collection settings."""

        name = "support_requests"
        indexes = ["user_id", "status"]
