"""Group message thread model (additive - DOCX section 10, Messaging, does
not describe group threads specifically; a Figma screen implied
multi-participant threads, so this is built as a genuinely new, additive
concept rather than a rewrite of the existing 2-party `Message` flow).

`Message.thread_id` (nullable) links a message to one of these when it was
sent in a group thread; existing 1:1 messages keep using `thread_key` and
leave `thread_id` unset, unaffected by this addition.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MessageThread(Document):
    """A real multi-participant message thread."""

    participant_ids: list[PydanticObjectId]
    title: str | None = None
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "message_threads"
        indexes = [
            IndexModel([("participant_ids", 1)]),
        ]
