"""Metadata schemas for dropdown options."""

from pydantic import BaseModel


class DropdownOptionRead(BaseModel):
    """Single dropdown option payload."""

    label: str
    value: str


class OrganizationRoleOptionsRead(BaseModel):
    """Organization and role dropdown payload."""

    organizations: list[DropdownOptionRead]
    roles: list[DropdownOptionRead]
