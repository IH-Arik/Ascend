"""User document model."""

from datetime import datetime, timezone

from beanie import Document
from pydantic import EmailStr, Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class User(Document):
    """Core user identity document for auth and role assignment."""

    email: EmailStr
    full_name: str | None = None
    role: str = "Airman"
    unit_id: str | None = None
    rank_grade: str | None = None
    avatar_storage_path: str | None = None
    avatar_file_name: str | None = None
    avatar_content_type: str | None = None
    avatar_uploaded_at: datetime | None = None
    theme_preference: str = "dark"
    notifications_enabled: bool = True
    activation_date: datetime | None = None
    deactivation_date: datetime | None = None
    is_active: bool = True
    is_verified: bool = False
    hashed_password: str | None = None
    onboarding_completed: bool = False
    onboarding_status: str = "incomplete"
    onboarding_step: str = "welcome"
    first_use_flow_code: str = "PR-M-001"
    first_use_trace_id: str | None = None
    day0_daily_checkin_status: str = "pending"
    day0_daily_checkin_timestamp: datetime | None = None
    current_ops_status: str = "inactive"
    ops_confidence_level: str = "low"
    onboarding_baseline_ops_score: float | None = None
    onboarding_baseline_band: str | None = None
    onboarding_component_scores: dict[str, float | None] | None = None
    current_ops_score: float | None = None
    current_ops_band: str | None = None
    current_component_scores: dict[str, float | None] | None = None
    weekly_cadence_start_date: datetime | None = None
    monthly_cadence_start_date: datetime | None = None
    data_use_consent: bool = False
    data_use_consent_at: datetime | None = None
    wellness_recommendations_opt_in: bool = False
    policy_version_accepted: str | None = None
    policy_acknowledged_at: datetime | None = None
    email_verification_code: str | None = None
    email_verification_expires_at: datetime | None = None
    password_reset_code: str | None = None
    password_reset_expires_at: datetime | None = None
    last_login_at: datetime | None = None
    # Not DOCX-sourced - a Figma "Roles & RBAC" screen showed an access-
    # expiration/annual-renewal concept with no prior backend equivalent.
    # Real tracking (set at registration, extendable via
    # `POST /admin/users/{id}/renew-access`), but not enforced at
    # login/access-check and not auto-renewed by any background process -
    # a date that silently re-extends itself before anyone reaches it would
    # make the concept meaningless. Documented scope decision, not a gap.
    access_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "users"
        indexes = [
            IndexModel([("email", 1)], unique=True),
            IndexModel([("unit_id", 1)]),
        ]
