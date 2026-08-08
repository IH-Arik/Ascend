"""AI insight schemas."""

from typing import Any

from pydantic import BaseModel, Field


class AIInsightResponse(BaseModel):
    """AI insight payload returned to dashboard/provider views."""

    id: str
    user_id: str
    trace_id: str
    insight_type: str
    source_flow: str
    model_name: str
    status: str
    title: str
    summary: str
    signals: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    payload: dict[str, Any]
    created_at: str
    updated_at: str
