"""SMS delivery scaffolding (Twilio).

Real code, honestly not live-deliverable yet: no Twilio credentials exist
in this project (see `docs/CREDENTIALS_NEEDED.md`). `send` checks for real
credential presence first and returns an honest `not_configured` result
rather than fabricating delivery or silently no-op'ing. Dropping in real
`TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_FROM_NUMBER` values later
makes this immediately live - no further code changes needed.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class SmsService:
    """Send SMS via Twilio, once real credentials are configured."""

    async def send(self, to_phone_number: str, body: str) -> dict[str, Any]:
        """Send one real SMS, or honestly report that Twilio isn't configured yet."""
        settings = get_settings()
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            logger.info("SMS not sent to %s - Twilio credentials are not configured.", to_phone_number)
            return {"sent": False, "reason": "not_configured"}

        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                    data={"From": settings.twilio_from_number, "To": to_phone_number, "Body": body},
                )
            if response.status_code >= 400:
                logger.warning("Twilio SMS to %s failed: %s %s", to_phone_number, response.status_code, response.text)
                return {"sent": False, "reason": "provider_error"}
            return {"sent": True, "reason": None}
        except httpx.HTTPError:
            logger.exception("Twilio SMS to %s raised a network error.", to_phone_number)
            return {"sent": False, "reason": "network_error"}
