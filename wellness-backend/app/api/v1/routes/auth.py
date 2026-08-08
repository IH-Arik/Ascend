"""Authentication routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.services.account_service import AccountService
from app.services.auth_service import AuthService
from app.utils.response import success_response

router = APIRouter()
auth_service = AuthService()
account_service = AccountService()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> dict[str, Any]:
    """Register a new user account."""
    data = await auth_service.register_user(payload)
    return success_response("Account created successfully.", data)


@router.post("/login", status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest) -> dict[str, Any]:
    """Authenticate a user and return JWT tokens."""
    data = await auth_service.login_user(payload)
    return success_response("Login successful.", data)


@router.post("/leader-login", status_code=status.HTTP_200_OK)
async def leader_login(payload: LoginRequest) -> dict[str, Any]:
    """Authenticate a leader and return JWT tokens for leader dashboard access."""
    data = await auth_service.login_leader(payload)
    return success_response("Leader login successful.", data)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_token(payload: RefreshRequest) -> dict[str, Any]:
    """Issue a new access token using a refresh token."""
    data = await auth_service.refresh_token(payload)
    return success_response("Token refreshed successfully.", data)


@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(payload: VerifyEmailRequest) -> dict[str, Any]:
    """Verify a user's email address."""
    data = await auth_service.verify_email(payload)
    return success_response("Email verified successfully.", data)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Send a password reset code if the email exists."""
    data = await auth_service.forgot_password(payload)
    return success_response(
        "If an account exists for this email, a reset code has been sent.",
        data,
    )


@router.post("/leader-forgot-password", status_code=status.HTTP_200_OK)
async def leader_forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Send a leader password reset code if the email belongs to a leader account."""
    data = await auth_service.forgot_password_leader(payload)
    return success_response(
        "If a leader account exists for this email, a reset code has been sent.",
        data,
    )


@router.post("/leader-resend-reset-code", status_code=status.HTTP_200_OK)
async def leader_resend_reset_code(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Resend a leader password reset code using the same leader-only flow."""
    data = await auth_service.forgot_password_leader(payload)
    return success_response(
        "If a leader account exists for this email, a new reset code has been sent.",
        data,
    )


@router.post("/superadmin-forgot-password", status_code=status.HTTP_200_OK)
async def superadmin_forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Send a superadmin password reset code if the email belongs to a superadmin account."""
    data = await auth_service.forgot_password_superadmin(payload)
    return success_response(
        "If a superadmin account exists for this email, a reset code has been sent.",
        data,
    )


@router.post("/superadmin-resend-reset-code", status_code=status.HTTP_200_OK)
async def superadmin_resend_reset_code(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Resend a superadmin password reset code using the same superadmin-only flow."""
    data = await auth_service.forgot_password_superadmin(payload)
    return success_response(
        "If a superadmin account exists for this email, a new reset code has been sent.",
        data,
    )


@router.post("/verify-reset-code", status_code=status.HTTP_200_OK)
async def verify_reset_code(payload: VerifyResetCodeRequest) -> dict[str, Any]:
    """Verify a password reset code."""
    data = await auth_service.verify_reset_code(payload)
    return success_response("Reset code verified successfully.", data)


@router.post("/leader-verify-reset-code", status_code=status.HTTP_200_OK)
async def leader_verify_reset_code(payload: VerifyResetCodeRequest) -> dict[str, Any]:
    """Verify a leader password reset code."""
    data = await auth_service.verify_reset_code_leader(payload)
    return success_response("Leader reset code verified successfully.", data)


@router.post("/superadmin-verify-reset-code", status_code=status.HTTP_200_OK)
async def superadmin_verify_reset_code(
    payload: VerifyResetCodeRequest,
) -> dict[str, Any]:
    """Verify a superadmin password reset code."""
    data = await auth_service.verify_reset_code_superadmin(payload)
    return success_response("Superadmin reset code verified successfully.", data)


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Reset a user's password."""
    data = await auth_service.reset_password(payload)
    return success_response("Password updated successfully.", data)


@router.post("/leader-reset-password", status_code=status.HTTP_200_OK)
async def leader_reset_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Reset a leader account password."""
    data = await auth_service.reset_password_leader(payload)
    return success_response("Leader password updated successfully.", data)


@router.post("/superadmin-reset-password", status_code=status.HTTP_200_OK)
async def superadmin_reset_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Reset a superadmin account password."""
    data = await auth_service.reset_password_superadmin(payload)
    return success_response("Superadmin password updated successfully.", data)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Acknowledge logout for JWT clients."""
    data = await account_service.logout_user(current_user)
    return success_response("Logged out successfully.", data)
