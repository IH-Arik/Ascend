"""Profile request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileCreate(BaseModel):
    """Payload for creating a user profile."""

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


class ProfileRead(ProfileCreate):
    """Serialized profile response."""

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    """Payload for updating a user profile."""

    name: str | None = None
    age: int | None = None
    gender: str | None = None
    company: str | None = None
    department: str | None = None
    team: str | None = None
    role: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    profile_image_url: str | None = None
    contact_number: str | None = None
    employee_id: str | None = None
    company_address: str | None = None
    company_logo_url: str | None = None
