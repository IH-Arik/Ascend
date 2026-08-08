"""User read and update schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserRead(BaseModel):
    """Serialized user response."""

    id: str
    name: str
    email: EmailStr
    is_verified: bool
    onboarding_completed: bool
    organization_name: Optional[str]
    role: Optional[str]
    created_at: datetime


class UserUpdate(BaseModel):
    """Payload for updating user fields."""

    name: Optional[str] = None
    organization_name: Optional[str] = None
    role: Optional[str] = None


class OnboardingUpdateRequest(BaseModel):
    """Payload for updating optional onboarding information."""

    organization_name: Optional[str] = None
    role: Optional[str] = None
    onboarding_completed: bool = False
