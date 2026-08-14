"""Recommendation engine / assigned-action schemas."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class RecommendationResponse(BaseModel):
    """A single readiness recommendation or assigned action."""

    id: str
    readiness_component: str
    severity: str
    signal_label: str
    title: str
    body: str
    provider_action_type: str
    specialist_route: str | None
    route_level: str | None = None
    plan_link_category: str | None = None
    coordination_signoff_status: str = "not_required"
    signed_off_by_name: str | None = None
    signed_off_at: str | None = None
    follow_up_timeline: str
    trigger_reason: str
    status: str
    assigned_provider_name: str | None = None
    assigned_provider_role: str | None = None
    due_date: str | None = None
    instructions: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ActionStep(BaseModel):
    """A single step within an assigned action."""

    title: str
    description: str = ""
    completed: bool = False


class AssignActionRequest(BaseModel):
    """SCS/PT-IM assigns a provider-authored action to a user."""

    readiness_component: str
    assigned_provider_name: str = Field(min_length=1, max_length=120)
    assigned_provider_role: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=2000)
    steps: list[ActionStep] = Field(default_factory=list)
    due_date: date | None = None
    follow_up_timeline: str = "Next check-in"
    # DOCX: "Joint PT/IM-SCS Coordination: any item where pain, limitation,
    # failed OFT, recovery decline, or uploaded medical history affects
    # training plan decisions." A real judgment call at assignment time, not
    # auto-inferred from the assigned role.
    is_joint_coordination: bool = False
