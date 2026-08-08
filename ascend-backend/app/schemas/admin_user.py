"""Admin user-management schemas (DOCX Admin Panel: "Assign roles, coaches,
specialists, teams, units, reporting groups, and support pathways.")."""

from pydantic import BaseModel, Field


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
