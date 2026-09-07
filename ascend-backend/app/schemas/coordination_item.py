"""PT/IM-SCS coordination item schemas."""

from pydantic import BaseModel, Field

from app.models.coordination_item import AFFECTS_CATEGORIES, TRIGGER_CATEGORIES

TRIGGER_LABELS: dict[str, str] = {
    "pain": "Pain",
    "limitation": "Limitation",
    "failed_oft": "Failed OFT",
    "recovery_decline": "Recovery decline",
}

AFFECTS_LABELS: dict[str, str] = {
    "training_load": "Training load",
    "session_plan": "Session plan",
    "assessment": "Assessment",
    "programming": "Programming",
}


class CoordinationItemCreateRequest(BaseModel):
    """PT/IM or SCS raises a new joint coordination item for an operator."""

    user_id: str
    title: str = Field(min_length=1, max_length=160)
    trigger_category: str = Field(pattern="^(" + "|".join(TRIGGER_CATEGORIES) + ")$")
    trigger_detail: str | None = Field(default=None, max_length=120)
    affects: str = Field(pattern="^(" + "|".join(AFFECTS_CATEGORIES) + ")$")
