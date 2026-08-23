"""Authentication request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.roles import ROLE_AIRMAN
from app.core.roles import is_supported_role
from app.core.roles import normalize_role


def validate_password_strength(value: str) -> str:
    """Enforce the password rules shown on the Ascend UI (8+ chars, 1 uppercase, 1 number)."""
    if not any(char.isupper() for char in value):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one number.")
    return value


class RegisterRequest(BaseModel):
    """Register a new user account."""

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default=ROLE_AIRMAN, min_length=2, max_length=60)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Restrict registration to approved Ascend roles."""
        normalized = normalize_role(value)
        if not is_supported_role(normalized):
            raise ValueError("Role is not supported by Ascend.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Enforce password strength rules."""
        return validate_password_strength(value)


class LoginRequest(BaseModel):
    """Authenticate with email and password."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    remember_me: bool = False


class RefreshRequest(BaseModel):
    """Request a fresh access token."""

    refresh_token: str = Field(min_length=20)


class VerifyEmailRequest(BaseModel):
    """Verify a user's email with a short code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Trim and validate the verification code."""
        code = value.strip()
        if not code.isdigit():
            raise ValueError("Code must contain exactly 4 digits.")
        return code


class ForgotPasswordRequest(BaseModel):
    """Request a password reset code."""

    email: EmailStr


class ResendVerificationCodeRequest(BaseModel):
    """Request that a verification code be generated again."""

    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    """Validate a password reset code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Trim and validate the reset code."""
        code = value.strip()
        if not code.isdigit():
            raise ValueError("Code must contain exactly 4 digits.")
        return code


class ResetPasswordRequest(BaseModel):
    """Reset a password with a validated code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """Trim and validate the reset code."""
        code = value.strip()
        if not code.isdigit():
            raise ValueError("Code must contain exactly 4 digits.")
        return code

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Enforce password strength rules."""
        return validate_password_strength(value)


class ChangePasswordRequest(BaseModel):
    """A signed-in user changes their own password, proving the current one."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        """Enforce password strength rules."""
        return validate_password_strength(value)


class UserResponse(BaseModel):
    """Serialized user payload returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    is_verified: bool
    onboarding_completed: bool
    onboarding_status: str
    onboarding_step: str
    day0_daily_checkin_status: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AuthScreenConfigResponse(BaseModel):
    """Frontend-facing login screen support metadata."""

    allow_email_login: bool = True
    allow_forgot_password: bool = True
    allow_register: bool = True
    allow_verify_email: bool = True
    allow_resend_verification_code: bool = True
    allow_set_new_password: bool = True
    allow_remember_me: bool = True
    allow_show_hide_password: bool = True
    support_email: str | None = None
    support_phone: str | None = None
    help_center_url: str | None = None
    terms_of_use_url: str | None = None
    privacy_policy_url: str | None = None
    opsec_notice_text: str | None = None
