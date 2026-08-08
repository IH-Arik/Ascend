"""In-app notification routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.services.notification_service import NotificationService

router = APIRouter()
notification_service = NotificationService()


@router.get("", status_code=status.HTTP_200_OK)
async def list_notifications(
    category: str | None = Query(default=None, pattern="^(reminders|records|updates)$"),
    unread_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's notifications, with All/Unread/category filters."""
    data = await notification_service.list_for_user(
        current_user, category=category, unread_only=unread_only
    )
    return success_response("Notifications loaded successfully.", data)


@router.post("/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a single notification as read."""
    data = await notification_service.mark_read(current_user, notification_id)
    return success_response("Notification marked as read.", data)


@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark all of the user's notifications as read."""
    data = await notification_service.mark_all_read(current_user)
    return success_response("All notifications marked as read.", data)
