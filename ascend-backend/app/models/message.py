"""Direct message model (DOCX section 10, Messaging).

`thread_key` is a stable, order-independent key for the pair of
participants (sorted user id strings joined by "_"), so both directions of
a conversation query the same thread without needing a separate Thread
document.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def build_thread_key(user_id_a: str, user_id_b: str) -> str:
    """Return a stable, order-independent key for a two-party thread."""
    return "_".join(sorted([user_id_a, user_id_b]))


class Message(Document):
    """A single direct message between two users."""

    thread_key: str
    sender_id: PydanticObjectId
    sender_role: str
    recipient_id: PydanticObjectId
    body: str
    is_read: bool = False
    source_type: str = "user_initiated"
    related_recommendation_id: PydanticObjectId | None = None
    attachment_file_name: str | None = None
    attachment_storage_path: str | None = None
    attachment_file_size_bytes: int | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "messages"
        indexes = [
            IndexModel([("thread_key", 1), ("created_at", 1)]),
            IndexModel([("recipient_id", 1), ("is_read", 1)]),
        ]
