"""Authentication request and response schemas."""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    """Payload for new user registration."""

    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    organization_name: Optional[str] = None
    role: Optional[str] = None


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password reset code."""

    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    """Payload for validating a password reset code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)


class ResetPasswordRequest(BaseModel):
    """Payload for resetting a password with a verification code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)
    new_password: str = Field(min_length=8)
    confirm_password: str


class VerifyEmailRequest(BaseModel):
    """Payload for email verification."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=4)


class TokenResponse(BaseModel):
    """JWT token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class RefreshRequest(BaseModel):
    """Payload for requesting a refreshed access token."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Payload for changing password while logged in."""

    current_password: str
    new_password: str = Field(min_length=8)
    confirm_password: str
