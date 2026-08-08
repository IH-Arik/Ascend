"""Data access helpers for assistant chat messages."""

from beanie import PydanticObjectId

from app.models.chat import ChatMessage


class ChatMessageRepository:
    """Repository for persisted chat messages."""

    async def create(self, message: ChatMessage) -> ChatMessage:
        """Persist a chat message document."""
        await message.insert()
        return message

    async def list_by_user_id(
        self,
        user_id: PydanticObjectId,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """Return recent chat messages for a user in ascending order."""
        messages = (
            await ChatMessage.find(ChatMessage.user_id == user_id)
            .sort(-ChatMessage.created_at)
            .limit(limit)
            .to_list()
        )
        return list(reversed(messages))
