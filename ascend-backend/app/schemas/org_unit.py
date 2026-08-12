"""Org unit hierarchy schemas (see `app/models/org_unit.py`)."""

from pydantic import BaseModel, Field


class OrgUnitCreate(BaseModel):
    """Admin creates a real Wing/Detachment/Flight node."""

    name: str = Field(min_length=1, max_length=120)
    unit_type: str
    parent_id: str | None = None


class RoleScopeConfigUpdate(BaseModel):
    """Admin updates one role's cohort-k minimum and/or visible components."""

    cohort_k: int = Field(ge=1, le=1000)
    visible_components: list[str]
