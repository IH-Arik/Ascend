"""Resend email integration service."""

import logging

import resend
from resend.exceptions import ResendError

from app.core.config import settings
from app.utils.constants import CODE_EXPIRY_MINUTES

resend.api_key = settings.RESEND_API_KEY
logger = logging.getLogger(__name__)


class EmailService:
    """Service for transactional email delivery."""

    async def send_verification_email(self, to: str, name: str, code: str) -> bool:
        """Send an email verification code to a user."""
        return self._send_email(
            to=to,
            subject="Verify your Dominion Wellness Solutions account",
            html=(
                f"<div style='font-family:Arial,sans-serif;line-height:1.6;'>"
                f"<h2>Verify your email</h2>"
                f"<p>Hello {name},</p>"
                f"<p>Your 4-digit verification code is:</p>"
                f"<p style='font-size:28px;font-weight:bold;letter-spacing:8px;'>{code}</p>"
                f"<p>This code will expire in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"</div>"
            ),
        )

    async def send_password_reset_email(self, to: str, name: str, code: str) -> bool:
        """Send a password reset code to a user."""
        return self._send_email(
            to=to,
            subject="Reset your Dominion Wellness Solutions password",
            html=(
                f"<div style='font-family:Arial,sans-serif;line-height:1.6;'>"
                f"<h2>Password reset request</h2>"
                f"<p>Hello {name},</p>"
                f"<p>Your 4-digit password reset code is:</p>"
                f"<p style='font-size:28px;font-weight:bold;letter-spacing:8px;'>{code}</p>"
                f"<p>This code will expire in {CODE_EXPIRY_MINUTES} minutes.</p>"
                f"</div>"
            ),
        )

    async def send_welcome_email(self, to: str, name: str) -> bool:
        """Send a welcome email after successful verification."""
        return self._send_email(
            to=to,
            subject="Welcome to Dominion Wellness Solutions",
            html=(
                f"<div style='font-family:Arial,sans-serif;line-height:1.6;'>"
                f"<h2>Welcome to Dominion Wellness Solutions</h2>"
                f"<p>Hello {name},</p>"
                f"<p>Your account is now verified and ready to use.</p>"
                f"<p>You can continue with organization access or skip onboarding and start using the app.</p>"
                f"</div>"
            ),
        )

    def _send_email(self, to: str, subject: str, html: str) -> bool:
        """Attempt to send an email and return whether delivery was accepted."""
        try:
            resend.Emails.send(
                {
                    "from": settings.FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
            )
        except ResendError as exc:
            logger.warning("Email delivery failed: %s", exc)
            return False

        return True
