"""Reflection entry schemas (see model docstring)."""

from pydantic import BaseModel, Field

from app.models.reflection import REFLECTION_THEMES


class ReflectionCreate(BaseModel):
    """The operator writes a real, private reflection entry."""

    theme: str = Field(pattern="^(" + "|".join(REFLECTION_THEMES) + ")$")
    body: str = Field(min_length=1, max_length=4000)


class ReflectionResponse(BaseModel):
    """A single reflection entry."""

    id: str
    theme: str
    body: str
    length_chars: int
    created_at: str
