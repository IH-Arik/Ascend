"""Real, live email delivery via Resend (https://resend.com).

`RESEND_API_KEY` has sat in `.env` unused since early in this project - not
loaded into `Settings`, never called anywhere. This wires it for real,
live-tested delivery, not scaffolding. If the key is unset, `send` returns
`False` and logs why, the same honest-failure shape `SmsService`/
`PushService` use for credentials that don't exist yet.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class EmailService:
    """Send real email via the Resend API."""

    async def send(self, to: str, subject: str, html_body: str) -> bool:
        """Send one real email. Returns True only on a real Resend success response."""
        settings = get_settings()
        if not settings.resend_api_key:
            logger.info("Email not sent to %s ('%s') - RESEND_API_KEY is not configured.", to, subject)
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    RESEND_API_URL,
                    headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                    json={
                        "from": settings.resend_from_address,
                        "to": [to],
                        "subject": subject,
                        "html": html_body,
                    },
                )
            if response.status_code >= 400:
                logger.warning("Resend email to %s failed: %s %s", to, response.status_code, response.text)
                return False
            return True
        except httpx.HTTPError:
            logger.exception("Resend email to %s raised a network error.", to)
            return False
