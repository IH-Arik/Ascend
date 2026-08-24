"""Authentication service for Ascend."""

from datetime import timedelta
import logging
import secrets
from typing import Any

from fastapi import HTTPException, status
from beanie.exceptions import CollectionWasNotInitialized
from pymongo.errors import PyMongoError

from app.core.config import get_settings
from app.core.roles import ROLE_SUPERADMIN, normalize_role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    utc_now,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    AuthScreenConfigResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationCodeRequest,
    ChangePasswordRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.schemas.profile import ChangeEmailRequest
from app.services.audit_log_service import AuditLogService
from app.services.email_service import EmailService

CODE_EXPIRY_MINUTES = 10
REMEMBER_ME_REFRESH_MULTIPLIER = 2
# Not DOCX-sourced (see `app/models/user.py`) - own reasonable default,
# the DOCX does not specify an access-review cadence.
ACCESS_EXPIRY_DAYS = 365
logger = logging.getLogger(__name__)


class AuthService:
    """Service for user registration, authentication, and recovery."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.email_service = EmailService()

    async def register_user(self, payload: RegisterRequest) -> dict[str, Any]:
        """Register a user and issue auth tokens."""
        try:
            existing_user = await User.find_one({"email": payload.email.lower()})
        except (PyMongoError, CollectionWasNotInitialized, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is temporarily unavailable. Please try again shortly.",
            ) from exc

        verification_code = self._generate_code()
        expires_at = utc_now() + timedelta(minutes=CODE_EXPIRY_MINUTES)

        if existing_user is not None and existing_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        resolved_role = self._resolve_role(payload)

        try:
            if existing_user is not None:
                existing_user.full_name = payload.full_name
                existing_user.role = resolved_role
                existing_user.is_active = True
                existing_user.is_verified = False
                existing_user.hashed_password = get_password_hash(payload.password)
                existing_user.onboarding_completed = False
                existing_user.email_verification_code = verification_code
                existing_user.email_verification_expires_at = expires_at
                existing_user.password_reset_code = None
                existing_user.password_reset_expires_at = None
                existing_user.activation_date = utc_now()
                existing_user.deactivation_date = None
                existing_user.access_expires_at = utc_now() + timedelta(days=ACCESS_EXPIRY_DAYS)
                existing_user.updated_at = utc_now()
                await existing_user.save()
                user = existing_user
            else:
                user = User(
                    email=payload.email.lower(),
                    full_name=payload.full_name,
                    role=resolved_role,
                    hashed_password=get_password_hash(payload.password),
                    email_verification_code=verification_code,
                    email_verification_expires_at=expires_at,
                    activation_date=utc_now(),
                    access_expires_at=utc_now() + timedelta(days=ACCESS_EXPIRY_DAYS),
                )
                await user.insert()
        except (PyMongoError, CollectionWasNotInitialized, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is temporarily unavailable. Please try again shortly.",
            ) from exc

        self._log_delivery_code("verification", user.email, verification_code)
        await self.email_service.send(
            to=user.email,
            subject="Ascend – Verify Your Email",
            html_body=(
                f"<p>Hello {user.full_name},</p>"
                f"<p>Your Ascend email verification code is: <strong>{verification_code}</strong></p>"
                f"<p>This code expires in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"<p>If you did not register, you can ignore this email.</p>"
            ),
        )
        return self._build_token_response(user)

    def _resolve_role(self, payload: RegisterRequest) -> str:
        """Return the role to assign at registration.

        The only Superadmin bootstrap path in this project: if
        `SUPERADMIN_EMAIL` is set and the registering email matches it
        (case-insensitively), the account gets `DWS Superadmin` regardless
        of the role requested in the payload - documented in
        `.env.example`/`UPDATE.MD`, not a hidden backdoor. Every other
        email is normalized as before.
        """
        settings = get_settings()
        if settings.superadmin_email and payload.email.lower() == settings.superadmin_email.lower():
            return ROLE_SUPERADMIN
        return normalize_role(payload.role)

    async def login_user(
        self,
        payload: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate a user and return issued tokens."""
        try:
            user = await self._authenticate_user(payload, ip_address, user_agent)
            user.last_login_at = utc_now()
            user.updated_at = utc_now()
            await user.save()
            await self.audit_log_service.record(
                event_type="login_success",
                actor_id=user.id,
                actor_role=user.role,
                target_entity_type="user",
                target_entity_id=str(user.id),
                summary_message="Successful login.",
                metadata_payload={
                    "method": "password",
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            )
        except HTTPException:
            raise
        except (PyMongoError, CollectionWasNotInitialized, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is temporarily unavailable. Please try again shortly.",
            ) from exc
        return self._build_token_response(user, remember_me=payload.remember_me)

    async def refresh_token(self, payload: RefreshRequest) -> dict[str, Any]:
        """Issue a new access token from a valid refresh token."""
        try:
            token_payload = decode_token(payload.refresh_token)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            ) from exc

        if token_payload.get("token_type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        user = await User.get(token_payload.get("sub"))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        return self._build_token_response(user, refresh_token=payload.refresh_token)

    async def verify_email(self, payload: VerifyEmailRequest) -> dict[str, Any]:
        """Verify a user email with the stored code."""
        user = await User.find_one({"email": payload.email.lower()})
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        if user.email_verification_code != payload.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code.",
            )

        if self._is_code_expired(user.email_verification_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired.",
            )

        user.is_verified = True
        user.email_verification_code = None
        user.email_verification_expires_at = None
        user.updated_at = utc_now()
        await user.save()
        return {"user": self._serialize_user(user)}

    async def resend_verification_code(
        self,
        payload: ResendVerificationCodeRequest,
    ) -> dict[str, Any]:
        """Regenerate a verification code if the account exists and is unverified."""
        user = await User.find_one({"email": payload.email.lower()})
        if user is None or not user.is_active or user.is_verified:
            return {}

        verification_code = self._generate_code()
        user.email_verification_code = verification_code
        user.email_verification_expires_at = utc_now() + timedelta(
            minutes=CODE_EXPIRY_MINUTES
        )
        user.updated_at = utc_now()
        await user.save()
        self._log_delivery_code("verification-resend", user.email, verification_code)
        await self.email_service.send(
            to=user.email,
            subject="Ascend – New Verification Code",
            html_body=(
                f"<p>Hello {user.full_name},</p>"
                f"<p>Your new Ascend email verification code is: <strong>{verification_code}</strong></p>"
                f"<p>This code expires in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"<p>If you did not request this, you can ignore this email.</p>"
            ),
        )
        return {}

    async def forgot_password(self, payload: ForgotPasswordRequest) -> dict[str, Any]:
        """Create and log a reset code without leaking account existence."""
        user = await User.find_one({"email": payload.email.lower()})
        if user is None or not user.is_active:
            return {}

        reset_code = self._generate_code()
        user.password_reset_code = reset_code
        user.password_reset_expires_at = utc_now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        user.updated_at = utc_now()
        await user.save()
        self._log_delivery_code("password-reset", user.email, reset_code)
        await self.email_service.send(
            to=user.email,
            subject="Ascend – Password Reset Code",
            html_body=(
                f"<p>Hello {user.full_name},</p>"
                f"<p>Your Ascend password reset code is: <strong>{reset_code}</strong></p>"
                f"<p>This code expires in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"<p>If you did not request a password reset, you can ignore this email.</p>"
            ),
        )
        return {}

    async def verify_reset_code(
        self,
        payload: VerifyResetCodeRequest,
    ) -> dict[str, Any]:
        """Verify that a password reset code is valid."""
        user = await User.find_one({"email": payload.email.lower()})
        if user is None or user.password_reset_code != payload.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset code.",
            )

        if self._is_code_expired(user.password_reset_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset code has expired.",
            )

        return {}

    async def reset_password(self, payload: ResetPasswordRequest) -> dict[str, Any]:
        """Reset a user password after code validation."""
        if payload.new_password != payload.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match.",
            )

        user = await User.find_one({"email": payload.email.lower()})
        if user is None or user.password_reset_code != payload.code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid reset code.",
            )

        if self._is_code_expired(user.password_reset_expires_at):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reset code has expired.",
            )

        user.hashed_password = get_password_hash(payload.new_password)
        user.password_reset_code = None
        user.password_reset_expires_at = None
        user.updated_at = utc_now()
        await user.save()
        return {}

    async def change_password(self, user: User, payload: ChangePasswordRequest) -> dict[str, Any]:
        """A signed-in user changes their own password. Audit logged.

        Not DOCX-sourced (the DOCX never mentions passwords at all), but a
        real functional gap rather than a Figma-only one: the admin
        password-reset email already tells the recipient to "sign in and
        change it as soon as possible", and `POST /admin/users` hands a new
        account an admin-chosen initial password - without this endpoint
        neither instruction was actually possible to follow, leaving the
        provisioning admin permanently in possession of the user's working
        password.

        Distinct from the existing `reset_password`, which proves identity
        with an emailed code because the user is locked out; here the user
        is already authenticated and proves intent with the current
        password instead. Neither the old nor the new password is ever
        written to the audit log.
        """
        if payload.new_password != payload.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match.",
            )
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        if verify_password(payload.new_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from the current password.",
            )

        user.hashed_password = get_password_hash(payload.new_password)
        user.updated_at = utc_now()
        await user.save()

        await self.audit_log_service.record(
            event_type="password_changed",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="user",
            target_entity_id=str(user.id),
            summary_message="User changed their own password.",
        )
        return {"changed": True}

    async def change_email(self, user: User, payload: ChangeEmailRequest) -> dict[str, Any]:
        """A signed-in user changes their own login email. Requires the current
        password and re-triggers email verification against the new address.

        Not DOCX-sourced (the DOCX's User Profile data dictionary lists `role`/
        `unit`/`team` as admin-provisioned but never addresses self-service email
        changes either way) - a real, genuine gap: a typo'd or outdated
        registration email had no correction path at all before this. Distinct
        from `change_password`: proving intent still requires the current
        password, but the outcome also flips `is_verified` back to False and
        sends a fresh verification code to the new address, since the old
        code/expiry were only ever valid for the old email.
        """
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )

        new_email = payload.new_email.lower()
        old_email = user.email
        if new_email == old_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New email must be different from the current email.",
            )

        existing = await User.find_one({"email": new_email})
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        verification_code = self._generate_code()
        user.email = new_email
        user.is_verified = False
        user.email_verification_code = verification_code
        user.email_verification_expires_at = utc_now() + timedelta(minutes=CODE_EXPIRY_MINUTES)
        user.updated_at = utc_now()
        await user.save()

        await self.audit_log_service.record(
            event_type="email_changed",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="user",
            target_entity_id=str(user.id),
            summary_message="User changed their own login email.",
            metadata_payload={"old_email": old_email, "new_email": new_email},
        )

        self._log_delivery_code("email-change-verification", user.email, verification_code)
        await self.email_service.send(
            to=user.email,
            subject="Ascend – Verify Your New Email",
            html_body=(
                f"<p>Hello {user.full_name},</p>"
                f"<p>Your Ascend account email was just changed to this address. "
                f"Your verification code is: <strong>{verification_code}</strong></p>"
                f"<p>This code expires in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"<p>If you did not request this change, contact your DWS Admin immediately.</p>"
            ),
        )
        return {"user": self._serialize_user(user)}

    async def get_me(self, user: User) -> dict[str, Any]:
        """Return the current authenticated user payload."""
        return self._serialize_user(user)

    async def get_auth_screen_config(self) -> dict[str, Any]:
        """Return frontend-facing config for the login and recovery screen."""
        settings = get_settings()
        payload = AuthScreenConfigResponse(
            support_email=settings.support_email or None,
            support_phone=settings.support_phone or None,
            help_center_url=settings.help_center_url or None,
            terms_of_use_url=settings.terms_of_use_url or None,
            privacy_policy_url=settings.privacy_policy_url or None,
            opsec_notice_text=settings.opsec_notice_text or None,
        )
        return payload.model_dump(mode="json")

    async def _authenticate_user(
        self,
        payload: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        """Return the authenticated active user."""
        user = await User.find_one({"email": payload.email.lower()})
        if user is None:
            # No real user to attribute a failed-login audit entry to - not logged.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )
        if not verify_password(payload.password, user.hashed_password):
            await self.audit_log_service.record(
                event_type="login_failed",
                actor_id=user.id,
                actor_role=user.role,
                target_entity_type="user",
                target_entity_id=str(user.id),
                summary_message="Failed login attempt (invalid password).",
                metadata_payload={
                    "method": "password",
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
                outcome_status="failure",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is inactive.",
            )

        return user

    def _build_token_response(
        self,
        user: User,
        refresh_token: str | None = None,
        remember_me: bool = False,
    ) -> dict[str, Any]:
        """Return auth tokens and a safe user payload."""
        settings = get_settings()
        refresh_expire_minutes = settings.refresh_token_expire_minutes
        if remember_me:
            refresh_expire_minutes *= REMEMBER_ME_REFRESH_MULTIPLIER

        return {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": refresh_token
            or create_refresh_token(
                str(user.id),
                expires_minutes=refresh_expire_minutes,
            ),
            "token_type": "bearer",
            "remember_me": remember_me,
            "user": self._serialize_user(user),
        }

    def _serialize_user(self, user: User) -> dict[str, Any]:
        """Serialize a user for API responses."""
        payload = UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            onboarding_completed=user.onboarding_completed,
            onboarding_status=user.onboarding_status,
            onboarding_step=user.onboarding_step,
            day0_daily_checkin_status=user.day0_daily_checkin_status,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )
        return payload.model_dump(mode="json")

    def _generate_code(self) -> str:
        """Generate a 4-digit verification code."""
        return f"{secrets.randbelow(10000):04d}"

    def _is_code_expired(self, expires_at) -> bool:
        """Return whether a stored code has expired."""
        return expires_at is None or expires_at <= utc_now()

    def _log_delivery_code(self, code_type: str, email: str, code: str) -> None:
        """Log auth codes for audit trail alongside email delivery."""
        logger.info(
            "Ascend %s code generated for %s. Code: %s",
            code_type,
            email,
            code,
        )
