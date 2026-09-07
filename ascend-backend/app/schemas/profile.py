"""User profile schema."""

from datetime import date, datetime, timezone

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.user import SEX_VALUES

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
    date_of_birth: date | None
    age: int | None
    sex: str | None
    height_in: float | None
    weight_lb: float | None
    bmi: float | None
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
    # Real, self-reported biometric fields - see `app/models/user.py`.
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, pattern="^(" + "|".join(SEX_VALUES) + ")$")
    height_in: float | None = Field(default=None, ge=36, le=96)
    weight_lb: float | None = Field(default=None, ge=60, le=500)

    @field_validator("date_of_birth")
    @classmethod
    def _dob_not_in_future_or_implausible(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = datetime.now(timezone.utc).date()
        if value > today:
            raise ValueError("Date of birth cannot be in the future.")
        age_years = (today - value).days / 365.25
        if age_years < 16 or age_years > 80:
            raise ValueError("Date of birth is outside a plausible range.")
        return value


class ChangeEmailRequest(BaseModel):
    """A signed-in user changes their own login email.

    Requires the current password (same "prove intent" pattern as
    `ChangePasswordRequest`) since the email doubles as the login
    identifier. Re-verification is required afterward - the new address
    is unverified until the user confirms the code sent to it.
    """

    new_email: EmailStr
    current_password: str = Field(min_length=1)
