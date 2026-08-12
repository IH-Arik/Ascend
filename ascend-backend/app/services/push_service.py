"""Push notification delivery scaffolding (Firebase Cloud Messaging, legacy
HTTP API).

Real code, honestly not live-deliverable yet: no FCM server key exists in
this project (see `docs/CREDENTIALS_NEEDED.md`). `send` checks for real
credential presence first and returns an honest `not_configured` result
rather than fabricating delivery or silently no-op'ing. Dropping in a real
`FCM_SERVER_KEY` value later makes this immediately live - no further code
changes needed. (FCM's legacy HTTP API is deprecated in favor of v1 +
service-account JSON; `docs/CREDENTIALS_NEEDED.md` documents both real
options - whichever the client provides first is the one to wire.)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

FCM_LEGACY_SEND_URL = "https://fcm.googleapis.com/fcm/send"


class PushService:
    """Send push notifications via FCM, once a real server key is configured."""

    async def send(self, device_token: str, title: str, body: str) -> dict[str, Any]:
        """Send one real push notification, or honestly report that FCM isn't configured yet."""
        settings = get_settings()
        if not settings.fcm_server_key:
            logger.info("Push not sent to device %s - FCM_SERVER_KEY is not configured.", device_token)
            return {"sent": False, "reason": "not_configured"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    FCM_LEGACY_SEND_URL,
                    headers={
                        "Authorization": f"key={settings.fcm_server_key}",
                        "Content-Type": "application/json",
                    },
                    json={"to": device_token, "notification": {"title": title, "body": body}},
                )
            if response.status_code >= 400:
                logger.warning("FCM push to %s failed: %s %s", device_token, response.status_code, response.text)
                return {"sent": False, "reason": "provider_error"}
            return {"sent": True, "reason": None}
        except httpx.HTTPError:
            logger.exception("FCM push to %s raised a network error.", device_token)
            return {"sent": False, "reason": "network_error"}
