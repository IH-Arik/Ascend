"""Pathway approval/enablement schemas."""

from pydantic import BaseModel, Field


class PathwayEnableRequest(BaseModel):
    """Admin enables a previously-approved pathway, optionally recording its access policy."""

    access_policy: str | None = Field(default=None, max_length=200)
