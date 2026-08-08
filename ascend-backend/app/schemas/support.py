"""Support pathway ("My Support Team") schemas."""

from pydantic import BaseModel, Field


class SupportPathwayResponse(BaseModel):
    """A single support pathway available to the user."""

    key: str
    label: str
    description: str
    availability_status: str


class SupportRequestCreate(BaseModel):
    """Submit a support request to a pathway."""

    pathway_key: str
    message: str | None = Field(default=None, max_length=280)


class SupportRequestResponse(BaseModel):
    """A single support request."""

    id: str
    pathway_key: str
    pathway_label: str
    message: str | None
    status: str
    priority_flag: bool
    safety_notice: str | None
    created_at: str
    updated_at: str


class AssignedSupportRequestResponse(SupportRequestResponse):
    """A support request as seen by the provider it was routed to."""

    user_id: str
    user_name: str | None


class UpdateRequestStatusRequest(BaseModel):
    """A provider updating a support request's status."""

    status: str


class TeamProvider(BaseModel):
    """The provider assigned to a pathway, if one exists."""

    user_id: str
    name: str | None


class TeamFollowUpStatus(BaseModel):
    """The most recent support request made to a pathway, if any."""

    request_id: str
    status: str
    created_at: str


class TeamAssignedAction(BaseModel):
    """The active assigned action tied to a pathway, if any."""

    id: str
    title: str
    status: str
    due_date: str | None


class TeamPathwayStatus(BaseModel):
    """One pathway's assignment/enable status on the My Team screen."""

    pathway_key: str
    label: str
    role_title: str
    description: str
    always_available: bool
    status: str
    messaging_available: bool
    provider: TeamProvider | None
    follow_up_status: TeamFollowUpStatus | None
    assigned_action: TeamAssignedAction | None


class TogglePathwayRequest(BaseModel):
    """Enable or disable an optional support pathway."""

    enabled: bool
