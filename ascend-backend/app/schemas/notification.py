"""In-app notification schemas."""

from typing import Any

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """A single in-app notification."""

    id: str
    family: str
    title: str
    body: str
    related_entity_type: str | None
    related_entity_id: str | None
    is_read: bool
    created_at: str


class NotificationListResponse(BaseModel):
    """A list of notifications plus an unread count for the bell badge."""

    unread_count: int
    notifications: list[dict[str, Any]]
