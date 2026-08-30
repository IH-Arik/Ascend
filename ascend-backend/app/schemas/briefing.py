"""Leadership "Briefings" schemas."""

from pydantic import BaseModel, Field


class BriefingSectionInput(BaseModel):
    """A single outline entry when creating/editing a briefing with a custom outline."""

    section_key: str
    title: str = Field(min_length=1, max_length=120)


class BriefingCreateRequest(BaseModel):
    """Create a real briefing, either from a template or a custom outline."""

    title: str = Field(min_length=1, max_length=120)
    template_key: str | None = None
    custom_outline: list[BriefingSectionInput] | None = None


class BriefingOutlineUpdateRequest(BaseModel):
    """Edit a draft briefing's outline (add/remove/reorder sections)."""

    outline: list[BriefingSectionInput] = Field(min_length=1)


class BriefingSendRequest(BaseModel):
    """Send a briefing, optionally recording which real in-app roles it's addressed to.

    `recipient_roles` is validated against `SUPPORTED_ROLES` in the service
    layer (real in-app roles, not free-text organizational titles like
    "CC"/"SEL" - no such concept exists in this system).
    """

    recipient_roles: list[str] | None = None
