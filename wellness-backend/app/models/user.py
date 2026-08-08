"""User document model."""

from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import EmailStr, Field
from pymongo import IndexModel


class User(Document):
    """Authentication and onboarding user record."""

    email: EmailStr
    hashed_password: str
    name: str
    organization_name: Optional[str] = None
    role: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    onboarding_completed: bool = False
    email_verification_code: Optional[str] = None
    email_verification_expires_at: Optional[datetime] = None
    password_reset_code: Optional[str] = None
    password_reset_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        """Beanie collection settings."""

        name = "users"
        indexes = [IndexModel([("email", 1)], unique=True)]
