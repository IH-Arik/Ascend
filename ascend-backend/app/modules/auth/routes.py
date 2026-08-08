"""Authentication routes."""

from typing import Any

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationCodeRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.services.auth_service import AuthService

router = APIRouter()
auth_service = AuthService()


@router.get("/screen-config", status_code=status.HTTP_200_OK)
async def get_auth_screen_config() -> dict[str, Any]:
    """Return login-screen support config for the frontend."""
    data = await auth_service.get_auth_screen_config()
    return success_response("Auth screen config loaded successfully.", data)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> dict[str, Any]:
    """Register a new user account."""
    data = await auth_service.register_user(payload)
    return success_response("Account created successfully.", data)


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    """Authenticate a user and issue JWT tokens."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    data = await auth_service.login_user(payload, ip_address=ip_address, user_agent=user_agent)
    return success_response("Login successful.", data)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_token(payload: RefreshRequest) -> dict[str, Any]:
    """Issue a new access token from a refresh token."""
    data = await auth_service.refresh_token(payload)
    return success_response("Token refreshed successfully.", data)


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(payload: VerifyEmailRequest) -> dict[str, Any]:
    """Verify a user's email address."""
    data = await auth_service.verify_email(payload)
    return success_response("Email verified successfully.", data)


@router.post("/resend-verification-code", status_code=status.HTTP_200_OK)
async def resend_verification_code(
    payload: ResendVerificationCodeRequest,
) -> dict[str, Any]:
    """Regenerate the email verification code when needed."""
    data = await auth_service.resend_verification_code(payload)
    return success_response(
        "If an eligible account exists, a new verification code has been generated.",
        data,
    )


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Generate a password reset code when the account exists."""
    data = await auth_service.forgot_password(payload)
    return success_response(
        "If an account exists for this email, a reset code has been generated.",
        data,
    )


@router.post("/verify-reset-code", status_code=status.HTTP_200_OK)
async def verify_reset_code(payload: VerifyResetCodeRequest) -> dict[str, Any]:
    """Verify the supplied password reset code."""
    data = await auth_service.verify_reset_code(payload)
    return success_response("Reset code verified successfully.", data)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Reset a user's password."""
    data = await auth_service.reset_password(payload)
    return success_response("Password updated successfully.", data)


@router.post("/set-new-password", status_code=status.HTTP_200_OK)
async def set_new_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Alias for reset-password tailored to frontend wording."""
    data = await auth_service.reset_password(payload)
    return success_response("New password set successfully.", data)


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the current authenticated user."""
    data = await auth_service.get_me(current_user)
    return success_response("Current user loaded successfully.", data)
