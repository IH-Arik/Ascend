"""User profile schema."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}
AVATAR_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
}


class AssignedProvider(BaseModel):
    """A provider assigned to the user through My Support Team."""

    user_id: str
    name: str | None
    avatar_url: str | None


class SignInActivation(BaseModel):
    """Account verification/activation summary."""

    is_verified: bool
    member_since: datetime
    last_login_at: datetime | None


class ProfileResponse(BaseModel):
    """Aggregated profile payload for the Profile screen."""

    id: str
    email: EmailStr
    full_name: str | None
    role: str
    unit_id: str | None
    rank_grade: str | None
    avatar_url: str | None
    is_verified: bool
    onboarding_completed: bool
    onboarding_status: str
    day0_daily_checkin_status: str
    current_ops_score: float | None
    current_ops_band: str | None
    current_ops_band_meaning: str
    ops_confidence_level: str
    onboarding_baseline_ops_score: float | None
    onboarding_baseline_band: str | None
    support_pathways_opted_in: list[str]
    assigned_scs: AssignedProvider | None
    assigned_ptim: AssignedProvider | None
    communications_preference: str
    theme_preference: str
    notifications_enabled: bool
    data_use_consent: bool
    wellness_recommendations_opt_in: bool
    policy_version_accepted: str | None
    policy_acknowledged_at: datetime | None
    sign_in_activation: SignInActivation
    member_since: datetime


class UpdateProfileSettingsRequest(BaseModel):
    """Locally controllable profile settings the user can edit themselves.

    `full_name` is included here (self-reported, not CAC-sourced - see
    `profile_service.py`'s module docstring). `role` and `unit_id` are
    deliberately absent: those remain admin/provisioning-set, since a
    self-service edit of either would be a real authorization/assignment
    risk, not a cosmetic preference like a name correction.
    """

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    rank_grade: str | None = Field(default=None, max_length=40)
    theme_preference: str | None = None
    notifications_enabled: bool | None = None


class ChangeEmailRequest(BaseModel):
    """A signed-in user changes their own login email.

    Requires the current password (same "prove intent" pattern as
    `ChangePasswordRequest`) since the email doubles as the login
    identifier. Re-verification is required afterward - the new address
    is unverified until the user confirms the code sent to it.
    """

    new_email: EmailStr
    current_password: str = Field(min_length=1)
