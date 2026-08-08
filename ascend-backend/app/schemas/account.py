"""Sign-in history and account deactivation schemas."""

from pydantic import BaseModel, Field


class SignInEvent(BaseModel):
    """One login attempt, success or failure."""

    event_type: str
    method: str
    outcome: str
    ip_address: str | None
    user_agent: str | None
    created_at: str


class SignInHistoryResponse(BaseModel):
    """The Sign-in & activation screen payload."""

    last_sign_in: SignInEvent | None
    recent_history: list[SignInEvent]
    activation_date: str | None
    deactivation_date: str | None


class DeactivationRequestCreate(BaseModel):
    """A user requesting their own account be deactivated."""

    reason: str | None = Field(default=None, max_length=500)


class DeactivationRequestResponse(BaseModel):
    """A single deactivation request."""

    id: str
    user_id: str
    user_name: str | None
    reason: str | None
    status: str
    requested_at: str
    reviewed_at: str | None
