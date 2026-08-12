"""In-app notification service.

Two trigger patterns are used, both without a background scheduler (see
"background job approach" as an open decision in TASKS.MD):

1. Pure event-driven: fired as a side effect of another action (a
   recommendation/assigned action being created, a support request being
   submitted, an OFT/assessment being scheduled).
2. Lazy/on-access: fired the next time a relevant endpoint is loaded (e.g.
   the daily check-in or weekly gate screen), guarded so at most one
   reminder per user per day/cycle is created. This is real and honestly
   timed (it fires exactly when the condition becomes true and the user's
   client next asks), just not push-delivered ahead of that.

Every notification's title/body is screened against a best-effort OPSEC
keyword list before it is stored, per the Notifications screen's own
warning ("Notification copy is scanned before deep-link handoff").
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.notification_rules import NOTIFICATION_FAMILIES
from app.core.notification_rules import get_category
from app.core.notification_rules import scan_for_opsec_terms
from app.models.notification import Notification
from app.models.user import User
from app.services.email_service import EmailService


class NotificationService:
    """Create and manage in-app notifications for a user."""

    def __init__(self) -> None:
        self.email_service = EmailService()

    async def notify(
        self,
        user_id: Any,
        *,
        family: str,
        title: str,
        body: str,
        related_entity_type: str | None = None,
        related_entity_id: str | None = None,
        send_email: bool = False,
    ) -> Notification:
        """Screen, create, and persist a notification.

        `send_email`, when True, additionally sends a real email via
        `EmailService` to the user's real address - not instead of the
        in-app notification, on top of it. Used only for the highest-stakes
        call site (Level-5 safety-boundary flags); every other call site
        keeps in-app-only behavior, unchanged.
        """
        if family not in NOTIFICATION_FAMILIES:
            raise ValueError(f"Unknown notification family: {family}")

        blocked_terms = scan_for_opsec_terms(title, body)
        if blocked_terms:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Notification content was blocked by the OPSEC content scan.",
                    "blocked_terms": blocked_terms,
                },
            )

        record = Notification(
            user_id=user_id,
            family=family,
            title=title,
            body=body,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        await record.insert()

        if send_email:
            recipient = await User.get(user_id)
            if recipient is not None and recipient.email:
                await self.email_service.send(recipient.email, title, f"<p>{body}</p>")

        return record

    async def exists_since(
        self,
        user_id: Any,
        *,
        family: str,
        related_entity_type: str,
        related_entity_id: str,
    ) -> bool:
        """Return whether a matching notification already exists (dedupe guard)."""
        existing = await Notification.find_one(
            Notification.user_id == user_id,
            Notification.family == family,
            Notification.related_entity_type == related_entity_type,
            Notification.related_entity_id == related_entity_id,
        )
        return existing is not None

    async def list_for_user(
        self,
        user: User,
        *,
        category: str | None = None,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        """Return a user's notifications, newest first, with counts for the filter tabs."""
        records = await Notification.find(Notification.user_id == user.id).to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)

        unread_count = sum(1 for item in records if not item.is_read)
        category_counts: dict[str, int] = {}
        for item in records:
            item_category = get_category(item.family)
            category_counts[item_category] = category_counts.get(item_category, 0) + 1

        filtered = records
        if unread_only:
            filtered = [item for item in filtered if not item.is_read]
        if category is not None:
            filtered = [item for item in filtered if get_category(item.family) == category]

        return {
            "total_count": len(records),
            "unread_count": unread_count,
            "category_counts": category_counts,
            "notifications": [self._serialize(item) for item in filtered],
        }

    async def mark_read(self, user: User, notification_id: str) -> dict[str, Any]:
        """Mark a single notification as read."""
        record = await Notification.get(notification_id)
        if record is None or record.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )
        record.is_read = True
        await record.save()
        return self._serialize(record)

    async def mark_all_read(self, user: User) -> dict[str, Any]:
        """Mark all of a user's notifications as read."""
        records = await Notification.find(
            Notification.user_id == user.id, Notification.is_read == False  # noqa: E712
        ).to_list()
        for record in records:
            record.is_read = True
            await record.save()
        return {"marked_read": len(records)}

    def _serialize(self, record: Notification) -> dict[str, Any]:
        """Convert a stored notification to a transport-safe dict."""
        return {
            "id": str(record.id),
            "family": record.family,
            "category": get_category(record.family),
            "title": record.title,
            "body": record.body,
            "related_entity_type": record.related_entity_type,
            "related_entity_id": record.related_entity_id,
            "is_read": record.is_read,
            "created_at": record.created_at.isoformat(),
        }
