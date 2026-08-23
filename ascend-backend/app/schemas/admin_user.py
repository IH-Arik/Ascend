"""Admin user-management schemas (DOCX Admin Panel: "Assign roles, coaches,
specialists, teams, units, reporting groups, and support pathways.")."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import validate_password_strength


class UserSummary(BaseModel):
    """One row in the Admin user list."""

    id: str
    email: str
    full_name: str | None
    role: str
    unit_id: str | None
    is_active: bool
    is_verified: bool


class RoleChangeRequest(BaseModel):
    """Admin changes a user's role."""

    role: str = Field(min_length=1, max_length=40)


class UnitAssignRequest(BaseModel):
    """Admin assigns a user to a unit."""

    unit_id: str | None = Field(default=None, max_length=80)


class ProviderAssignRequest(BaseModel):
    """Admin manually assigns (overrides) a pathway's provider for a user."""

    pathway_key: str
    provider_user_id: str


class AdminDeactivationRequest(BaseModel):
    """Admin requests deactivation of a provider/admin-level account (second-reviewer gated)."""

    reason: str | None = Field(default=None, max_length=500)


class AdminCreateUserRequest(BaseModel):
    """Admin directly provisions a new account (DOCX 2A Step 1 - "Account
    Provisioning/Activation": "DWS Admin ... creates or provisions the
    account.")."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: str = Field(min_length=1, max_length=40)
    unit_id: str | None = None
    is_active: bool = True
    initial_password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("initial_password")
    @classmethod
    def validate_initial_password(cls, value: str | None) -> str | None:
        """Enforce the same password strength rules as self-registration, when supplied."""
        if value is None:
            return value
        return validate_password_strength(value)
