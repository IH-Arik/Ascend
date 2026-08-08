"""Authentication and user services."""

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.core.dependencies import user_has_superadmin_access
from app.db.repositories.user_repo import UserRepository
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.schemas.user import OnboardingUpdateRequest, UserUpdate
from app.services.email_service import EmailService
from app.services.meta_service import MetaService
from app.utils.constants import CODE_EXPIRY_MINUTES
from app.utils.helpers import generate_verification_code, is_code_expired, utc_now
from app.utils.response import error_response


class AuthService:
    """Service for authentication and authenticated user workflows."""

    def __init__(self) -> None:
        """Initialize service dependencies."""
        self.user_repository = UserRepository()
        self.email_service = EmailService()
        self.meta_service = MetaService()

    async def register_user(self, data: RegisterRequest) -> dict[str, Any]:
        """Register a user and return issued tokens with the serialized user."""
        self._validate_organization_role(data.organization_name, data.role)
        existing_user = await self.user_repository.get_by_email(data.email)
        verification_code = generate_verification_code()
        expires_at = utc_now() + timedelta(minutes=CODE_EXPIRY_MINUTES)

        if existing_user is not None and existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "An account with this email already exists.",
                    {"email": "Email is already registered."},
                ),
            )

        if existing_user is not None:
            user = await self.user_repository.update_user(
                str(existing_user.id),
                {
                    "name": data.name,
                    "hashed_password": get_password_hash(data.password),
                    "organization_name": data.organization_name,
                    "role": data.role,
                    "is_active": True,
                    "is_verified": False,
                    "onboarding_completed": False,
                    "email_verification_code": verification_code,
                    "email_verification_expires_at": expires_at,
                    "password_reset_code": None,
                    "password_reset_expires_at": None,
                },
            )
        else:
            user = await self.user_repository.create_user(
                {
                    "name": data.name,
                    "email": data.email,
                    "hashed_password": get_password_hash(data.password),
                    "organization_name": data.organization_name,
                    "role": data.role,
                    "email_verification_code": verification_code,
                    "email_verification_expires_at": expires_at,
                }
            )

        await self.email_service.send_verification_email(
            to=user.email,
            name=user.name,
            code=verification_code,
        )

        return self._build_token_response(user)

    async def login_user(self, data: LoginRequest) -> dict[str, Any]:
        """Authenticate a user and return issued tokens with the serialized user."""
        user = await self._authenticate_user(data)
        return self._build_token_response(user)

    async def login_leader(self, data: LoginRequest) -> dict[str, Any]:
        """Authenticate a leader user and return issued tokens with the serialized user."""
        user = await self._authenticate_user(data)
        if not self._user_has_leader_access(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    "This account does not have leader dashboard access.",
                    {"role": "Leader login requires a leadership role."},
                ),
            )
        return self._build_token_response(user)

    async def refresh_token(self, data: RefreshRequest) -> dict[str, Any]:
        """Issue a new access token from a refresh token."""
        payload = decode_token(data.refresh_token)
        if payload.get("token_type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response("Invalid refresh token."),
            )

        user_id = payload.get("sub")
        user = await self.user_repository.get_by_id(str(user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )

        return self._build_token_response(user, refresh_token=data.refresh_token)

    async def verify_email(self, data: VerifyEmailRequest) -> dict[str, Any]:
        """Verify a user's email with a 4-digit code."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )

        if user.email_verification_code != data.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid verification code.",
                    {"code": "Verification code does not match."},
                ),
            )

        if is_code_expired(user.email_verification_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Verification code has expired.",
                    {"code": "Please request a new verification code."},
                ),
            )

        updated_user = await self.user_repository.update_user(
            str(user.id),
            {
                "is_verified": True,
                "email_verification_code": None,
                "email_verification_expires_at": None,
            },
        )
        await self.email_service.send_welcome_email(
            to=updated_user.email,
            name=updated_user.name,
        )
        return {"user": self._serialize_user(updated_user)}

    async def forgot_password(self, data: ForgotPasswordRequest) -> dict[str, Any]:
        """Generate and email a password reset code without revealing account existence."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None:
            return {}

        reset_code = generate_verification_code()
        expires_at = utc_now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        updated_user = await self.user_repository.update_user(
            str(user.id),
            {
                "password_reset_code": reset_code,
                "password_reset_expires_at": expires_at,
            },
        )
        await self.email_service.send_password_reset_email(
            to=updated_user.email,
            name=updated_user.name,
            code=reset_code,
        )
        return {}

    async def forgot_password_leader(
        self,
        data: ForgotPasswordRequest,
    ) -> dict[str, Any]:
        """Generate a password reset code for leader accounts without revealing existence."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_leader_access(user):
            return {}
        return await self.forgot_password(data)

    async def forgot_password_superadmin(
        self,
        data: ForgotPasswordRequest,
    ) -> dict[str, Any]:
        """Generate a password reset code for superadmin accounts without revealing existence."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_superadmin_access(user):
            return {}
        return await self.forgot_password(data)

    async def verify_reset_code(
        self, data: VerifyResetCodeRequest
    ) -> dict[str, Any]:
        """Validate a password reset code for the provided email."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or user.password_reset_code != data.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )

        if is_code_expired(user.password_reset_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Reset code has expired.",
                    {"code": "Please request a new reset code."},
                ),
            )

        await self.user_repository.update_user(
            str(user.id),
            {"is_verified": True},
        )
        return {}

    async def verify_reset_code_leader(
        self,
        data: VerifyResetCodeRequest,
    ) -> dict[str, Any]:
        """Validate a password reset code for a leader account."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_leader_access(user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )
        return await self.verify_reset_code(data)

    async def verify_reset_code_superadmin(
        self,
        data: VerifyResetCodeRequest,
    ) -> dict[str, Any]:
        """Validate a password reset code for a superadmin account."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_superadmin_access(user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )
        return await self.verify_reset_code(data)

    async def reset_password(self, data: ResetPasswordRequest) -> dict[str, Any]:
        """Reset a user's password after validating the reset code."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or user.password_reset_code != data.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )

        if is_code_expired(user.password_reset_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Reset code has expired.",
                    {"code": "Please request a new reset code."},
                ),
            )

        if data.new_password != data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Passwords do not match.",
                    {"confirm_password": "Password confirmation does not match."},
                ),
            )

        await self.user_repository.update_user(
            str(user.id),
            {
                "hashed_password": get_password_hash(data.new_password),
                "password_reset_code": None,
                "password_reset_expires_at": None,
            },
        )
        return {}

    async def reset_password_leader(self, data: ResetPasswordRequest) -> dict[str, Any]:
        """Reset a leader account password after validating the reset code."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_leader_access(user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )
        return await self.reset_password(data)

    async def reset_password_superadmin(
        self,
        data: ResetPasswordRequest,
    ) -> dict[str, Any]:
        """Reset a superadmin account password after validating the reset code."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None or not self._user_has_superadmin_access(user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid reset code.",
                    {"code": "Reset code is invalid."},
                ),
            )
        return await self.reset_password(data)

    async def change_password(
        self,
        user: User,
        data: ChangePasswordRequest,
    ) -> dict[str, Any]:
        """Change the password for an authenticated user."""
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response(
                    "Current password is incorrect.",
                    {"current_password": "Current password is incorrect."},
                ),
            )

        if data.new_password != data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Passwords do not match.",
                    {"confirm_password": "Password confirmation does not match."},
                ),
            )

        if verify_password(data.new_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "New password must be different from current password.",
                    {"new_password": "Choose a different password."},
                ),
            )

        await self.user_repository.update_user(
            str(user.id),
            {"hashed_password": get_password_hash(data.new_password)},
        )
        return {"detail": "Password updated successfully."}

    async def get_me(self, user: User) -> dict[str, Any]:
        """Return the serialized authenticated user."""
        return self._serialize_user(user)

    async def update_me(self, user: User, data: UserUpdate) -> dict[str, Any]:
        """Update basic user profile fields."""
        update_payload = data.model_dump(exclude_unset=True)
        if not update_payload:
            return self._serialize_user(user)

        updated_user = await self.user_repository.update_user(str(user.id), update_payload)
        return self._serialize_user(updated_user)

    async def update_onboarding(
        self,
        user: User,
        data: OnboardingUpdateRequest,
    ) -> dict[str, Any]:
        """Update organization access fields and onboarding completion state."""
        update_payload = data.model_dump(exclude_unset=True)
        if not update_payload:
            return self._serialize_user(user)

        organization_name = update_payload.get("organization_name", user.organization_name)
        role = update_payload.get("role", user.role)
        self._validate_organization_role(organization_name, role)

        updated_user = await self.user_repository.update_user(str(user.id), update_payload)
        return self._serialize_user(updated_user)

    def _validate_organization_role(
        self,
        organization_name: str | None,
        role: str | None,
    ) -> None:
        """Validate organization and role selections."""
        try:
            self.meta_service.validate_organization_role(organization_name, role)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    str(exc),
                    {
                        "organization_name": str(exc),
                        "role": str(exc),
                    },
                ),
            ) from exc

    async def _authenticate_user(self, data: LoginRequest) -> User:
        """Validate basic credentials and return the active user."""
        user = await self.user_repository.get_by_email(data.email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )

        if not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_response("Invalid email or password."),
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response("This account is inactive."),
            )
        return user

    def _user_has_leader_access(self, user: User) -> bool:
        """Return whether the user's role qualifies for leader dashboard access."""
        role = (user.role or "").strip().lower()
        if not role:
            return False

        leader_keywords = (
            "lead",
            "manager",
            "head",
            "executive",
            "director",
            "coach",
        )
        return any(keyword in role for keyword in leader_keywords)

    def _user_has_superadmin_access(self, user: User) -> bool:
        """Return whether the user's role qualifies for superadmin dashboard access."""
        return user_has_superadmin_access(user)

    def _build_token_response(
        self,
        user: User,
        refresh_token: str | None = None,
    ) -> dict[str, Any]:
        """Return the token response data for a user."""
        return {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": refresh_token or create_refresh_token(str(user.id)),
            "token_type": "bearer",
            "user": self._serialize_user(user),
        }

    def _serialize_user(self, user: User) -> dict[str, Any]:
        """Return a response-safe user payload."""
        return {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "is_verified": user.is_verified,
            "onboarding_completed": user.onboarding_completed,
            "organization_name": user.organization_name,
            "role": user.role,
            "created_at": user.created_at,
        }
